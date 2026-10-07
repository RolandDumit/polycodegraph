"""Parametric 0.8 pilot runner/evaluator. External executors and oracles are explicit.

Raw requests/results/usage stay in --work. Published reports contain identities and
aggregates. No model/API is simulated; missing telemetry remains not_measured.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
import shutil
import signal
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

from efficiency_process import DEFAULT_FILE_SIZE_BYTES, file_size_budget
from efficiency_usage import codex_metadata, requests, verify

PROCESS_CAPTURE_LIMIT = 8 * 1024 * 1024
ORDERS = ("ABC", "ACB", "BAC", "BCA", "CAB", "CBA")
COMPONENTS = (
    "input_tokens",
    "uncached_input_tokens",
    "cached_input_tokens",
    "cache_creation_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def validate_manifest(
    manifest: dict, repository: Path, launch: bool = False
) -> list[str]:
    if manifest.get("protocol_revision") in ("comparison-v1", "comparison-v2"):
        from efficiency_comparison import validate

        return validate(manifest, repository, launch)
    missing = []
    if manifest["primary_metric"] not in (
        "uncached_input_per_accepted_task",
        "money_per_accepted_task",
    ):
        raise ValueError("unregistered primary metric")
    post08 = manifest.get("protocol_revision") == "post08-v1"
    if post08:
        if manifest["primary_metric"] != "uncached_input_per_accepted_task":
            raise ValueError("post08-v1 freezes uncached input as its primary metric")
        if not 1 <= len(manifest["tasks"]) <= 32 or any(
            t["order"] not in ORDERS for t in manifest["tasks"]
        ):
            raise ValueError("bounded registered ABC schedule required")
        replicas = set()
        for task in manifest["tasks"]:
            key = (task["base_task_id"], task["replica"])
            if (
                type(task["replica"]) is not int
                or not 1 <= task["replica"] <= 3
                or key in replicas
            ):
                raise ValueError("duplicate/invalid task replica")
            replicas.add(key)
        limits = manifest["limits"]
        if (
            type(limits.get("attempts_per_cell")) is not int
            or not 1 <= limits["attempts_per_cell"] <= 3
        ):
            raise ValueError("bounded attempt count 1..3 required")
        if (
            type(limits.get("timeout_seconds")) is not int
            or not 1 <= limits["timeout_seconds"] <= 1200
        ):
            raise ValueError("bounded executor timeout 1..1200 required")
        for key in (
            "authorized_runs",
            "authorized_model_requests",
            "authorized_uncached_input_tokens",
        ):
            if type(limits.get(key)) is not int or limits[key] < 0:
                raise ValueError("explicit nonnegative campaign authorization required")
            if limits[key] == 0:
                missing.append(f"limits: {key} is zero; model execution not authorized")
        if (
            limits["authorized_runs"]
            < len(manifest["tasks"]) * 3 * limits["attempts_per_cell"]
        ):
            missing.append("limits: execution schedule exceeds authorized runs")
        if manifest["executor"].get("budget_enforcement_verified") is not True:
            missing.append(
                "executor: verified enforcement of registered model request/token budgets"
            )
    elif (
        len(manifest["tasks"]) != 6
        or tuple(t["order"] for t in manifest["tasks"]) != ORDERS
    ):
        raise ValueError("six counterbalanced tasks required")
    if len({t["id"] for t in manifest["tasks"]}) != len(manifest["tasks"]):
        raise ValueError("duplicate task identity")
    for task in manifest["tasks"]:
        base = repository / task["snapshot"]
        check_snapshot(base, task["source_hashes"], repository)
        if not task.get("prompt") or not task.get("correctness_criteria"):
            raise ValueError("missing task prompt/criteria")
        if not task.get("oracle_digest"):
            missing.append(f"{task['id']}: independent oracle identity")
    for name in "BC":
        condition = manifest["conditions"][name]
        for key in (
            "binary_sha256",
            "source_identity",
            "config_sha256",
            "harness_sha256",
            "schema_sha256",
            "model_schema_sha256",
            "loaded_graph_instructions_sha256",
        ):
            if not condition.get(key):
                missing.append(f"{name}: {key}")
    if manifest["conditions"]["A"].get("graph_enabled") is not False:
        raise ValueError("A must exclude graph schemas/instructions/artifacts")
    for key in (
        "model",
        "effort",
        "version",
        "isolation_verifier_sha256",
        "command_sha256",
    ):
        if not manifest["executor"].get(key):
            missing.append(f"executor: {key}")
    if launch:
        for name in "BC":
            if not manifest["conditions"][name].get("artifact_paths"):
                missing.append(f"{name}: local artifact paths for digest verification")
            if not manifest["conditions"][name].get("provider_artifacts"):
                missing.append(f"{name}: prepared provider artifact identities")
    if launch and missing:
        raise ValueError(
            "launch blocked by missing preregistered identities: " + ", ".join(missing)
        )
    return missing


def check_snapshot(base: Path, expected: dict, confinement: Path) -> None:
    declared_root = confinement.absolute()
    resolved_root = confinement.resolve()
    if not base.resolve().is_relative_to(resolved_root) or ".." in base.parts:
        raise ValueError("snapshot outside declared repository")
    for path in (base, *base.parents):
        if path.is_symlink():
            raise ValueError("symlink snapshot ancestor")
        # macOS temporary paths can use /var or its canonical /private/var
        # spelling. Accept that trusted-root alias, never a link inside it.
        if path.absolute() in (declared_root, resolved_root):
            break
    inventory = {}
    for path in base.rglob("*"):
        if path.is_symlink():
            raise ValueError("symlink snapshot entry")
        if path.is_file():
            inventory[path.relative_to(base).as_posix()] = digest(path)
    if inventory != expected:
        raise ValueError("snapshot file inventory/hashes differ from registration")


def bounded_process(
    command: Path,
    payload: dict,
    local: Path,
    label: str,
    timeout: int,
    *,
    file_size_limit_bytes: int = DEFAULT_FILE_SIZE_BYTES,
) -> dict:
    """Bound each captured stream independently of an owned cache's file allowance."""

    limit = file_size_budget(file_size_limit_bytes)
    encoded = json.dumps(payload).encode()
    if len(encoded) > PROCESS_CAPTURE_LIMIT:
        raise ValueError("executor request exceeds 8 MiB bound")
    argv = [str(command.resolve())]
    if os.name != "nt":
        argv = [
            sys.executable,
            "-I",
            str(Path(__file__).with_name("efficiency_process.py")),
            "--file-size-limit-bytes",
            str(limit),
            *argv,
        ]
    with (
        (local / (label + ".stdout")).open("wb") as out,
        (local / (label + ".stderr")).open("wb") as err,
    ):
        process = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=os.name != "nt",
        )
        failures = []
        capture_lock = threading.Lock()
        capture_closed = False

        def stop() -> None:
            try:
                if os.name == "nt":
                    process.kill()
                else:
                    os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

        def capture(stream, destination, stream_name) -> None:
            written = 0
            try:
                while chunk := stream.read1(65536):
                    remaining = PROCESS_CAPTURE_LIMIT - written
                    with capture_lock:
                        if capture_closed:
                            return
                        destination.write(chunk[:remaining])
                    written += min(len(chunk), remaining)
                    if len(chunk) > remaining:
                        failures.append(stream_name + " exceeds 8 MiB response bound")
                        stop()
                        return
            except OSError:
                failures.append(stream_name + " capture failed")
                stop()
            finally:
                stream.close()

        def supply() -> None:
            try:
                process.stdin.write(encoded)
            except (BrokenPipeError, OSError):
                pass  # Exit status/response determine whether the request was consumed.
            finally:
                with contextlib.suppress(BrokenPipeError, OSError):
                    process.stdin.close()

        readers = [
            threading.Thread(
                target=capture, args=(process.stdout, out, "stdout"), daemon=True
            ),
            threading.Thread(
                target=capture, args=(process.stderr, err, "stderr"), daemon=True
            ),
        ]
        writer = threading.Thread(target=supply, daemon=True)
        for worker in (*readers, writer):
            worker.start()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            stop()
            process.wait()
            raise
        finally:
            # A grandchild retaining pipes cannot extend the executor deadline indefinitely.
            drain_deadline = time.monotonic() + 2
            for worker in (*readers, writer):
                worker.join(timeout=max(0, drain_deadline - time.monotonic()))
            if any(worker.is_alive() for worker in (*readers, writer)):
                stop()
                failures.append("executor retained capture pipes after exit")
            with capture_lock:
                capture_closed = True
    if failures:
        raise ValueError("; ".join(failures))
    if process.returncode != 0:
        raise ValueError(
            f"{label} exit {process.returncode}; recover partial usage from local journal"
        )
    path = local / (label + ".stdout")
    if path.stat().st_size > PROCESS_CAPTURE_LIMIT:
        raise ValueError("executor/oracle JSON exceeds 8 MiB response bound")
    return read(path)


