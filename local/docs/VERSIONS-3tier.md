# MemSteward 三版架构（2026-11-17 ARC-AGI 实测后拍板）

> 来源：今天 ARC-AGI-3 实测发现三种场景需求完全不同
> 版本号格式：YYYY.MM.DD，三线独立递增

---

## 版本对照表

| | A. 插件版 | B. 完整版 | C. 本地版 |
|---|---|---|---|
| **形态** | OpenClaw 插件 | daemon + Python 库 | 纯进程内 Python 库 |
| **通信** | 插件 API | HTTP (127.0.0.1:8877) | 直接函数调用 |
| **延迟** | ~0ms | ~1ms/调用 | **~0ms** |
| **部署** | `plugins.load.paths` | systemd + pip | `import memsteward` |
| **依赖** | OpenClaw 运行时 | Python + HTTP 服务 | **仅 Python 标准库** |
| **多 agent** | ✅（共享 OpenClaw 会话） | ✅（HTTP 并发） | ❌（单进程） |
| **跨语言** | ❌（TypeScript） | ✅（HTTP） | ❌（Python） |
| **适用场景** | OpenClaw 用户 | 服务端 / 多 agent | **具身智能 / 自动驾驶 / 游戏开发** |
| **代表案例** | OpenClaw 代理 | MemGate 产品 | **机器人控制器 / 游戏 NPC / 自动驾驶决策** |

---

## C. 本地版（完全单场景本地版）

### 定位
**实时低延迟场景的经验外挂**——具身智能、自动驾驶、游戏开发。
任何毫秒级决策链路，agent 需要在运行中学习并记住经验，但不能承受网络延迟。

### 核心场景
| 场景 | 延迟要求 | 为什么需要本地版 |
|---|---|---|
| **具身智能**（机器人控制） | <1ms | 传感器→决策→执行，每步都要记忆 |
| **自动驾驶** | <5ms | 实时路况学习，不能等网络 |
| **游戏开发**（NPC/玩家行为） | <2ms | 每帧决策，NPC 需要跨局学习 |
| 竞赛/研究 | 宽松 | 无外部服务依赖 |

### 包含
- `memsteward_local.py` — 进程内三入层记忆（零 HTTP）
- `mechanism_learner.py` — 假设生命周期（形成→确认→推翻）
- `mechanism_advisor.py` — 失败识别 + 目标引导
- `observed_env.py` — 零侵入观察包装器

### 不包含
- memt-daemon（不需要服务）
- model_router（单场景不需要路由）
- HTTP 通信层（无网络调用）
- OpenClaw 插件接口

### 用法
```python
from memsteward_local import MemSteward
from observed_env import make_observed_env

ms = MemSteward()  # 进程内，零延迟
env = make_observed_env(env, mem=ag.mem, memsteward=ms)
# 跑 episode，学到的东西自动存进 ms
# 下次跑，ms 里的知识还在
```

### 验收标准
1. 同一 agent 带/不带 memsteward → C(k) / 决策质量对比
2. 多局间记忆持久化 → 跨局/跨任务学习
3. 假设确认/推翻 → 不重复犯错
4. **延迟 < 1ms / 次调用**（进程内函数调用）

---

## 版本关系

```
C. 本地版（核心引擎）
  ├── 打包成 B. 完整版（+ daemon + HTTP）
  └── 打包成 A. 插件版（+ OpenClaw 接口）
```

**本地版是核心引擎**——完整版和插件版都是它的包装。今天 ARC-AGI 测试用的就是本地版的雏形。

---

## 变更历史

| 日期 | A.插件版 | B.完整版 | C.本地版 | 关键变更 |
|---|---|---|---|---|
| 2026-11-17 | 2026.11.17 | 2026.11.17 | 2026.11.17 | 三版架构拍板；ARC-AGI 实测 |
