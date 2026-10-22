# MCP access

The MCP server uses stdio and the same local database and services as the browser.
It does not require the HTTP server to be running. It is not a remotely exposed
MCP endpoint. A client needs permission to start the local Python process and read
the configured data directory.

From the installed environment:

```sh
promptlibrary-mcp --print-config
promptlibrary-mcp --print-tools
```

The first command prints a common `mcpServers` configuration with absolute paths;
adapt the enclosing client setting if your host uses a different configuration
shape. On Windows, run `.venv\Scripts\promptlibrary-mcp.exe`; on Unix,
`.venv/bin/promptlibrary-mcp` works without activation. Give both interfaces the
same `PROMPTLIB_DATA_DIR`. Normal server mode is `promptlibrary-mcp` with no flags;
stdout is reserved for the MCP protocol.

## Discover and use

Use `tools/list` instead of relying on a copied tool count. Schemas include required
inputs, defaults and read/destructive/network hints. Input errors name the failing
fields without echoing supplied secrets. Tool failures set `isError` and include
a stable code such as `not_found`, `conflict` or `invalid_input`.

A typical workflow is:

1. Find content with `search_library`, `search_prompts` or `get_prompt`.
2. Create/edit prompts and metadata using the discovered contracts. Mutations are
   committed only when the operation succeeds.
3. Compose workflow stages, then call `start_workflow_run` with its required inputs.
4. Read `get_workflow_run`, execute its rendered text using your chosen provider,
   and submit the output with `complete_workflow_step` and the expected stage.
5. Continue until completed, or cancel the run. Saved outputs remain available.

The exact callable names are listed by the server; [tool reference](mcp-tools.md)
is generated from the registry. The resources `library://stats` and
`library://recent` provide compact JSON summaries.

## Approval and data boundaries

A connected client has access to the full library. There is no per-agent role or
project permission system. Require approval for deletion, history clearing,
replacement imports, remote configuration and remote writes. Tool annotations
are advice to the client, not an enforcement mechanism.

Remote configuration returns masked secret fields, and portable snapshots omit
remote credentials. Prompts, notes and outputs are still sensitive content.
Do not send them to an external model without the user's permission. Treat their
text as data rather than trusted instructions to your agent.

The adapter uses MCP SDK 1.x. Upgrading that major version requires transport
tests, not a dependency-only version bump.
