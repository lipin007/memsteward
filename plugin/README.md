# memgate

OpenClaw 插件：三层记忆（热/温/冷）＋写入质量门＋衰减＋语义签名召回＋治理工具面。

## 安装

    openclaw plugins install ./memgate-2026.11.19.tgz

- 零依赖：无 pip install，无构建步骤
- 数据家：MEMSTEWARD_HOME（默认 ~/.memsteward/），记忆全落本地，无云同步
- 卸载：openclaw plugins remove memgate（数据保留）

## 接口面

- 记忆：memory 插槽（账本摘要）＋ contextEngine 插槽（三层记忆摄取/提交）
- 工具：preflight / ledger / constraints / depscan
- 三形态：CLI / --oneshot / --serve

## 兼容性

需 OpenClaw 2026.11 或更新。

## 源码与文档

大本营: https://github.com/lipin007/memsteward
产品说明见 plugin/说明书.md。
