# MemSteward — LLM 记忆中间件家族

让任何 LLM agent 记得住、管得住: 三层记忆 (热/温/冷) + 写入质量门 + 衰减 + 语义签名召回 + 治理工具面。

三个版本, 一份 kernel (13 件核心同源), 按场景分形态:

| 版本 | 目录 | 场景 | 模型连接 |
|---|---|---|---|
| **MemGate** (插件版) | plugin/ | OpenClaw 插件商店/平台 | 云 API / 本地皆可 (LLM_ARM 预设) |
| 完整版 | complete/ | 服务端/集成部署 | 云 API 连接模式 (预设) |
| 本地版 | local/ | 专用本地情景 (游戏/行业) | 本地模型 (离线) |

## 快速入口

- 插件安装: openclaw plugins install memgate (或见 plugin/README.md)
- 数据家: MEMSTEWARD_HOME (默认 ~/.memsteward/), 记忆全落本地, 无云同步
- 各版 README 带 10 分钟买家快速开始

## 版本

三版本共享同一 kernel 与同一版本号 (语义化版本); 全家发版一起升, 见 CHANGELOG.md。
后续平台版本 (其他 agent 平台) 同仓扩展, 共享 kernel 与版本号。

## 许可

全件统一 AI Research Source License v1.3 (2026-11-20): 非商用免费 (研究/教学/评估),
商用与商业托管服务须书面授权, 专利一律保留, 商标不随代码授权。全文见 LICENSE。

## 文档

- plugin/说明书.md — 产品说明 (承诺清单+验证口径)
- plugin/历史脉络.md — 版本演进
- local/CAPABILITY_INDEX.md — 能力索引
