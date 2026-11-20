# -*- coding: utf-8 -*-
"""OpenAI 兼容代理 —— 改 base_url 即接。

- POST /v1/chat/completions       默认原样透传；请求体带 "_calldecay" 字段
                                  （或 x-calldecay-* 头）时进入决策模式
- POST /v1/calldecay/decide       原生决策 {"obj","goal","current","actions"}
- POST /v1/calldecay/learn        原生回灌 {"obj","act","actual","cur"}
- GET  /v1/calldecay/metrics      实测指标
- GET  /health

决策模式的响应为 OpenAI chat.completion 形状，content = 决策 JSON；
查表命中时 usage 全 0（未发生上游调用）。v1 不支持 stream:true。
"""

import http.client
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .adapter import CallDecay


class ProxyState:
    def __init__(self, upstream, model, upstreams=None):
        self.model = model
        self.cd = CallDecay()
        # 多上游（包裹本地模型模式，2026-11-06）：name -> URL，声明顺序即回落顺序。
        # 未传时等价 {"default": upstream}，单上游旧行为不变。
        self.upstreams = {}
        if upstreams:
            for name, url in (upstreams.items() if isinstance(upstreams, dict)
                              else upstreams):
                self.upstreams[name] = url.rstrip("/")
        if not self.upstreams:
            self.upstreams = {"default": (upstream or "").rstrip("/")}
        self.route = list(self.upstreams.keys())
        self.upstream = self.upstreams[self.route[0]]


def _usage_of(resp_json):
    u = (resp_json or {}).get("usage") or {}
    return int(u.get("prompt_tokens", 0) or 0), int(u.get("completion_tokens", 0) or 0)


def _synth_completion(model, content, pt=0, ct=0):
    return {
        "id": "chatcmpl-calldecay-" + str(int(time.time() * 1000)),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0,
                     "message": {"role": "assistant", "content": content},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": pt, "completion_tokens": ct,
                  "total_tokens": pt + ct},
    }


def _decision_params(body, headers):
    cc = body.get("_calldecay") if isinstance(body, dict) else None
    if isinstance(cc, dict):
        return {k: cc.get(k) for k in ("obj", "goal", "current", "actions", "context")}
    h = {}
    for k, v in headers.items():
        if k.lower().startswith("x-calldecay-"):
            h[k.lower()[len("x-calldecay-"):]] = v
    if "obj" in h and "goal" in h:
        acts = [a for a in (h.get("actions") or "").split(",") if a]
        return {"obj": h["obj"], "goal": h["goal"], "current": h.get("current"),
                "actions": acts or None, "context": None}
    return None


class Handler(BaseHTTPRequestHandler):
    state = None
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {"ok": True, "upstream": self.state.upstream,
                                    "upstreams": self.state.upstreams,
                                    "route": self.state.route})
        if self.path == "/v1/calldecay/metrics":
            s = self.state.cd.stats()
            out = dict(s.get("metrics", {}))
            out["core"] = s.get("core", {})
            return self._send(200, out)
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            body = json.loads(raw) if raw else {}
        except Exception:
            body = {}
        if self.path == "/v1/calldecay/decide":
            return self._native_decide(body)
        if self.path == "/v1/calldecay/learn":
            return self._native_learn(body)
        if self.path == "/v1/chat/completions":
            return self._chat(body, raw)
        return self._send(404, {"error": "not found"})

    # ---- 决策/回灌原生接口 ----

    def _native_decide(self, body):
        d = self.state.cd.decide(obj=body.get("obj"), goal=body.get("goal"),
                                 current=body.get("current"),
                                 actions=body.get("actions"),
                                 context=body.get("context"))
        return self._send(200, d)

    def _native_learn(self, body):
        r = self.state.cd.learn(obj=body.get("obj"), act=body.get("act"),
                                actual=body.get("actual"), cur=body.get("cur"))
        return self._send(200, r if isinstance(r, dict) else {"ok": True})

    # ---- OpenAI 兼容入口 ----

    def _chat(self, body, raw):
        if isinstance(body, dict) and body.get("stream"):
            return self._send(400, {"error": {"message": "calldecay v1 不支持 stream:true",
                                              "type": "invalid_request_error"}})
        params = _decision_params(body, self.headers)
        if params and params.get("obj") and params.get("goal"):
            d = self.state.cd.decide(obj=params["obj"], goal=params["goal"],
                                     current=params.get("current"),
                                     actions=params.get("actions"),
                                     context=params.get("context"))
            content = json.dumps(d, ensure_ascii=False)
            return self._send(200, _synth_completion(self.state.model, content))
        return self._passthrough(raw)

    def _forward(self, url, raw):
        """透传到单上游；仅传输层失败（拒连/超时）抛异常。"""
        u = urlparse(url)
        port = u.port or (443 if u.scheme == "https" else 80)
        if u.scheme == "https":
            import ssl
            conn = http.client.HTTPSConnection(u.hostname, port, timeout=180,
                                               context=ssl.create_default_context())
        else:
            conn = http.client.HTTPConnection(u.hostname, port, timeout=180)
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in ("host", "content-length")
                   and not k.lower().startswith("x-calldecay-")}
        headers["Content-Length"] = str(len(raw))
        try:
            conn.request("POST", self.path, body=raw, headers=headers)
            r = conn.getresponse()
            data = r.read()
            status = r.status
            ctype = r.getheader("Content-Type") or "application/json"
        finally:
            conn.close()
        return status, ctype, data

    def _passthrough(self, raw):
        # 多上游回落（2026-11-06 包裹本地模型模式）：按 route 顺序试，只对传输失败
        # （拒连/超时）回落；上游 5xx/4xx 是真实响应，原样返回不回落。
        # x-calldecay-upstream: <name> 头可钉住指定上游。
        pin = (self.headers.get("x-calldecay-upstream") or "").strip()
        names = list(self.state.route)
        if pin and pin in self.state.upstreams:
            names = [pin] + [n for n in names if n != pin]
        errs = []
        for i, name in enumerate(names):
            try:
                status, ctype, data = self._forward(self.state.upstreams[name], raw)
            except Exception as e:
                errs.append(f"{name}: {type(e).__name__}: {e}")
                self.state.cd.metrics.bump("upstream_fail:" + name)
                continue
            m = self.state.cd.metrics
            m.bump("upstream_calls")
            m.bump("upstream_calls:" + name)
            if i > 0:
                m.bump("upstream_fallbacks")
            m.bump("request_chars_sent", len(raw))
            try:
                pt, ct = _usage_of(json.loads(data))
                m.bump("upstream_prompt_tokens", pt)
                m.bump("upstream_completion_tokens", ct)
            except Exception:
                pass
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self._send(502, {"error": {"message": f"all upstreams failed: {errs}",
                                   "type": "upstream_unreachable"}})


def serve(listen="127.0.0.1:8787", upstream="http://127.0.0.1:8082",
          model="calldecay-decided", upstreams=None):
    host, _, port = listen.partition(":")
    state = ProxyState(upstream=upstream, model=model, upstreams=upstreams)
    handler = type("BoundHandler", (Handler,), {"state": state})
    srv = ThreadingHTTPServer((host, int(port or 8787)), handler)
    print(f"CallDecay 代理已启动 http://{host}:{port}  上游={state.upstreams} 回落序={state.route}")
    print("端点: /v1/chat/completions（透传/决策两用） /v1/calldecay/*  /health")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n停止。指标:", json.dumps(state.cd.stats(), ensure_ascii=False))
