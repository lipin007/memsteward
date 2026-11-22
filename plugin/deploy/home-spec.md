# MemSteward home directory spec v1 (~/.memsteward/)

> Philosophy (decided 2026-11-11): after install, **everything lives in one dedicated home directory**, like `~/.openclaw` — a spec/standard that can grow: **this home is the platform**, where the future ecosystem (module packs / memory packs / third-party extensions) will thrive.
> Iron rule: the home lives on the /home partition as its own door; no defaults write to the root partition (/, /tmp, /var, /opt).

## 1. Standard layout (set up once at install; anything missing = sick)

```
~/.memsteward/
├── README.md          <- this spec (placed by the installer; the home manual)
├── 家/ (home)         <- T0 memory assets: landing.json · archive/ · lock — **the memory body, never deleted**
├── state/             <- runtime state: activity.json · summarize-buffer.json · m3_pilot_*
├── shadow/            <- observation surface: serve.log · telemetry.jsonl · dashboard data
├── config/            <- configuration: daemon_forward.json (gate/ports/allowlists) · future config files
├── modules/           <- ecosystem slots (capability module packs): local acceleration · enterprise governance · third-party modules
├── packs/             <- ecosystem slots (content packs): memory asset packs · rule sets · courses/templates
└── tmp/               <- scratch (TMPDIR points here — /tmp forbidden)
```

## 2. Partition law

| Zone | Owns | Lifecycle | Who writes |
|---|---|---|---|
| `家/` (home) | memory assets (T0 ledger + archive) | **never deleted** (kept on uninstall — memory belongs to its owner) | daemon (serve.py) only |
| `state/` | runtime state | rebuildable (kept by default) | daemon + bridge |
| `shadow/` | observation | rotatable/cleanable | daemon + probes |
| `config/` | configuration | user-editable (back up before editing) | user + installer |
| `modules/` | **capability module packs** | install/uninstall independently (see §3 module contract) | installer + the module own install steps |
| `packs/` | **content packs** | install/uninstall independently | same |
| `tmp/` | scratch | clear anytime | anyone |

## 3. Ecosystem contract (module packs v1)

A module pack = one directory `modules/<name>/`, minimum three files:

```
modules/local-acceleration-pack/
├── MODULE.md        <- module description (what it is / dependencies / install / rollback)
├── manifest.json    <- {"name": "…", "version": "…", "requires": ["kv-llama@…"], "entry": "…"}
└── (the module own clients/configs/scripts)
```

- **the core does not depend on modules** (if a module fails to install or is removed, the memory core keeps running) — the ecosystem is added value, not the foundation
- modules never write into each other directories; shared resources go through `state/` or are declared in `manifest.json` under `shared`
- content packs (`packs/`) are isomorphic (manifest marks `type: "content"`)

## 4. Versions and migration

- this spec ships with the package (the installer places `README.md`); layout changes = **migration scripts** (never silently rewrite the home)
- ledger format upgrades = keep the old version in `家/archive/` + a migration record (write history, do not delete it — continuing the 11-08 decision)

## 5. Ecosystem horizon (reserved for v2+)

- module marketplace (discovery / install / signing for third-party module packs) — plug into the ClawHub ecosystem
- memory pack marketplace (portable memory assets — the carrier of the "switch frameworks, keep your memories" moat)
- home directory as identity (export `~/.memsteward` = take all your memories and capabilities with you — one-line migration/backup across machines)
