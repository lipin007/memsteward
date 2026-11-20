# MANIFEST — C-完全的本地版 物料清单（2026-11-19 组合审查修正）

> 版本: v2026.11.19

## 组合清单（实 import 证据）

| # | 件 | 用途 |
|---|---|---|
| 1/2/3/5 | tokenizer/quality_gate/distiller/tiered_decay | 记忆链 |
| 7/8 | landing_store/summarizer | 落盘/摘要（kernel calldecacy） |
| 10/11 | mechanism_learn/planner | 假设生命周期+规划（C 树平铺影子） |
| 12 | m3 | m3_judge（kernel） |
| 20 | calldecacy-sdk | 记忆引擎整包 |
| 21/22 | admission/semantic_recall | 准入+语义臂 |
| 23 | core-kit | hebbian/events/concept_space（真源 core.hebbian 非 hebbian_link） |

> 组合审查修正：移除 #4 hebbian_link（C 用 core.hebbian 非此件）与 #6 memory_core（C 实不 import），原报虚。

## 产品本体

memsteward_local.py / observed_env.py / sdk/memsteward（pip）

## 变更流
同 A
