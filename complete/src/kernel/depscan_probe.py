import os
import json
"""提取件 v1（2026-11-19 组件提取入册）
来源：src/bridge_cli.py 行 [(294, 382)]
状态：未接线提取稿。接线前按本夹 README 的参数化清单补齐。
"""
def classify_probe(status, body, err):
    """探针分类（纯函数，离线可测）→ reachable|billing|schema_reject|timeout|unreachable|error。

    口径：reachable=传输通（鉴权/服务质量另判，配 apiKey 的 openai-chat 探针才看得见欠费/拒 schema）。
    分类串取自 2026-11-03 实况（billing 欠费/拒 schema/超时/拒连）。
    """
    if err is not None:
        e = str(err).lower()
        if "timed out" in e or "timeout" in e:
            return "timeout"
        if "refused" in e or "name or service" in e or "getaddrinfo" in e:
            return "unreachable"
        return "error"
    b = (body or "").lower()
    if status == 402 or "billing" in b or "insufficient balance" in b or "out of credits" in b:
        return "billing"
    if "rejected the request schema" in b or ("schema" in b and status == 400):
        return "schema_reject"
    if status is not None and 200 <= status < 500:
        return "reachable"
    return "error"


def probe_target(t, timeout=5.0):
    """真跑探活：http=GET；openai-chat=1-token completion（假兜底死法在这一层才现形）。

    timeout：探针窗秒（targets 可选 "timeout" 字段经 _run_depscan 传入，缺省 5.0）。
    """
    import urllib.error
    import urllib.request

    url = (t.get("url") or "").strip()
    kind = t.get("kind", "http")
    headers = {}
    if t.get("apiKey"):
        headers["Authorization"] = "Bearer " + t["apiKey"]
    try:
        if kind == "openai-chat":
            base = url.rstrip("/")
            if not base.endswith("/chat/completions"):
                base += "/chat/completions"
            data = json.dumps({"model": t.get("model", "probe"),
                               "messages": [{"role": "user", "content": "ping"}],
                               "max_tokens": 1}).encode("utf-8")
            headers["Content-Type"] = "application/json"
            req = urllib.request.Request(base, data=data, headers=headers)
        else:
            req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(2000).decode("utf-8", "replace")
            return classify_probe(r.status, body, None)
    except urllib.error.HTTPError as e:
        try:
            body = e.read(2000).decode("utf-8", "replace")
        except Exception:
            body = ""
        return classify_probe(e.code, body, None)
    except Exception as e:
        return classify_probe(None, "", e)


def _run_depscan(targets, st):
    """逐条真跑＋分类＋死链入账（S2：声明不算数，探针才算数）。"""
    counts, results, healthy = {}, [], 0
    for t in targets:
        # 修尺（2026-11-14，证据）：缺省探针窗 5s < xiaomi 冷启动实测 5.7s ⇒ 13:46 冒烟把健康
        # xiaomi 误判 timeout（误报死链）。targets 可选 "timeout"（秒），缺省 5.0＝既有调用方
        # 行为逐字不变（v3 兼容扩展，调用面语义未变不升位）；云端 chat 靶由 runner 给 20s。
        cls = probe_target(t, timeout=float(t.get("timeout") or 5.0))
        counts[cls] = counts.get(cls, 0) + 1
        if cls == "reachable":
            healthy += 1
        else:
            st.deposit(obj=f"dep:{t.get('id') or t.get('url')}", act=cls,
                       actual=str(t.get("url", ""))[:200], cur="depscan",
                       via="governance.depscan")
        results.append({"id": t.get("id"), "class": cls, "url": t.get("url")})
    return {"n": len(targets), "healthy": healthy, "dead": len(targets) - healthy,
            "counts": counts, "results": results}


def _load_targets(a, ws):
    raw = getattr(a, "targets", None)
    if not raw:
        path = getattr(a, "targets_file", None) or os.path.join(ws, "deps_targets.json")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                raw = f.read()
    return json.loads(raw) if raw else []

