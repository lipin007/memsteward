# D-MCP Edition · History

- **Project opened 2026-11-21 22:40** (decision: "start, manage the platform well, no mess"): strategic call = MCP is the de-facto standard for AI coding platforms (Claude Code / Cursor / Copilot / Windsurf / Cline / Zed all covered); one MCP surface unlocks the whole ecosystem — more leverage than one plugin per host.
- Shape decision: join the **middleware family** (alongside A/B/C, family management), no separate stovepipe — reuse the family production/listing separation, VERSIONS binding, and registration gate.
- Implementation decision: **zero third-party dependencies**, hand-rolled MCP stdio (family self-sufficiency philosophy); kernel driven in-process (works offline); semantics mirror the B edition REST surface.
- 2026-11-21 23:0x smoke all green (handshake / four tools / error code -32601), see test/test_mcp.py.

## Correction record (2026-11-21 22:5x, opened after the question "0.1.0 does not look right")

- **Original text**: VERSIONS.json / server version = 0.1.0
- **Root cause**: opening the project casually started a new semver line, violating the family versioning rule (VERSIONS-3tier.md, decided 2026-11-17: version format YYYY.MM.DD, three lines increment independently); the same day the A/B lines were already drifting (npm 0.2.x forced by re-release, GHCR 0.1.2 an ad-hoc in-tree number) — three lines, three eras = confirmed version drift
- **Current ruling**: the D edition first number = **2026.11.21** (family scheme, and legal semver for npm); **all lines standardize on YYYY.MM.DD going forward** — published npm 0.2.x / GHCR 0.1.2 are immutable; from the next release they rejoin the line
- **Impact**: all D management files (VERSIONS.json / mcp_server.py / manual) updated; A/B listing artifacts unchanged
- **Open items**: the B line next release uses 2026.11.x; the npm line next release likewise rejoins (the version jump is the drift zero point)
- **2026-11-22 listing package built**: 73 files + memgate-mcp-2026.11.21.tgz (350KB), smoke all green; added package.json + bin/memgate-mcp.js launcher; MANIFEST version corrected 0.1.0 -> 2026.11.21.

## Correction record (2026-11-22)

- License statement corrected: the top-level LICENSE had mistakenly held old commercial-license text; that day it first rejoined the unified statement, then switched to Elastic License 2.0 per plan A (see next entry).

## Correction record (2026-11-22)

- License switched again: everything under **Elastic License 2.0** (SPDX: Elastic-2.0) — standard terms, free internal and commercial use, no offering the software itself as a hosted/managed service to third parties, patents licensed with the software (suit terminates), trademarks not licensed with code. The previous Unified Statement v1.3 wording is retired.
