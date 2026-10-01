"""Shared graph records, source coordinates and repository-local identities."""

from __future__ import annotations

import hashlib
from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import url2pathname

Json = dict[str, Any]


@dataclass
class Source:
    """Preserve original line endings and convert parser/LSP source coordinates."""

    file: str
    path: Path
    text: str
    record: Json
    lines: list[str] = field(init=False)
    starts: list[int] = field(init=False)
    byte_starts: list[int] = field(init=False)
    encoded_lines: list[bytes] = field(init=False)

    def __post_init__(self) -> None:
        parts = self.text.split("\n")
        self.lines = [part + "\n" for part in parts[:-1]]
        if parts[-1] or not self.lines:
            self.lines.append(parts[-1])
        self.starts = []
        self.byte_starts = []
        self.encoded_lines = []
        offset = 0
        byte_offset = 0
        for line in self.lines:
            self.starts.append(offset)
            self.byte_starts.append(byte_offset)
            encoded = line.replace("\r\n", "\n").encode("utf-8")
            self.encoded_lines.append(encoded)
            offset += len(line)
            byte_offset += len(encoded)
        self.lines.append("")
        self.starts.append(len(self.text))
        self.byte_starts.append(byte_offset)
        self.encoded_lines.append(b"")
        self.record["nodes"].append(
            {
                "id": self.file_id,
                "name": self.file,
                "kind": "file",
                "file": self.file,
                "q": self.file,
                "line": 1,
                "end": self.text.count("\n") + 1,
                "offset": 0,
                "length": len(self.text),
            }
        )

    @property
    def file_id(self) -> str:
        """The shared file identity never depends on a native path separator."""
        return f"{self.file}::file"

    def char_offset(self, line: int, column: int) -> int:
        """Convert zero-based code-point coordinates to a source offset."""
        return self.starts[line] + column

    def byte_column(self, line: int, column: int) -> int:
        """Convert Python AST UTF-8 columns to code-point offsets."""
        prefix = self.encoded_lines[line][:column].decode("utf-8")
        return self.char_offset(line, len(prefix))

    def byte_offset(self, offset: int) -> int:
        """Convert rust-analyzer's newline-normalized UTF-8 offsets."""
        line = min(bisect_right(self.byte_starts, offset) - 1, len(self.lines) - 2)
        prefix = self.encoded_lines[line][: offset - self.byte_starts[line]].decode("utf-8")
        return self.starts[line] + len(prefix)

    def lsp_offset(self, position: Json) -> int:
        """Convert negotiated UTF-16 LSP columns to code-point offsets."""
        line, column = position["line"], position["character"]
        prefix = self.lines[line].encode("utf-16-le")[: column * 2].decode("utf-16-le")
        return self.char_offset(line, len(prefix))

    def lsp_position(self, offset: int) -> Json:
        """Convert an offset to UTF-16 for a semantic LSP query."""
        line = min(bisect_right(self.starts, offset) - 1, len(self.lines) - 2)
        prefix = self.text[self.starts[line] : offset]
        return {"line": line, "character": len(prefix.encode("utf-16-le")) // 2}

    def location(self, start: int, end: int) -> Json:
        """Store code-point offsets while snippets use one-based line windows."""
        line = self.text[:start].count("\n") + 1
        end_line = self.text[: max(start, end - 1)].count("\n") + 1
        return {"line": line, "end": end_line, "offset": start, "length": end - start}

    def diagnostic(self, code: str, message: str, line: int = 1, severity: str = "warning") -> None:
        """Record explicit precision/coverage limits without poisoning other files."""
        self.record["diagnostics"].append({"code": code, "message": message[:2000], "line": line, "severity": severity})


class Graph:
    """Collect records and attach only resolved targets in indexed source files."""

    def __init__(self, request: Json) -> None:
        self.root = Path(request["root"]).resolve()
        self.sources: dict[str, Source] = {}
        self.by_path: dict[Path, Source] = {}
        self.nodes: dict[str, Json] = {}
        for item in request["files"]:
            path = self.root / item["file"]
            if not path.resolve().is_relative_to(self.root) or path.is_symlink():
                raise ValueError("Source escapes repository")
            limit = int(request.get("options", {}).get("max_file_bytes", 2 * 1024 * 1024))
            with path.open("rb") as stream:
                content = stream.read(limit + 1)
            if len(content) > limit:
                raise ValueError("Source exceeds file budget")
            if hashlib.sha256(content).hexdigest() != item["hash"]:
                raise ValueError("Source changed after discovery")
            text = content.decode("utf-8")
            record: Json = {
                "file": item["file"],
                "hash": item["hash"],
                "nodes": [],
                "edges": [],
                "dependencies": [],
                "diagnostics": [],
                "unresolvedCalls": 0,
            }
            source = Source(item["file"], path, text, record)
            self.sources[source.file] = source
            self.by_path[path.resolve()] = source
            self.nodes[source.file_id] = record["nodes"][0]

    def uri_source(self, uri: str) -> Source | None:
        """Accept file URIs on all platforms; never guess a symbol's file."""
        parsed = urlparse(uri)
        if parsed.scheme != "file":
            return None
        native = url2pathname(parsed.path)
        if parsed.netloc and parsed.netloc != "localhost":
            native = "//" + parsed.netloc + native
        return self.by_path.get(Path(native).resolve())

    def declare(
        self,
        source: Source,
        name: str,
        qualified: str,
        kind: str,
        start: int,
        end: int,
        parent: str | None = None,
        tags: list[str] | None = None,
    ) -> Json:
        """Create a stable declaration identity; duplicate scopes get an ordinal."""
        base = qualified
        ordinal = 1
        identifier = f"{source.file}::{qualified}#{kind}"
        while identifier in self.nodes:
            ordinal += 1
            qualified = f"{base}[{ordinal}]"
            identifier = f"{source.file}::{qualified}#{kind}"
        node = {
            "id": identifier,
            "name": name,
            "kind": kind,
            "file": source.file,
            "q": qualified,
            **source.location(start, end),
        }
        if parent:
            node["parent"] = parent
        if tags:
            node["tags"] = tags
        self.nodes[identifier] = node
        source.record["nodes"].append(node)
        self.edge(source, parent or source.file_id, identifier, "contains", start)
        return node

    def owner(self, source: Source, offset: int) -> str:
        """Choose the innermost declaration containing a reference/call site."""
        candidates = [
            node
            for node in source.record["nodes"]
            if node["kind"] != "file" and node["offset"] <= offset < node["offset"] + node["length"]
        ]
        return min(candidates, key=lambda node: node["length"])["id"] if candidates else source.file_id

    def edge(self, source: Source, origin: str, target: str, kind: str, offset: int) -> None:
        """Never emit cross-repository or guessed same-name targets."""
        if target not in self.nodes or origin not in self.nodes:
            return
        source.record["edges"].append(
            {
                "source": origin,
                "target": target,
                "kind": kind,
                "file": source.file,
                "line": source.text[:offset].count("\n") + 1,
                "offset": offset,
                "confidence": "resolved",
            }
        )
        target_file = self.nodes[target]["file"]
        if target_file != source.file:
            source.record["dependencies"].append(target_file)

    def results(self) -> list[Json]:
        """Serialize stable records with deduplicated file dependencies."""
        for source in self.sources.values():
            source.record["dependencies"] = sorted(set(source.record["dependencies"]))
        return [self.sources[file].record for file in sorted(self.sources)]
