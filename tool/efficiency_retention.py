"""Explicit binding-owned source retention; no inference from logs or wire output."""

from __future__ import annotations

import copy
import hashlib
import json
from functools import wraps
from threading import RLock


def _synchronized(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return guarded


def _compact(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class RetainedContext:
    """Reference exact source only after the client confirms its continued presence.

    The binding must call committed after successful insertion, then acknowledge
    only IDs whose full text it knows remains in the model context. Compaction
    clears every acknowledgement; future responses rehydrate from native pages.
    Hashes/metadata are bounded and no source or summaries are stored here.
    """

    def __init__(self, max_windows: int = 256) -> None:
        if type(max_windows) is not int or not 1 <= max_windows <= 256:
            raise ValueError("retention window budget must be 1..256")
        self.max_windows = max_windows
        self._lock = RLock()
        self.epoch = 0
        self.identity = None
        self.offered: set[str] = set()
        self.known: set[str] = set()

    @_synchronized
    def compaction(self) -> None:
        """New epoch requires explicit full-text rehydration and acknowledgement."""
        self.epoch += 1
        self.identity = None
        self.offered.clear()
        self.known.clear()

    @_synchronized
    def acknowledge(self, epoch: int, window_ids: list[str]) -> None:
        """Confirm retention from the binding's actual context, never a transcript."""
        if (
            type(epoch) is not int
            or epoch != self.epoch
            or not isinstance(window_ids, list)
            or len(window_ids) > self.max_windows
            or any(not isinstance(key, str) or key not in self.offered | self.known for key in window_ids)
        ):
            raise ValueError("acknowledgement outside committed context/epoch")
        # The client supplies its complete current retained set; eviction is explicit.
        self.known = set(window_ids)

    @_synchronized
    def committed(self, value: dict) -> None:
        """Record offers only after this prepared projection was actually inserted."""
        receipt = value.get("retention", {})
        if receipt.get("epoch") != self.epoch:
            raise ValueError("prepared retention epoch changed before insertion")
        self.offered = set(receipt.get("offered_windows", []))

    @_synchronized
    def valid(self, value: dict) -> bool:
        """Validate references immediately before the binding inserts them."""
        if value.get("retention", {}).get("epoch") != self.epoch:
            return False
        pages = value.get("pages", []) if value.get("format") == "pcg-lean-collection-1" else [value]
        return all(
            window.get("retained_window") in self.known
            for page in pages
            for source in page.get("sources", [])
            for window in source.get("windows", [])
            if "retained_window" in window
        )

    @_synchronized
    def prepare(self, value: dict, request: dict | None = None) -> dict:
        """Produce a smaller reference projection when explicit acknowledgements permit."""
        result = copy.deepcopy(value)
        pages = result.get("pages", []) if result.get("format") == "pcg-lean-collection-1" else [result]
        snapshots = [page.get("snapshot", {}) for page in pages]
        if not snapshots or any(snapshot != snapshots[0] for snapshot in snapshots):
            return result
        snapshot = snapshots[0]
        if any(
            not isinstance(snapshot.get(k), str) or not snapshot[k]
            for k in ("root_id", "generation", "health_fingerprint", "environment_fingerprint")
        ):
            return result
        effective_request = request if request is not None else result.get("request", {})
        baseline = effective_request.get("options", {}).get("baseline")
        if baseline is None:
            baseline = [page.get("facts", {}).get("baseline") for page in pages]
        identity = _compact([snapshot, baseline])
        if self.identity is not None and self.identity != identity:
            self.compaction()
        self.identity = identity
        offered = []
        referenced = 0
        hashes = {}
        for page in pages:
            for source in page.get("sources", []):
                file = source.get("file")
                source_hash = source.get("source_hash")
                if not file or not source_hash:
                    continue
                if file in hashes and hashes[file] != source_hash:
                    raise ValueError("retention source hashes disagree")
                hashes[file] = source_hash
                for window in source.get("windows", []):
                    text = window.get("text")
                    start, end = window.get("start_line"), window.get("end_line")
                    if (
                        not isinstance(text, str)
                        or window.get("truncated")
                        or source.get("phase", window.get("phase", "current")) != "current"
                        or type(start) is not int
                        or type(end) is not int
                        or start < 1
                        or end - start + 1 != len(text.split("\n"))
                    ):
                        continue
                    key = hashlib.sha256(_compact([identity, file, source_hash, window]).encode()).hexdigest()
                    if key in self.known:
                        reference = {k: v for k, v in window.items() if k != "text"}
                        reference.update(retained_window=key, retention_epoch=self.epoch)
                        if len(_compact(reference)) < len(_compact(window)):
                            window.clear()
                            window.update(reference)
                            referenced += 1
                    elif len(offered) < self.max_windows:
                        offered.append(key)
        result["retention"] = {
            "epoch": self.epoch,
            "offered_windows": offered,
            "referenced_windows": referenced,
            "contract": "Full source remains in binding-confirmed context; compaction/new identity requires rehydration. This is not standalone source.",
        }
        return result
