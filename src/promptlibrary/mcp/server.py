"""MCP stdio adapter. Importing domain tools does not start a server or require the SDK."""

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, cast

from promptlibrary import __version__
from promptlibrary.config import settings
from promptlibrary.database import get_db, init_db
from promptlibrary.mcp import tools as tools  # Registers the annotated domain handlers.
from promptlibrary.mcp.registry import TOOLS, ToolDefinition, ToolText, execute_tool, text_result
from promptlibrary.services.validation import Record

if TYPE_CHECKING:
    from mcp.server import Server


async def list_tools() -> list[ToolDefinition]:
    return [registered.definition for registered in TOOLS.values()]


async def call_tool(name: str, arguments: Record) -> list[ToolText]:
    payload, _ = await execute_tool(name, arguments)
    return text_result(payload)


async def read_resource(uri: str) -> str:
    async with get_db() as db:
        if uri == "library://stats":
            result: Record = {}
            for table, key in (
                ("prompts", "total_prompts"),
                ("workflows", "total_workflows"),
                ("categories", "categories"),
                ("tags", "tags"),
                ("projects", "projects"),
            ):
                cursor = await db.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608 - identifiers are selected from a closed schema allowlist.
                row = await cursor.fetchone()
                if row is None:
                    raise RuntimeError("The database returned no result for an atomic operation.")
                result[key] = row[0]
            cursor = await db.execute(
                "SELECT status,COUNT(*) AS count FROM prompts GROUP BY status"
            )
            result["prompt_statuses"] = {row[0]: row[1] for row in await cursor.fetchall()}
            for status, key in (
                ("published", "published"),
                ("draft", "drafts"),
                ("staged", "staged"),
            ):
                result[key] = result["prompt_statuses"].get(status, 0)
            return json.dumps(result)
        if uri == "library://recent":
            cursor = await db.execute(
                "SELECT id,title,status,updated_at FROM prompts ORDER BY updated_at "
                "DESC,id DESC LIMIT 10"
            )
            return json.dumps([dict(row) for row in await cursor.fetchall()])
    raise ValueError("Unknown resource.")


def _register_sdk_handler[SDKHandler: Callable[..., Awaitable[Any]]](
    factory: Callable[..., Any], handler: SDKHandler, **options: bool
) -> None:
    # MCP 1.x registration factories have unannotated return types. Keep this SDK
    # boundary local rather than making the handlers or domain services untyped.
    register = cast(Callable[[SDKHandler], SDKHandler], factory(**options))
    register(handler)


def create_server() -> "Server":
    from mcp.server import Server
    from mcp.types import CallToolResult, Resource, TextContent, Tool
    from pydantic import AnyUrl

    server = Server("promptlibrary")

    async def sdk_list_tools() -> list[Tool]:
        return [Tool.model_validate(definition.model_dump()) for definition in await list_tools()]

    # The registry validates inputs without echoing rejected secrets in SDK errors.
    async def sdk_call_tool(name: str, arguments: Record) -> CallToolResult:
        payload, is_error = await execute_tool(name, arguments)
        return CallToolResult(
            content=[TextContent(type="text", text=item.text) for item in text_result(payload)],
            isError=is_error,
        )

    async def sdk_list_resources() -> list[Resource]:
        return [
            Resource(uri=AnyUrl(uri), name=name, mimeType="application/json")
            for uri, name in (
                ("library://stats", "Library statistics"),
                ("library://recent", "Recent prompts"),
            )
        ]

    async def sdk_read_resource(uri: AnyUrl) -> str:
        return await read_resource(str(uri))

    _register_sdk_handler(server.list_tools, sdk_list_tools)
    _register_sdk_handler(server.call_tool, sdk_call_tool, validate_input=False)
    _register_sdk_handler(server.list_resources, sdk_list_resources)
    _register_sdk_handler(server.read_resource, sdk_read_resource)
    return server


async def _run() -> None:
    from mcp.server.stdio import stdio_server

    await init_db()
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="PromptLibrary MCP stdio server")
    parser.add_argument("--version", action="version", version=__version__)
    flags = parser.add_mutually_exclusive_group()
    flags.add_argument("--print-config", action="store_true")
    flags.add_argument("--print-tools", action="store_true")
    arguments = parser.parse_args(argv)
    if arguments.print_config:
        # Do not resolve an interpreter symlink: that would escape its virtual environment.
        entry = {
            "command": os.path.abspath(sys.executable),
            "args": ["-m", "promptlibrary.mcp.server"],
            "env": {
                "PROMPTLIB_DATA_DIR": str(settings.data_dir.expanduser().resolve()),
                "PROMPTLIB_DB_NAME": settings.db_name,
            },
        }
        print(json.dumps({"mcpServers": {"promptlibrary": entry}}, indent=2))
    elif arguments.print_tools:
        print(json.dumps([tool.definition.model_dump() for tool in TOOLS.values()], indent=2))
    else:
        asyncio.run(_run())


if __name__ == "__main__":
    main()
