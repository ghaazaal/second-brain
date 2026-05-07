import logging
from collections.abc import Sequence
from typing import Any
import os
from dotenv import load_dotenv
from mcp.server import Server
from mcp.types import (
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
)

load_dotenv()

from . import tools
from . import obsidian

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp-obsidian")

app = Server("mcp-obsidian")

tool_handlers: dict[str, tools.ToolHandler] = {}


def _register_handlers(api: obsidian.Obsidian) -> None:
    for handler in [
        tools.ListFilesInDirToolHandler(api),
        tools.ListFilesInVaultToolHandler(api),
        tools.GetFileContentsToolHandler(api),
        tools.SearchToolHandler(api),
        tools.PatchContentToolHandler(api),
        tools.AppendContentToolHandler(api),
        tools.PutContentToolHandler(api),
        tools.DeleteFileToolHandler(api),
        tools.ComplexSearchToolHandler(api),
        tools.BatchGetFileContentsToolHandler(api),
        tools.PeriodicNotesToolHandler(api),
        tools.RecentPeriodicNotesToolHandler(api),
        tools.RecentChangesToolHandler(api),
        tools.SummarizeFolderToolHandler(api),
    ]:
        tool_handlers[handler.name] = handler


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [th.get_tool_description() for th in tool_handlers.values()]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
    if not isinstance(arguments, dict):
        raise RuntimeError("arguments must be dictionary")

    handler = tool_handlers.get(name)
    if not handler:
        raise ValueError(f"Unknown tool: {name}")

    try:
        return handler.run_tool(arguments)
    except Exception as e:
        logger.error(str(e))
        raise RuntimeError(f"Caught Exception. Error: {str(e)}")


async def main():
    api_key = os.getenv("OBSIDIAN_API_KEY")
    if not api_key:
        raise ValueError(f"OBSIDIAN_API_KEY environment variable required. Working directory: {os.getcwd()}")

    api = obsidian.Obsidian(api_key=api_key)
    _register_handlers(api)

    # Import here to avoid issues with event loops
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )
