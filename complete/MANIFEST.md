# MANIFEST — B-完整版 物料清单（2026-11-19 组合审查修正）

> 版本: v2026.11.19

## 组合清单（实 import 证据）

| # | 件 | 用途 |
|---|---|---|
| 1/2/3/4/5 | tokenizer/quality_gate/distiller/hebbian_link/tiered_decay | bridge_cli kernel 链 |
| 6 | memory_core | cloud_api 多租户记忆核心 |
| 7/8 | landing_store/summarizer | 落盘/摘要 |
| 13-18 | 渲染/遥测/depscan/入册门/版本绑定/健康面 | kernel 装配（P1 单源化 2026-11-19，内联段已回流正源） |
| 26 | daemon | **可选服务形态**（组件 #26：web UI+落地引擎；装进 B=B 起服务，不装=B 纯库栈；正源=实验/记忆体/daemon/） |
| 20 | calldecacy-sdk | 记忆引擎整包 |
| 21 | admission | 写入准入 |
| 22 | semantic_recall | 语义臂 |

> 组合审查修正：补 #2/#10/#21/#22（原漏报）。

## 产品本体

bridge_cli.py（与 A 同文）/ admission / dashboard_serve / health_dashboard / cloud_api（多租户）

## 注意
daemon 本体＝ai-research/实验/记忆体/daemon/serve.py（归属待拍板）；本地模型包裹＝llm-kit #24（llm_backends/langchain_adapter/llm_gate，2026-11-19 拍板「当然用」，待接线）

## 变更流
同 A

> **cloud_api 定位 (2026-11-20)**: src/cloud_api/ = 未来收费线 (云盘记忆存储), 当前预留种子件, 不上架不部署; 三版本功能差 = 模型连接模式, 非本模块。