def prepare(manifest: dict, repository: Path, work: Path) -> dict:
    if manifest.get("protocol_revision") in ("comparison-v1", "comparison-v2"):
        from efficiency_comparison import prepare_campaign

        return prepare_campaign(manifest, repository, work)
    jobs = []
    for task in manifest["tasks"]:
        for condition in task["order"]:
            identity = f"{task['id']}-{condition}-1"
            destination = work / identity
            if destination.exists():
                raise ValueError(
                    f"refusing to overwrite an existing execution: {identity}"
                )
            shutil.copytree(repository / task["snapshot"], destination / "workspace")
            request = {
                "run_id": identity,
                "task_id": task["id"],
                "condition": condition,
                "prompt": task["prompt"],
                "workspace": str((destination / "workspace").resolve()),
                "model": manifest["executor"]["model"],
                "effort": manifest["executor"]["effort"],
                "graph": manifest["conditions"][condition],
                "limits": manifest["limits"],
                "client_measurement": manifest["client_measurement"],
            }
            if manifest.get("protocol_revision") == "post08-v1":
                request.update(
                    base_task_id=task["base_task_id"], replica=task["replica"]
                )
            # The oracle criteria and other cells never enter executor input.
            write(destination / "request.json", request)
            jobs.append(
                {
                    "id": identity,
                    "task_id": task["id"],
                    "condition": condition,
                    "request": str((destination / "request.json").resolve()),
                }
            )
    result = {
        "manifest_sha256": hashlib.sha256(
            json.dumps(manifest, sort_keys=True).encode()
        ).hexdigest(),
        "jobs": jobs,
    }
    write(work / "jobs.json", result)
    return result


