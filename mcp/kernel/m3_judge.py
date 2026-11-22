#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M3 判读·三分账（34号「池挖掘三分账评测」口径移植，2026-11-07）。

判据先行（J1–J6；断言见 CallDecay/sdk/tests/test_m3_judge.py）：
J1  回声同源：转录层命中且与查询同文 → 剔除（查询撞自己的投递件）。
J2  自消化同源：摘要锚区间含查询自身轮次 → 剔除（把问题自己抄进记忆）。
J2b 未来件：摘要锚完全晚于查询轮次 → 剔除分列（查询发生时不可得，
    含其答复衍生线——记忆里有答案只因问题催生了它，恰是 34 号
    「名义命中≈22%、同源占 96.7%、真泛化≈5%」要抓的自欺）。
J3  直取：有效命中恰 1 件。J4 组合链：≥2 件。J5 库外：0 件。
    有效命中＝严格先行（锚尾 < 查询轮次；无锚件按 ts 先于查询 ts）。
J6  口径：有效命中率＝(直取+组合链)/总查询；回声/自消化/未来件/转录他文/
    未判分列不入账；旧口径 hits 仅作对照（名义≠有效）。

时间可得性原则（J2b 的依据）：记忆只能用查询当刻已存在的内容答题——
后来才digest 的内容无论多相关都不该记作「记忆答对」。

