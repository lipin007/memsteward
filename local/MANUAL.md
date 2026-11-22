# MemSteward Local Edition (C) · Manual

> **In one line**: a pure-local LLM memory middleware SDK — data never leaves the machine, three lines of pip to start.

## Buyer quick start (10 minutes)

### ① Install (1 minute)

```bash
pip install ./sdk
```

### ② Three lines to use (2 minutes)

```python
from memsteward import Memory

mem = Memory('memory.json')
mem.deposit('player', 'mining', 'found diamond', kind='experience')
print(mem.recall('diamond'))
```

`deposit` passes the quality gate (echo fragments / ultra-short entries quarantined automatically); `recall` carries a liveness gate.

### ③ Timeline retrieval (1 minute)

```python
print(mem.recall_recent(hours=24))   # last 24 hours
print(mem.recall_by_time(top_k=10))  # in time order
```

## API surface

| Method | Purpose |
|---|---|
| `Memory(path)` | open/create a local memory store (JSON on disk, survives restart) |
| `deposit(obj, act, actual, kind, source)` | write one memory (object/action/outcome) |
| `recall(query, top_k=5)` | semantic retrieval (hybrid, native Chinese support) |
| `recall_recent(hours, top_k)` | last N hours |
| `recall_by_time(start, end, top_k)` | time-range retrieval |

For the fuller capability surface (quarantine / distillation / concept space and more), use the source-level `MemStewardLocal` in `src/memsteward_local.py` (advanced; see the comments there).

## Data and home

By default data lands in a JSON file in the current working directory (`Memory('memory.json')` gives the path explicitly); service-grade deployment (Edition B) is where the `~/.memsteward` home directory comes in.

## Version scheme (dual track)

**SDK = SemVer**: from `0.1.0`, the API may break at any time during 0.x; `1.0` freezes the public API. Product family = CalVer. See sdk/README.md.
