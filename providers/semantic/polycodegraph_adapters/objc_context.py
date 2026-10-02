"""Clang statement extents and canonical local declaration bindings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .mobile_common import byte_offset
from .model import Graph, Json


def objc_context(graph: Graph, cursor: Any) -> None:
    from .objc_graph import cursor_kind

    rows: list[tuple[Any, list[Any]]] = []

    def walk(c: Any, parents: list[Any]) -> None:
        rows.append((c, parents))
        for child in c.get_children():
            walk(child, [*parents, c])

    walk(cursor, [])

    def source(c: Any) -> Any:
        return graph.by_path.get(Path(c.location.file.name).resolve()) if c.location.file else None

    def scope(s: Any, offset: int) -> str:
        nodes = [
            n
            for n in graph.nodes.values()
            if n["file"] == s.file
            and n["kind"] in {"function", "method", "constructor"}
            and n["offset"] <= offset < n["offset"] + n["length"]
        ]
        return str(min(nodes, key=lambda n: n["length"])["id"]) if nodes else str(s.file_id)

    def site(c: Any, s: Any) -> Json:
        start, end = byte_offset(s, c.extent.start.offset), byte_offset(s, c.extent.end.offset)
        return {
            "line": s.text[:start].count("\n") + 1,
            "end": s.text[: max(start, end - 1)].count("\n") + 1,
            "offset": start,
            "end_offset": end,
            "scope": scope(s, start),
        }

    def identity(c: Any, s: Any) -> str:
        return f"{s.file}@{byte_offset(s, c.location.offset)}"

    bindings: dict[str, Json] = {}
    contexts: dict[str, Json] = {}
    for c, parents in rows:
        s = source(c)
        if s is None:
            continue
        contexts.setdefault(
            s.file,
            {
                "version": 1,
                "offset_unit": "unicode",
                "bindings": [],
                "uses": [],
                "statements": [],
                "controls": [],
                "limitations": [
                    "No pointer/alias, block escape, exception, ARC/lifetime or hypothetical type-check proof"
                ],
            },
        )
        if cursor_kind(c) in {"VAR_DECL", "PARM_DECL"} and any(
            cursor_kind(p)
            in {"FUNCTION_DECL", "OBJC_INSTANCE_METHOD_DECL", "OBJC_CLASS_METHOD_DECL", "CXX_METHOD", "CONSTRUCTOR"}
            for p in parents
        ):
            bindings[identity(c, s)] = {
                **site(c, s),
                "id": identity(c, s),
                "name": c.spelling,
                "kind": "parameter" if cursor_kind(c) == "PARM_DECL" else "local",
                "type": c.type.spelling,
            }
    for c, parents in rows:
        s = source(c)
        if s is None:
            continue
        ast = contexts[s.file]
        kind = cursor_kind(c)
        if parents and cursor_kind(parents[-1]) == "COMPOUND_STMT":
            ast["statements"].append({**site(c, s), "block": parents[-1].extent.start.offset})
        if kind in {"RETURN_STMT", "BREAK_STMT", "CONTINUE_STMT", "OBJC_AT_THROW_STMT", "CXX_THROW_EXPR"}:
            ast["controls"].append({**site(c, s), "kind": kind.lower()})
        if kind != "DECL_REF_EXPR":
            continue
        target = c.referenced
        target_source = source(target) if target else None
        binding = bindings.get(identity(target, target_source)) if target_source else None
        if binding:
            write, read = False, True
            if parents:
                parent = parents[-1]
                pk = cursor_kind(parent)
                children = list(parent.get_children())
                if (
                    pk in {"BINARY_OPERATOR", "COMPOUND_ASSIGNMENT_OPERATOR"}
                    and children
                    and children[0].extent.start.offset <= c.location.offset < children[0].extent.end.offset
                ):
                    operators = [
                        t.spelling
                        for t in parent.get_tokens()
                        if children[0].extent.end.offset
                        <= t.extent.start.offset
                        < (children[1].extent.start.offset if len(children) > 1 else parent.extent.end.offset)
                    ]
                    write = any(
                        o in {"=", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "<<=", ">>="} for o in operators
                    )
                    read = not write or pk == "COMPOUND_ASSIGNMENT_OPERATOR"
                if pk == "UNARY_OPERATOR" and any(t.spelling in {"++", "--"} for t in parent.get_tokens()):
                    write = True
            ast["uses"].append({**site(c, s), "binding": binding["id"], "read": read, "write": write})
    for file, ast in contexts.items():
        ast["bindings"] = [b for b in bindings.values() if b["id"].startswith(file + "@")]
        old = graph.sources[file].record.get("intent", {}).get("ast")
        if old:
            for section in ("bindings", "uses", "statements", "controls"):
                import json

                ast[section] = list({json.dumps(v, sort_keys=True): v for v in [*old[section], *ast[section]]}.values())
        graph.sources[file].record["intent"] = {"capabilities": ["region_bindings"], "ast": ast}
