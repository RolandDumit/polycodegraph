"""Parametric 0.8 pilot runner/evaluator. External executors and oracles are explicit.

Raw requests/results/usage stay in --work. Published reports contain identities and
aggregates. No model/API is simulated; missing telemetry remains not_measured.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
import signal
import shutil
import subprocess
import time
from pathlib import Path
from efficiency_usage import requests, verify, codex_metadata

ORDERS = ('ABC', 'ACB', 'BAC', 'BCA', 'CAB', 'CBA')
COMPONENTS = ('input_tokens', 'uncached_input_tokens', 'cached_input_tokens',
              'cache_creation_input_tokens', 'output_tokens', 'reasoning_output_tokens', 'total_tokens')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def validate_manifest(manifest: dict, repository: Path, launch: bool = False) -> list[str]:
    missing = []
    if manifest['primary_metric'] not in ('uncached_input_per_accepted_task', 'money_per_accepted_task'):
        raise ValueError('unregistered primary metric')
    if len(manifest['tasks']) != 6 or tuple(t['order'] for t in manifest['tasks']) != ORDERS:
        raise ValueError('six counterbalanced tasks required')
    if len({t['id'] for t in manifest['tasks']}) != 6:
        raise ValueError('duplicate task identity')
    for task in manifest['tasks']:
        base = repository / task['snapshot']
        check_snapshot(base, task['source_hashes'], repository)
        if not task.get('prompt') or not task.get('correctness_criteria'):
            raise ValueError('missing task prompt/criteria')
        if not task.get('oracle_digest'):
            missing.append(f'{task["id"]}: independent oracle identity')
    for name in 'BC':
        condition = manifest['conditions'][name]
        for key in ('binary_sha256', 'source_identity', 'config_sha256', 'harness_sha256', 'schema_sha256', 'model_schema_sha256', 'loaded_graph_instructions_sha256'):
            if not condition.get(key):
                missing.append(f'{name}: {key}')
    if manifest['conditions']['A'].get('graph_enabled') is not False:
        raise ValueError('A must exclude graph schemas/instructions/artifacts')
    for key in ('model', 'effort', 'version', 'isolation_verifier_sha256', 'command_sha256'):
        if not manifest['executor'].get(key):
            missing.append(f'executor: {key}')
    if launch:
        for name in 'BC':
            if not manifest['conditions'][name].get('artifact_paths'):
                missing.append(f'{name}: local artifact paths for digest verification')
            if not manifest['conditions'][name].get('provider_artifacts'):
                missing.append(f'{name}: prepared provider artifact identities')
    if launch and missing:
        raise ValueError('launch blocked by missing preregistered identities: ' + ', '.join(missing))
    return missing


def check_snapshot(base: Path, expected: dict, confinement: Path) -> None:
    if not base.absolute().is_relative_to(confinement.absolute()) or '..' in base.parts:
        raise ValueError('snapshot outside declared repository')
    for path in (base, *base.parents):
        if path.is_symlink():
            raise ValueError('symlink snapshot ancestor')
        if path == confinement:
            break
    inventory = {}
    for path in base.rglob('*'):
        if path.is_symlink():
            raise ValueError('symlink snapshot entry')
        if path.is_file():
            inventory[path.relative_to(base).as_posix()] = digest(path)
    if inventory != expected:
        raise ValueError('snapshot file inventory/hashes differ from registration')


def bounded_process(command: Path, payload: dict, local: Path, label: str, timeout: int) -> dict:
    """Spool trusted executor output locally; limit reading, timeout descendants too."""
    def output_limit():
        import resource
        resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024 * 1024, 8 * 1024 * 1024))
    with (local / (label + '.stdout')).open('wb') as out, (local / (label + '.stderr')).open('wb') as err:
        process = subprocess.Popen([str(command.resolve())], stdin=subprocess.PIPE,
                                   stdout=out, stderr=err, start_new_session=os.name != 'nt',
                                   preexec_fn=output_limit if os.name != 'nt' else None)
        try:
            process.communicate(json.dumps(payload).encode(), timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == 'nt':
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise
    if process.returncode != 0:
        raise ValueError(f'{label} exit {process.returncode}; recover partial usage from local journal')
    path = local / (label + '.stdout')
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('executor/oracle JSON exceeds 8 MiB response bound')
    return read(path)


def prepare(manifest: dict, repository: Path, work: Path) -> dict:
    jobs = []
    for task in manifest['tasks']:
        for condition in task['order']:
            identity = f'{task["id"]}-{condition}-1'
            destination = work / identity
            if destination.exists():
                raise ValueError(f'refusing to overwrite an existing execution: {identity}')
            shutil.copytree(repository / task['snapshot'], destination / 'workspace')
            request = dict(run_id=identity, task_id=task['id'], condition=condition,
                           prompt=task['prompt'], workspace=str((destination / 'workspace').resolve()),
                           model=manifest['executor']['model'], effort=manifest['executor']['effort'],
                           graph=manifest['conditions'][condition],
                           limits=manifest['limits'], client_measurement=manifest['client_measurement'])
            # The oracle criteria and other cells never enter executor input.
            write(destination / 'request.json', request)
            jobs.append(dict(id=identity, task_id=task['id'], condition=condition,
                             request=str((destination / 'request.json').resolve())))
    result = dict(manifest_sha256=hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(), jobs=jobs)
    write(work / 'jobs.json', result)
    return result


def run(manifest: dict, jobs: dict, command: Path, oracle: Path, work: Path) -> list[dict]:
    if jobs['manifest_sha256'] != hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest():
        raise ValueError('jobs prepared from a different manifest')
    expected_jobs = [(t['id'], c) for t in manifest['tasks'] for c in t['order']]
    if [(j['task_id'], j['condition']) for j in jobs['jobs']] != expected_jobs:
        raise ValueError('jobs differ from frozen counterbalanced order')
    if digest(command) != manifest['executor']['command_sha256']:
        raise ValueError('executor binary differs from registered identity')
    for name in 'BC':
        condition = manifest['conditions'][name]
        for key, path in condition.get('artifact_paths', {}).items():
            if digest(Path(path)) != condition[key]:
                raise ValueError(f'{name}: artifact {key} changed after freeze')
        for path, expected in condition['provider_artifacts'].items():
            if digest(Path(path)) != expected:
                raise ValueError(f'{name}: prepared provider artifact changed after freeze: {path}')
    if command.resolve().is_relative_to(work.resolve()) or oracle.resolve().is_relative_to(work.resolve()):
        raise ValueError('trusted executor/oracle must be outside task copies')
    runs = []
    for job in jobs['jobs']:
        task = next(t for t in manifest['tasks'] if t['id'] == job['task_id'])
        if digest(oracle) != task['oracle_digest']:
            raise ValueError('independent oracle differs from registered identity')
        request = Path(job['request']); local = request.parent
        if not request.resolve().is_relative_to(work.resolve()):
            raise ValueError('prepared request outside local work directory')
        prepared = read(request)
        workspace = Path(prepared['workspace'])
        check_snapshot(workspace, task['source_hashes'], work)
        if prepared['graph'] != manifest['conditions'][job['condition']] or prepared['prompt'] != task['prompt']:
            raise ValueError('prepared condition/prompt changed')
        for attempt in range(1, manifest['limits']['attempts_per_cell'] + 1):
            usage = None
            observed = {}
            started = time.monotonic()
            try:
                # Each retry receives a fresh source copy and explicit fresh-context identity.
                if attempt > 1:
                    workspace = local / f'workspace-retry-{attempt}'
                    shutil.copytree(Path(__file__).resolve().parent.parent / task['snapshot'], workspace)
                    check_snapshot(workspace, task['source_hashes'], work)
                payload = dict(prepared, attempt=attempt, context_id=f"{job['id']}-{attempt}", workspace=str(workspace.resolve()))
                observed = bounded_process(command, payload, local, f'executor-{attempt}', manifest['limits']['timeout_seconds'])
                if observed.get('run_id') != job['id'] or observed.get('attempt', attempt) != attempt:
                    raise ValueError('executor run/attempt identity mismatch')
                if 'usage_events' in observed and 'codex_usage_metadata' in observed:
                    raise ValueError('choose per-request events or verified cumulative metadata, not both')
                usage = codex_metadata(observed['codex_usage_metadata']) if 'codex_usage_metadata' in observed else requests(observed['usage_events'])
                expected = manifest['executor']
                if usage['model_settings'][1:] != [expected['model'], expected['effort']]:
                    raise ValueError('observed model/effort differ from preregistration')
                validation = bounded_process(oracle, dict(
                    task_id=task['id'], workspace=str(workspace.resolve()),
                    answer=observed.get('answer'), criteria=task['correctness_criteria']),
                    local, f'oracle-{attempt}', 60)
                if type(validation.get('accepted')) is not bool:
                    raise ValueError('oracle did not provide independent acceptance')
                record = dict(task_id=task['id'], condition=job['condition'], attempt=attempt,
                              success=validation['accepted'], reason_code=validation.get('reason_code'),
                              usage=usage, client=observed['client_measurement'],
                              isolation=observed['isolation'], monetary_cost=observed.get('monetary_cost'),
                              server=observed.get('server'), oracle_sha256=digest(oracle))
                # Raw usage fields stay in local results; reports below export totals only.
            except (ValueError, KeyError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as error:
                record = dict(task_id=task['id'], condition=job['condition'], attempt=attempt,
                              success=False, reason_code=type(error).__name__, measurement_error=True,
                              usage=usage or {}, client=observed.get('client_measurement', {}),
                              isolation=observed.get('isolation', {}), monetary_cost=observed.get('monetary_cost'))
                (local / f'measurement-error-{attempt}.txt').write_text(str(error))
            record['duration_ms'] = (time.monotonic() - started) * 1000
            runs.append(record); write(local / f'result-{attempt}.json', record)
            if record['success']:
                break
    return runs


def valid_money(value: object) -> bool:
    return (isinstance(value, dict) and value.get('verified') is True
            and value.get('scope') == 'entire_attempt'
            and isinstance(value.get('currency'), str) and bool(value['currency'])
            and type(value.get('amount')) in (int, float)
            and math.isfinite(value['amount']) and value['amount'] >= 0)


def evaluate(manifest: dict, runs: list[dict]) -> dict:
    expected = {(t['id'], c) for t in manifest['tasks'] for c in 'ABC'}
    cells = {}
    failures = []
    settings = set()
    measurement_errors = []
    frozen_order = [(t['id'], c) for t in manifest['tasks'] for c in t['order']]
    encountered = []
    valid_usage = set()
    for record in runs:
        key = (record['task_id'], record['condition'])
        if key not in expected or type(record.get('success')) is not bool:
            raise ValueError('unexpected run/correctness identity')
        if key not in cells:
            encountered.append(key)
            if encountered != frozen_order[:len(encountered)]:
                raise ValueError('runs differ from frozen counterbalanced order')
        elif encountered[-1] != key:
            raise ValueError('non-contiguous retry changes counterbalanced order')
        cell = cells.setdefault(key, [])
        if record['attempt'] != len(cell) + 1 or (cell and cell[-1]['success']):
            raise ValueError('duplicate/out-of-order attempt, or retry after acceptance')
        if record['attempt'] > manifest['limits']['attempts_per_cell']:
            raise ValueError('attempt exceeds frozen retry policy')
        cell.append(record)
        if not record['success']:
            failures.append(dict(task_id=key[0], condition=key[1], attempt=record['attempt'], reason_code=record.get('reason_code')))
        usage = record.get('usage', {})
        client = record.get('client', {})
        isolation = record.get('isolation', {})
        required_client = ('actual_schema_sha256', 'loaded_graph_instructions_sha256', 'response_representation',
                           'model_requests', 'mcp_calls', 'external_reads', 'new_context_chars',
                           'repeated_context_chars', 'rehydrated_context_chars', 'pages', 'expansions', 'compactions', 'context_identity_complete')
        try:
            verify(usage)
            valid_usage.add(id(record))
            if client.get('model_requests') != usage['model_requests']:
                raise ValueError('client/model request count disagreement')
        except (KeyError, ValueError, TypeError):
            measurement_errors.append(f'{key}: raw usage accounting is inconsistent or unavailable')
        if usage.get('counters_verified') is not True or any(k not in client for k in required_client):
            measurement_errors.append(f'{key}: missing usage/client boundary')
        if isolation.get('verified') is not True or isolation.get('verifier_sha256') != manifest['executor']['isolation_verifier_sha256'] or not isolation.get('probe_artifact_sha256'):
            measurement_errors.append(f'{key}: executor access isolation not independently verified')
        if key[1] == 'A' and (client.get('mcp_calls', 0) or client.get('actual_schema_sha256') is not None or client.get('loaded_graph_instructions_sha256') is not None):
            measurement_errors.append(f'{key}: A contaminated by graph surface')
        if key[1] in 'BC' and (client.get('actual_schema_sha256') != manifest['conditions'][key[1]]['model_schema_sha256'] or client.get('loaded_graph_instructions_sha256') != manifest['conditions'][key[1]]['loaded_graph_instructions_sha256']):
            measurement_errors.append(f'{key}: actual graph schema/harness differs from manifest')
        numeric = ('model_requests','mcp_calls','external_reads','new_context_chars','repeated_context_chars','rehydrated_context_chars','pages','expansions','compactions')
        if any(type(client.get(k)) is not int or client[k] < 0 for k in numeric):
            measurement_errors.append(f'{key}: invalid client counters')
        representations = client.get('response_representation')
        if not isinstance(representations, list) or any(v not in ('text','structured','both','transformed') for v in representations):
            measurement_errors.append(f'{key}: unspecified client response transformation')
        if client.get('context_identity_complete') is not True:
            measurement_errors.append(f'{key}: retained source windows lack comparable identities')
        if usage.get('model_settings'):
            settings.add(tuple(usage['model_settings']))
    if settings and (len(settings) != 1 or next(iter(settings))[1:] != (manifest['executor']['model'], manifest['executor']['effort'])):
        measurement_errors.append('actual model/effort differ across runs or from manifest')
    currency = {r['monetary_cost']['currency'] for r in runs if valid_money(r.get('monetary_cost'))}
    if manifest['primary_metric'] == 'money_per_accepted_task' and (len(currency) != 1 or any(not valid_money(r.get('monetary_cost')) for r in runs)):
        measurement_errors.append('missing/incompatible entire-attempt monetary accounting')
    aggregates = {}
    per_task = []
    for condition in 'ABC':
        selected = [r for key, attempts in cells.items() if key[1] == condition for r in attempts]
        accepted = sum(attempts[-1]['success'] for key, attempts in cells.items() if key[1] == condition)
        all_measured = bool(selected) and all(id(r) in valid_usage for r in selected)
        totals = {k: sum(r['usage']['totals'][k] for r in selected) if all_measured and all(r['usage']['totals'].get(k) is not None for r in selected) else None for k in COMPONENTS}
        primary_sum = totals['uncached_input_tokens']
        money = [r.get('monetary_cost') for r in selected]
        monetary = None
        if money and all(valid_money(v) for v in money) and len({v['currency'] for v in money}) == 1:
            monetary = dict(amount=sum(v['amount'] for v in money), currency=money[0]['currency'])
        if manifest['primary_metric'] == 'money_per_accepted_task':
            primary_sum = None if monetary is None else monetary['amount']
        aggregates[condition] = dict(attempts=len(selected), accepted_tasks=accepted,
                                     completed_cells=sum(key[1] == condition for key in cells),
                                     components=totals, monetary_cost=monetary,
                                     primary_per_accepted_task=primary_sum / accepted if accepted and primary_sum is not None else None,
                                     duration_ms=sum(r.get('duration_ms', 0) for r in selected))
    for task in manifest['tasks']:
        values = {}
        for condition in 'ABC':
            attempts = cells.get((task['id'], condition), [])
            accepted = bool(attempts) and attempts[-1]['success']
            cost = sum(r['usage']['totals']['uncached_input_tokens'] for r in attempts) if accepted and all(id(r) in valid_usage for r in attempts) else None
            if manifest['primary_metric'] == 'money_per_accepted_task':
                cost = sum(r['monetary_cost']['amount'] for r in attempts) if accepted and all(valid_money(r.get('monetary_cost')) for r in attempts) else None
            values[condition] = dict(accepted=accepted if attempts else None, status='accepted' if accepted else 'failed' if attempts else 'not_measured', primary=cost, attempts=len(attempts))
        per_task.append(dict(task_id=task['id'], task_class=task['class'], values=values,
                             comparisons={f'C/{base}': values['C']['primary'] / values[base]['primary'] if values['C']['primary'] is not None and values[base]['primary'] else None for base in 'AB'}))
    if manifest['primary_metric'] == 'money_per_accepted_task' and len(currency) != 1:
        for item in per_task:
            item['comparisons'] = {f'C/{base}': None for base in 'AB'}
    comparisons = {f'C/{base}': aggregates['C']['primary_per_accepted_task'] / aggregates[base]['primary_per_accepted_task'] if aggregates['C']['primary_per_accepted_task'] is not None and aggregates[base]['primary_per_accepted_task'] else None for base in 'AB'}
    if manifest['primary_metric'] == 'money_per_accepted_task' and len(currency) != 1:
        comparisons = {f'C/{base}': None for base in 'AB'}
    complete = set(cells) == expected
    quality = complete and all(attempts[-1]['success'] for attempts in cells.values())
    measured = complete and not measurement_errors
    local = [t for t in per_task if t['task_class'] == 'local']
    local_no_regression = bool(local) and all(t['comparisons']['C/A'] is not None and t['comparisons']['C/A'] <= 1 for t in local)
    target = measured and quality and local_no_regression and comparisons['C/A'] is not None and comparisons['C/A'] <= .8 and comparisons['C/B'] is not None and comparisons['C/B'] < 1
    return dict(primary_metric=manifest['primary_metric'], aggregates=aggregates, per_task=per_task,
                comparisons=comparisons, all_correct=quality, local_no_regression=local_no_regression,
                target_reached=target, target_status='passed' if target else 'failed' if measured else 'not_measured', correctness_status='passed' if quality else 'failed' if complete else 'not_measured', failures=failures, measurement_errors=measurement_errors,
                gates={'G2': {'status': 'passed' if measured else 'failed' if runs and measurement_errors else 'not_measured', 'reason': 'accounting, client boundary and isolation checks'},
                       'G3': {'status': 'passed' if measured and complete else 'not_measured', 'reason': '18 cells with valid comparable measurements'},
                       'G4': {'status': 'not_measured', 'reason': 'extended corpus, replicas and holdout need separate preregistration'}},
                model_runs=sum(r.get('usage', {}).get('model_requests', 0) for r in runs),
                limits='one pilot replica per cell; no significance, robustness or subscription-quota inference')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'prepare', 'run', 'evaluate'))
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--work', type=Path)
    parser.add_argument('--executor', type=Path)
    parser.add_argument('--oracle', type=Path)
    parser.add_argument('--runs', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.work is not None:
        repository_root = Path(__file__).resolve().parent.parent
        if args.work.resolve().is_relative_to(repository_root) and not args.work.resolve().is_relative_to(repository_root / 'work'):
            parser.error('raw execution logs must be outside the repository or in ignored work/')
    manifest = read(args.manifest); repository = Path(__file__).resolve().parent.parent
    missing = validate_manifest(manifest, repository, launch=args.action == 'run')
    if args.action == 'check':
        result = dict(launch_ready=not missing, missing=missing)
    elif args.action == 'prepare':
        if args.work is None:
            parser.error('--work is required')
        result = prepare(manifest, repository, args.work)
    elif args.action == 'run':
        if args.work is None or args.executor is None or args.oracle is None:
            parser.error('--work, --executor and --oracle are required')
        result = {'runs': run(manifest, read(args.work / 'jobs.json'), args.executor, args.oracle, args.work)}
    else:
        result = evaluate(manifest, read(args.runs)['runs'] if args.runs else [])
    write(args.output, result)


if __name__ == '__main__':
    main()
