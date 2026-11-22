from activity_telemetry import _HOME  # 单源 2026-11-19
import os
import json
import time
"""提取件 v1（2026-11-19 组件提取入册）
来源：src/bridge_cli.py 行 [(105, 284)]
状态：未接线提取稿。接线前按本夹 README 的参数化清单补齐。
"""
def _dashboard(st, landing, html_path=None):
    """只读观测面（2026-11-05）：账本规模/冷暖分布/good 计数/省调用曲线（日粒度，
    口径＝good_hit 零 token 回落次数）/衰减节拍/合账历史/杠杆值。"""
    hist = {}
    for e in st.entries.values():
        b = min(9, int(float(e.get("liveness", 1.0)) * 10))
        hist[b] = hist.get(b, 0) + 1
    liveness_hist = {f"{b / 10:.1f}-{(b + 1) / 10:.1f}": hist.get(b, 0)
                     for b in range(10)}
    base = (os.path.dirname(os.path.expanduser(landing)) if landing
            else _HOME)
    daily = {}
    try:
        with open(os.path.join(base, "telemetry.jsonl"), encoding="utf-8") as f:
            for line in f:
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                d = daily.setdefault(str(ev.get("ts", ""))[:10],
                                     {"good_hit": 0, "good_miss": 0,
                                      "good_ok": 0, "good_revoke": 0})
                if ev.get("kind") in d:
                    d[ev["kind"]] += 1
    except OSError:
        pass
    arc_n = 0
    try:
        with open(st._archive_path(), encoding="utf-8") as f:
            arc_n = len(json.load(f).get("entries", {}))
    except (OSError, ValueError):
        pass
    from calldecay.landing import (DECAY_FACTOR, MIN_LIVENESS,  # noqa: E402
                                   TICK_SECONDS, AUTO_COMPACT_AT)
    q = int(st.meta.get("good_queries", 0))
    h = int(st.meta.get("good_hits", 0))
    act = {}
    try:
        with open(os.path.join(base, "activity.json"), encoding="utf-8") as f:
            act = json.load(f)
    except (OSError, ValueError):
        pass
    import socket as _sock

    def _port_ok(port):
        try:
            c = _sock.create_connection(("127.0.0.1", port), timeout=0.5)
            c.close()
            return True
        except OSError:
            return False
    data = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "stats": st.stats(),
        "liveness_hist": liveness_hist,
        "good": {"patterns": len(st.good_patterns),
                 "ok": int(st.meta.get("good_ok", 0)),
                 "revoke": int(st.meta.get("good_revoke", 0)),
                 "queries": q, "hits": h,
                 "hit_rate": (round(h / q, 3) if q else None)},
        "daily": [{"date": k, **v} for k, v in sorted(daily.items())],
        "pipeline": {"enhance_fail": int(st.meta.get("summary_enhance_fail", 0)),
                     "base_starved": int(st.meta.get("summary_base_starved", 0)),
                     "p8083": _port_ok(8083), "p8082": _port_ok(8082)},
        "act": act,
        "decay": {"last_decay_ts": st.meta.get("last_decay_ts"),
                  "next_auto_compact_at": st.meta.get("next_auto_compact_at"),
                  "levers": {"decayFactor": DECAY_FACTOR,
                             "minLiveness": MIN_LIVENESS,
                             "tickSeconds": TICK_SECONDS,
                             "autoCompactAt": AUTO_COMPACT_AT}},
        "archive": {"entries": arc_n},
    }
    if html_path:
        hp = os.path.abspath(os.path.expanduser(html_path))
        with open(hp, "w", encoding="utf-8") as f:
            f.write(_dashboard_html(data))
        data["html"] = hp
    return data


