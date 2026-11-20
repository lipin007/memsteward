#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MemGate 生产仪表盘 · 只读 HTTP 服务（每次请求现算快照，零写盘）.

用法: PORT=8899 python3 dashboard_serve.py
范围: GET / 与 /index.html → 现算自包含 HTML；其余路径 404。
绑定 127.0.0.1（对外走 OpenClaw portal 代理）；单请求异常不杀服务。
"""
from __future__ import annotations

import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))  # L09: __file__ 锚定
sys.path.insert(0, os.path.join(HERE, "src"))

import bridge_cli as B  # noqa: E402


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path not in ("/", "/index.html"):
            self.send_response(404)
            self.end_headers()
            return
        try:
            st = B._store(None)  # 生产账只读（本路径零 save/零入账）
            body = B._dashboard_html(B._dashboard(st, None)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:  # noqa: BLE001 —— 单请求失败不杀服务
            msg = f"dashboard error: {type(e).__name__}: {e}".encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    def log_message(self, *args):
        pass  # 静默访问日志


if __name__ == "__main__":
    B._bootstrap(B._ws(None))
    port = int(os.environ.get("PORT", "8899"))
    HTTPServer(("127.0.0.1", port), _Handler).serve_forever()