def run(
    manifest: dict, jobs: dict, command: Path, oracle: Path, work: Path
) -> list[dict]:
    if manifest.get("protocol_revision") in ("comparison-v1", "comparison-v2"):
        from efficiency_comparison import run_campaign

        return run_campaign(manifest, jobs, command, oracle, work)
    if manifest.get("protocol_revision") == "post08-v1":
        validate_manifest(manifest, Path(__file__).resolve().parent.parent, launch=True)
    if (
        jobs["manifest_sha256"]
        != hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    ):
        raise ValueError("jobs prepared from a different manifest")
    expected_jobs = [(t["id"], c) for t in manifest["tasks"] for c in t["order"]]
    if [(j["task_id"], j["condition"]) for j in jobs["jobs"]] != expected_jobs:
        raise ValueError("jobs differ from frozen counterbalanced order")
    if digest(command) != manifest["executor"]["command_sha256"]:
        raise ValueError("executor binary differs from registered identity")
    for name in "BC":
        condition = manifest["conditions"][name]
        for key, path in condition.get("artifact_paths", {}).items():
            if digest(Path(path)) != condition[key]:
                raise ValueError(f"{name}: artifact {key} changed after freeze")
        for path, expected in condition["provider_artifacts"].items():
            if digest(Path(path)) != expected:
                raise ValueError(
                    f"{name}: prepared provider artifact changed after freeze: {path}"
                )
    if command.resolve().is_relative_to(
        work.resolve()
    ) or oracle.resolve().is_relative_to(work.resolve()):
        raise ValueError("trusted executor/oracle must be outside task copies")
    runs = []
    for job in jobs["jobs"]:
        task = next(t for t in manifest["tasks"] if t["id"] == job["task_id"])
        if digest(oracle) != task["oracle_digest"]:
            raise ValueError("independent oracle differs from registered identity")
        request = Path(job["request"])
        local = request.parent
        if not request.resolve().is_relative_to(work.resolve()):
            raise ValueError("prepared request outside local work directory")
        prepared = read(request)
        workspace = Path(prepared["workspace"])
        check_snapshot(workspace, task["source_hashes"], work)
        if (
            prepared["graph"] != manifest["conditions"][job["condition"]]
            or prepared["prompt"] != task["prompt"]
        ):
            raise ValueError("prepared condition/prompt changed")
        for attempt in range(1, manifest["limits"]["attempts_per_cell"] + 1):
            usage = None
            observed = {}
            started = time.monotonic()
            try:
                # Each retry receives a fresh source copy and explicit fresh-context identity.
                if attempt > 1:
                    workspace = local / f"workspace-retry-{attempt}"
                    shutil.copytree(
                        Path(__file__).resolve().parent.parent / task["snapshot"],
                        workspace,
                    )
                    check_snapshot(workspace, task["source_hashes"], work)
                payload = dict(
                    prepared,
                    attempt=attempt,
                    context_id=f"{job['id']}-{attempt}",
                    workspace=str(workspace.resolve()),
                )
                observed = bounded_process(
                    command,
                    payload,
                    local,
                    f"executor-{attempt}",
                    manifest["limits"]["timeout_seconds"],
                )
                if (
                    observed.get("run_id") != job["id"]
                    or observed.get("attempt", attempt) != attempt
                ):
                    raise ValueError("executor run/attempt identity mismatch")
                if "usage_events" in observed and "codex_usage_metadata" in observed:
                    raise ValueError(
                        "choose per-request events or verified cumulative metadata, not both"
                    )
                usage = (
                    codex_metadata(observed["codex_usage_metadata"])
                    if "codex_usage_metadata" in observed
                    else requests(observed["usage_events"])
                )
                expected = manifest["executor"]
                if usage["model_settings"][1:] != [
                    expected["model"],
                    expected["effort"],
                ]:
                    raise ValueError(
                        "observed model/effort differ from preregistration"
                    )
                validation = bounded_process(
                    oracle,
                    {
                        "task_id": task["id"],
                        "workspace": str(workspace.resolve()),
                        "answer": observed.get("answer"),
                        "criteria": task["correctness_criteria"],
                    },
                    local,
                    f"oracle-{attempt}",
                    60,
                )
                if type(validation.get("accepted")) is not bool:
                    raise ValueError("oracle did not provide independent acceptance")
                record = {
                    "task_id": task["id"],
                    "condition": job["condition"],
                    "attempt": attempt,
                    "success": validation["accepted"],
                    "reason_code": validation.get("reason_code"),
                    "usage": usage,
                    "client": observed["client_measurement"],
                    "isolation": observed["isolation"],
                    "monetary_cost": observed.get("monetary_cost"),
                    "server": observed.get("server"),
                    "oracle_sha256": digest(oracle),
                }
                # Raw usage fields stay in local results; reports below export totals only.
            except (
                ValueError,
                KeyError,
                subprocess.TimeoutExpired,
                subprocess.CalledProcessError,
            ) as error:
                record = {
                    "task_id": task["id"],
                    "condition": job["condition"],
                    "attempt": attempt,
                    "success": False,
                    "reason_code": type(error).__name__,
                    "measurement_error": True,
                    "usage": usage or {},
                    "client": observed.get("client_measurement", {}),
                    "isolation": observed.get("isolation", {}),
                    "monetary_cost": observed.get("monetary_cost"),
                }
                (local / f"measurement-error-{attempt}.txt").write_text(str(error))
            record["duration_ms"] = (time.monotonic() - started) * 1000
            runs.append(record)
            write(local / f"result-{attempt}.json", record)
            if manifest.get("protocol_revision") == "post08-v1":
                # Unknown usage aborts this campaign; it can never be a cheap retry.
                if record.get("measurement_error"):
                    return runs
                limits = manifest["limits"]
                if (
                    sum(r["usage"]["model_requests"] for r in runs)
                    >= limits["authorized_model_requests"]
                    or sum(r["usage"]["totals"]["uncached_input_tokens"] for r in runs)
                    >= limits["authorized_uncached_input_tokens"]
                ):
                    return runs
            if record["success"]:
                break
    return runs


