# -*- coding: utf-8 -*-
"""内置 mock LLM（llama.cpp / OpenAI 兼容）——离线演示与测试用。

GET  任意路径              → {"status":"ok"}（模拟 llama.cpp /health）
POST /v1/chat/completions  → 从 prompt 的 "Available actions:" 取第一个动作回显
POST /completion           → 同上（llama.cpp 原始续写格式）
"""

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_ACT_RE = re.compile(r"Available actions:\s*([^\n]+)")


def _pick_action(text):
    m = _ACT_RE.search(text or "")
    return m.group(1).split(",")[0].strip() if m else "观望"


class _MockHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send({"status": "ok", "ok": True})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            body = json.loads(raw or b"{}")
        except Exception:
            body = {}
        text = ""
        if isinstance(body, dict):
            msgs = body.get("messages") or []
            if msgs:
                text = str(msgs[-1].get("content", ""))
            text = text or str(body.get("prompt", ""))
        act = _pick_action(text)
        if self.path.endswith("/chat/completions"):
            self._send({
                "id": "chatcmpl-mock", "object": "chat.completion",
                "choices": [{"index": 0,
                             "message": {"role": "assistant", "content": act},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 42, "completion_tokens": 2,
                          "total_tokens": 44}})
        else:
            self._send({"content": act,
                        "timings": {"prompt_n": 42, "predicted_n": 2}})


def start_mock_server(host="127.0.0.1", port=0):
    """启动 mock（守护线程），返回 (host, port, server)。"""
    srv = ThreadingHTTPServer((host, port), _MockHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_address[0], srv.server_address[1], srv