def _dashboard_html(d):
    """自包含 HTML（内联 CSS/SVG，零外部依赖）——橱窗件，可直接随商品分发。"""

    def vbars(pairs, w=430, h=130, color="#5b8def", unit=""):
        if not pairs:
            return "<p class='dim'>（无数据）</p>"
        mx = max(v for _, v in pairs) or 1
        bw = w / len(pairs)
        out = [f"<svg viewBox='0 0 {w} {h + 26}' class='chart' role='img'>"]
        for i, (k, v) in enumerate(pairs):
            bh = (h - 18) * v / mx
            x = i * bw + bw * 0.18
            out.append(f"<rect x='{x:.1f}' y='{h - bh:.1f}' width='{bw * 0.64:.1f}' "
                       f"height='{bh:.1f}' fill='{color}' rx='2'><title>{k}: {v}{unit}</title></rect>")
            out.append(f"<text x='{i * bw + bw / 2:.1f}' y='{h + 15}' text-anchor='middle' "
                       f"class='lbl'>{k}</text>")
            out.append(f"<text x='{i * bw + bw / 2:.1f}' y='{h - bh - 4:.1f}' text-anchor='middle' "
                       f"class='val'>{v}</text>")
        out.append("</svg>")
        return "".join(out)

    good = d["good"]
    hr = "—" if good["hit_rate"] is None else f"{good['hit_rate'] * 100:.1f}%"
    daily_tbl = (
        "".join(
            f"<tr><td>{r['date']}</td><td>{r['good_hit']}</td><td>{r['good_miss']}</td>"
            f"<td>{r['good_ok']}</td><td>{r['good_revoke']}</td></tr>" for r in d["daily"])
        or "<tr><td colspan='5' class='dim'>（事件账还没数据——口径自 2026-11-05 接线起算）</td></tr>"
    )
    lv_pairs = [(k.split("-")[0], v) for k, v in d["liveness_hist"].items() if v]
    hit_pairs = [(r["date"][5:], r["good_hit"]) for r in d["daily"]]
    s = d["stats"]
    lv = d["decay"]["levers"]
    return f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MemGate 仪表盘</title><style>
