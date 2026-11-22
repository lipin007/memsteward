# MemGate · Manual

> **In one line**: the OpenClaw governance middleware plugin — three-tier memory (hot/warm/cold) + governance tool surface + gates; all business logic lives in a single Python bridge source, the TS layer is call surface only.

## Buyer quick start (10 minutes)

**① Get and unpack the package (30 seconds)**

```bash
tar -xzf memgate-2026.11.19.tgz && cd package
```

**② Use the Python bridge source directly (2 minutes, no OpenClaw needed)**

```bash
mkdir -p ~/.memsteward/landing
python3 src/bridge_cli.py deposit --landing ~/.memsteward/landing/landing.json --obj player --act mining --actual "found diamond"
python3 src/bridge_cli.py recall --landing ~/.memsteward/landing/landing.json --signature 'player|mining'
```

Writes pass the quality gate (admission: echo fragments / ultra-short entries are quarantined automatically); recall carries a liveness gate (cold entries not injected ≠ deleted). Recall is **signature-gated**: `--signature` takes an `object|action` key (e.g. `player|mining`), not free text.

**③ Hook into OpenClaw (standard install)**

```bash
openclaw plugins install ./memgate-2026.11.19.tgz   # run on the buyer machine
# or one-shot: bash deploy/install.sh (package -> daemon -> wiring -> self-check; --skip-unit skips systemd)
```

Once installed, four governance tools are available: `governance_preflight` / `governance_ledger` / `governance_deposit` / `governance_recall`.

---
## Naming history (why MemGate)

`governance-middleware` (skeleton, 11-03) -> `calldecacy` (assembly, 11-04) -> **`MemGate`** (product overhaul, 11-05).
It is a **separate product** from the old CallDecay (dependency relationship, not same-source); the rename severs the confusion completely.

## What is in the box

| Path | Contents |
|---|---|
| `index.ts` / `src/*.ts` | plugin surface: context-engine (three-tier memory), memory-capability (ledger digest), tools (the four governance tools) |
| `src/bridge_cli.py` | **single Python source** (all business logic): CLI / oneshot / serve forms, self-healing resident worker |
| `src/vendor/` | build artifacts (shipped by pack.sh): calldecay-sdk + core + pvs-sdk — **dependency libraries, regenerable** |
| `assemble.sh` / `pack.sh` | one-shot assembly check (syntax -> version binding -> regression suite -> preflight; suite size as the run reports) / npm artifact packaging |
| `_legacy/` | backup of the predecessor governance-middleware (kept for the record) |

## Tools and interfaces

- **Four governance tools** (TS surface): `governance_preflight` / `governance_ledger` / `governance_deposit` / `governance_recall`
- **bridge subcommands** (13): deposit / recall / digest / ingest / commit / preflight / ledger / constraints / depscan / version / compact / restore / ping
- **Slots**: `plugins.slots.memory=memgate`, `contextEngine=memgate` (openclaw.json)

## Dependencies (vendor origin)

| Dependency | Origin | Purpose |
|---|---|---|
| calldecay-sdk | `../CallDecay/sdk/calldecay` | LandingStore engine (hard persistence / signature-gated recall / replay) |
| core | `../CallDecay/core/` | accept_contract (F1/F3 boundaries) |
| pvs-sdk | `../pvs-sdk/` | pvs.gate gates / ledgers / governance discipline surface |

**Relationship to the old CallDecay = dependency, not same source**: this plugin touches the decision loop in zero places (verified by grep across 5 source files).

## Operations

- Assembly check: `bash assemble.sh --write`; artifacts: `bash pack.sh`
- Data directory: `$MEMSTEWARD_HOME/landing/landing.json` (default `~/.memsteward/`; `~/.calldecacy` is a **legacy default fallback** for some kernel auxiliaries — override via env or explicit arguments; production runs use explicit paths throughout — corrected after 2026-11-20 testing)
- Release red line: pack.sh artifacts = internal / same-machine distribution; public releases go through the Release Exclusion List six gates
