# MemGate · History

| Date | Milestone | Evidence |
|---|---|---|
| 2026-11-03 | **plugin skeleton up** (named governance-middleware, 8 files): three surfaces registered (context-engine three-tier memory / memory ledger digest / four governance tools) + bridge_cli.py single Python bridge; seven-way smoke + TS syntax pass | memory/2026-11-03 |
| 2026-11-04 17:28 | **assembly v0.1.0** (renamed calldecacy): three-tier memory + governance discipline surface + four governance tools + depscan S2 + bridge dual channel (oneshot/serve); first VERSIONS.json binding (sdk 0.1.0 / bridgeProtocol 2); predecessor backed up in _legacy/ | assembly manual v1_20261104.md / VERSIONS.json |
| 2026-11-04 22:11 | first vendor build (snapshot from the upstream source) | file timestamps |
| 2026-11-05 15:3x | **dependency refresh + worker restart**: full pack.sh chain green (A-class leak scan zero hits); 3 vendor components updated (landing/adapter/decision_symbolic); zero behavior change (the plugin calls no decision-loop interface; classified as dependency refresh after evidence) | registry A21 |
| 2026-11-05 17:1x | **product overhaul**: (1) renamed to **MemGate** (slug / display name / both slots switch to memgate) (2) moved to its own product home (3) path self-adaptation (walk up from WS/root to find the repo marker; works at old and new depths) (4) regression 44/44 (F10 engine id fixed across 4 TS files) (5) registry gate 5/5 | registry A22 |

## Naming chain

governance-middleware -> (renamed 11-04) -> calldecacy -> (renamed 11-05, product overhaul) -> **MemGate**

## Open items (as they stand)

- bridge 14th subcommand (feedback, decided 2026-11-05): good-mode feedback goes straight into LandingStore.feedback (accumulates; --revoke withdraws), F25 regression stamped 45/45 — good mode upgraded from "library ready" to "bridge-feedable"
- the root plugins/calldecacy transitional compatibility chain was removed after the gateway restart

| 2026-11-07 12:2x | **transcript echo fix (consumer side)**: the default recall surface no longer injects transcript re-delivery entries (M3 measured: queries hitting their own message-delivery entry score 1.00/0.73 = echo, polluting the hit-rate metric 3/3); bridge adds recall --include-transcripts as the explicit audit surface (the store-and-fetch contract migrated here, W2/W3 migration done); vendor landing.py synced | registry change log 2026-11-07 / CallDecay tests 8/8 |

## 2026-11-09 · v0.2.0: four-round mechanism chain complete + three-track readings on the board

- mechanism chain (selector anchors on new value words / visibility gate revival / cross-session verdict timing / compression-face value-word fidelity / two-layer signature matching) all closed; controlled bed S9 = D perfect score
- three-track product readings on the board (new dashboard section): local 0.092x (KV + verbatim lock) / cloud 94.2-98.5% (memory frame O(1), usage measured) / M3 40/71 (net-signal 57.1%)
- version 0.1.0 -> 0.2.0; listing copy synced to 0.2.0 (showcase fork retained; release push gated by the six gates — gate 3 patent gate: not-yet-filed mechanisms are uncertain = do not publish)
