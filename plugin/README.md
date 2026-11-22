# memgate

The OpenClaw governance plugin (v0.1.0): three-tier memory (hot/warm/cold) + governance tool surface. All business logic lives in the single Python source (shipped in `src/vendor/`); the TS layer is call surface only.

## Install

| Form | Command | Fits |
|---|---|---|
| ClawHub store | `openclaw plugins install memgate` | public direct install (recommended) |
| local artifact | `openclaw plugins install ./memgate-2026.11.19.tgz` | same-machine / offline distribution |
| workspace link | `plugins.load.paths` points at this directory | development |

## Surface

- memory: memory slot (ledger digest) + contextEngine slot (three-tier memory ingest/commit)
- tools: preflight / ledger / constraints / depscan (call surface)
- three forms: CLI / `--oneshot` / `--serve`, dispatched by the same `run()`, one behavior

## Configuration

- data home: `MEMSTEWARD_HOME` (default `~/.memsteward/`), all memory stays local, no cloud sync
- LLM connection preset: copy `config/llm_connection.env.example` to `.env` (cloud API or local localhost)
- slots: after install, `openclaw.json` wires the slots automatically (memory/contextEngine=memgate)

## Version binding

`VERSIONS.json` binds plugin/sdk/bridge protocol/embedding model fingerprint/config slots; verify with `python3 src/bridge_cli.py version` (bound/mismatches).

## Install (2 minutes, zero fuss)

    openclaw plugins install memgate

- zero-build for buyers: compiled artifacts and vendor ship with the package; no pip install, no compile step
- uninstall: `openclaw plugins remove memgate` (data kept) / delete `MEMSTEWARD_HOME` manually (data deleted)

## Compatibility

- OpenClaw pluginApi >= 2026.9.4; bridge protocol BRIDGE_PROTOCOL=3 (see `VERSIONS.json`)
- the plugin tools need no model routing (deposit/recall/ledger are fully offline), decoupled from model preflight
- older OpenClaw (before 2026.11) reporting "could not verify a usable inference route" (old SecretRef key-resolution bug, fixed 2026.11.3): upgrade OpenClaw

## Security model

- all data local: memory/ledgers/backups live under `MEMSTEWARD_HOME`; no cloud sync, no telemetry upload
- gated writes: every write passes the quality gate (write grading / watchdog table / registration gate); single-writer protocol prevents concurrent pollution
- contract first: out-of-contract writes stop and wait for review, flags need registration confirmation — better to remember less than to remember wrong

---

Home base (source / docs / issues): https://github.com/lipin007/memsteward
