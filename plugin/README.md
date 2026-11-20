# memgate

OpenClaw 治理插件（v0.1.0）：三层记忆（热/温/冷）＋治理工具面。业务逻辑单一来源在
Python 单源（随包进 `src/vendor/`），TS 层只做调用面。

## 装法

| 形态 | 命令 | 适用 |
|---|---|---|
| ClawHub 商店 | `openclaw plugins install memgate` | 公开直装（推荐） |
| 本地制品 | `openclaw plugins install ./memgate-2026.11.19.tgz` | 同机/离线分发 |
| workspace 链装 | `plugins.load.paths` 指本目录 | 开发态 |

## 接口面

- 记忆：memory 插槽（账本摘要）＋ contextEngine 插槽（三层记忆摄取/提交）
- 工具：preflight / ledger / constraints / depscan（调用面）
- 三形态：CLI / `--oneshot` / `--serve`，同一 `run()` 派发，行为唯一

## 配置

- 数据家：`MEMSTEWARD_HOME`（默认 `~/.memsteward/`），记忆全落本地，无云同步
- LLM 连接预设：`config/llm_connection.env.example` 复制改名 `.env`（云 API 或本地 localhost）
- 插槽：安装后 `openclaw.json` 自动接 slots（memory/contextEngine=memgate）

## 版本绑定

`VERSIONS.json` 绑定 plugin/sdk/桥协议/嵌入模型指纹/配置槽位；核对
`python3 src/bridge_cli.py version`（bound/mismatches）。

## 安装（2 分钟，零折腾）

    openclaw plugins install memgate

- 买家零构建：随包带编译产物与 vendor，无 pip install、无编译步骤
- 卸载：`openclaw plugins remove memgate`（数据保留）／手动删 `MEMSTEWARD_HOME`（数据删除）

## 兼容性

- OpenClaw pluginApi ≥ 2026.9.4；桥协议 BRIDGE_PROTOCOL=3（见 `VERSIONS.json`）
- 本插件工具不需要模型路由（deposit/recall/ledger 全离线），与模型预检解耦
- 旧版 OpenClaw（2026.11 之前）若报 "could not verify a usable inference route"
  （旧版 SecretRef 密钥解析缺陷，2026.11.3 已修）：升级 OpenClaw 即可

## 安全模型

- 数据全落本地：记忆/账本/备份都在 `MEMSTEWARD_HOME`，无云同步、无遥测回传
- 写入有门：所有写入过质量门（写入分级/守望查表/登记门），单写者协议防并发污染
- 契约先行：越界写入停收待复核，标记需登记确认——宁可少记，不记错的

---

大本营（源码/文档/issue）：https://github.com/lipin007/memsteward
