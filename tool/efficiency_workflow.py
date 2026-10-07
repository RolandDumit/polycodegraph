"""Static task surfaces derived from the actual MCP catalog; no lazy registration."""

from __future__ import annotations

import copy

AGENT_TOOLS = ("status", "search_symbol", "inspect_change", "snippet", "index_repository")
WORKFLOW_GUIDE = (
    "Use the known target directly. Collect required sites before editing; preserve full IDs, "
    "offsets, confidence, snapshot and limits. Expand only a concrete missing fact or source. "
    "Static completion is not compiler/test verification. Review needs an exact baseline before "
    "editing and the same scope afterward. Follow the repository checks."
)


def workflow_surface(catalog: list[dict], profile: str, *, discovery: bool = False, continuation: bool = False) -> dict:
    """Materialize a task-start surface; register these tools and exactly these instructions.

    Full/agent retain the canonical specs. A selected intent uses the canonical name,
    fixes its intent and lean format, and exposes only its own typed options. Pagination
    belongs to the adapter. No server catalog or semantic configuration is changed.
    """
    if profile == "local":
        return {"profile": profile, "tools": [], "instructions": ""}
    by_name = {tool["name"]: tool for tool in catalog}
    if profile in ("full", "agent"):
        names = list(by_name) if profile == "full" else list(AGENT_TOOLS)
        return {
            "profile": profile,
            "tools": copy.deepcopy([by_name[name] for name in names]),
            "instructions": WORKFLOW_GUIDE,
        }
    spec = copy.deepcopy(by_name["inspect_change"])
    canonical = spec["inputSchema"]
    variants = {rule["if"]["properties"]["intent"]["const"]: rule["then"] for rule in canonical["allOf"]}
    if profile not in variants:
        raise ValueError("unknown workflow profile")
    variant = variants[profile]
    properties = {
        key: copy.deepcopy(canonical["properties"][key]) for key in ("target", "depth", "detail", "budget", "view")
    }
    properties["intent"] = {"type": "string", "enum": [profile]}
    properties["format"] = {"type": "string", "enum": ["lean"]}
    properties["options"] = copy.deepcopy(variant["properties"]["options"])
    if continuation:
        properties["cursor"] = copy.deepcopy(canonical["properties"]["cursor"])
        properties["cursor"]["description"] = (
            "Explicit recovery after a collector limit: repeat identical arguments. Returns one canonical lean page."
        )
    spec["inputSchema"] = {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": ["target", "intent", "format", *variant.get("required", [])],
    }
    spec["description"] = f"Collect {profile} evidence and all required sites. The client owns bounded pagination."
    tools = [spec]
    if discovery:
        tools.insert(0, copy.deepcopy(by_name["search_symbol"]))
    return {"profile": profile, "tools": tools, "instructions": WORKFLOW_GUIDE}


def workflow_arguments(surface: dict, arguments: dict) -> dict:
    """Reject other workflows/collector-owned controls; canonical validation stays on the server."""
    specs = {tool["name"]: tool for tool in surface["tools"]}
    if "inspect_change" not in specs:
        raise ValueError("inspect_change is not registered for this task")
    schema = specs["inspect_change"]["inputSchema"]
    if surface["profile"] in ("full", "agent"):
        return copy.deepcopy(arguments)
    if set(arguments) - schema["properties"].keys():
        raise ValueError("argument outside selected workflow")
    if any(field not in arguments for field in schema["required"]):
        raise ValueError("missing required workflow argument")
    if arguments["intent"] != surface["profile"] or arguments["format"] != "lean":
        raise ValueError("argument conflicts with selected workflow")
    if set(arguments.get("options", {})) - schema["properties"]["options"]["properties"].keys():
        raise ValueError("option outside selected workflow")
    return copy.deepcopy(arguments)
