# -*- coding: utf-8 -*-
"""Governance middleware Python bridge — 业务逻辑单一来源（单源原则）.

TS 层只做调用面；一切业务逻辑走本桥：
  LandingStore (CallDecay sdk)  — deposit/recall/replay：硬落盘(原子写)/签名门控召回/回放
  pvs.gate (pvs-sdk)            — boot/preflight/ledger/constraints：门禁断言/教训台账/治理纪律面
  accept_contract (core)        — 候选认知 vs 权威提交边界（F1/F3，由 deposit 侧复用）

三种调用形态（同一 run() 派发，行为唯一）:
  CLI     python3 bridge_cli.py <sub> [--landing PATH] [--ws PATH] [参数…] → stdout 单行 JSON
  oneshot python3 bridge_cli.py --oneshot   (stdin: {"sub","args":[…]} → stdout 单行 JSON)
          —— 载荷走 stdin，绕开 execve 单参上限（旧 TS 侧 60000 字符截断随之删除）
  serve   python3 bridge_cli.py --serve     (stdin 逐行 {"id","sub","args"} → stdout 逐行
          {"id","ok","result"} | {"id","ok":false,"error"}) —— 常驻 worker，进程复用；
          单请求异常不杀进程

子命令: deposit / recall / digest / ingest / commit / preflight / ledger / constraints / depscan / version / compact / restore / feedback / recall_good / health / dashboard / ping / quarantine-mark
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

import admission   # 写入侧准入过滤（五病#1：横幅/信封残片拒收、疑似回声隔离）

HERE = os.path.dirname(os.path.abspath(__file__))  # L09: __file__ 锚定

# --- Kernel 增强(2026-11-19 接线批 v2; 判据 test_kernel_wiring.py 先立后接) ---
# 标准化: 树内自含 kernel(sync_kernel.sh 装配); MEMGATE_NO_KERNEL=1 关闭; fail-soft 可见告警(一次性, 不静默不刷屏)
_KERNEL = os.path.join(HERE, "kernel")
if os.environ.get("MEMGATE_NO_KERNEL") == "1" or not os.path.isdir(_KERNEL):
    _HAS_KERNEL = False
    if os.environ.get("MEMGATE_NO_KERNEL") == "1":
        print("[memgate] kernel 增强已关闭(MEMGATE_NO_KERNEL=1)", file=sys.stderr)  # 显式关也留痕
else:
    if _KERNEL not in sys.path:
        sys.path.insert(0, _KERNEL)
    try:
        from tokenizer import tokenize
        from knowledge_distiller import KnowledgeDistiller
        from hebbian_link import HebbianLink
        from tiered_decay import apply_tiered_decay
        _HAS_KERNEL = True
    except ImportError as _kie:
        _HAS_KERNEL = False
        print("[memgate] kernel 增强未加载(%s); tokenize 回退" % _kie, file=sys.stderr)
if not _HAS_KERNEL:
    def tokenize(text):
        import re
        return re.findall(r"[a-z0-9]+", text.lower())
_KERNEL_WARNED = set()
# ── 切片件单源化(2026-11-19 P1): 6 件从 kernel 装配 import; 内联段已回流正源 ──
# F12 纪律(fail-soft): 缺 kernel 时降级可用+一次性可见告警(T5), 非核心缺席静默跳过(T6)
try:
    from dashboard_render import _dashboard, _dashboard_html
    from activity_telemetry import _telemetry, _bump_activity, _HOME
    from depscan_probe import _run_depscan, _load_targets, classify_probe, probe_target
    from registry_gate import registry_gate
    from version_binding import _sha256, _version, _bootstrap, BRIDGE_PROTOCOL
except ImportError:
    print("warn: kernel 切片件缺席, 降级运行(fail-soft)", file=sys.stderr)
    _HOME = os.environ.get("CALLDECACY_HOME") or os.path.expanduser("~/.memsteward/landing")
    BRIDGE_PROTOCOL = 3
    def _bootstrap(ws):
        for _n in ("calldecacy-sdk", "pvs-sdk"):  # fail-soft 回退装载(vendor 优先)
            _p = os.path.join(HERE, "vendor", _n)
            if not os.path.isdir(_p):
                _p = os.path.join(ws, "中间件", "组件总文件夹", _n)
            if _p not in sys.path:
                sys.path.insert(0, _p)
    def _telemetry(*a, **k): pass
    def _bump_activity(*a, **k): pass
    def _sha256(*a, **k): return ""
    def _version(*a, **k): return {"error": "kernel 缺席: version 不可用"}
    def _dashboard(*a, **k): return {"error": "kernel 缺席"}
    def _dashboard_html(*a, **k): return "<p>kernel 缺席</p>"
    def _run_depscan(*a, **k): return {"error": "kernel 缺席"}
    def _load_targets(*a, **k): return []
    def classify_probe(*a, **k): return "unknown"
    def probe_target(*a, **k): return None
    def registry_gate(*a, **k): return {"error": "kernel 缺席"}

def _kernel_warn(tag, e):
    if tag not in _KERNEL_WARNED:
        _KERNEL_WARNED.add(tag)
        print("[memgate] kernel %s 降级: %r" % (tag, e), file=sys.stderr)


class UnknownSub(Exception):
    """未知子命令（CLI/oneshot → error JSON + 退出码 1；serve → 单请求错误，进程不退出）."""



def _ws(explicit):
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))
    env = os.environ.get("GOV_WS")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    # 工作区根自适应（2026-11-05 迁址）：向上找 ai-research 标记，
    # 兼容旧深度（plugins/<name>/src）与新深度（ai-research/商用产品/<name>/src）。
    p = HERE
    for _ in range(6):
        if os.path.isdir(os.path.join(p, "ai-research")):
            return p
        p = os.path.dirname(p)
    return os.path.abspath(os.path.join(HERE, "..", "..", ".."))


def _store(landing):
    from calldecay.landing import LandingStore  # noqa: E402

    return LandingStore(os.path.expanduser(landing) if landing else None)


def _emb_cache_path(landing):
    """语义臂向量缓存 sidecar：与账本同名 .emb.json（内容寻址，随账本并存）。"""
    import calldecay.landing as _land  # noqa: E402
    base = os.path.expanduser(landing) if landing else _land.DEFAULT_PATH
    return base + ".emb.json"


def _summary_buffer(landing):
    """摘要引擎缓冲文件（与账本同目录）：oneshot/serve 跨进程接力攒轮次。"""
    base = (os.path.dirname(os.path.expanduser(landing)) if landing
            else _HOME)
    return os.path.join(base, "summarize-buffer.json")


def _out(obj):
    print(json.dumps(obj, ensure_ascii=False))


SCOPE_BANS = [
    "〔纲〕不可逆外部动作（发/删/改/推）必须带明示动词——问号是问号，不是发射指令",
    "〔纲〕未验证声明不得冒充事实入账（声明必须带口径/证据锚点）",
    "〔纲〕工程纪律违规只在开工/交账时查——提问/方案/讨论零拦截",
]


# v2 (2026-11-04): recall 默认带 min_liveness 量门（冷条目不注入≠删除）——旧调用方结果集变小，语义升位
# v3 (2026-11-12): 写入侧准入（五病#1）——deposit/observe/summarize-flush 可返回
#   rejected/quarantined；recall 默认合格面排除 admit=quarantine 条目（排除≠删除）


def build_parser():
    ap = argparse.ArgumentParser(prog="bridge_cli")
    ap.add_argument("sub")
    ap.add_argument("--landing")
    ap.add_argument("--ws")
    # deposit
    ap.add_argument("--obj")
    ap.add_argument("--act")
    ap.add_argument("--actual")
    ap.add_argument("--cur")
    # recall / ledger
    ap.add_argument("--signature")
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--min-liveness", type=float, default=0.03,
                    help="recall 冷条目注入下限（0=不过滤；阈值扫描膝点 0.03）")
    ap.add_argument("--include-transcripts", dest="include_transcripts",
                    action="store_true",
                    help="recall 显式审计面：转录类条目一并召回（默认排除——回声修复）")
    ap.add_argument("--include-quarantine", dest="include_quarantine",
                    action="store_true",
                    help="recall 审计面：隔离条目（admit=quarantine）一并召回（默认排除）；"
                         "转录类隔离件另需 --include-transcripts（两维排除正交）")
    # 混合计分 G∪E1（五病#3 修法，2026-11-12 落地）：语义臂默认开、fail-soft
    ap.add_argument("--no-hybrid", dest="no_hybrid", action="store_true",
                    help="recall 关闭语义臂（纯词面；等效 MEMGATE_HYBRID=0）")
    ap.add_argument("--embed-url",
                    help="语义臂嵌入服务 URL（默认 $MEMGATE_EMBED_URL 或 127.0.0.1:8085）")
    ap.add_argument("--id")
    # ingest
    ap.add_argument("--role")
    ap.add_argument("--text")
    # commit
    ap.add_argument("--key")
    ap.add_argument("--payload")
    ap.add_argument("--targets")
    ap.add_argument("--targets-file")
    # version
    ap.add_argument("--write", action="store_true", help="落盘 VERSIONS.json 绑定清单")
    ap.add_argument("--config", help="openclaw.json 路径（默认 ~/.openclaw/openclaw.json）")
    ap.add_argument("--model", help="嵌入模型路径（--write 时覆盖配置值）")
    # compact / restore
    ap.add_argument("--liveness-max", type=float, default=0.6, help="compact：liveness 口径上限")
    ap.add_argument("--hits-max", type=int, default=1, help="compact：hits 口径上限")
    ap.add_argument("--age-days", type=float, default=7.0, help="compact：账龄口径下限（天）")
    # feedback（good 答案模式沉淀/撤销）
    ap.add_argument("--revoke", action="store_true", help="feedback：撤销（ok=False）")
    ap.add_argument("--probe", action="store_true",
                    help="recall_good：兼容保留（no-op）——读半边恒报命中；"
                         "直答门在消费面按 MEMGATE_GOOD_DIRECT 收口")
    # dashboard
    ap.add_argument("--html", help="dashboard：另写自包含 HTML 快照到 PATH")
    # observe / summarize-flush（摘要引擎喂料嘴，M3 接入）
    ap.add_argument("--turn-id", type=int, dest="turn_id",
                    help="observe：轮次号（缺省自动递增）")
    ap.add_argument("--kind", default="narrative", help="observe：narrative|summary")
    ap.add_argument("--accumulate", action="store_true",
                    help="observe：批量档（攒轮闩锁定稿）；缺省逐轮编译即刻入账"
                         "（碎片<MIN_DIGEST_TOKENS 攒批，防超短条目）")
    ap.add_argument("--topic", help="summarize-flush：话题签名")
    ap.add_argument("--source-anchor", dest="source_anchor",
                    help="summarize-flush：来源锚（缺省 session:首-末轮）")
    ap.add_argument("--session", help="observe/flush：会话名（锚/缓冲前缀）")
    ap.add_argument("--summarize-url", dest="summarize_url",
                    help="摘要模型上游（缺省 env SUMMARIZE_URL）")
    # quarantine-mark（既有污染条目标记/重分类；默认 dry-run 零写入）
    ap.add_argument("--apply", action="store_true",
                    help="quarantine-mark：真打标记（缺省 dry-run 只报告不动账本）")
    return ap


def run(a):
    """业务派发（CLI/oneshot/serve 共用，行为唯一）→ 结果 dict；未知子命令抛 UnknownSub。"""
    _bump_activity(landing=getattr(a, "landing", None),
                   sub=getattr(a, "sub", "?"))   # 全路径计数（含 serve/oneshot）
    ws = _ws(a.ws)
    _bootstrap(ws)

    if a.sub == "deposit":
        # 写入准入（五病#1）：确定性横幅/信封残片拒收；疑似回声收下但隔离
        verdict = admission.classify_text(
            " ".join(str(x) for x in (a.obj, a.act, a.actual) if x), echo=True)
        if verdict["verdict"] == "reject":
            return {"rejected": verdict["reason"], "patterns": verdict["patterns"],
                    "entry": None}
        st = _store(a.landing)
        e = st.deposit(
            obj=a.obj, act=a.act, actual=a.actual, cur=a.cur, via="memgate")
        st._time_tick()   # 拍改墙钟（2026-11-14 调整）：入账不加拍——写风暴实证
                          #   4 天 ~7700 入账拍把全体打到量门下（15712/15745≤0.03），
                          #   且与 D2「13 拍≈13h 回冷」契约冲突（拍=墙钟小时）；
                          #   回放床 decay_lever_eval 直调 decay() 不受影响
        if verdict["verdict"] == "quarantine":
            admission.mark_quarantine(st, e, verdict["reason"])
            return {"entry": e, "quarantined": True, "reason": verdict["reason"]}
        # Kernel 增强: 蒸馏沉淀 + Hebbian 共现(原 11-18 hunk 死路径/静默吞错, 本次修)
        if _HAS_KERNEL:
            try:
                _d = KnowledgeDistiller.distill_from_text("%s %s %s" % (a.obj, a.act, a.actual))
                _d = KnowledgeDistiller.deduplicate(_d, similarity_threshold=0.5)
                _d = KnowledgeDistiller.filter_by_confidence(_d, min_confidence=0.5)
                for _x in _d[:3]:
                    if _x.get("knowledge"):
                        st.deposit(obj="knowledge", act=_x.get("type", "learned"),
                                   actual=_x["knowledge"], cur=a.cur, via="distilled")
            except Exception as _e:
                _kernel_warn("distill", _e)
            try:
                _ld = os.path.dirname(os.path.expanduser(a.landing or os.path.expanduser("~/.memsteward/landing/landing.json")))
                _h = HebbianLink(os.path.join(_ld, "hebbian.json"))
                _toks = tokenize("%s %s" % (a.obj, a.act))
                for _i, _w1 in enumerate(_toks):
                    for _w2 in _toks[_i + 1:]:
                        _h.boost(_w1, _w2, 0.1)
            except Exception as _e:
                _kernel_warn("hebbian_boost", _e)
        return {"entry": e}
    if a.sub == "recall":
        st = _store(a.landing)
        audit = bool(getattr(a, "include_transcripts", False)
                     or getattr(a, "include_quarantine", False))
        # Kernel 增强: Hebbian 查询扩展(原 11-18 hunk 静默吞错, 本次修)
        if _HAS_KERNEL and getattr(a, "signature", None):
            try:
                _ld = os.path.dirname(os.path.expanduser(a.landing or os.path.expanduser("~/.memsteward/landing/landing.json")))
                _h = HebbianLink(os.path.join(_ld, "hebbian.json"))
                _toks = tokenize(a.signature)
                _exp = list(_toks)
                for _w in _toks:
                    _exp.extend(_h.get_associated(_w, top_k=3))
                if _exp != _toks:
                    a.signature = " ".join(_exp)
            except Exception as _e:
                _kernel_warn("hebbian_expand", _e)
        n_quar = 0
        if not audit:
            # 隔离条目默认出合格面（五病#1：排除≠删除）；多拉槽位防占坑
            n_quar = sum(1 for e in st.entries.values()
                         if admission.is_quarantined(e))
        hits = st.recall(
            a.signature or "", k=a.k + min(n_quar, 64),
            min_liveness=a.min_liveness,
            include_transcripts=getattr(a, "include_transcripts", False))
        # 审计面（--include-transcripts 或 --include-quarantine）可查
        if not audit:
            hits = [h for h in hits
                    if not admission.is_quarantined(h.get("entry") or {})][:a.k]
        # 混合计分 G∪E1（五病#3 修法，2026-11-12 落地；2026-11-13 装配收敛单源件）：
        # 词面臂∪语义臂交织去重，k=6 输出即两臂 top-3 并集（full_verdict 54/78 口径）；
        # 语义臂命中同轨保活。装配走 semantic_recall.hybrid_recall（daemon /decision
        # 同件，防双面漂移）；fail-soft：语义臂任何故障→纯词面原样返回（零回归）。
        # 关闭：--no-hybrid 或 MEMGATE_HYBRID=0。
        revived = []   # 语义复活 D2 附加字段（信封 additive，既有键不动）
        if not getattr(a, "no_hybrid", False):
            try:
                import semantic_recall as sr
                hits = sr.hybrid_recall(
                    st, hits, a.signature or "", a.k,
                    cache_path=_emb_cache_path(a.landing),
                    embed_url=getattr(a, "embed_url", None),
                    min_liveness=a.min_liveness,
                    include_transcripts=getattr(a, "include_transcripts", False),
                    include_quarantine=audit,
                    revived_out=revived)
            except Exception as e:  # noqa: BLE001 —— 语义臂装配故障同样 fail-soft
                print(f"[memgate] 语义臂不可用（fail-soft 纯词面）: "
                      f"{type(e).__name__}: {e}", file=sys.stderr)
        _bump_activity(landing=a.landing, recall_hits=len(hits),
                       recall_empty=(1 if not hits else 0))
        return {"hits": hits, "revived": revived}
    if a.sub == "snapshots-sweep":
        # shrink 快照保留清扫（手动档·全量）：混合保留策略/参数见 calldecay.landing 模块头
        import calldecay.landing as _land  # noqa: E402
        p = (os.path.expanduser(a.landing) if a.landing else _land.DEFAULT_PATH)
        return {"sweep": _land.sweep_shrink_snapshots(p)}
    if a.sub == "feedback":
        # good 答案模式沉淀/撤销（SDK LandingStore.feedback；证据 G1 +57.6pp，
        # 门槛 LR3：假阳>75% 净毒性——喂之前先想清楚反馈源≠核验源）
        if not (a.cur and a.act):
            return {"error": "feedback 需要 --cur 与 --act"}
        st = _store(a.landing)
        r = st.feedback(cur=a.cur, act=a.act, ok=not a.revoke)
        _telemetry(a.landing, "good_revoke" if a.revoke else "good_ok", a.cur)
        return {"feedback": r, "good_patterns": len(st.good_patterns)}
    if a.sub == "recall_good":
        # good 模式读半边（2026-11-05 方案第 2 件）＝**报告面**：键面 C+B 三层回落
        # 命中→沉淀动作（act 逐字报出）；未命中 null。命中只报不直答——直答门在
        # 消费面（adapter.decide 的 gmem 直答 / serve.decide 的响应）按
        # MEMGATE_GOOD_DIRECT 收口（灰度缺省只读，观察一周再开直答）。
        # probe kwarg 已随"matcher 只报"定型移除（2026-11-15），--probe 旗标保留
        # 兼容（现为 no-op：读半边恒报命中）。与 CallDecay adapter.decide 的 gmem
        # 回落同源（LandingStore.recall_good）。计数口径：queries/hits 入 meta 随写事务
        # 落盘（SDK 侧已自持久，无需桥侧再 save——2026-11-07 并发事故后并入事务）。
        if not a.cur:
            return {"error": "recall_good 需要 --cur"}
        from calldecay.landing import _good_direct
        st = _store(a.landing)
        act = st.recall_good(a.cur)   # 报告面恒报命中（计数/telemetry 全在）
        _telemetry(a.landing, "good_hit" if act else "good_miss", a.cur)
        return {"act": act, "good_patterns": len(st.good_patterns),
                "queries": st.meta.get("good_queries"),
                "hits": st.meta.get("good_hits"),
                "shadow_hits": st.meta.get("good_shadow_hits"),
                "direct": _good_direct()}
    if a.sub == "health":
        # 观测面板数据源（2026-11-05 方案第 1 件）：规模/good 数/衰减拍/杠杆值一行 JSON
        from calldecay.landing import (DECAY_FACTOR, MIN_LIVENESS,  # noqa: E402
                                       TICK_SECONDS, AUTO_COMPACT_AT)
        st = _store(a.landing)
        return {"stats": st.stats(),
                "good_patterns": len(st.good_patterns),
                "meta": st.meta,
                "levers": {"decayFactor": DECAY_FACTOR,
                           "minLiveness": MIN_LIVENESS,
                           "tickSeconds": TICK_SECONDS,
                           "autoCompactAt": AUTO_COMPACT_AT}}
    if a.sub == "dashboard":
        # 生产仪表盘（2026-11-05 用户拍板开做）：只读观测，--html 另出自包含快照
        return _dashboard(_store(a.landing), a.landing, html_path=a.html)
    if a.sub == "digest":
        st = _store(a.landing)
        top = sorted(st.entries.values(),
                     key=lambda e: (int(e.get("hits", 1)), float(e.get("liveness", 1.0))),
                     reverse=True)[: a.k]
        return {"stats": st.stats(),
                "top": [{"signature": e.get("signature"), "hits": e.get("hits"),
                         "ts": e.get("ts")} for e in top]}
    if a.sub == "ingest":
        # 冷层入账：签名＝角色＋内容（head#哈希）——
        # 同角色异内容不并账（治粒度丢失），内容可召回（治存得进捞不出）；
        # 同内容再入账仍走同构合并不变。
        # 写入准入（五病#1，前任半成品修正补接）：横幅/信封残片拒收（零入账）；
        # 疑似回声收下打标隔离（不注≠删）。
        text = a.text or ""
        v = admission.classify_text(text, echo=True)
        if v["verdict"] == "reject":
            return {"ingested": False, "id": None, "rejected": v["reason"],
                    "patterns": v["patterns"]}
        head = text[:60]
        act = (head if len(text) <= 60 else
               head + "#" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:8])
        st = _store(a.landing)
        e = st.deposit(
            obj=f"msg:{a.role or '?'}", act=act,
            actual=text[:200], cur="contextEngine.ingest",
            via="contextEngine.ingest")
        st._time_tick()   # 拍改墙钟（2026-11-14）：入账不加拍（写风暴见 deposit 处注）
        if v["verdict"] == "quarantine":
            admission.mark_quarantine(st, e, v["reason"])
            return {"ingested": True, "id": e.get("id"),
                    "quarantined": True, "reason": v["reason"]}
        return {"ingested": True, "id": e.get("id")}
    if a.sub == "commit":
        # 幂等落盘：同 advancementKey 只入账一次（duplicate 判定）
        st = _store(a.landing)
        for e in st.entries.values():
            for p in e.get("provenance", []):
                if p.get("advancementKey") == a.key:
                    return {"status": "duplicate", "id": e.get("id")}
        e = st.deposit(obj="turn", act=a.key or "?",
                       actual=(a.payload or "")[:200], cur="commitTurn",
                       via="contextEngine.commitTurn",
                       extra={"advancementKey": a.key})
        # 衰减节拍并入墙钟（2026-11-14）：入账不加拍——只管排序新鲜度（旧的排后）
        # ＋冷门量控（min_liveness），不删条目；拍=墙钟小时（_time_tick 同拍不同源）
        st._time_tick()
        return {"status": "committed", "id": e.get("id")}
    if a.sub == "preflight":
        from pvs.gate.boot import boot, render  # noqa: E402

        st = _store(a.landing)
        pkg = boot(landing=st, signature="memgate",
                   digest="plugin boot: 三层记忆+门禁接线", root=ws)
        out = {"ok": pkg.get("ok"), "n_fail": pkg.get("n_fail"),
               "n_decl": pkg.get("n_decl"), "rendered": render(pkg)}
        targets = _load_targets(a, ws)
        if targets:
            deps = _run_depscan(targets, st)
            out["deps"] = deps
            out["n_dead"] = deps["dead"]
            out["rendered"] += ("\n\n## 依赖链巡检（S2：真跑探活，声明不算数）\n"
                                f"探 {deps['n']} 条：健康 {deps['healthy']}，死链 {deps['dead']}\n"
                                + "\n".join(f"- {r['id']}: {r['class']}" for r in deps["results"]))
        reg = registry_gate(ws)
        out["registry"] = reg
        out["rendered"] += ("\n\n## 入册门（registry 自动化：未登记的产物视为不存在）\n"
                            f"查 {reg['checked']} 个产物名：未登记 {len(reg['unregistered'])}\n"
                            + "\n".join(f"- {u}: 未登记" for u in reg["unregistered"]))
        return out
    if a.sub == "ledger":
        from pvs.gate.ledger import LESSONS, get_lesson  # noqa: E402

        if a.id:
            return {"lesson": get_lesson(a.id)}
        return {"count": len(LESSONS),
                "lessons": [{"id": l.get("id"), "title": l.get("title")}
                            for l in LESSONS]}
    if a.sub == "constraints":
        # 事前约束（治理纪律面）：治理纲 3 条 + 教训断言 13 条 → 常驻注入上下文组装。
        # 语义：违规动作从"被 preflight 拦"提前到"不被生成"；拦截率下降＝这层在干活。
        from pvs.gate.ledger import LESSONS  # noqa: E402

        lines = list(SCOPE_BANS)
        for l in LESSONS:
            lesson = (l.get("lesson") or "").strip().replace("\n", " ")
            lines.append(f"[{l.get('id')}] {lesson[:100]}")
        return {"lines": lines}
    if a.sub == "depscan":
        return {"deps": _run_depscan(_load_targets(a, ws), _store(a.landing))}

    if a.sub == "version":
        return _version(ws, write=a.write, config_path=a.config, model_path=a.model)
    if a.sub == "compact":
        st = _store(a.landing)
        if _HAS_KERNEL:
            try:
                apply_tiered_decay(st.entries)  # H4 修: 真 API 单参(原 TieredDecay() NameError 死码)
                st.save()  # 衰减改动自带落盘(compact 空搬账早退不 save, 不落会丢)
            except Exception as _e:
                _kernel_warn("tiered_decay", _e)
        return st.compact(liveness_max=a.liveness_max,
                          hits_max=a.hits_max, min_age_days=a.age_days)
    if a.sub == "restore":
        return _store(a.landing).restore(rollup_id=a.id)
    if a.sub == "ping":
        return {"pid": os.getpid(), "mode": "bridge"}
    if a.sub == "observe":
        # 摘要引擎喂料嘴：整轮叙事进缓冲（跨进程持久），满阈自动摘要入账。
        # kind=summary 短路（防双重压缩）；无模型时 fail-soft 底稿兜底。
        # 写入准入（五病#1）：横幅/信封残片拒收（不进摘要管线）；疑似回声隔离。
        v = ({"verdict": "ok", "reason": None, "patterns": []}
             if (a.kind or "narrative") == "summary"
             else admission.classify_text(a.text or "", echo=True))
        if v["verdict"] == "reject":
            return {"observe": {"rejected": v["reason"],
                                "patterns": v["patterns"], "flushed": False}}
        st = _store(a.landing)
        if v["verdict"] == "quarantine":
            # 隔离：收下打标入审计面，但不喂摘要管线（防回声塑形摘要）
            e = st.deposit(obj=f"echo:{a.session or 'bridge'}",
                           act=(a.text or "").strip()[:60] or "-",
                           actual=(a.text or "")[:200],
                           cur="admission.quarantine", via="memgate.admission")
            admission.mark_quarantine(st, e, v["reason"])
            st._time_tick()
            return {"observe": {"quarantined": True, "reason": v["reason"],
                                "entry_id": e.get("id"), "flushed": False}}
        from calldecay.summarize import Summarizer  # noqa: E402
        summ = Summarizer(st, session=a.session or "bridge",
                          summarize_url=a.summarize_url or None,
                          state_path=_summary_buffer(a.landing))
        res = summ.feed(a.text or "", turn_id=a.turn_id,
                        kind=a.kind or "narrative",
                        accumulate=bool(a.accumulate))
        if res.get("entry"):
            # 自动定稿也过条目级准入（词汤/碎片→打标隔离；不注≠删）
            ve = admission.classify_entry(res["entry"])
            if ve["verdict"] != "ok":
                admission.mark_quarantine(st, res["entry"], ve["reason"])
                res["quarantined"] = True
            _bump_activity(landing=a.landing, summary_produced=1)
        return {"observe": res}
    if a.sub == "summarize-flush":
        # 手动定稿入账（来源锚缺省 session:首-末轮；无锚拒收硬闸在 deposit_summary）
        # 写入准入（五病#1）：定稿正文过准入——横幅残片拒收、疑似回声隔离
        from calldecay.summarize import Summarizer  # noqa: E402
        st = _store(a.landing)
        summ = Summarizer(st, session=a.session or "bridge",
                          summarize_url=a.summarize_url or None,
                          state_path=_summary_buffer(a.landing))
        pending = " ".join(t for _, t in getattr(summ, "_turns", []))
        v = admission.classify_text(pending, echo=True)
        if v["verdict"] == "reject":
            # 确定性横幅/信封残片：拒收不落账（攒批轮次原样保留，人工处置）
            return {"entry": None, "rejected": v["reason"],
                    "patterns": v["patterns"]}
        e = summ.flush(source_anchor=a.source_anchor, topic=a.topic)
        if e and isinstance(e, dict) and e.get("id"):
            ve = admission.classify_entry(e)
            if ve["verdict"] != "ok":
                # 不注≠删：已入账碎片/词汤转隔离标（出合格面，审计可查）
                admission.mark_quarantine(
                    st, e, ("flush-reclass: " if ve["verdict"] == "reject" else "")
                    + ve["reason"])
                _bump_activity(landing=a.landing, summary_produced=1)
                return {"entry": e, "quarantined": True, "reason": ve["reason"]}
        _bump_activity(landing=a.landing, summary_produced=(1 if e else 0),
                       flush_empty=(0 if e else 1))
        return {"entry": e}
    if a.sub == "quarantine-mark":
        # 既有污染条目标记/重分类（五病#1 收尾）：默认 dry-run 零写入；
        # --apply 才打标记。不注≠删：只加 admit 字段，条目数/原字段零变化。
        if not a.landing:
            return {"error": "quarantine-mark 需显式 --landing（禁止默认落在生产账本）"}
        st = _store(a.landing)
        r = admission.scan_quarantine(st, apply=bool(a.apply))
        return {"quarantine_mark": r, "dry_run": not a.apply}
    raise UnknownSub(f"unknown sub: {a.sub}")


def _oneshot():
    req = json.load(sys.stdin)
    argv = [str(req.get("sub", "?"))] + [str(x) for x in (req.get("args") or [])]
    try:
        _out(run(build_parser().parse_args(argv)))
    except UnknownSub as e:
        _out({"error": str(e)})
        return 1
    except RuntimeError as e:  # 账本封写等域错：协议化报错（R1 口径＝exit 0＋stderr 报警，不裸奔 traceback）
        _out({"error": f"{type(e).__name__}: {e}"})
        return 0
    return 0


def _serve():
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        rid = None
        try:
            req = json.loads(raw)
            rid = req.get("id")
            argv = [str(req.get("sub", "?"))] + [str(x) for x in (req.get("args") or [])]
            result = run(build_parser().parse_args(argv))
            resp = {"id": rid, "ok": True, "result": result}
        except (Exception, SystemExit) as e:  # noqa: BLE001 —— 单请求失败不杀 worker
            resp = {"id": rid, "ok": False, "error": f"{type(e).__name__}: {e}"}
        print(json.dumps(resp, ensure_ascii=False), flush=True)
    return 0


def main():
    argv = sys.argv[1:]
    if argv == ["--serve"]:
        return _serve()
    if argv == ["--oneshot"]:
        return _oneshot()
    a = build_parser().parse_args()
    try:
        _out(run(a))
    except UnknownSub as e:
        _out({"error": str(e)})
        return 1
    except RuntimeError as e:  # 账本封写等域错：协议化报错（R1 口径＝exit 0＋stderr 报警，不裸奔 traceback）
        _out({"error": f"{type(e).__name__}: {e}"})
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
