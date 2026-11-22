# D-MCP Edition · File list (2026.11.21)

- **mcp_server.py** — MCP stdio server (zero third-party dependencies) | production single source
- **bin/memgate-mcp.js** — npm launcher (spawns python3 mcp_server.py, stdio passthrough)
- **kernel/** — shipped kernel (vendor) | regenerable
- **test/test_mcp.py** — smoke: handshake + four tools + error codes | verification
- **config/mcp-config-examples.md** — host connection config snippets | delivery docs
- **README.md / MANUAL.md / HISTORY.md** — listing page / product manual / history | delivery docs
- **package.json** — npm package description (memgate-mcp, bin=memgate-mcp)
- **VERSIONS.json** — version binding (product/protocol/tool surface/zero-dependency declaration) | binding source
- **LICENSE** — Elastic License 2.0 (SPDX: Elastic-2.0)

Same-source semantics: Plugin Edition (A) tool surface == Complete Edition (B) REST surface == D-MCP tool surface (deposit/recall/stats/compact).
