"""Generate the public reference from the same registry used by MCP discovery."""

import asyncio
from pathlib import Path

from promptlibrary.mcp.server import list_tools


async def main() -> None:
    lines = [
        "# MCP tool reference",
        "",
        "Generated with `python scripts/generate_mcp_reference.py`.",
        "Use runtime `tools/list` for complete JSON schemas and current defaults.",
        "",
    ]
    for definition in await list_tools():
        properties = definition.inputSchema.get("properties", {})
        required = set(definition.inputSchema.get("required", []))
        lines.extend(
            [
                "## `" + definition.name + "`",
                "",
                definition.description,
                "",
                "Parameters: "
                + (
                    ", ".join(
                        "`" + key + "`" + (" (required)" if key in required else "")
                        for key in properties
                    )
                    or "none"
                )
                + ".",
                "",
            ]
        )
    (Path(__file__).resolve().parents[1] / "docs/mcp-tools.md").write_text("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
