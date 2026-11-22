# MemSteward three-edition architecture (decided 2026-11-17 after ARC-AGI field testing)

> Origin: ARC-AGI-3 field testing that day showed the three scenario classes have completely different needs
> Version format: YYYY.MM.DD, three lines increment independently

---

## Edition comparison

| | A. Plugin | B. Complete | C. Local |
|---|---|---|---|
| **Shape** | OpenClaw plugin | daemon + Python library | pure in-process Python library |
| **Communication** | plugin API | HTTP (127.0.0.1:8877) | direct function calls |
| **Latency** | ~0ms | ~1ms/call | **~0ms** |
| **Deployment** | `plugins.load.paths` | systemd + pip | `import memsteward` |
| **Dependencies** | OpenClaw runtime | Python + HTTP service | **Python stdlib only** |
| **Multi-agent** | yes (shared OpenClaw session) | yes (HTTP concurrency) | no (single process) |
| **Cross-language** | no (TypeScript) | yes (HTTP) | no (Python) |
| **Fits** | OpenClaw users | servers / multi-agent | **embodied AI / autonomous driving / game dev** |
| **Examples** | OpenClaw agents | MemGate product | **robot controllers / game NPCs / driving decisions** |

---

## C. Local edition (fully single-scenario local)

### Positioning
**An experience plug-in for real-time, low-latency scenarios** — embodied AI, autonomous driving, game development.
Any millisecond decision loop where the agent must learn and remember on the fly but cannot afford network latency.

### Core scenarios
| Scenario | Latency budget | Why the local edition |
|---|---|---|
| **Embodied AI** (robot control) | <1ms | sense -> decide -> act, every step needs memory |
| **Autonomous driving** | <5ms | learn live road conditions, no time for the network |
| **Game dev** (NPC / player behavior) | <2ms | per-frame decisions, NPCs learn across matches |
| Competitions / research | relaxed | no external service dependencies |

### Included
- `memsteward_local.py` — in-process memory (zero HTTP)
- `mechanism_learner.py` — hypothesis lifecycle (form -> confirm -> overturn)
- `mechanism_advisor.py` — failure recognition + goal guidance
- `observed_env.py` — zero-intrusion observation wrapper

### Not included
- memt-daemon (no service needed)
- model_router (single scenario needs no routing)
- HTTP layer (no network calls)
- OpenClaw plugin interface

### Usage
```python
from memsteward_local import MemSteward
from observed_env import make_observed_env

ms = MemSteward()  # in-process, zero latency
env = make_observed_env(env, mem=ag.mem, memsteward=ms)
# run the episode; whatever is learned persists into ms
# next run, the knowledge in ms is still there
```

### Acceptance criteria
1. same agent with/without memsteward -> C(k) / decision-quality comparison
2. memory persists across matches -> cross-match / cross-task learning
3. hypothesis confirm/overturn -> no repeated mistakes
4. **latency < 1ms per call** (in-process function call)

---

## Edition relationships

```
C. Local edition (core engine)
  ├── packaged as B. Complete edition (+ daemon + HTTP)
  └── packaged as A. Plugin edition (+ OpenClaw interface)
```

**The local edition is the core engine** — the complete and plugin editions are wrappers around it. The ARC-AGI test used an early form of the local edition.

---

## Change history

| Date | A. Plugin | B. Complete | C. Local | Key change |
|---|---|---|---|---|
| 2026-11-17 | 2026.11.17 | 2026.11.17 | 2026.11.17 | three-edition architecture decided; ARC-AGI field tests |
