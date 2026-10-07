"""0.8 provider accounting; no character-to-token, pricing or subscription inference."""

from __future__ import annotations

import json
from pathlib import Path

from token_usage import extract as extract_codex


def integer(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"invalid {name} token counter")
    return value


def normalize(provider: str, usage: dict, revision: str = "usage-v1") -> dict:
    """Retain raw provider fields; cached/reasoning are subsets, never double added."""
    if revision not in ("usage-v1", "usage-v2"):
        raise ValueError("unknown usage revision")
    output = integer(usage["output_tokens"], "output")
    if provider == "anthropic":
        ordinary = integer(usage["input_tokens"], "ordinary input")
        cached = integer(usage["cache_read_input_tokens"], "cache read")
        creation = integer(usage["cache_creation_input_tokens"], "cache creation")
        total_input = ordinary + cached + creation
        uncached = ordinary + creation
        reasoning = None  # Not inferred from visible text or output length.
    elif provider in ("openai", "codex"):
        total_input = integer(usage["input_tokens"], "input")
        details = usage.get("input_tokens_details", {})
        if "cached_input_tokens" not in usage and "cached_tokens" not in details:
            raise ValueError("missing cached-input counter; uncached primary cannot be inferred")
        cached = integer(usage.get("cached_input_tokens", details.get("cached_tokens")), "cached")
        creation = (
            None
            if revision == "usage-v2" and "cache_write_input_tokens" not in usage
            else integer(usage.get("cache_write_input_tokens", 0), "cache creation")
        )
        reasoning_value = usage.get(
            "reasoning_output_tokens", usage.get("output_tokens_details", {}).get("reasoning_tokens")
        )
        reasoning = None if reasoning_value is None else integer(reasoning_value, "reasoning")
        uncached = total_input - cached
    else:
        raise ValueError(f"unsupported usage provider: {provider}")
    if (
        cached > total_input
        or (creation is not None and creation > uncached)
        or (reasoning is not None and reasoning > output)
    ):
        raise ValueError("invalid cache/reasoning subset")
    if "total_tokens" in usage and integer(usage["total_tokens"], "total") != total_input + output:
        raise ValueError("usage total disagrees with input + output")
    return {
        "input_tokens": total_input,
        "uncached_input_tokens": uncached,
        "cached_input_tokens": cached,
        "cache_creation_input_tokens": creation,
        "output_tokens": output,
        "reasoning_output_tokens": reasoning,
        "total_tokens": total_input + output,
        "raw_usage": usage,
    }


def requests(events: list[dict], revision: str = "usage-v1") -> dict:
    """Normalize unique model responses, rejecting conflicting duplicate identities."""
    if revision not in ("usage-v1", "usage-v2"):
        raise ValueError("unknown usage revision")
    seen = {}
    settings = set()
    for event in events:
        identity = event["request_id"]
        if not isinstance(identity, str) or not identity:
            raise ValueError("missing request identity")
        if identity in seen:
            if seen[identity]["event"] != event:
                raise ValueError("conflicting duplicated request event")
            continue
        if not event.get("model") or not event.get("effort"):
            raise ValueError("missing actual model/effort")
        settings.add((event["provider"], event["model"], event["effort"]))
        seen[identity] = {"event": event, "usage": normalize(event["provider"], event["usage"], revision)}
    if not seen or len(settings) != 1:
        raise ValueError("missing usage or inconsistent provider/model/effort")
    components = (
        "input_tokens",
        "uncached_input_tokens",
        "cached_input_tokens",
        "cache_creation_input_tokens",
        "output_tokens",
        "total_tokens",
    )
    result = {
        key: sum(v["usage"][key] for v in seen.values())
        if all(v["usage"][key] is not None for v in seen.values())
        else None
        for key in components
    }
    reasoning = [v["usage"]["reasoning_output_tokens"] for v in seen.values()]
    result["reasoning_output_tokens"] = None if any(v is None for v in reasoning) else sum(reasoning)
    measured = {
        "totals": result,
        "model_settings": list(next(iter(settings))),
        "model_requests": len(seen),
        "duplicate_events": len(events) - len(seen),
        "normalized_requests": [v["usage"] for v in seen.values()],
        "request_events": [v["event"] for v in seen.values()],
        "counters_verified": True,
    }
    if revision == "usage-v2":
        measured["usage_revision"] = revision
    return measured


def codex_metadata(events: list[dict], revision: str = "usage-v1") -> dict:
    """Preserve only usage/model metadata; recheck with the frozen cumulative parser."""
    metadata = []
    for event in events:
        payload = event.get("payload", {})
        if event.get("type") == "turn_context":
            metadata.append(
                {"type": "turn_context", "payload": {k: payload[k] for k in ("model", "effort") if k in payload}}
            )
        elif event.get("type") == "event_msg" and payload.get("type") == "token_count" and payload.get("info"):
            metadata.append(
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {k: payload["info"][k] for k in ("total_token_usage", "last_token_usage")},
                    },
                }
            )
    extracted = extract_codex(metadata)
    if len(extracted["model"]) != 1 or len(extracted["reasoning_effort"]) != 1:
        raise ValueError("actual model/effort missing or mixed")
    usage = normalize("codex", extracted["total_token_usage"], revision)
    measured = {
        "totals": {k: v for k, v in usage.items() if k != "raw_usage"},
        "model_settings": ["codex", extracted["model"][0], extracted["reasoning_effort"][0]],
        "model_requests": extracted["usage_events"],
        "duplicate_events": extracted["duplicates_ignored"],
        "counter_resets": extracted["counter_resets"],
        "counters_verified": True,
        "raw_usage": extracted["total_token_usage"],
        "codex_usage_metadata": metadata,
    }
    if revision == "usage-v2":
        measured["usage_revision"] = revision
    return measured


def codex_rollout(path: Path, revision: str = "usage-v1") -> dict:
    """Read locally; never retain/export conversation messages or source text."""
    with path.open(encoding="utf-8") as stream:
        events = (json.loads(line) for line in stream)
        return codex_metadata(events, revision)


def verify(usage: dict) -> dict:
    """Recompute normalized per-response data; a caller's verified flag is insufficient."""
    cumulative = "codex_usage_metadata" in usage
    revision = usage.get("usage_revision", "usage-v1")
    rebuilt = (
        codex_metadata(usage["codex_usage_metadata"], revision)
        if cumulative
        else requests(usage["request_events"], revision)
    )
    keys = (
        ("totals", "model_settings", "model_requests", "raw_usage", "counter_resets", "duplicate_events")
        if cumulative
        else ("totals", "model_settings", "model_requests", "normalized_requests")
    )
    for key in keys:
        if usage.get(key) != rebuilt[key]:
            raise ValueError(f"usage {key} disagrees with raw request events")
    if usage.get("counters_verified") is not True:
        raise ValueError("usage was not verified by the executor adapter")
    return rebuilt