def valid_money(value: object) -> bool:
    return (
        isinstance(value, dict)
        and value.get("verified") is True
        and value.get("scope") == "entire_attempt"
        and isinstance(value.get("currency"), str)
        and bool(value["currency"])
        and type(value.get("amount")) in (int, float)
        and math.isfinite(value["amount"])
        and value["amount"] >= 0
    )


def evaluate(manifest: dict, runs: list[dict]) -> dict:
    if manifest.get("protocol_revision") in ("comparison-v1", "comparison-v2"):
        from efficiency_comparison import evaluate_campaign

        return evaluate_campaign(manifest, runs)
    if manifest.get("protocol_revision") == "post08-v1":
        return evaluate_post08(manifest, runs)
    expected = {(t["id"], c) for t in manifest["tasks"] for c in "ABC"}
    cells = {}
    failures = []
    settings = set()
    measurement_errors = []
    frozen_order = [(t["id"], c) for t in manifest["tasks"] for c in t["order"]]
    encountered = []
    valid_usage = set()
    for record in runs:
        key = (record["task_id"], record["condition"])
        if key not in expected or type(record.get("success")) is not bool:
            raise ValueError("unexpected run/correctness identity")
        if key not in cells:
            encountered.append(key)
            if encountered != frozen_order[: len(encountered)]:
                raise ValueError("runs differ from frozen counterbalanced order")
        elif encountered[-1] != key:
            raise ValueError("non-contiguous retry changes counterbalanced order")
        cell = cells.setdefault(key, [])
        if record["attempt"] != len(cell) + 1 or (cell and cell[-1]["success"]):
            raise ValueError(
                "duplicate/out-of-order attempt, or retry after acceptance"
            )
        if record["attempt"] > manifest["limits"]["attempts_per_cell"]:
            raise ValueError("attempt exceeds frozen retry policy")
        cell.append(record)
        if not record["success"]:
            failures.append(
                {
                    "task_id": key[0],
                    "condition": key[1],
                    "attempt": record["attempt"],
                    "reason_code": record.get("reason_code"),
                }
            )
        usage = record.get("usage", {})
        client = record.get("client", {})
        isolation = record.get("isolation", {})
        required_client = (
            "actual_schema_sha256",
            "loaded_graph_instructions_sha256",
            "response_representation",
            "model_requests",
            "mcp_calls",
            "external_reads",
            "new_context_chars",
            "repeated_context_chars",
            "rehydrated_context_chars",
            "pages",
            "expansions",
            "compactions",
            "context_identity_complete",
        )
        try:
            verify(usage)
            valid_usage.add(id(record))
            if client.get("model_requests") != usage["model_requests"]:
                raise ValueError("client/model request count disagreement")
        except (KeyError, ValueError, TypeError):
            measurement_errors.append(
                f"{key}: raw usage accounting is inconsistent or unavailable"
            )
        if usage.get("counters_verified") is not True or any(
            k not in client for k in required_client
        ):
            measurement_errors.append(f"{key}: missing usage/client boundary")
        if (
            isolation.get("verified") is not True
            or isolation.get("verifier_sha256")
            != manifest["executor"]["isolation_verifier_sha256"]
            or not isolation.get("probe_artifact_sha256")
        ):
            measurement_errors.append(
                f"{key}: executor access isolation not independently verified"
            )
        if key[1] == "A" and (
            client.get("mcp_calls", 0)
            or client.get("actual_schema_sha256") is not None
            or client.get("loaded_graph_instructions_sha256") is not None
        ):
            measurement_errors.append(f"{key}: A contaminated by graph surface")
        if key[1] in "BC" and (
            client.get("actual_schema_sha256")
            != manifest["conditions"][key[1]]["model_schema_sha256"]
            or client.get("loaded_graph_instructions_sha256")
            != manifest["conditions"][key[1]]["loaded_graph_instructions_sha256"]
        ):
            measurement_errors.append(
                f"{key}: actual graph schema/harness differs from manifest"
            )
        numeric = (
            "model_requests",
            "mcp_calls",
            "external_reads",
            "new_context_chars",
            "repeated_context_chars",
            "rehydrated_context_chars",
            "pages",
            "expansions",
            "compactions",
        )
        if any(type(client.get(k)) is not int or client[k] < 0 for k in numeric):
            measurement_errors.append(f"{key}: invalid client counters")
        representations = client.get("response_representation")
        if not isinstance(representations, list) or any(
            v not in ("text", "structured", "both", "transformed")
            for v in representations
        ):
            measurement_errors.append(
                f"{key}: unspecified client response transformation"
            )
        if client.get("context_identity_complete") is not True:
            measurement_errors.append(
                f"{key}: retained source windows lack comparable identities"
            )
        if usage.get("model_settings"):
            settings.add(tuple(usage["model_settings"]))
    if settings and (
        len(settings) != 1
        or next(iter(settings))[1:]
        != (manifest["executor"]["model"], manifest["executor"]["effort"])
    ):
        measurement_errors.append(
            "actual model/effort differ across runs or from manifest"
        )
    currency = {
        r["monetary_cost"]["currency"]
        for r in runs
        if valid_money(r.get("monetary_cost"))
    }
    if manifest["primary_metric"] == "money_per_accepted_task" and (
        len(currency) != 1 or any(not valid_money(r.get("monetary_cost")) for r in runs)
    ):
        measurement_errors.append(
            "missing/incompatible entire-attempt monetary accounting"
        )
    aggregates = {}
    per_task = []
    for condition in "ABC":
        selected = [
            r
            for key, attempts in cells.items()
            if key[1] == condition
            for r in attempts
        ]
        accepted = sum(
            attempts[-1]["success"]
            for key, attempts in cells.items()
            if key[1] == condition
        )
        all_measured = bool(selected) and all(id(r) in valid_usage for r in selected)
        totals = {
            k: sum(r["usage"]["totals"][k] for r in selected)
            if all_measured
            and all(r["usage"]["totals"].get(k) is not None for r in selected)
            else None
            for k in COMPONENTS
        }
        primary_sum = totals["uncached_input_tokens"]
        money = [r.get("monetary_cost") for r in selected]
        monetary = None
        if (
            money
            and all(valid_money(v) for v in money)
            and len({v["currency"] for v in money}) == 1
        ):
            monetary = {
                "amount": sum(v["amount"] for v in money),
                "currency": money[0]["currency"],
            }
        if manifest["primary_metric"] == "money_per_accepted_task":
            primary_sum = None if monetary is None else monetary["amount"]
        aggregates[condition] = {
            "attempts": len(selected),
            "accepted_tasks": accepted,
            "completed_cells": sum(key[1] == condition for key in cells),
            "components": totals,
            "monetary_cost": monetary,
            "primary_per_accepted_task": primary_sum / accepted
            if accepted and primary_sum is not None
            else None,
            "duration_ms": sum(r.get("duration_ms", 0) for r in selected),
        }
    for task in manifest["tasks"]:
        values = {}
        for condition in "ABC":
            attempts = cells.get((task["id"], condition), [])
            accepted = bool(attempts) and attempts[-1]["success"]
            cost = (
                sum(r["usage"]["totals"]["uncached_input_tokens"] for r in attempts)
                if accepted and all(id(r) in valid_usage for r in attempts)
                else None
            )
            if manifest["primary_metric"] == "money_per_accepted_task":
                cost = (
                    sum(r["monetary_cost"]["amount"] for r in attempts)
                    if accepted
                    and all(valid_money(r.get("monetary_cost")) for r in attempts)
                    else None
                )
            values[condition] = {
                "accepted": accepted if attempts else None,
                "status": "accepted"
                if accepted
                else "failed"
                if attempts
                else "not_measured",
                "primary": cost,
                "attempts": len(attempts),
            }
        per_task.append(
            {
                "task_id": task["id"],
                "task_class": task["class"],
                "values": values,
                "comparisons": {
                    f"C/{base}": values["C"]["primary"] / values[base]["primary"]
                    if values["C"]["primary"] is not None and values[base]["primary"]
                    else None
                    for base in "AB"
                },
            }
        )
    if manifest["primary_metric"] == "money_per_accepted_task" and len(currency) != 1:
        for item in per_task:
            item["comparisons"] = {f"C/{base}": None for base in "AB"}
    comparisons = {
        f"C/{base}": aggregates["C"]["primary_per_accepted_task"]
        / aggregates[base]["primary_per_accepted_task"]
        if aggregates["C"]["primary_per_accepted_task"] is not None
        and aggregates[base]["primary_per_accepted_task"]
        else None
        for base in "AB"
    }
    if manifest["primary_metric"] == "money_per_accepted_task" and len(currency) != 1:
        comparisons = {f"C/{base}": None for base in "AB"}
    complete = set(cells) == expected
    quality = complete and all(attempts[-1]["success"] for attempts in cells.values())
    measured = complete and not measurement_errors
    local = [t for t in per_task if t["task_class"] == "local"]
    local_no_regression = bool(local) and all(
        t["comparisons"]["C/A"] is not None and t["comparisons"]["C/A"] <= 1
        for t in local
    )
    target = (
        measured
        and quality
        and local_no_regression
        and comparisons["C/A"] is not None
        and comparisons["C/A"] <= 0.8
        and comparisons["C/B"] is not None
        and comparisons["C/B"] < 1
    )
    return {
        "primary_metric": manifest["primary_metric"],
        "aggregates": aggregates,
        "per_task": per_task,
        "comparisons": comparisons,
        "all_correct": quality,
        "local_no_regression": local_no_regression,
        "target_reached": target,
        "target_status": "passed"
        if target
        else "failed"
        if measured
        else "not_measured",
        "correctness_status": "passed"
        if quality
        else "failed"
        if complete
        else "not_measured",
        "failures": failures,
        "measurement_errors": measurement_errors,
        "gates": {
            "G2": {
                "status": "passed"
                if measured
                else "failed"
                if runs and measurement_errors
                else "not_measured",
                "reason": "accounting, client boundary and isolation checks",
            },
            "G3": {
                "status": "passed" if measured and complete else "not_measured",
                "reason": "18 cells with valid comparable measurements",
            },
            "G4": {
                "status": "not_measured",
                "reason": "extended corpus, replicas and holdout need separate preregistration",
            },
        },
        "model_runs": sum(r.get("usage", {}).get("model_requests", 0) for r in runs),
        "limits": "one pilot replica per cell; no significance, robustness or subscription-quota inference",
    }


