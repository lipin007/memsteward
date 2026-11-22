# D-MCP版 · 文件清单（2026.11.21）

- **mcp_server.py** — MCP stdio 服务器（零第三方依赖）｜生产单源
- **bin/memgate-mcp.js** — npm 启动器（spawn python3 mcp_server.py，stdio 直通）
- **kernel/** — 随包 kernel（vendor）｜可再生
- **test/test_mcp.py** — 冒烟：握手+四工具+错法码 ｜验证件
- **config/mcp-config-examples.md** — 各宿主接入配置片段 ｜交付文档
- **README.md / 说明书.md / 历史脉络.md** — 上架说明 / 产品说明书 / 脉络 ｜交付文档
- **package.json** — npm 包描述（memgate-mcp，bin=memgate-mcp）
- **VERSIONS.json** — 版本绑定（产品/协议/工具面/零依赖声明）｜绑定源
- **LICENSE** — Elastic License 2.0（SPDX: Elastic-2.0）

语义同源：A-插件版工具面 ≡ B-完整版 REST 面 ≡ D-MCP工具面（deposit/recall/stats/compact）。
