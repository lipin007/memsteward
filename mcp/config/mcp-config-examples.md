# 宿主接入配置片段（MCP stdio）

通用形状（Claude Desktop / Cursor / Cline / Windsurf / Zed 均适用，各家配置文件位置不同）：

    {
      "mcpServers": {
        "memgate": {
          "command": "python3",
          "args": ["/绝对路径/memgate-mcp/mcp_server.py"],
          "env": { "MEMGATE_HOME": "/绝对路径/记忆库目录" }
        }
      }
    }

npm 安装后也可用随包启动器（免手填路径）：

    {
      "mcpServers": {
        "memgate": {
          "command": "memgate-mcp",
          "env": { "MEMGATE_HOME": "/绝对路径/记忆库目录" }
        }
      }
    }

- Claude Desktop: claude_desktop_config.json（Help → Developer → Edit Config）
- Cursor: .cursor/mcp.json（项目级）或全局 MCP 设置
- Cline / Windsurf: 扩展设置里的 MCP Servers 面板
- 换机器/换宿主零改动：stdio 协议，只要 python3 >= 3.9（npm 启动器另需 node >= 16）

工具面：memgate_deposit（存）/ memgate_recall（取）/ memgate_stats（账）/ memgate_compact（压实）。
