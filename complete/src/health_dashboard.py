#!/usr/bin/env python3
"""MemGate 健康观测台 · 全中间件实时健康面（自包含 HTML）

用法: python3 health_dashboard.py          # 生成 HTML 并起服务
      python3 health_dashboard.py --gen   # 只生成 HTML
      python3 health_dashboard.py --watch  # 持续刷新模式（30s 轮询）
输出: MemGate/health.html（自包含单文件，浏览器直开）
      绑定 127.0.0.1:8901（GET /health）
"""
import json, os, sys, time, subprocess, socket
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

WORKSPACE = os.path.abspath(os.path.join(HERE, "../..", ".."))

try:
    from health_probe import probe_port, probe_http, shell, collect, render_html, HERE, PROD
except ImportError:
    print("warn: health_probe 缺席, 降级(fail-soft)", file=_s.stderr)
    HERE = os.path.dirname(os.path.abspath(__file__))
    PROD = os.path.abspath(os.path.join(HERE, "..", "记忆体"))
    def probe_port(*a, **k): return None
    def probe_http(*a, **k): return None
    def shell(*a, **k): return ""
    def collect(*a, **k): return {}
    def render_html(*a, **k): return "<p>health_probe 缺席</p>"

class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        st = collect()
        body = render_html(st).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a): pass


if __name__ == "__main__":
    if "--gen" in sys.argv:
        st = collect()
        open(os.path.join(HERE, "health.html"), "w").write(render_html(st))
        print(f"health.html generated: {st['summary']}")
    elif "--watch" in sys.argv:
        while True:
            st = collect()
            open(os.path.join(HERE, "health.html"), "w").write(render_html(st))
            print(f"[{st['ts']}] {st['summary']}")
            time.sleep(30)
    else:
        port = int(os.environ.get("PORT", 8901))
        srv = HTTPServer(("127.0.0.1", port), _Handler)
        print(f"MemGate 健康观测台: http://127.0.0.1:{port}")
        srv.serve_forever()
