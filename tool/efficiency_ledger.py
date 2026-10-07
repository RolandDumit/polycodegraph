"""Bounded source accounting at insertion; hashes identify text, never retention promises."""

from __future__ import annotations

import hashlib
import json


def source_key(root_id: str, file_hash: str, start: int, end: int, text: str) -> str:
    """Identify one exact source window without storing its contents."""
    value = [root_id, file_hash, start, end, hashlib.sha256(text.encode()).hexdigest()]
    return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()


class ContextLedger:
    """Count exact windows and partial line overlaps with an explicit memory ceiling."""

    def __init__(self, max_entries: int = 8192) -> None:
        if not 1 <= max_entries <= 65536:
            raise ValueError("ledger entry budget out of range")
        self.max_entries = max_entries
        self.epoch = 0
        self.retained: set[str] = set()
        self.seen: set[str] = set()
        self.new_chars = self.repeated_chars = self.rehydrated_chars = 0
        self.external_reads = self.compactions = self.unidentified_chars = 0
        self.omitted_entries = 0
        self.complete = True

    def compaction(self) -> None:
        """Start a new observed context epoch without inferring what the model kept."""
        self.epoch += 1
        self.retained.clear()
        self.compactions += 1

    def _count(self, key: str, length: int) -> str:
        if key in self.retained:
            self.repeated_chars += length
            return "repeated"
        if key in self.seen:
            self.rehydrated_chars += length
            self.retained.add(key)
            return "rehydrated"
        if len(self.seen) >= self.max_entries:
            self.unidentified_chars += length
            self.omitted_entries += 1
            self.complete = False
            return "unknown"
        self.new_chars += length
        self.seen.add(key)
        self.retained.add(key)
        return "new"

    def window(self, key: str, text: str, external: bool = False) -> str:
        """Account for an opaque exact window when line identity is unavailable."""
        if external:
            self.external_reads += 1
        return self._count(key, len(text))

    def range(
        self,
        root_id: str,
        file_hash: str,
        start: int,
        end: int,
        text: str,
        external: bool = False,
        phase: str = "current",
    ) -> str:
        """Count line bodies and separators independently, preserving CRLF and Unicode."""
        if external:
            self.external_reads += 1
        lines = text.split("\n")
        if type(start) is not int or type(end) is not int or start < 1 or end - start + 1 != len(lines):
            self.unidentified_chars += len(text)
            self.complete = False
            return "unknown"
        states = set()
        for offset, line in enumerate(lines):
            identity = source_key(root_id, file_hash, start + offset, start + offset, phase + "\0" + line)
            states.add(self._count(identity, len(line)))
            if offset < len(lines) - 1:
                states.add(self._count(identity + ":newline", 1))
        return next(iter(states)) if len(states) == 1 else "mixed"

    def external(self, root_id: str, file_hash: str, start: int, end: int, text: str) -> None:
        """Account for a read only when the binding observes its insertion."""
        self.range(root_id, file_hash, start, end, text, external=True)
