# MemSteward Capability Index

> **The single authoritative entry point.** For any capability, look here first; if it is not here, it is not built and does not exist.
> Update rule: new capabilities must be registered; gaps get filled immediately.

## 1. LLM wrapping layer

| Capability | File | import path | Purpose |
|---|---|---|---|
| **LLMGate** (model wrapping) | `MemGate/src/vendor/pvs-sdk/pvs/core/llm_gate.py` | `from pvs.core.llm_gate import LLMGate` | intercept / dispatch / circuit-break LLM calls |
| **LlamaCppBackend** (local inference) | `MemGate/src/vendor/pvs-sdk/pvs/adapters/llm_backends.py` | `from pvs.adapters.llm_backends import LlamaCppBackend` | connect llama.cpp server |
| **llm_arm.py** (llama.cpp integration) | `MemGate/src/vendor/core/llm_arm.py` | `from core.llm_arm import ...` | token metering / health checks / calls |
| **MockLLM** (offline testing) | `MemGate/src/vendor/calldecay-sdk/calldecay/mock.py` | `from calldecay.mock import ...` | model-free testing |

## 2. Memory layer

| Capability | File | import path | Purpose |
|---|---|---|---|
| **hybrid_recall** (semantic + lexical) | `MemGate/src/semantic_recall.py` | `from semantic_recall import hybrid_recall` | hybrid retrieval |
| **EmbedCache** (embedding cache) | `MemGate/src/semantic_recall.py` | `from semantic_recall import EmbedCache` | KV cache reuse |
| **semantic_topk** (semantic retrieval) | `MemGate/src/semantic_recall.py` | `from semantic_recall import semantic_topk` | vector similarity |
| **GateMemory** | `MemGate/src/vendor/pvs-sdk/pvs/core/memory.py` | `from pvs.core.memory import GateMemory` | gated memory |
| **RecallGate** (recall gating) | `MemGate/src/vendor/calldecay-sdk/calldecay/gate.py` | `from calldecay.gate import RecallGate` | recall quality control |

## 3. Quality control

| Capability | File | import path | Purpose |
|---|---|---|---|
| **classify_entry** (quality grading) | `MemGate/src/admission.py` | `from admission import classify_entry` | admission quality gate |
| **quarantine** | `MemGate/src/admission.py` | `from admission import mark_quarantine` | quarantine low-quality content |
| **m3_judge.classify** (verdict criteria) | `MemGate/src/m3_judge.py` | `from m3_judge import classify` | outcome verification |
| **self_cert** (self-attestation) | `MemGate/src/m3_judge.py` | `from m3_judge import self_cert` | self certification |

## 4. Compute scheduling

| Capability | File | import path | Purpose |
|---|---|---|---|
| **estimateTokensForContent** | `MemGate/src/context-engine.ts` | TS only | token estimation |
| **compute_guard** (circuit breaker) | to be confirmed | — | LLM timeout / over-budget circuit breaker |
| **retry_budget** (backoff) | to be confirmed | — | exponential backoff retry |

## 5. Application layer (built 2026-11-17)

| Capability | File | import path | Purpose |
|---|---|---|---|
| **MemStewardLocal** (local wrapper) | `MemSteward/local/src/memsteward_local.py` | `from memsteward_local import MemStewardLocal` | wraps everything above |
| **MechanismLearner** (hypothesis lifecycle) | `MemSteward/local/src/mechanism_learner.py` | `from mechanism_learner import MechanismLearner` | form -> confirm -> overturn |
| **MechanismAdvisor** (failure recognition) | `MemSteward/local/src/mechanism_advisor.py` | `from mechanism_advisor import MechanismAdvisor` | avoid pitfalls + guidance |
| **ObservedEnv** (observation wrapper) | `MemSteward/local/src/observed_env.py` | `from observed_env import ObservedEnv` | zero-intrusion observation |
| **PanoramicPlanner** (panoramic planning) | `MemSteward/local/src/panoramic_planner.py` | `from panoramic_planner import PanoramicPlanner` | goals + action sequences |
| **RollingPlanner** (rolling replan) | `MemSteward/local/src/rolling_planner.py` | `from rolling_planner import RollingPlanner` | re-order as knowledge grows |
| **KnowledgeDistiller** (knowledge distillation) | `MemSteward/local/src/knowledge_distiller.py` | `from knowledge_distiller import KnowledgeDistiller` | raw -> structured knowledge |

## Quick index

- **Need model wrapping?** -> LLMGate + LlamaCppBackend
- **Need memory retrieval?** -> hybrid_recall + EmbedCache
- **Need quality control?** -> admission + m3_judge
- **Need planning?** -> PanoramicPlanner + RollingPlanner
- **Need observation?** -> ObservedEnv + MechanismLearner
- **Need knowledge extraction?** -> KnowledgeDistiller

---
*Created 2026-11-17 | Rule: new capabilities must be registered; gaps get filled immediately*
