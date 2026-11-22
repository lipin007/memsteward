#!/usr/bin/env python3
"""MemGate MCP Server (D-MCP版) — 治理中间件的 Model Context Protocol 面

零第三方依赖（手搓 JSON-RPC 2.0 stdio 传输），随包 kernel 在进程内直驱。
语义与 B-完整版 REST 面 / A-插件版 工具面同源：deposit / recall / stats / compact。

传输：stdin/stdout 换行分隔 JSON-RPC（MCP stdio 规范）。
协议：MCP 2025-06-18（initialize / notifications/initialized / tools/list / tools/call / ping）。

环境变量：
  MEMGATE_HOME  记忆库根目录（默认 ~/.memgate-mcp）

用法：python3 mcp_server.py   （由宿主（Claude Desktop/Cursor/Cline 等）拉起）
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "kernel"))

from memory_core import MemoryCore  # noqa: E402  随包 kernel

SERVER_NAME = "memgate-mcp"
SERVER_VERSION = "2026.11.21"
PROTOCOL_VERSION = "2025-06-18"

_core = None


def core():
    """MemoryCore 单例：记忆库落 MEMGATE_HOME/memory.json。"""
    global _core
    if _core is None:
        root = os.environ.get("MEMGATE_HOME", os.path.join(os.path.expanduser("~"), ".memgate-mcp"))
        os.makedirs(root, exist_ok=True)
        _core = MemoryCore(persist_path=os.path.join(root, "memory.json"))
    return _core


TOOLS = [
    {
        "name": "memgate_deposit",
        "description": "存一条治理记忆（谁-做了什么-实际内容）。入质量门与统计账。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "obj": {"type": "string", "description": "对象（谁/什么）"},
                "act": {"type": "string", "description": "动作（做了什么）"},
                "actual": {"type": "string", "description": "实际内容（细情）"},
                "kind": {"type": "string", "description": "类别: fact/decision/lesson/todo 等", "default": "fact"},
                "source": {"type": "string", "description": "来源标注", "default": "mcp"},
            },
            "required": ["obj", "act"],
        },
    },
    {
        "name": "memgate_recall",
        "description": "按签名/查询召回记忆（带分数排序）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "查询签名/关键词"},
                "top_k": {"type": "integer", "description": "返回条数", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "memgate_stats",
        "description": "记忆库统计（条数/类别分布/体量）。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "memgate_compact",
        "description": "压实记忆库（清冗余/重整存储）。",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def call_tool(name, args):
    c = core()
    if name == "memgate_deposit":
        return c.deposit(
            obj=args["obj"],
            act=args["act"],
            actual=args.get("actual", ""),
            kind=args.get("kind", "fact"),
            source=args.get("source", "mcp"),
        )
    if name == "memgate_recall":
        return c.recall(query=args["query"], top_k=int(args.get("top_k", 5)))
    if name == "memgate_stats":
        return c.stats()
    if name == "memgate_compact":
        return c.compact()
    raise ValueError("unknown tool: " + name)


def text_content(payload):
    try:
        text = json.dumps(payload, ensure_ascii=False)
    except TypeError:
        text = json.dumps(payload, ensure_ascii=False, default=str)
    return {"content": [{"type": "text", "text": text}], "isError": False}


def handle(req):
    """返回响应 dict；通知（无 id）返回 None。"""
    method = req.get("method", "")
    rid = req.get("id")
    params = req.get("params") or {}

    if rid is None and method.startswith("notifications/"):
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments") or {}
        try:
            return {"jsonrpc": "2.0", "id": rid, "result": text_content(call_tool(name, args))}
        except Exception as e:  # 工具级错误=结果携带 isError（MCP 规范）
            return {
                "jsonrpc": "2.0",
                "id": rid,
                "result": {"content": [{"type": "text", "text": "ERROR: " + str(e)}], "isError": True},
            }
    return {
        "jsonrpc": "2.0",
        "id": rid,
        "error": {"code": -32601, "message": "method not found: " + method},
    }


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
