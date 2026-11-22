#!/usr/bin/env python3
"""D-MCP版冒烟：JSON-RPC 握手 + 工具面全链（deposit/recall/stats）。"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env = dict(os.environ, MEMGATE_HOME=tempfile.mkdtemp(prefix="memgate_mcp_test_"))
p = subprocess.Popen(
    [sys.executable, os.path.join(HERE, "mcp_server.py")],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env, text=True,
)

def rpc(method, params=None, rid=1):
    msg = {"jsonrpc": "2.0", "id": rid, "method": method}
    if params is not None:
        msg["params"] = params
    p.stdin.write(json.dumps(msg) + "\n")
    p.stdin.flush()
    return json.loads(p.stdout.readline())

r = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "smoke", "version": "0"}})
assert r["result"]["serverInfo"]["name"] == "memgate-mcp", r
print("PASS initialize:", r["result"]["serverInfo"])

p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
p.stdin.flush()

r = rpc("tools/list", {}, rid=2)
names = [t["name"] for t in r["result"]["tools"]]
assert names == ["memgate_deposit", "memgate_recall", "memgate_stats", "memgate_compact"], names
print("PASS tools/list:", names)

r = rpc("tools/call", {"name": "memgate_deposit", "arguments": {"obj": "smoke", "act": "test", "actual": "MCP roundtrip"}}, rid=3)
assert r["result"]["isError"] is False, r
print("PASS deposit:", r["result"]["content"][0]["text"][:100])

r = rpc("tools/call", {"name": "memgate_recall", "arguments": {"query": "smoke", "top_k": 3}}, rid=4)
assert r["result"]["isError"] is False, r
print("PASS recall:", r["result"]["content"][0]["text"][:100])

r = rpc("tools/call", {"name": "memgate_stats", "arguments": {}}, rid=5)
assert r["result"]["isError"] is False, r
print("PASS stats:", r["result"]["content"][0]["text"][:100])

r = rpc("bogus/method", {}, rid=6)
assert r["error"]["code"] == -32601, r
print("PASS 未知方法=-32601")

p.stdin.close()
p.wait(timeout=10)
print("SMOKE ALL GREEN")
