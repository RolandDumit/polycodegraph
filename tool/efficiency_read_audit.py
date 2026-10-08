"""Audit existing ordinary-tool receipts without executing a solver or source code.

Equal hashes identify repeated observations. They do not establish that a read
was unnecessary, that the model retained source, or that an edit was correct.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import OrderedDict
from collections.abc import Iterable
from pathlib import Path

HASH = re.compile(r"[0-9a-f]{64}\Z")


def source_hash(result: dict, file: str) -> str | None:
    """Return only an exact file-matched SHA-256 receipt; missing identity is unknown."""
    value = result.get("source_sha256")
    if (
        result.get("file") != file
        or not isinstance(value, str)
        or not HASH.fullmatch(value)
    ):
        return None
    return value


def audit(
    records: Iterable[dict], *, max_records: int = 100000, max_files: int = 4096
) -> dict:
    """Count reads after successful same-file edits, retaining bounded hash-only state.

    A different or unknown observation invalidates a write receipt. Failed writes
    also invalidate it, because the receipt cannot establish the resulting source.
    Evicted identities become unknown, never evidence of an unchanged file.
    """
    if max_records < 1 or max_files < 1:
        raise ValueError("audit limits must be positive")
    receipts: OrderedDict[str, str | None] = OrderedDict()
    counts = dict(
        tool_calls=0,
        failed_tool_calls=0,
        successful_reads=0,
        successful_changed_writes=0,
        reads_with_unknown_identity=0,
        post_edit_same_hash_reads=0,
        post_edit_changed_hash_reads=0,
        post_edit_unknown_hash_reads=0,
        evicted_file_identities=0,
        untracked_reads_after_eviction=0,
    )
    for event in records:
        if counts["tool_calls"] >= max_records:
            raise ValueError("audit record limit exceeded; no complete report")
        if not isinstance(event, dict) or not isinstance(event.get("success"), bool):
            raise ValueError("ordinary tool receipt needs explicit success")
        tool = event.get("tool")
        args = event.get("arguments")
        result = event.get("result")
        if (
            not isinstance(tool, str)
            or not isinstance(args, dict)
            or not isinstance(result, dict)
        ):
            raise ValueError("invalid ordinary tool receipt")
        counts["tool_calls"] += 1
        file = args.get("file")
        if tool in ("source_read", "source_replace") and (
            not isinstance(file, str) or not file
        ):
            raise ValueError("source receipt needs a file")
        if not event["success"]:
            counts["failed_tool_calls"] += 1
            if tool in ("source_replace", "source_read") and file in receipts:
                receipts[file] = None
            continue
        if tool == "source_replace" and result.get("changed") is True:
            counts["successful_changed_writes"] += 1
            receipts[file] = source_hash(result, file)
            receipts.move_to_end(file)
            if len(receipts) > max_files:
                receipts.popitem(last=False)
                counts["evicted_file_identities"] += 1
        elif tool == "source_replace" and file in receipts:
            if source_hash(result, file) != receipts[file]:
                receipts[file] = None
        elif tool == "source_read":
            counts["successful_reads"] += 1
            observed = source_hash(result, file)
            if observed is None:
                counts["reads_with_unknown_identity"] += 1
            if file not in receipts:
                if counts["evicted_file_identities"]:
                    counts["untracked_reads_after_eviction"] += 1
                continue
            expected = receipts[file]
            receipts.move_to_end(file)
            if observed is None or expected is None:
                counts["post_edit_unknown_hash_reads"] += 1
                receipts[file] = None
            elif observed == expected:
                counts["post_edit_same_hash_reads"] += 1
            else:
                counts["post_edit_changed_hash_reads"] += 1
                receipts[file] = None
    return {
        "counts": counts,
        "complete": True,
        "post_edit_classification_complete": counts["evicted_file_identities"] == 0,
        "measurement": "ordinary tool call counts and exact source receipt identities; not model tokens",
        "read_necessity": "unknown",
        "model_retention": "unknown",
        "edit_correctness": "unknown; use an independent oracle/project checks",
    }


def read_records(path: Path) -> Iterable[dict]:
    """Read bounded JSONL receipts; reject oversized/truncated evidence."""
    with path.open("rb") as stream:
        while line := stream.readline(1048577):
            if len(line) > 1048576:
                raise ValueError("ordinary receipt exceeds 1 MiB")
            yield json.loads(line)


def main() -> None:
    """Print aggregate diagnostics from an existing receipt file; no source or prompts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipts", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(read_records(args.receipts)), indent=2))


if __name__ == "__main__":
    main()
