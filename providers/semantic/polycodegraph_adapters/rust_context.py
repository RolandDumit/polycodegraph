"""Local syntax regions bound by rust-analyzer definition locations."""

from __future__ import annotations

from .model import Graph, Json, Source


def rust_context(graph: Graph, source: Source, tree: Json, definitions: dict[int, list[Json]]) -> Json:
    nodes: list[tuple[Json, list[Json]]] = []

    def walk(n: Json, parents: list[Json]) -> None:
        nodes.append((n, parents))
        for child in n.get("children", []):
            walk(child, [*parents, n])

    walk(tree, [])

    def site(n: Json) -> Json:
        start, end = source.byte_offset(n["start"][0]), source.byte_offset(n["end"][0])
        return {
            "line": source.text[:start].count("\n") + 1,
            "end": source.text[: max(start, end - 1)].count("\n") + 1,
            "offset": start,
            "end_offset": end,
            "scope": graph.owner(source, start),
        }

    result: Json = {
        "version": 1,
        "offset_unit": "unicode",
        "bindings": [],
        "uses": [],
        "statements": [],
        "controls": [],
        "limitations": [
            "No borrow/lifetime, alias, macro expansion, closure escape or hypothetical extracted type-check proof"
        ],
    }
    bindings: dict[int, Json] = {}
    for n, parents in nodes:
        if n["kind"] == "NAME" and parents and parents[-1]["kind"] in {"IDENT_PAT", "SELF_PARAM"}:
            s = site(n)
            binding = {
                **s,
                "id": f"{source.file}@{s['offset']}",
                "name": source.text[s["offset"] : s["end_offset"]],
                "kind": "parameter" if any(p["kind"] in {"PARAM", "SELF_PARAM"} for p in parents[-3:]) else "local",
                "type": "unknown",
            }
            bindings[s["offset"]] = binding
            result["bindings"].append(binding)
    for n, parents in nodes:
        kind = n["kind"]
        if (
            parents
            and parents[-1]["kind"] == "STMT_LIST"
            and (kind in {"LET_STMT", "EXPR_STMT"} or kind.endswith("_EXPR"))
        ):
            result["statements"].append({**site(n), "block": parents[-1]["start"][0]})
        if kind in {"RETURN_EXPR", "BREAK_EXPR", "CONTINUE_EXPR", "AWAIT_EXPR", "TRY_EXPR"}:
            result["controls"].append({**site(n), "kind": kind.lower()})
        if kind != "NAME_REF":
            continue
        matches = []
        for loc in definitions.get(n["start"][0], []):
            target_source = graph.uri_source(str(loc.get("targetUri", loc.get("uri", ""))))
            selection = loc.get("targetSelectionRange") or loc.get("range") or {}
            if target_source is source and "start" in selection:
                resolved_binding = bindings.get(source.lsp_offset(selection["start"]))
                if resolved_binding:
                    matches.append(resolved_binding)
        if len(matches) == 1:
            write, read = False, True
            for parent in reversed(parents):
                if parent["kind"] == "BIN_EXPR":
                    children = parent.get("children", [])
                    operator = next(
                        (
                            c["kind"]
                            for c in children
                            if c["type"] == "Token"
                            and c["kind"]
                            in {
                                "EQ",
                                "PLUSEQ",
                                "MINUSEQ",
                                "STAREQ",
                                "SLASHEQ",
                                "PERCENTEQ",
                                "AMPEQ",
                                "PIPEEQ",
                                "CARETEQ",
                                "SHLEQ",
                                "SHREQ",
                            }
                        ),
                        None,
                    )
                    lhs = next((c for c in children if c["type"] == "Node"), None)
                    if operator and lhs and lhs["start"][0] <= n["start"][0] < lhs["end"][0]:
                        write, read = True, operator != "EQ"
                    break
            result["uses"].append({**site(n), "binding": matches[0]["id"], "read": read, "write": write})
        elif not matches:
            result["uses"].append({**site(n), "binding": None, "read": True, "write": False})
    return result
