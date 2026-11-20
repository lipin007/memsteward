# MemSteward 能力总表（Capability Index）

> **唯一权威入口**。任何能力先查这里，不找→不建→不编。
> 更新规则：新增能力必须登记；发现遗漏立即补。

## 一、模型包裹层（LLM Wrapping）

| 能力 | 文件 | import 路径 | 用途 |
|---|---|---|---|
| **LLMGate**（模型包裹） | `MemGate/src/vendor/pvs-sdk/pvs/core/llm_gate.py` | `from pvs.core.llm_gate import LLMGate` | 拦截/调度/熔断 LLM 调用 |
| **LlamaCppBackend**（本地推理） | `MemGate/src/vendor/pvs-sdk/pvs/adapters/llm_backends.py` | `from pvs.adapters.llm_backends import LlamaCppBackend` | 接 llama.cpp server |
| **llm_arm.py**（llama.cpp 集成） | `MemGate/src/vendor/core/llm_arm.py` | `from core.llm_arm import ...` | token 计量/健康检查/调用 |
| **MockLLM**（离线测试） | `MemGate/src/vendor/calldecay-sdk/calldecay/mock.py` | `from calldecay.mock import ...` | 无模型测试 |

## 二、记忆层（Memory）

| 能力 | 文件 | import 路径 | 用途 |
|---|---|---|---|
| **hybrid_recall**（语义+词法检索） | `MemGate/src/semantic_recall.py` | `from semantic_recall import hybrid_recall` | 混合检索 |
| **EmbedCache**（嵌入缓存） | `MemGate/src/semantic_recall.py` | `from semantic_recall import EmbedCache` | KV cache 复用 |
| **semantic_topk**（语义检索） | `MemGate/src/semantic_recall.py` | `from semantic_recall import semantic_topk` | 向量相似度 |
| **GateMemory** | `MemGate/src/vendor/pvs-sdk/pvs/core/memory.py` | `from pvs.core.memory import GateMemory` | 门控记忆 |
| **RecallGate**（召回门控） | `MemGate/src/vendor/calldecay-sdk/calldecay/gate.py` | `from calldecay.gate import RecallGate` | 召回质量控制 |

## 三、质量控制（Quality）

| 能力 | 文件 | import 路径 | 用途 |
|---|---|---|---|
| **classify_entry**（质量分类） | `MemGate/src/admission.py` | `from admission import classify_entry` | 入库质量门 |
| **quarantine**（隔离） | `MemGate/src/admission.py` | `from admission import mark_quarantine` | 低质量内容隔离 |
| **m3_judge.classify**（验证判据） | `MemGate/src/m3_judge.py` | `from m3_judge import classify` | 结果验证 |
| **self_cert**（自证） | `MemGate/src/m3_judge.py` | `from m3_judge import self_cert` | 自我认证 |

## 四、算力调度（Compute）

| 能力 | 文件 | import 路径 | 用途 |
|---|---|---|---|
| **estimateTokensForContent** | `MemGate/src/context-engine.ts` | TS only | Token 估算 |
| **compute_guard**（熔断） | 待确认位置 | — | LLM 超时/超额熔断 |
| **retry_budget**（退避） | 待确认位置 | — | 指数退避重试 |

## 五、应用层（Application，2026-11-17 建）

| 能力 | 文件 | import 路径 | 用途 |
|---|---|---|---|
| **MemStewardLocal**（本地封装） | `MemSteward/local/src/memsteward_local.py` | `from memsteward_local import MemStewardLocal` | wrap 以上全部 |
| **MechanismLearner**（假设生命周期） | `MemSteward/local/src/mechanism_learner.py` | `from mechanism_learner import MechanismLearner` | 形成→确认→推翻 |
| **MechanismAdvisor**（失败识别） | `MemSteward/local/src/mechanism_advisor.py` | `from mechanism_advisor import MechanismAdvisor` | 避坑+引导 |
| **ObservedEnv**（观察包装器） | `MemSteward/local/src/observed_env.py` | `from observed_env import ObservedEnv` | 零侵入观察 |
| **PanoramicPlanner**（全景计划） | `MemSteward/local/src/panoramic_planner.py` | `from panoramic_planner import PanoramicPlanner` | 目标+动作序列 |
| **RollingPlanner**（滚动 replan） | `MemSteward/local/src/rolling_planner.py` | `from rolling_planner import RollingPlanner` | 知识增长时重排 |
| **KnowledgeDistiller**（知识蒸馏） | `MemSteward/local/src/knowledge_distiller.py` | `from knowledge_distiller import KnowledgeDistiller` | 原始→结构化知识 |

## 快速索引

- **要模型包裹？** → LLMGate + LlamaCppBackend
- **要记忆检索？** → hybrid_recall + EmbedCache
- **要质量控制？** → admission + m3_judge
- **要规划？** → PanoramicPlanner + RollingPlanner
- **要观察？** → ObservedEnv + MechanismLearner
- **要知识提炼？** → KnowledgeDistiller

---
*建立：2026-11-17 | 规则：新建能力必须登记，发现缺失立即补*
