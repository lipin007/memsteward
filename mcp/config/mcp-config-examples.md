# Host connection config snippets (MCP stdio)

Common shape (works for Claude Desktop / Cursor / Cline / Windsurf / Zed; each host keeps its config in a different place):

    {
      "mcpServers": {
        "memgate": {
          "command": "python3",
          "args": ["/absolute/path/memgate-mcp/mcp_server.py"],
          "env": { "MEMGATE_HOME": "/absolute/path/to/memory-store" }
        }
      }
    }

After an npm install the shipped launcher works too (no hand-typed paths):

    {
      "mcpServers": {
        "memgate": {
          "command": "memgate-mcp",
          "env": { "MEMGATE_HOME": "/absolute/path/to/memory-store" }
        }
      }
    }

- Claude Desktop: claude_desktop_config.json (Help -> Developer -> Edit Config)
- Cursor: .cursor/mcp.json (project level) or the global MCP settings
- Cline / Windsurf: the MCP Servers panel in extension settings
- moving machines or hosts changes nothing: stdio protocol, only python3 >= 3.9 required (the npm launcher additionally needs node >= 16)

Tool surface: memgate_deposit (store) / memgate_recall (fetch) / memgate_stats (ledger) / memgate_compact (compact).
