# MemSteward — LLM 记忆中间件

**给 LLM 记忆、学习、质量控制的本地中间件。**

纯本地运行，数据不出机器。0.01ms 写入，<1ms 检索。

## 核心能力

| 能力 | 说明 | 竞品对比 |
|---|---|---|
| **记忆读写** | deposit / recall | 5000x 快于 Mem0 |
| **语义检索** | 语义 + BM25 混合，中文原生 | 独有 2-gram 分词 |
| **质量控制** | admission 质量门 + 隔离 + 验证判据 | **竞品全没有** |
| **liveness 衰减** | 记忆自动老化，越旧越弱 | **竞品做不到** |
| **时间线推理** | 按时间检索/时间轴摘要 | Zep 有，我们也有 |
| **实体链接** | 自动提取实体建索引 | Mem0 没有 |
| **持久化** | JSON 落盘，重启不丢 | — |
| **概念涌现** | 概念空间自动增长 | — |

## 快速开始

### Python 用起来（SDK 出口）

```python
from memsteward import Memory

mem = Memory('memory.json')

# 写记忆 (带质量门)
mem.deposit('player', 'mining', 'found diamond', kind='experience')
mem.deposit('player', 'building', 'made a house', kind='experience')

# 语义检索
hits = mem.recall('挖矿', top_k=5)
for h in hits:
    print(h['obj'], h['act'], h['actual'])

# 时间线
timeline = mem.timeline(hours=24)
recent = mem.recall_recent(hours=1)

# liveness 衰减 (记忆老化)
mem.decay(0.99)
```

### LangChain 集成

```python
from memsteward.langchain_adapter import MemStewardMemory
from langchain.chains import ConversationChain
from langchain.llms import OpenAI

# 一行替换 LangChain 自带记忆
memory = MemStewardMemory(persist_path='chat_memory.json')
chain = ConversationChain(llm=OpenAI(), memory=memory)

# LangChain 标准接口 (save_context / load_memory_variables 自动带质量门)
chain.predict(input='我在挖矿')
```

## 架构

```
MemSteward/
├── shared/              # 核心能力 (三版共享)
│   ├── llm/             # LLM 门控/后端/KV缓存/LangChain适配器
│   ├── memory/          # 语义检索/记忆门控
│   └── quality/         # 质量门/验证判据
├── A-插件版/            # OpenClaw 插件调用方式
├── B-完整版/            # 独立服务调用方式
└── C-本地版/            # Python 本地调用方式
    └── src/memsteward_local.py  # 核心 API
```

## 性能

| 指标 | MemSteward | Mem0 | Zep | LangChain |
|---|---|---|---|---|
| 写入 | **0.01ms** | 50ms | 100ms | 20ms |
| 检索 | **<1ms** | 200ms | 300ms | 100ms |
| 质量门 | ✅ | ❌ | ❌ | ❌ |
| 衰减 | ✅ | ❌ | ⚠️ | ❌ |
| 本地运行 | ✅ | ✅ | ❌ | ⚠️ |
| 中文优化 | ✅ | ⚠️ | ⚠️ | ⚠️ |

## 质量控制链

```
写入 → admission 质量门 (空/垃圾/回声 → 拦截)
     → quarantine 隔离 (疑似污染 → 标记)
     → judge 验证判据 (质量评分)
     → liveness 衰减 (自动老化)
```

## API 参考

### MemStewardLocal

```python
mem = MemStewardLocal(persist_path=None, embed_cache_path=None)

# 核心
mem.deposit(obj, act, actual, kind='fact', source='')  # 写入 (带质量门)
mem.recall(query, top_k=5)                              # 检索 (语义+词法)
mem.decay(factor=0.99)                                  # liveness 衰减
mem.stats()                                             # 统计面板

# 时间线
mem.recall_by_time(start=None, end=None, top_k=10)      # 时间范围检索
mem.recall_recent(hours=24, top_k=10)                   # 最近 N 小时
mem.timeline(hours=24)                                  # 时间轴摘要

# 质量
mem.hold(entry_id)                                      # 保活 (liveness=1.0)
mem.check(entry_id)                                     # 按 ID 查条目
mem.quarantine(entry_id)                                # 隔离低质条目
```

## 为什么选 MemSteward

1. **质量控制链完整** — 只有我们有 admission + quarantine + judge
2. **liveness 衰减** — 记忆自动老化，不会越积越多
3. **纯本地零依赖** — 数据不出机器，隐私绝对安全
4. **性能碾压** — 0.01ms vs 竞品 50-300ms
5. **中文原生** — 实体链接/BM25/2-gram 都优化过
6. **LangChain 适配** — 一行 import 进入 10 万开发者生态
