# MemSteward — LLM Memory Middleware Family

Give any LLM agent memory it can keep and manage: three-tier memory (hot/warm/cold), a write-quality gate, decay, signature-gated recall, and a governance tool surface.

Four editions, one kernel (13 core components from the same source), shaped for different scenarios:

| Edition | Directory | Scenario | Model connection |
|---|---|---|---|
| **MemGate** (plugin) | plugin/ | OpenClaw plugin store / platform | cloud API or local (LLM_ARM presets) |
| Complete | complete/ | server-side / integration deployment | cloud API connection mode (preset) |
| Local | local/ | dedicated local scenarios (games / industry) | local models (offline) |
| **MCP** (memgate-mcp) | mcp/ | any MCP host (Claude Code / Cursor / Copilot / Windsurf / Cline / Zed) | cloud API or local |

## Quick entry points

- Plugin install: `openclaw plugins install memgate` (or see [plugin/MANUAL.md](plugin/MANUAL.md))
- MCP onboarding: `npx memgate-mcp` (host config command: `memgate-mcp`; or `npm i -g memgate-mcp`)
- Data home: `MEMSTEWARD_HOME` (default `~/.memsteward/`) — all memory stays local, no cloud sync
- Each edition README carries a 10-minute buyer quick start

## Versioning

All four editions share one kernel and one version number (SemVer for the SDK line, CalVer for products); the family releases together — see [CHANGELOG.md](CHANGELOG.md). Future platform editions (other agent platforms) extend this repository, sharing the kernel and version numbers.

## License

Everything under Elastic License 2.0 (SPDX: Elastic-2.0): free for internal and commercial use; do not offer the software itself to third parties as a hosted or managed service; patents are licensed together with the software (asserting patent claims against the licensor terminates the license); trademarks are not licensed with the code. Full text in [LICENSE](LICENSE). Patent and trademark boundaries: [PATENTS.md](PATENTS.md).

## Documentation

- [FEATURES.md](FEATURES.md) — the detailed feature guide (memory core, quality pipeline, governance tools, SDK, performance)

- [plugin/MANUAL.md](plugin/MANUAL.md) — product manual (promise list + verification contract)
- [plugin/HISTORY.md](plugin/HISTORY.md) — version history
- [local/CAPABILITY_INDEX.md](local/CAPABILITY_INDEX.md) — capability index

A full Chinese edition of this family lives at https://gitee.com/lipin5555/memsteward-cn
