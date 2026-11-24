# MemGate / MemSteward — Feature Guide

Governed memory for LLM agents: the agent remembers, the memory stays clean, and everything is auditable. One kernel, four deployment shapes.

## 1. Memory core (LandingStore)

- **Triple-signature entries** — every memory is an (object, action, actual) triple with kind/source metadata, so recall is structured, not fuzzy string matching.
- **Write path** — admission quality gate -> single-writer protocol -> hard persistence (JSON on disk, crash-safe, survives restart). No background rewrite of your data.
- **Read path** — **signature-gated recall** (query by object|action keys), hybrid semantic + BM25 retrieval, plus a liveness gate: cold entries are not injected into context, never silently deleted.
- **Timeline queries** — recall_recent(hours), recall_by_time(start, end), timeline() digest.
- **Embeddings** — pluggable local embedding backend with a KV cache (EmbedCache) so repeated queries cost nothing.

## 2. Quality pipeline (why "governance-grade")

- **Admission gate** — echo fragments, ultra-short and junk writes are quarantined automatically before they ever land in the store.
- **Quarantine + verdicts** — suspicious entries are flagged, not deleted; verification criteria score outcomes.
- **Feedback loop** — good-mode feedback lands in LandingStore.feedback with revoke support.
- **Ledger** — every write is traceable through the governance ledger tool. Better to remember less than to remember wrong.

## 3. Liveness decay (memories age)

- Entries carry a liveness value that decays over time (default decay factor 0.9, configurable floor).
- Older memories fade from recall automatically instead of piling up forever.
- hold(entry) keeps an entry alive (liveness = 1.0) when it matters.

## 4. Governance tool surface (OpenClaw plugin)

Four tools out of the box: governance_preflight / governance_ledger / governance_deposit / governance_recall. Plus a Python bridge with 13 subcommands (deposit, recall, digest, ingest, commit, preflight, ledger, constraints, depscan, version, compact, restore, ping) usable from CLI, oneshot, or serve mode. The plugin wires two OpenClaw slots (memory + contextEngine) and ships a three-tier (hot/warm/cold) memory ingest.

## 5. MCP tool surface (memgate-mcp)

One MCP server, any host: Claude Code, Cursor, Copilot Studio, Windsurf, Cline, Zed.

- memgate_deposit(obj, act, actual, kind, source) — store one governed memory
- memgate_recall(query, top_k) — signature/keyword recall with scores
- memgate_stats() — store statistics
- memgate_compact() — drop redundancy

Python >= 3.9, **zero third-party dependencies** (stdlib + shipped kernel). Config: one JSON block in your host config (see config/mcp-config-examples.md).

## 6. Python SDK

    from memsteward import Memory
    mem = Memory('memory.json')
    mem.deposit('player', 'mining', 'found diamond', kind='experience')
    hits = mem.recall('mining', top_k=5)
    mem.recall_recent(hours=24); mem.timeline(hours=24)
    mem.decay(0.99)          # liveness aging
    mem.hold(entry_id)       # keep alive
    mem.quarantine(entry_id) # flag low quality

Advanced surface (MemStewardLocal): quarantine, distillation, concept space, panoramic/rolling planners, mechanism learner/advisor, zero-intrusion observation wrapper.

## 7. Performance (measured)

| Metric | MemSteward | Mem0 | Zep | LangChain |
|---|---|---|---|---|
| write | **0.01ms** | 50ms | 100ms | 20ms |
| retrieve | **<1ms** | 200ms | 300ms | 100ms |
| quality gate | yes | no | no | no |
| liveness decay | yes | no | partial | no |
| fully local | yes | yes | no | partial |
| Chinese-native tokenizer | yes | partial | partial | partial |

## 8. Privacy and security

- All data stays on your machine (MEMSTEWARD_HOME, default ~/.memsteward/). No cloud sync, no telemetry upload.
- Every write passes the quality gate; single-writer protocol prevents concurrent pollution.
- Contract first: out-of-contract writes stop for review instead of landing silently.

## 9. Versions and compatibility

- Product family: CalVer (YYYY.MM.DD, one release line for all editions). SDK: SemVer (0.x = API may change; 1.0 freezes).
- VERSIONS.json binds plugin/sdk/bridge protocol/embedding fingerprint; verify with: python3 src/bridge_cli.py version
- OpenClaw pluginApi >= 2026.9.4; bridge protocol 3; Python >= 3.9.

## 10. License

Elastic License 2.0 (SPDX: Elastic-2.0): free for internal and commercial use; do not offer the software itself as a hosted/managed service to third parties; patents licensed with the software (suit terminates); trademarks not licensed with the code. Patent boundaries: PATENTS.md.

Deeper documentation: each edition ships a MANUAL.md (promise list + verification contract), a HISTORY.md, and a MANIFEST.md (parts list). The local edition also ships a full capability index (CAPABILITY_INDEX.md).
