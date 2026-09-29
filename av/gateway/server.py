"""MCP server (official Python SDK, stdio) exposing EXACTLY the agent's six tools (rule 4).

    python -m av.gateway.server --scenario <id> --workspace <dir> --ledger <file>

The task comes from scenarios/<id>/task.yaml when the server starts; the agent cannot change it.
Tool arguments are only the fixed per-tool params (av.contracts.TOOL_PARAMS): the agent has no
channel to assert scope or provenance, and none would be read if it did (rule 3).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from av.contracts import TOOLS
from av.gateway.core import Gateway
from av.scenarios import load_scenario

INSTRUCTIONS = (
    "Every call is verified before it runs. The reply says the decision and why; a blocked "
    "action changed nothing. Do not retry a blocked action with the same content."
)


def build_server(gateway: Gateway) -> MCPServer:
    server = MCPServer("av-gateway", instructions=INSTRUCTIONS)

    @server.tool(name="list_files", description="List files under a workspace directory (default: the whole workspace).")
    def list_files(path: str = "") -> str:
        return gateway.call("list_files", {"path": path} if path else {}).text

    @server.tool(name="read_file", description="Read a text file in the workspace.")
    def read_file(path: str) -> str:
        return gateway.call("read_file", {"path": path}).text

    @server.tool(name="write_file", description="Replace a file's whole content (creates it if missing).")
    def write_file(path: str, content: str) -> str:
        return gateway.call("write_file", {"path": path, "content": content}).text

    @server.tool(name="delete_file", description="Delete a file in the workspace.")
    def delete_file(path: str) -> str:
        return gateway.call("delete_file", {"path": path}).text

    @server.tool(name="run_tests", description="Run the repo's test suite and return the output.")
    def run_tests() -> str:
        return gateway.call("run_tests", {}).text

    @server.tool(name="submit", description="Finish the task with a one-line summary.")
    def submit(summary: str = "") -> str:
        return gateway.call("submit", {"summary": summary} if summary else {}).text

    return server


def tool_names(server: MCPServer) -> list[str]:
    import asyncio

    return sorted(t.name for t in asyncio.run(server.list_tools()))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--workspace", required=True, type=Path)
    ap.add_argument("--ledger", required=True, type=Path)
    args = ap.parse_args(argv)
    scenario = load_scenario(args.scenario)
    server = build_server(Gateway(scenario.task, args.workspace, args.ledger))
    assert sorted(TOOLS) == tool_names(server), "gateway must expose exactly the six tools"
    server.run("stdio")


if __name__ == "__main__":
    main()
