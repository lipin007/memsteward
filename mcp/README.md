# MemGate MCP (D-MCP Edition)

**In one line**: connect governed memory (audited writes/reads, quality gates, statistical ledgers) to any MCP-capable AI platform — Claude Code, Cursor, Copilot Studio, Windsurf, Cline, Zed, one surface for all.

## Quick start

    # 1. smoke self-test (should print SMOKE ALL GREEN)
    python3 test/test_mcp.py

    # 2. connect a host (Claude Desktop example; see config/mcp-config-examples.md)
    #    paste the config JSON into claude_desktop_config.json, restart the host
    #    after npm install the shipped launcher works too: "command": "memgate-mcp"

## Tool surface (same-source semantics with the Plugin Edition (A) / Complete Edition (B))

- **memgate_deposit(obj, act, actual, kind, source)** — store one governed memory
- **memgate_recall(query, top_k)** — recall by signature/keyword (with scores)
- **memgate_stats()** — memory store statistics
- **memgate_compact()** — compact (drop redundancy)

## Environment

- Python >= 3.9, **zero third-party dependencies** (stdlib + shipped kernel)
- MEMGATE_HOME: memory store directory (default ~/.memgate-mcp) — multi-project isolation = one directory per project
- family relationship: tool semantics are same-source with the Plugin Edition (A) / Complete Edition (B) (deposit/recall/stats/compact)

## Version

2026.11.21 (2026-11-21, family YYYY.MM.DD scheme) — MCP 2025-06-18, four-tool surface, smoke test shipped.
