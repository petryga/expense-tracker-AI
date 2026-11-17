"""The Expense Tracker MCP server as the assistant's toolbox.

The server (the MCP/ repo) runs as a subprocess over stdio for one question
and calls the Expense Tracker API as the asking user. Only tools the server
marks read-only are offered to the model: the assistant never writes.
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp import Client, StdioServerParameters

from app.agent.loop import ToolSpec, tool_text


class McpToolBox:
    def __init__(self, client: Client) -> None:
        self._client = client
        self._allowed: set[str] = set()

    async def tools(self) -> list[ToolSpec]:
        listed = (await self._client.list_tools()).tools
        specs = [
            ToolSpec(t.name, t.description or "", dict(t.input_schema))
            for t in listed
            if t.annotations is not None and t.annotations.read_only_hint is True
        ]
        self._allowed = {s.name for s in specs}
        return specs

    async def call(self, name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        if name not in self._allowed:
            return f"There is no tool named {name}.", True
        try:
            result = await self._client.call_tool(name, arguments, read_timeout_seconds=30)
        except Exception as error:  # The tool failed outright; let the model say so.
            return f"The tool failed ({type(error).__name__}).", True
        return tool_text(result.content, result.structured_content), bool(result.is_error)


@asynccontextmanager
async def mcp_toolbox(
    command: str, args: list[str], api_url: str, token: str | None
) -> AsyncIterator[McpToolBox]:
    env = {
        "EXPENSE_TRACKER_API_URL": api_url,
        **({"EXPENSE_TRACKER_TOKEN": token} if token else {}),
    }
    # PATH lets the command (node) be found; nothing else from this process is passed on.
    env["PATH"] = os.environ.get("PATH", "")
    async with Client(StdioServerParameters(command=command, args=args, env=env)) as client:
        yield McpToolBox(client)
