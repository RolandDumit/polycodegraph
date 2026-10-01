"""Regression contracts for compiler JSON references."""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from polycodegraph_adapters.model import Graph  # noqa: E402
from polycodegraph_adapters.swift_graph import SwiftGraph  # noqa: E402


class SwiftReferencesTest(unittest.TestCase):
    def test_textual_unresolved_decl_does_not_poison_resolved_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            content = "func load() { fetch() }\nfunc fetch() {}\n"
            (root / "Use.swift").write_text(content, encoding="utf-8")
            graph = Graph(
                {
                    "root": temporary,
                    "files": [{"file": "Use.swift", "hash": hashlib.sha256(content.encode()).hexdigest()}],
                }
            )
            source = graph.sources["Use.swift"]
            target = graph.declare(source, "fetch", "fetch()", "function", 23, 38, None, [])
            provider = SwiftGraph(graph, {})
            provider.symbols["s:resolved"] = target
            provider.relations(
                source,
                {
                    "_kind": "source_file",
                    "items": [
                        {"_kind": "declref_expr", "range": {"start": 0}, "decl": "unresolved"},
                        {"_kind": "call_expr", "range": {"start": 14}, "fn": {"decl": {"decl_usr": "s:resolved"}}},
                        {"_kind": "call_expr", "range": {"start": 5}, "fn": {"decl": "textual target is not a USR"}},
                    ],
                },
            )
            calls = [edge for edge in source.record["edges"] if edge["kind"] == "calls"]
            self.assertEqual([edge["target"] for edge in calls], [target["id"]])
            self.assertEqual(source.record["unresolvedCalls"], 1)


if __name__ == "__main__":
    unittest.main()
