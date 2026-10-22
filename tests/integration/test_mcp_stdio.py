"""Wire-level MCP checks against the installed SDK and a separate server process."""

import json
import os
import sys
from datetime import timedelta
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent


async def test_stdio_discovery_mutation_resource_and_error(tmp_path: Path):
    environment = dict(os.environ)
    environment["PROMPTLIB_DATA_DIR"] = str(tmp_path / "mcp library")
    environment["PROMPTLIB_HOST"] = "127.0.0.1"
    parameters = StdioServerParameters(
        command=sys.executable, args=["-m", "promptlibrary.mcp.server"], env=environment
    )
    with anyio.fail_after(30):
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(
                reader, writer, read_timeout_seconds=timedelta(seconds=10)
            ) as client:
                await client.initialize()
                discovered = await client.list_tools()
                names = {item.name for item in discovered.tools}
                assert {
                    "search_prompts",
                    "create_prompt",
                    "start_workflow_run",
                    "export_library",
                } <= names
                created = await client.call_tool(
                    "create_prompt", {"title": "Wire test", "body": "Useful"}
                )
                assert not created.isError
                assert isinstance(created.content[0], TextContent)
                identity = json.loads(created.content[0].text)["id"]
                retrieved = await client.call_tool("get_prompt", {"id": identity})
                assert not retrieved.isError
                assert isinstance(retrieved.content[0], TextContent)
                assert json.loads(retrieved.content[0].text)["body"] == "Useful"
                rejected = await client.call_tool(
                    "create_prompt", {"title": "Bad", "secret": "do-not-echo"}
                )
                assert rejected.isError
                assert "do-not-echo" not in rejected.model_dump_json()
                stats = await client.read_resource("library://stats")
                assert stats.contents
                assert json.loads(stats.contents[0].text)["total_prompts"] == 1
