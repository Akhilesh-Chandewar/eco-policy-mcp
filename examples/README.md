# Connecting any MCP client

`eco-policy-mcp` is client-agnostic: it speaks standard MCP (stdio +
streamable-HTTP), so **any** MCP-compatible client works — Claude Desktop,
Cursor, Gemini CLI, VS Code, Cline, Windsurf, custom agents, anything.

## Local clients (stdio)

Run via `uvx` (no install needed once published to PyPI):

```json
{
  "mcpServers": {
    "eco-policy-mcp": {
      "command": "uvx",
      "args": ["eco-policy-mcp"]
    }
  }
}
```

Drop this shape into:

| Client | Config file |
|---|---|
| Claude Desktop | `claude_desktop_config.json` → see `claude_desktop.json` |
| Cursor | `.cursor/mcp.json` → see `cursor.mcp.json` |
| Gemini CLI | `~/.gemini/settings.json` → see `gemini-cli.settings.json` |
| VS Code (Copilot) | `.vscode/mcp.json`, same shape |
| Cline / others | same `command` + `args` shape |

Until the package is on PyPI, run from this repo instead:

```json
{
  "mcpServers": {
    "eco-policy-mcp": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/eco policy mcp", "run", "eco-policy-mcp"]
    }
  }
}
```

## Remote / web clients (streamable-HTTP)

Start the server:

```bash
eco-policy-mcp --http --port 8000
```

Then point any HTTP-capable MCP client at `http://127.0.0.1:8000/mcp`
(see `remote-http.client.json`). The same tools, resources and prompts are
exposed on both transports — no client-specific code anywhere.
