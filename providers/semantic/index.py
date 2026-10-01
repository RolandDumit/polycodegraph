"""JSON provider entrypoint; run with Python isolated mode (-I)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Only the installed adapter directory is added. The indexed repository never
# enters the interpreter's import path; Jedi separately parses its source.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from polycodegraph_adapters.model import Graph  # noqa: E402


def main() -> None:
    """Write only the shared graph JSON array to stdout."""
    request = json.load(sys.stdin)
    graph = Graph(request)
    if sys.argv[1:] == ["--python"]:
        from polycodegraph_adapters.python_graph import PythonGraph

        records = PythonGraph(graph, request.get("options", {})).extract()
    elif sys.argv[1:] == ["--rust"]:
        from polycodegraph_adapters.rust_graph import RustGraph

        records = RustGraph(graph, request.get("options", {})).extract()
    else:
        raise ValueError("Expected --python or --rust")
    sys.stdout.write(json.dumps(records, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