读审计：生产账快照到临时副本再跑 recall（保活副作用不落生产）。
判读侧污染收尾（2026-11-12）：采集侧 m3_collector 已滤 OpenClaw 内部块
（INTERNAL_BLOCK_MARKERS/is_internal_block），历史账里已标注 internal_polluted=true
的行判读侧同剔——不判读、不计入 queries 计数与 M3 ≥30 次门槛。
跑法: python3 m3_judge.py
"""
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SDK = os.path.abspath(os.path.join(HERE, "..", "..", "CallDecay", "sdk"))
sys.path.insert(0, SDK)

from calldecay.landing import LandingStore                 # noqa: E402

QLOG = os.path.expanduser(os.environ.get(
    "M3_QLOG", "~/.calldecacy/m3_pilot_queries.jsonl"))
LEDGER = os.path.expanduser(os.environ.get(
    "M3_LEDGER", "~/.calldecacy/landing.json"))
DB = os.environ.get("M3_DB",
    "file:~/.openclaw/agents/main/agent/openclaw-agent.sqlite?mode=ro")
SESSION = os.environ.get("M3_SESSION", "f1e43f73-1718-488d-9411-549af831bdf9")
K = 10


def norm(s) -> str:
    return re.sub(r"\s+", "", str(s or "")).strip().lower()


def t19(s) -> str:
    return str(s or "").strip()[:19]


def to_epoch(s):
    """ts 归一（2026-11-09 量具修复，L10 第 5 次同型错误留痕）：epoch 浮点/epoch
    串/ISO 串三形归一到 epoch 秒。旧 t19 字典序拿 ISO vs epoch 直比，'2'>'1' ⇒
    一切记忆都判'未来'——第六格'时间锁'结论即此假象，已出勘误。"""
    if s is None or s == "":
        return None
    try:
        v = float(s)
        while v > 1e11:          # 量纲归一：ms/µs 混装实锤（1.79e12 ms 同列 1.79e9 s）
            v /= 1000.0
        return v
    except (TypeError, ValueError):
        pass
    try:
        return float(__import__("time").mktime(
            __import__("time").strptime(str(s)[:19], "%Y-%m-%dT%H:%M:%S")))
    except (ValueError, OverflowError):
        return None


def parse_anchor(a):
    m = re.search(r":(\d+)-(\d+)$", str(a or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def classify(query, query_turn, query_ts, hits, query_label=None):
    """三分账分类（纯函数，J1–J6 断言点）。

    query_label（2026-11-09 P5 合入，第六格实锤）：传入时（含空串），锚前缀≠
    它的条目剥锚走全局 ts 可比路径——跨会话 turn 秩不可比（span 1-24<rank 30
    是数字巧合不是先于查询，假有效实锤）。None＝旧行为（span 全量，A/B 对照用）。"""
    q = norm(query)
    echo = selfdig = future = raw = unjudged = 0
    eff = []
    for h in hits:
        e = h.get("entry") or {}
        # ── J1/J6：转录层（回声剔除 / 他文单列，不入记忆账）──
        if (h.get("class") or "") == "transcript":
            na = norm(e.get("act"))
            if na and (na == q or (min(len(na), len(q)) >= 8
                                   and (na in q or q in na))):
                echo += 1
            else:
                raw += 1
            continue
        span = parse_anchor(e.get("source_anchor"))
        # ── P5：跨会话锚剥锚走 ts 可比路径（剥锚≠删条目，只是换可比尺）──
        if span and query_label is not None and \
                str(e.get("source_anchor") or "").split(":")[0] != str(query_label):
            span = None
        # ── 有锚摘要：时间可得性（J2/J2b/J3-J5）──
        if span:
            if query_turn is None:
                unjudged += 1
                continue
            lo, hi = span
            if lo <= query_turn <= hi:
                selfdig += 1              # J2 自消化
                continue
            if lo > query_turn:
                future += 1               # J2b 未来件（含答复衍生线）
                continue
            eff.append(e)                 # 严格先行 → 有效候选
            continue
        # ── 无锚件（决策/沉淀层）：按 epoch 秒先后判（to_epoch 归一）──
        ets, qts = to_epoch(e.get("ts")), to_epoch(query_ts)
        if ets is None or qts is None:
            unjudged += 1
            continue
        if ets < qts:
            eff.append(e)
        else:
            future += 1
    n = len(eff)
    account = "库外" if n == 0 else ("直取" if n == 1 else "组合链")   # J3/J4/J5
    return {"account": account, "effective": n, "echo": echo,
            "selfdig": selfdig, "future": future, "raw": raw,
            "unjudged": unjudged,
            "eff_ids": [str(e.get("id", ""))[:8] for e in eff]}


def self_cert(rows):
    """37号报单自证：收单方不采信报单——逐行独立重算三项对账（账目/标签/剔除）。"""
    bad = [r for r in rows
           if (r["account"] == "直取") != (r["effective"] == 1)
           or (r["account"] == "组合链") != (r["effective"] >= 2)
           or (r["account"] == "库外") != (r["effective"] == 0)
           or (r["effective"] + r["echo"] + r["selfdig"] + r["future"]
               + r["raw"] + r["unjudged"]) < 0]
    return {"ok": not bad, "bad": len(bad), "rows": len(rows)}


def main() -> int:
    all_recs = [json.loads(l) for l in open(QLOG, encoding="utf-8") if l.strip()]
    # 判读侧收尾（2026-11-12）：剔除已标注 internal_polluted=true 的内部块污染行
    # （OpenClaw 内部块混入采集账，非自然查询）——不判读、不计入 queries 计数
    # 与 M3 ≥30 次门槛。采集侧过滤见 m3_collector.is_internal_block。
    recs = [r for r in all_recs if not r.get("internal_polluted")]
    n_polluted = len(all_recs) - len(recs)
    con = sqlite3.connect(DB, uri=True)
    rows_db = con.execute(
        "SELECT rowid, session_id, timestamp FROM session_transcript_fts "
        "ORDER BY session_id, rowid").fetchall()
    con.close()
    # 多会话全覆盖（2026-11-09 ①：查询日志横跨 3 会话，单会话映射致 149 未判）
    rank, ts_map, _cnt = {}, {}, {}
    for rid, sid, ts in rows_db:
        _cnt[sid] = _cnt.get(sid, 0) + 1
        rank[rid] = _cnt[sid]          # turn ＝ 会话内行秩（各自计）
        ts_map[rid] = ts

    tmp = tempfile.mkdtemp(prefix="m3judge_")             # 读审计：快照副本
    snap = os.path.join(tmp, "landing.json")
    shutil.copyfile(LEDGER, snap)
    st = LandingStore(path=snap)

    out = []
    for rec in recs:
        q = rec.get("query", "")
        rid = rec.get("rowid")
        hits = st.recall(q, k=K, include_transcripts=True)
        c = classify(q, rank.get(rid), ts_map.get(rid), hits,
                     query_label=os.environ.get("M3_QUERY_LABEL", ""))
        c["q"] = q
        c["old"] = rec.get("hits", 0)
        out.append(c)

    tot = len(out)
    nd = sum(1 for r in out if r["account"] == "直取")
    nc = sum(1 for r in out if r["account"] == "组合链")
    no = sum(1 for r in out if r["account"] == "库外")
    print("== M3 三分账（34号口径·时间可得性原则）==")
    if n_polluted:
        print(f"内部块污染行剔除: {n_polluted}（internal_polluted 标注·不判读·不计入计数）")
    for i, r in enumerate(out, 1):
        print(f"{i:2d}.[{r['account']:>2}] eff={r['effective']} 回声={r['echo']} "
              f"自消={r['selfdig']} 未来={r['future']} 他文={r['raw']} "
              f"未判={r['unjudged']} 旧={r['old']} | {r['q'][:26]}")
    print(f"三账: 直取 {nd} | 组合链 {nc} | 库外 {no}")
    print(f"剔除分列: 回声 {sum(r['echo'] for r in out)} "
          f"自消化 {sum(r['selfdig'] for r in out)} "
          f"未来件 {sum(r['future'] for r in out)} "
          f"转录他文 {sum(r['raw'] for r in out)} "
          f"未判 {sum(r['unjudged'] for r in out)}")
    rate = (nd + nc) / tot if tot else 0.0
    old_nom = sum(1 for r in out if r["old"] > 0)
    print(f"有效命中率(同源剔除后): {nd + nc}/{tot} = {rate:.1%}")
    print(f"旧口径对照: 名义命中 {old_nom}/{tot}（含同源——名义≠有效）")
    cert = self_cert(out)
    if not cert["ok"]:
        print("JUDGE-BROKEN: 报单与账目不符", cert, "——本报告不可信")
        return 2
    print(f"自证: {cert['rows']} 行逐项对账一致（报单不采信·独立重算）")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
