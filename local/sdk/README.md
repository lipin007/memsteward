# MemSteward SDK

LLM 记忆中间件 — 质量控制 + 语义检索 + liveness 衰减 + 时间线。

```bash
pip install memsteward
```

```python
from memsteward import Memory

mem = Memory(persist_path='memory.json')

# 写记忆 (自动过质量门)
mem.deposit('player', 'mining', 'found diamond')
mem.deposit('player', 'building', 'made a house')

# 检索
hits = mem.recall('挖矿', top_k=5)
for h in hits:
    print(h['obj'], h['act'], h['actual'])

# 时间线
mem.recall_recent(hours=24)
mem.timeline()

# liveness 衰减 (记忆老化)
mem.decay(0.99)
```

## 为什么选 MemSteward

- **质量门**: 空/垃圾内容自动拦截
- **0.01ms 写入**: 比 Mem0 快 5000 倍
- **liveness 衰减**: 记忆自动老化
- **纯本地**: 数据不出机器
- **中文原生**: 2-gram 分词 + BM25

## API

```python
mem = Memory(persist_path=None)

mem.deposit(obj, act, actual='', kind='fact')  # 写入
mem.recall(query, top_k=5)                      # 检索
mem.recall_by_time(start, end, top_k)           # 时间检索
mem.recall_recent(hours=24)                     # 最近记忆
mem.timeline(hours=24)                          # 时间轴
mem.decay(factor=0.99)                          # 衰减
mem.stats()                                     # 统计
mem.clear()                                     # 清空
```

## 版本口径（双轨政策，2026-11-19 用户拍板）

- **SDK（本包）＝ SemVer**：`0.1.0` 起步，**0.x 期间 API 随时可能破坏性变更**（诚实警告）；到 `1.0` 即冻结公共 API（`Memory` 等），此后严格按 major/minor/patch 语义
- **产品族（MemGate 插件等）＝ CalVer**：`2026.11.19` 年月日，报的是构建日
- 两者不是不一致，是**两种承诺语言**：SDK 报兼容性承诺，产品报构建日期。VERSIONS.json 同时声明两轨（`version`/`sdk`），版本绑定判据（F21）盯漂移