body{{font-family:system-ui,-apple-system,'Noto Sans SC',sans-serif;margin:0;padding:24px;
background:#0f1115;color:#e8eaed}}h1{{font-size:20px;margin:0 0 4px}}h2{{font-size:14px;
color:#9aa0a6;margin:24px 0 8px;font-weight:600}}.dim{{color:#9aa0a6}}.grid{{display:grid;
grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}}.card{{background:#181b22;
border:1px solid #262a33;border-radius:10px;padding:14px}}.card .n{{font-size:22px;font-weight:700}}
.card .k{{font-size:12px;color:#9aa0a6;margin-top:2px}}.chart{{width:100%;max-width:430px}}
.lbl{{font-size:10px;fill:#9aa0a6}}.val{{font-size:10px;fill:#c6cad2}}
table{{border-collapse:collapse;width:100%;max-width:560px}}td,th{{border-bottom:1px solid #262a33;
padding:6px 10px;font-size:12px;text-align:left}}th{{color:#9aa0a6;font-weight:600}}
.foot{{margin-top:28px;font-size:11px;color:#7d828b;line-height:1.7}}code{{background:#181b22;
padding:1px 6px;border-radius:4px}}</style></head><body>
<h1>MemGate 仪表盘</h1>
<div class="dim">{d['generated_at']} · 只读观测面 · 数据源 <code>{s['path']}</code></div>
<div class="grid" style="margin-top:16px">
<div class="card"><div class="n">{s['n']}</div><div class="k">账本条目</div></div>
<div class="card"><div class="n">{s['bytes'] / 1048576:.2f} MB</div><div class="k">账本体积</div></div>
<div class="card"><div class="n">{good['patterns']}</div><div class="k">good 模式沉淀</div></div>
<div class="card"><div class="n">{hr}</div><div class="k">回落命中率（{good['hits']}/{good['queries']}）</div></div>
<div class="card"><div class="n">{good['hits']}</div><div class="k">省调用（零 token 回落）</div></div>
<div class="card"><div class="n">{good['ok']} / {good['revoke']}</div><div class="k">沉淀 / 撤销（撤销率上限 25%）</div></div>
<div class="card"><div class="n">{d['archive']['entries']}</div><div class="k">冷层归档条目</div></div>
<div class="card"><div class="n">{s['liveness_min']}–{s['liveness_max']}</div><div class="k">liveness 范围</div></div>
</div>
<h2>冷暖分布（liveness 直方）</h2>{vbars(lv_pairs, color='#3ddc97')}
<h2>省调用曲线（good_hit 日粒度）</h2>{vbars(hit_pairs)}
<h2>good 族事件明细</h2>
<table><tr><th>日期</th><th>命中</th><th>未中</th><th>沉淀</th><th>撤销</th></tr>{daily_tbl}</table>
<h2>衰减节拍与杠杆</h2>
<div class="grid">
<div class="card"><div class="n">{lv['decayFactor']}</div><div class="k">decayFactor</div></div>
<div class="card"><div class="n">{lv['minLiveness']}</div><div class="k">minLiveness（量门）</div></div>
<div class="card"><div class="n">{lv['tickSeconds'] / 3600:.0f} h</div><div class="k">时间拍</div></div>
<div class="card"><div class="n">{lv['autoCompactAt']}</div><div class="k">自动合账阈（下次 {d['decay']['next_auto_compact_at']}）</div></div>
</div>
<h2>三轨产品读数（2026-11-09 四轮机制链实测）</h2>
<div class="grid">
<div class="card"><div class="n">0.092×</div><div class="k">本地轨 KV 携带＋解码锁（省 90.8%）</div></div>
<div class="card"><div class="n">94–98.5%</div><div class="k">云轨省词元（记忆帧 O(1)，usage 实测）</div></div>
<div class="card"><div class="n">S9=D</div><div class="k">受控床：压缩账本追平原文 oracle</div></div>
<div class="card"><div class="n">40/71</div><div class="k">M3 有效命中（净-噪口径 57.1%）</div></div>
</div>
<h2>管线健康（摘要增强面）</h2>
<div class="grid">
<div class="card"><div class="n">{d['pipeline']['enhance_fail']}</div><div class="k">enhance 失败累计</div></div>
<div class="card"><div class="n">{d['pipeline']['base_starved']}</div><div class="k">底稿饥饿累计</div></div>
<div class="card"><div class="n">{'在线' if d['pipeline']['p8083'] else '离线'}</div><div class="k">summarize 3B@8083</div></div>
<div class="card"><div class="n">{'在线' if d['pipeline']['p8082'] else '离线'}</div><div class="k">main thinking@8082</div></div>
</div>
<h2>召回与治理活动面</h2>
<div class="grid">
<div class="card"><div class="n">{(d['act'].get('subs') or {}).get('recall', {}).get('n', 0)}</div><div class="k">recall 调用</div></div>
<div class="card"><div class="n">{d['act'].get('recall_hits', 0)}</div><div class="k">召回命中</div></div>
<div class="card"><div class="n">{d['act'].get('recall_empty', 0)}</div><div class="k">召回空</div></div>
<div class="card"><div class="n">{(d['act'].get('subs') or {}).get('deposit', {}).get('n', 0)}</div><div class="k">治理入账（deposit）</div></div>
<div class="card"><div class="n">{(d['act'].get('subs') or {}).get('feedback', {}).get('n', 0)}</div><div class="k">good 喂养（feedback）</div></div>
<div class="card"><div class="n">{(d['act'].get('subs') or {}).get('preflight', {}).get('n', 0)}</div><div class="k">门禁巡检（preflight）</div></div>
<div class="card"><div class="n">{(d['act'].get('subs') or {}).get('recall_good', {}).get('n', 0)}</div><div class="k">good 查表（recall_good）</div></div>
<div class="card"><div class="n">{(d['act'].get('subs') or {}).get('deposit', {}).get('last', '—')}</div><div class="k">末次入账时刻</div></div>
</div>
<div class="foot">口径：命中率＝good_hits/good_queries（recall_good 三层键面查表：精确/归一化/签名门控，自 2026-11-05 计数接线起算）；灰度期命中计 good_shadow_hits（只报不直答）；
省调用＝命中回落替代的 LLM/人工确认次数；撤销率＞25% 触发 LR3 净毒性警戒（宁缺勿滥）。<br>
刷新：<code>python3 bridge_cli.py dashboard --html &lt;path&gt;</code> · 生产/上架分离：此页随上架副本分发，生产代码不为上架精简</div>
</body></html>"""


SCOPE_BANS = [
    "〔纲〕不可逆外部动作（发/删/改/推）必须带明示动词——问号是问号，不是发射指令",
    "〔纲〕未验证声明不得冒充事实入账（声明必须带口径/证据锚点）",
    "〔纲〕工程纪律违规只在开工/交账时查——提问/方案/讨论零拦截",
]

