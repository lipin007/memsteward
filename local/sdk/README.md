# MemSteward SDK

LLM memory middleware — quality control + semantic retrieval + liveness decay + timelines.

```bash
pip install memsteward
```

```python
from memsteward import Memory

mem = Memory(persist_path='memory.json')

# write memory (passes the quality gate automatically)
mem.deposit('player', 'mining', 'found diamond')
mem.deposit('player', 'building', 'made a house')

# retrieval
hits = mem.recall('mining', top_k=5)
for h in hits:
    print(h['obj'], h['act'], h['actual'])

# timeline
mem.recall_recent(hours=24)
mem.timeline()

# liveness decay (memories age)
mem.decay(0.99)
```

## Why MemSteward

- **quality gate**: empty/junk content is rejected automatically
- **0.01ms writes**: 5000x faster than Mem0
- **liveness decay**: memories age automatically
- **pure local**: data never leaves the machine
- **native Chinese**: 2-gram tokenization + BM25

## API

```python
mem = Memory(persist_path=None)

mem.deposit(obj, act, actual='', kind='fact')  # write
mem.recall(query, top_k=5)                      # retrieve
mem.recall_by_time(start, end, top_k)           # time-range
mem.recall_recent(hours=24)                     # recent memories
mem.timeline(hours=24)                          # timeline
mem.decay(factor=0.99)                          # decay
mem.stats()                                     # stats
mem.clear()                                     # clear
```

## Version scheme (dual-track policy, decided 2026-11-19)

- **SDK (this package) = SemVer**: starts at `0.1.0`; **during 0.x the API may break at any time** (honest warning); `1.0` freezes the public API (`Memory` and friends), after which strict major/minor/patch semantics
- **product family (MemGate plugin and friends) = CalVer**: `2026.11.19` year-month-day, reporting the build date
- the two are not inconsistent, they are **two promise languages**: the SDK reports a compatibility promise, products report a build date. VERSIONS.json declares both tracks (`version`/`sdk`); the version-binding check (F21) watches for drift
