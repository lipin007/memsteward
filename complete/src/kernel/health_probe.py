import os
import json
import time
import subprocess
import socket
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(HERE) == "kernel":
    HERE = os.path.dirname(HERE)  # 装配位自适应
PROD = os.path.abspath(os.path.join(HERE, "..", "记忆体"))  # 语义随 health_dashboard 原样
"""提取件 v1（2026-11-19 组件提取入册）
来源：src/health_dashboard.py 行 [(19, 188)]
状态：未接线提取稿。接线前按本夹 README 的参数化清单补齐。
"""
def probe_port(host, port, timeout=2):
    try:
        s = socket.create_connection((host, port), timeout)
        s.close()
        return True
    except:
        return False

def probe_http(url, timeout=3):
    import urllib.request
    try:
        t0 = time.time()
        r = urllib.request.urlopen(url, timeout=timeout)
        dt = round((time.time() - t0) * 1000)
        return {"ok": True, "code": r.status, "ms": dt}
    except Exception as e:
        return {"ok": False, "err": str(e)[:80]}

def shell(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except:
        return "(timeout)"

def collect():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st = {"ts": now, "components": []}

    # 1. memt-daemon (8877)
    alive = probe_port("127.0.0.1", 8877)
    health = probe_http("http://127.0.0.1:8877/health") if alive else {"ok": False}
    st["components"].append({
        "name": "memt-daemon (决策观测面)", "port": 8877,
        "status": "green" if health.get("ok") else ("yellow" if alive else "red"),
        "detail": f"health {health.get('ms', '—')}ms" if health.get("ok") else (health.get("err", "port dead")[:60]),
        "metric": f"响应 {health.get('ms', '—')}ms" if health.get("ok") else "不可达"
    })

    # 2. carry_lock
    try:
        cl = json.load(open(os.path.join(HERE, "config", "carry_lock.json")))
        mode = cl.get("mode", "?")
        st["components"].append({
            "name": "carry_lock (S2/S3 锁定)", "port": None,
            "status": "green" if mode == "on" else "yellow",
            "detail": f"mode={mode}", "metric": "锁定生效" if mode == "on" else "未锁定"
        })
    except:
        st["components"].append({"name": "carry_lock", "port": None, "status": "red", "detail": "config missing", "metric": "?"})

    # 3. embedding (8085)
    alive85 = probe_port("127.0.0.1", 8085)
    h85 = probe_http("http://127.0.0.1:8085/health") if alive85 else {"ok": False}
    st["components"].append({
        "name": "llama-embed-8085 (nomic)", "port": 8085,
        "status": "green" if h85.get("ok") else ("yellow" if alive85 else "red"),
        "detail": f"health {h85.get('ms', '—')}ms" if h85.get("ok") else "不可达",
        "metric": f"{h85.get('ms', '—')}ms"
    })

    # 4. shadow continuation
    shadow_path = os.path.join(PROD, "shadow", "logs", "thinking_stub_shadow.jsonl")
    try:
        lines = sum(1 for _ in open(shadow_path))
        mtime = datetime.fromtimestamp(os.path.getmtime(shadow_path)).strftime("%H:%M:%S")
        age_min = (time.time() - os.path.getmtime(shadow_path)) / 60
        st["components"].append({
            "name": "影子续写 (thinking_stub)", "port": None,
            "status": "green" if age_min < 60 else "yellow",
            "detail": f"{lines} 行 · 最后写 {mtime} ({age_min:.0f}min 前)",
            "metric": f"{lines} entries"
        })
    except:
        st["components"].append({"name": "影子续写", "port": None, "status": "red", "detail": "no shadow log", "metric": "0"})

    # 5. P4 toolface (补丁活性)
    dist_dir = "~/.npm-global/lib/node_modules/openclaw/dist"
    hits = int(shell(f"grep -c __toolfaceFace {dist_dir}/agent-core-*.mjs {dist_dir}/attempt-system-prompt-prepare-*.mjs 2>/dev/null | awk -F: '{{s+=$2}}END{{print s}}'") or "0")
    st["components"].append({
        "name": "P4② 只藏不删 (toolface)", "port": None,
        "status": "green" if hits >= 2 else "red",
        "detail": f"__toolfaceFace × {hits}",
        "metric": "补丁激活" if hits >= 2 else "补丁丢失"
    })

    # 6. 网关
    gw = shell("systemctl --user is-active openclaw-gateway.service")
    ver = shell("openclaw --version 2>/dev/null | head -1")
    st["components"].append({
        "name": "OpenClaw 网关", "port": None,
        "status": "green" if gw == "active" else "red",
        "detail": ver or gw, "metric": gw
    })

    # 7. semantic 臂 (FTS)
    mem_status = shell("ls ~/.openclaw/memory/index/*.fts 2>/dev/null | wc -l")
    st["components"].append({
        "name": "memory FTS 索引", "port": None,
        "status": "green" if mem_status != "0" else "yellow",
        "detail": f"{mem_status} 个索引文件",
        "metric": "FTS 可用"
    })

    # 8. depscan cron
    st["components"].append({
        "name": "depscan (每日 09:30)", "port": None,
        "status": "green", "detail": "job 9d7f250a · cron 30 9 * * *",
        "metric": "scheduled"
    })

    # 汇总
    greens = sum(1 for c in st["components"] if c["status"] == "green")
    yellows = sum(1 for c in st["components"] if c["status"] == "yellow")
    reds = sum(1 for c in st["components"] if c["status"] == "red")
    st["summary"] = {"green": greens, "yellow": yellows, "red": reds, "total": len(st["components"])}
    return st


def render_html(st):
    colors = {"green": "#22c55e", "yellow": "#eab308", "red": "#ef4444"}
    icons = {"green": "●", "yellow": "◐", "red": "○"}
    rows = ""
    for c in st["components"]:
        col = colors[c["status"]]
        ico = icons[c["status"]]
        rows += f"""
<tr style="border-bottom:1px solid #1e293b">
  <td style="padding:10px 14px;white-space:nowrap"><span style="color:{col};font-size:18px">{ico}</span> {c["name"]}</td>
  <td style="padding:10px 14px;color:#94a3b8;font-family:monospace">{c["detail"]}</td>
  <td style="padding:10px 14px;color:{col};font-weight:600;text-align:right">{c["metric"]}</td>
</tr>"""
    s = st["summary"]
    overall = "#22c55e" if s["red"] == 0 and s["yellow"] == 0 else ("#eab308" if s["red"] == 0 else "#ef4444")
    overall_text = "ALL GREEN" if s["red"] == 0 and s["yellow"] == 0 else (f"{s['yellow']} WARN" if s["red"] == 0 else f"{s['red']} DOWN")
    return f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8"><meta http-equiv="refresh" content="30">
<title>MemGate 健康观测台</title>
<style>
body{{background:#0f172a;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,sans-serif;margin:0;padding:20px}}
.header{{display:flex;align-items:center;justify-content:space-between;margin-bottom:24px}}
.title{{font-size:28px;font-weight:700}}
.overall{{font-size:48px;font-weight:800;color:{overall}}}
.overall-label{{font-size:14px;color:#64748b;text-align:center}}
.meta{{color:#64748b;font-size:13px;margin-bottom:16px}}
table{{width:100%;border-collapse:collapse;background:#1e293b;border-radius:12px;overflow:hidden}}
thead{{background:#334155}}
thead th{{padding:12px 14px;text-align:left;font-size:13px;color:#94a3b8;font-weight:600}}
.badge{{display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:600;margin-right:8px}}
.b-green{{background:#052e16;color:#22c55e}}
.b-yellow{{background:#422006;color:#eab308}}
.b-red{{background:#450a0a;color:#ef4444}}
.summary-bar{{display:flex;gap:16px;margin-bottom:20px}}
</style></head><body>
<div class="header">
  <div><div class="title">🛡️ MemGate 健康观测台</div>
  <div class="meta">快照时间 {st["ts"]} · 30s 自动刷新</div></div>
  <div style="text-align:center"><div class="overall">{overall_text}</div>
  <div class="overall-label">{s["green"]}/{s["total"]} GREEN</div></div>
</div>
<div class="summary-bar">
  <span class="badge b-green">● {s["green"]} 正常</span>
  <span class="badge b-yellow">◐ {s["yellow"]} 告警</span>
  <span class="badge b-red">○ {s["red"]} 故障</span>
</div>
<table><thead><tr><th>组件</th><th>状态详情</th><th>指标</th></tr></thead>
<tbody>{rows}</tbody></table>
<div style="margin-top:20px;color:#475569;font-size:12px">
MemGate 健康观测台 · v1.0 · 只读零写盘 · 信号源: memt-daemon(8877) / carry_lock / llama-embed(8085) / shadow / toolface / gateway / FTS / cron
</div></body></html>"""

