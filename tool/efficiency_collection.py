"""Lossless, deterministic lean collection projection. No model or filesystem reads."""

from __future__ import annotations

import copy
import json
from collections import Counter


def compact(value: object) -> str:
    """Serialize one insertion representation, preserving Unicode."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


class CollectionConflict(ValueError):
    """Pages cannot belong to one coherent source/evidence collection."""


def _lines(window: dict) -> list[str] | None:
    if window.get("truncated") or "text" not in window:
        return None
    lines = window["text"].split("\n")
    if len(lines) != window["end_line"] - window["start_line"] + 1:
        return None
    return lines


def merge_windows(windows: list[dict]) -> list[dict]:
    """Merge complete compatible ranges; retain truncated/unknown provenance verbatim."""
    result: list[dict] = []
    for window in sorted(copy.deepcopy(windows), key=lambda w: (w["start_line"], w["end_line"], canonical(w))):
        lines = _lines(window)
        attrs = {k: v for k, v in window.items() if k not in ("start_line", "end_line", "text", "requested_end_line")}
        # Differing precision or truncation cannot excuse contradictory visible bytes.
        for prior in result:
            prior_lines = _lines(prior)
            if (
                "text" not in window
                or "text" not in prior
                or any(window.get(k) != prior.get(k) for k in ("view", "phase"))
            ):
                continue
            visible = window["text"].split("\n")
            prior_visible = prior["text"].split("\n")
            start = max(window["start_line"], prior["start_line"])
            end = min(window["end_line"], prior["end_line"])
            for line in range(start, end + 1):
                a, b = visible[line - window["start_line"]], prior_visible[line - prior["start_line"]]
                partial_a = window.get("truncated") and line == window["end_line"]
                partial_b = prior.get("truncated") and line == prior["end_line"]
                compatible = (
                    (a.startswith(b) or b.startswith(a))
                    if partial_a and partial_b
                    else b.startswith(a)
                    if partial_a
                    else a.startswith(b)
                    if partial_b
                    else a == b
                )
                if not compatible:
                    raise CollectionConflict("source_overlap_conflict")
        for prior in result:
            prior_lines = _lines(prior)
            prior_attrs = {
                k: v for k, v in prior.items() if k not in ("start_line", "end_line", "text", "requested_end_line")
            }
            # Different views/phases/precision/provenance remain separate windows.
            if attrs != prior_attrs or lines is None or prior_lines is None:
                continue
            start, end = window["start_line"], window["end_line"]
            if start > prior["end_line"] + 1:
                continue
            overlap = min(prior["end_line"], end) - start + 1
            if (
                overlap > 0
                and prior_lines[start - prior["start_line"] : start - prior["start_line"] + overlap] != lines[:overlap]
            ):
                raise CollectionConflict("source_overlap_conflict")
            prior["text"] = "\n".join(prior_lines + lines[max(0, overlap) :])
            prior["end_line"] = max(prior["end_line"], end)
            if "requested_end_line" in window:
                prior["requested_end_line"] = max(
                    prior.get("requested_end_line", prior["end_line"]), window["requested_end_line"]
                )
            break
        else:
            result.append(window)
    return result


def fuse_pages(pages: list[dict]) -> dict:
    """Fuse semantic records without changing sites, multiplicity, handles or limits.

    Equal metadata is emitted once. Any varying field (including freshness, limits,
    coverage and optional completion) remains in page_states. Only intermediate
    cursors are dropped; next_cursor always belongs to the last collected page.
    """
    if not pages:
        return {"format": "pcg-lean-collection-2", "records": [], "sources": [], "page_states": [], "next_cursor": None}
    identity = pages[0]["snapshot"]
    invariants = ("intent", "target", "snapshot", "source_role", "view")
    offset = 0
    required_seen = 0
    for page in pages:
        if page.get("format") != "pcg-lean-1" or page.get("restart_required"):
            raise CollectionConflict("invalid_lean_page")
        if any(page.get(k) != pages[0].get(k) for k in invariants):
            raise CollectionConflict("snapshot_changed")
        count = sum(len(record["sites"]) for record in page.get("records", []))
        if page.get("page", {}).get("offset") != offset or page["page"].get("records") != count:
            raise CollectionConflict("page_inventory_discontinuity")
        offset += count
        required_seen += sum(len(record["sites"]) for record in page.get("records", []) if record.get("required"))
        inventory = page["completion"]["required_inventory"]
        if (
            inventory.get("known_count") is not None
            and inventory["remaining_known"] != inventory["known_count"] - required_seen
        ):
            raise CollectionConflict("required_inventory_discontinuity")
        if page["completion"]["required_inventory"].get("known_count") != pages[0]["completion"][
            "required_inventory"
        ].get("known_count"):
            raise CollectionConflict("required_inventory_changed")
    skip = {"format", "records", "sources", "details", "next_cursor"}
    keys = sorted(set().union(*(p.keys() for p in pages)) - skip)
    common = {
        k: copy.deepcopy(pages[0][k])
        for k in keys
        if k in pages[0] and all(k in p and p[k] == pages[0][k] for p in pages)
    }
    states = [{k: copy.deepcopy(p[k]) for k in keys if k not in common and k in p} for p in pages]
    records: dict[str, dict] = {}
    sources: dict[str, dict] = {}
    details: dict = {}
    hashes: dict[str, str] = {}
    for page in pages:
        for record in page.get("records", []):
            attrs = {k: v for k, v in record.items() if k != "sites"}
            key = canonical(attrs)
            records.setdefault(key, dict(copy.deepcopy(attrs), sites=[]))["sites"].extend(
                copy.deepcopy(record["sites"])
            )
        for handle, detail in page.get("details", {}).items():
            if handle in details and details[handle] != detail:
                raise CollectionConflict("detail_handle_conflict")
            details[handle] = copy.deepcopy(detail)
        for source in page.get("sources", []):
            attrs = {k: v for k, v in source.items() if k != "windows"}
            # A phase is never inferred from record groups: source provenance owns it.
            phase_key = canonical([source["file"], source.get("phase", "current"), source.get("view")])
            file_hash = source.get("source_hash")
            if phase_key in hashes and hashes[phase_key] != file_hash:
                raise CollectionConflict("source_hash_changed")
            hashes[phase_key] = file_hash
            key = canonical(attrs)
            sources.setdefault(key, dict(copy.deepcopy(attrs), windows=[]))["windows"].extend(
                copy.deepcopy(source["windows"])
            )
    # Unknown hashes cannot justify merging even if file names/ranges happen to agree.
    for source in sources.values():
        if identity.get("root_id") and source.get("source_hash"):
            source["windows"] = merge_windows(source["windows"])
    result = dict(
        format="pcg-lean-collection-2",
        **common,
        records=list(records.values()),
        sources=list(sources.values()),
        page_states=states,
        next_cursor=pages[-1].get("next_cursor"),
    )
    if details:
        result["details"] = details
    # The last completion is visible at the top; historical page states still retain
    # every varying limit, source truncation and optional/verification state.
    if "completion" in pages[-1]:
        result["completion"] = copy.deepcopy(pages[-1]["completion"])
    result["source_windows_incomplete"] = any(p.get("source_windows_incomplete", False) for p in pages) or any(
        _lines(window) is None for source in sources.values() for window in source["windows"]
    )
    result["limit_causes"] = list(dict.fromkeys(cause for p in pages for cause in p.get("limit_causes", [])))
    return result


def intern_records(value: dict) -> dict:
    """Use collection-local integer references, with full IDs in typed dictionaries."""
    result = copy.deepcopy(value)
    dictionaries: dict[str, list] = {"symbols": [], "files": [], "reasons": []}
    indexes: dict[str, dict] = {name: {} for name in dictionaries}
    fields = {"source": "symbols", "target": "symbols", "file": "files", "reason": "reasons"}
    for record in result["records"]:
        for field, name in fields.items():
            if field not in record:
                continue
            item = record[field]
            key = canonical(item)
            if key not in indexes[name]:
                indexes[name][key] = len(dictionaries[name])
                dictionaries[name].append(item)
            record[field] = indexes[name][key]
    result["dictionaries"] = dictionaries
    return result


def expand_records(value: dict) -> list[dict]:
    """Resolve local aliases for checking/consumption; never send them to the server."""
    records = copy.deepcopy(value.get("records", []))
    if "dictionaries" in value:
        fields = {"source": "symbols", "target": "symbols", "file": "files", "reason": "reasons"}
        for record in records:
            for field, name in fields.items():
                if field in record:
                    record[field] = value["dictionaries"][name][record[field]]
    return records


def select_collection(pages: list[dict], collection: dict, request: dict) -> dict:
    """Choose the shortest valid representation; legacy wins ties and small responses."""
    legacy = {"format": "pcg-lean-collection-1", "pages": pages, "collection": collection}
    fused = fuse_pages(pages)
    fused.update(collection=collection, request=request)
    choices = [legacy, fused, intern_records(fused)]
    return min(choices, key=lambda value: len(compact(value)))


def normalized_inventory(value: dict | list[dict]) -> Counter:
    """Count full semantic identities/sites including provenance, phase and handles."""
    if isinstance(value, list):
        records = [record for page in value for record in page.get("records", [])]
    elif value.get("format") == "pcg-lean-collection-1":
        return normalized_inventory(value["pages"])
    else:
        records = expand_records(value)
    return Counter(
        canonical([{k: v for k, v in record.items() if k != "sites"}, site])
        for record in records
        for site in record["sites"]
    )


def source_windows(value: dict) -> list[dict]:
    """Recover exactly the source windows present in the selected insertion text."""
    pages = value["pages"] if value.get("format") == "pcg-lean-collection-1" else [value]
    return [
        dict(
            window,
            file=source["file"],
            root_id=page.get("snapshot", {}).get("root_id"),
            source_hash=source.get("source_hash"),
            phase=source.get("phase", window.get("phase", "current")),
        )
        for page in pages
        for source in page.get("sources", [])
        for window in source["windows"]
    ]