def evaluate_post08(manifest: dict, runs: list[dict]) -> dict:
    """New protocol: consumption and attribution are separate evidence levels."""
    expected = [(t["id"], c) for t in manifest["tasks"] for c in t["order"]]
    cells = {}
    encountered = []
    accounting_errors = []
    attribution_errors = []
    settings = set()
    measured = set()
    for record in runs:
        key = (record["task_id"], record["condition"])
        if key not in expected or type(record.get("success")) is not bool:
            raise ValueError("unexpected run/correctness identity")
        if key not in cells:
            encountered.append(key)
            if encountered != expected[: len(encountered)]:
                raise ValueError("runs differ from preregistered order")
        elif encountered[-1] != key:
            raise ValueError("non-contiguous retry")
        attempts = cells.setdefault(key, [])
        if (
            record["attempt"] != len(attempts) + 1
            or len(attempts) >= manifest["limits"]["attempts_per_cell"]
            or (attempts and attempts[-1]["success"])
        ):
            raise ValueError("invalid attempt sequence")
        attempts.append(record)
        try:
            usage = verify(record["usage"])
            measured.add(id(record))
            settings.add(tuple(usage["model_settings"]))
        except (KeyError, ValueError, TypeError):
            accounting_errors.append(f"{key}: usage unknown or invalid")
        isolation = record.get("isolation", {})
        if (
            isolation.get("verified") is not True
            or not isolation.get("probe_artifact_sha256")
            or isolation.get("verifier_sha256")
            != manifest["executor"]["isolation_verifier_sha256"]
        ):
            accounting_errors.append(f"{key}: isolation not independently verified")
        if record.get("oracle_sha256") != next(
            t["oracle_digest"] for t in manifest["tasks"] if t["id"] == key[0]
        ):
            accounting_errors.append(
                f"{key}: independent oracle identity missing/different"
            )
        client = record.get("client", {})
        if key[1] == "A":
            if (
                client.get("mcp_calls", 0)
                or client.get("actual_schema_sha256") is not None
                or client.get("loaded_graph_instructions_sha256") is not None
            ):
                accounting_errors.append(f"{key}: no-graph condition contaminated")
        else:
            condition = manifest["conditions"][key[1]]
            if any(
                client.get(k) is None or client.get(k) != condition[v]
                for k, v in [
                    ("actual_schema_sha256", "model_schema_sha256"),
                    (
                        "loaded_graph_instructions_sha256",
                        "loaded_graph_instructions_sha256",
                    ),
                ]
            ):
                accounting_errors.append(
                    f"{key}: actual graph surface unidentified/different"
                )
        if client.get("context_identity_complete") is not True or not client.get(
            "response_representation"
        ):
            attribution_errors.append(f"{key}: source/insertion trace incomplete")
    if settings and (
        len(settings) != 1
        or next(iter(settings))[1:]
        != (manifest["executor"]["model"], manifest["executor"]["effort"])
    ):
        accounting_errors.append("model/effort not identical to preregistration")
    aggregates = {}
    per_task = []
    for condition in "ABC":
        selected = [
            r
            for (task, c), attempts in cells.items()
            if c == condition
            for r in attempts
        ]
        valid = bool(selected) and all(id(r) in measured for r in selected)
        components = {
            k: sum(r["usage"]["totals"][k] for r in selected)
            if valid and all(r["usage"]["totals"].get(k) is not None for r in selected)
            else None
            for k in COMPONENTS
        }
        accepted = sum(
            attempts[-1]["success"]
            for (task, c), attempts in cells.items()
            if c == condition
        )
        assigned = len(manifest["tasks"])
        cost = components["uncached_input_tokens"]
        aggregates[condition] = {
            "label": manifest["conditions"][condition]["label"],
            "assigned_tasks": assigned,
            "executed_tasks": sum(c == condition for task, c in cells),
            "attempts": len(selected),
            "accepted_tasks": accepted,
            "success_rate": accepted / assigned if selected else None,
            "components": components,
            "primary_per_accepted_task": cost / accepted
            if accepted and cost is not None
            else None,
            "consumption_per_assigned_task": {
                k: v / assigned if v is not None else None
                for k, v in components.items()
            },
            "monetary_cost": None,
            "model_requests": sum(r["usage"]["model_requests"] for r in selected)
            if valid
            else None,
            "duration_ms": sum(r["duration_ms"] for r in selected)
            if selected and all(r.get("duration_ms") is not None for r in selected)
            else None,
        }
    for task in manifest["tasks"]:
        values = {}
        for condition in "ABC":
            attempts = cells.get((task["id"], condition), [])
            valid = bool(attempts) and all(id(r) in measured for r in attempts)
            components = {
                k: sum(r["usage"]["totals"][k] for r in attempts)
                if valid
                and all(r["usage"]["totals"].get(k) is not None for r in attempts)
                else None
                for k in COMPONENTS
            }
            values[condition] = {
                "accepted": attempts[-1]["success"] if attempts else None,
                "attempts": len(attempts),
                "components": components,
                "uncached_input_tokens": sum(
                    r["usage"]["totals"]["uncached_input_tokens"] for r in attempts
                )
                if valid
                else None,
                "graph_calls": sum(
                    r.get("client", {}).get("mcp_calls", 0) for r in attempts
                )
                if attempts
                else None,
                "client_counters": [
                    {
                        k: r.get("client", {}).get(k)
                        for k in (
                            "model_requests",
                            "mcp_calls",
                            "pages",
                            "errors",
                            "retries",
                            "expansions",
                            "external_reads",
                            "compactions",
                            "new_context_chars",
                            "repeated_context_chars",
                            "rehydrated_context_chars",
                        )
                    }
                    for r in attempts
                ],
            }
        per_task.append(
            {
                "task_id": task["id"],
                "base_task_id": task["base_task_id"],
                "replica": task["replica"],
                "task_class": task["class"],
                "values": values,
            }
        )
    medians = {}
    per_family = {}
    for base in sorted({t["base_task_id"] for t in manifest["tasks"]}):
        members = [t for t in per_task if t["base_task_id"] == base]
        medians[base] = {}
        per_family[base] = {}
        for condition in "ABC":
            costs = [t["values"][condition]["uncached_input_tokens"] for t in members]
            medians[base][condition] = (
                statistics.median(costs) if all(v is not None for v in costs) else None
            )
            values = [t["values"][condition] for t in members]
            components = {
                k: sum(v["components"][k] for v in values)
                if all(v["components"][k] is not None for v in values)
                else None
                for k in COMPONENTS
            }
            accepted = sum(v["accepted"] is True for v in values)
            per_family[base][condition] = {
                "assigned": len(values),
                "accepted": accepted,
                "attempts": sum(v["attempts"] for v in values),
                "components": components,
                "primary_per_accepted_task": components["uncached_input_tokens"]
                / accepted
                if accepted and components["uncached_input_tokens"] is not None
                else None,
                "consumption_per_assigned_task": {
                    k: v / len(values) if v is not None else None
                    for k, v in components.items()
                },
                "replica_range_uncached_input": [min(costs), max(costs)]
                if all(v is not None for v in costs)
                else None,
                "graph_used_tasks": sum(
                    v["graph_calls"] is not None and v["graph_calls"] > 0
                    for v in values
                ),
                "graph_avoided_tasks": sum(v["graph_calls"] == 0 for v in values),
            }
    ratios = {
        f"C/{base}": aggregates["C"]["primary_per_accepted_task"]
        / aggregates[base]["primary_per_accepted_task"]
        if aggregates["C"]["primary_per_accepted_task"] is not None
        and aggregates[base]["primary_per_accepted_task"]
        else None
        for base in "AB"
    }
    complete = set(cells) == set(expected)
    quality = complete and all(attempts[-1]["success"] for attempts in cells.values())
    comparable = complete and not accounting_errors
    non_regressing = sum(
        v["C"] is not None and v["A"] is not None and v["C"] <= v["A"]
        for v in medians.values()
    )
    decision = "inconclusive"
    if comparable and quality and ratios["C/A"] is not None:
        useful_segment = any(
            v["C"]["graph_used_tasks"] > 0
            and v["C"]["primary_per_accepted_task"] is not None
            and v["A"]["primary_per_accepted_task"] is not None
            and v["C"]["primary_per_accepted_task"]
            < v["A"]["primary_per_accepted_task"]
            for v in per_family.values()
        )
        decision = (
            "continue"
            if ratios["C/A"] <= 1 and non_regressing >= 2
            else "segment_only"
            if ratios["C/A"] > 1.10 and useful_segment
            else "stop"
            if ratios["C/A"] > 1.10
            else "inconclusive"
        )
    return {
        "protocol_revision": "post08-v1",
        "status": "not_run" if not runs else "measured",
        "primary_metric": manifest["primary_metric"],
        "consumption_evidence": {"comparable": comparable, "errors": accounting_errors},
        "attribution_evidence": {
            "complete": comparable and not attribution_errors,
            "errors": attribution_errors,
        },
        "aggregates": aggregates,
        "per_task": per_task,
        "per_family": per_family,
        "replica_medians": medians,
        "comparisons": ratios,
        "quality_equal": quality,
        "decision": decision,
        "executions": len(runs),
        "model_requests": sum(r.get("usage", {}).get("model_requests", 0) for r in runs)
        if all(id(r) in measured for r in runs)
        else None,
        "limits": "diagnostic tasks; replicas are not independent repositories; money unmeasured; no general advantage established",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "prepare", "run", "evaluate"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--executor", type=Path)
    parser.add_argument("--oracle", type=Path)
    parser.add_argument("--runs", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.work is not None:
        repository_root = Path(__file__).resolve().parent.parent
        if args.work.resolve().is_relative_to(
            repository_root
        ) and not args.work.resolve().is_relative_to(repository_root / "work"):
            parser.error(
                "raw execution logs must be outside the repository or in ignored work/"
            )
    manifest = read(args.manifest)
    repository = Path(__file__).resolve().parent.parent
    missing = validate_manifest(manifest, repository, launch=args.action == "run")
    if args.action == "check":
        result = {"launch_ready": not missing, "missing": missing}
    elif args.action == "prepare":
        if args.work is None:
            parser.error("--work is required")
        result = prepare(manifest, repository, args.work)
    elif args.action == "run":
        if args.work is None or args.executor is None or args.oracle is None:
            parser.error("--work, --executor and --oracle are required")
        result = {
            "runs": run(
                manifest,
                read(args.work / "jobs.json"),
                args.executor,
                args.oracle,
                args.work,
            )
        }
    else:
        result = evaluate(manifest, read(args.runs)["runs"] if args.runs else [])
    write(args.output, result)


if __name__ == "__main__":
    main()
