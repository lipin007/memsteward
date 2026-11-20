#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M3 试点采集器 v2：试点会话转录 → observe 喂料＋自然查询计数（零模型开销机械采集）。

判据口径（M3 样本触发）：自然查询 ≥30 次且跨 ≥5 话题即判读；负结果照登。
- 自然查询＝试点会话中用户新提问：**先 recall 后 observe**（顺序保证查询不吃自己）
- **内部块过滤**（2026-11-12 口径污染修复）：以 [Subagent Context]/[Subagent Task]/
  OPENCLAW_INTERNAL_CONTEXT/Conversation data 等标记开头的消息＝OpenClaw 内部上下文块，
  不是用户自然提问 ⇒ 不计查询、不喂 observe（实锤: m3_pilot_queries.jsonl rowid 799897）
- 喂料＝全部轮次（user+assistant）进 observe（8KB 闩锁自动定稿，3B 润色 fail-soft 兜底）
- 只读 sqlite（mode=ro），不碰主库写路径

v2（2026-11-12 根因修复——「喂料停滞 3 天＋111 次空刷零产出」两案并一案）：
- **换代跟随**：试点以会话 key 追踪（每轮现解析 session_nodes.current_session_id），
  水位按 session_id 分账；新 id 从 0 补全段（RUN_CAP 分轮消化）。
  根因＝v1 钉死 session id，id 换代后盯历史段空转（34f5a23d/f1e43f73/28c93139
  三个 id 均为历史段，现役流量在 1c382c4a/87d4e152——ID 级 diff/年代指纹实锤）。
- **空转不冲**：本轮没喂料且缓冲无残量 ⇒ 跳过 summarize-flush（治 111 次空刷）。
- **产出计数**：每轮 fed_n/flush_n/produced_n 落痕——「跑没出活」一眼可见。
- **冷源告警**：水位 M3_COLD_HOURS（缺省 24）小时无新料 ⇒ 报「源已冷」；
  新冷源退出码 2（自动化 failureAlert 接住报警），回暖自动复位。

跑法:
  python3 m3_collector.py --backfill   # 灌历史（不计查询，攒轮定稿）
  python3 m3_collector.py              # 收增量（计自然查询）——cron 周期跑
"""
import json
import os
import sqlite3
import subprocess
import sys
import time

DB = os.environ.get("M3_DB", "~/.openclaw/agents/main/agent/openclaw-agent.sqlite")
# 三试点（2026-11-07 用户拍板）：以**会话 key**挂载（v2 起换代跟随）。
# 格式 M3_PILOT_SESSIONS="<key或uuid>:<名>,..." 可覆盖；裸 uuid＝固定追踪（兼容旧用法）。
DEFAULT_PILOTS = (
    "agent:main:dashboard:e5b18b75-d0aa-4754-84a2-d6e6d6b32f9b:arc-prize-v3,"
    "agent:main:dashboard:9efd4ec6-ca77-4fe5-ab2d-e27b80217b4d:patent-9efd,"
    "agent:main:dashboard:38b23173-cb6c-4f9f-85cf-35bc5aa55cd4:midware-main")
COLD_HOURS = float(os.environ.get("M3_COLD_HOURS", "24"))
RUN_CAP = int(os.environ.get("M3_RUN_CAP", "150"))  # 每会话每轮喂料上限（补课分轮消化）

PILOTS = []
for _it in os.environ.get("M3_PILOT_SESSIONS", DEFAULT_PILOTS).split(","):
    _it = _it.strip()
    if _it and ":" in _it:
        # 名字缀在最后一个冒号后（key 本身含冒号，故 rsplit）
        _spec, _name = _it.rsplit(":", 1)
        if _spec.strip():
            PILOTS.append((_spec.strip(), _name.strip()))
BRIDGE = os.environ.get(
    "M3_BRIDGE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "bridge_cli.py"))  # 标准化(2026-11-19): 树内自含, env M3_BRIDGE 可覆盖
STATE = os.path.expanduser(os.environ.get("M3_STATE", os.path.expanduser("~/.memsteward/state/m3_pilot_state.json")))
QLOG = os.path.expanduser(os.environ.get("M3_QLOG", os.path.expanduser("~/.memsteward/state/m3_pilot_queries.jsonl")))
LANDING = os.path.expanduser(os.environ.get(
    "M3_BRIDGE_LANDING", "~/.memsteward/landing/landing.json"))

os.environ.setdefault("SUMMARIZE_URL", "http://127.0.0.1:8083")  # 3B 非 thinking

# 内部块标记（2026-11-12）：首行以这些标记开头的消息＝OpenClaw 内部上下文块/子代理路由块，
# 非用户自然提问。前缀匹配（首行判定），真实提问只要不以标记开头照常放行。
INTERNAL_BLOCK_MARKERS = (
    "[Subagent Context]",
    "[Subagent Task]",
    "OPENCLAW_INTERNAL_CONTEXT",
    "<<<BEGIN_OPENCLAW_INTERNAL_CONTEXT>>>",
    "<<<END_OPENCLAW_INTERNAL_CONTEXT>>>",
    "Conversation data",
)


def is_internal_block(text):
    """首条非空行以内部块标记开头 ⇒ 内部块（拒）；否则用户自然提问（放行）。"""
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        return line.startswith(INTERNAL_BLOCK_MARKERS)
    return False


def load_state():
    try:
        s = json.load(open(STATE, encoding="utf-8"))
    except Exception:
        s = {"sessions": {}}
    s.setdefault("sessions", {})
    s.setdefault("fed", 0)
    s.setdefault("queries", 0)
    for sv in s["sessions"].values():
        sv.pop("fresh", None)   # v1 遗留旗：v2 无用
    return s


def save_state(s):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = f"{STATE}.tmp.{os.getpid()}.{os.urandom(3).hex()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    os.replace(tmp, STATE)


def bridge(*args):
    r = subprocess.run([sys.executable, BRIDGE, *args],
                       capture_output=True, text=True, timeout=180)
    try:
        return json.loads(r.stdout or "{}")
    except Exception:
        return {"err": (r.stdout or "")[:120] + "|" + (r.stderr or "")[:120]}


def resolve_sid(con, spec):
    """会话 key → 现役 session_id（换代跟随）；裸 uuid 原样返回（固定追踪）。"""
    if not spec.startswith("agent:"):
        return spec
    row = con.execute(
        "SELECT current_session_id FROM session_nodes WHERE session_key=? LIMIT 1",
        (spec,)).fetchone()
    return (row[0] if row and row[0] else None)


def main():
    backfill = "--backfill" in sys.argv
    st = load_state()
    st.setdefault("fed_mids", [])
    fed_mid_set = set(st["fed_mids"])
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    now_ms = int(time.time() * 1000)
    fed_n = flush_n = produced_n = 0
    cold_alerts = []
    for spec, sname in PILOTS:
        sid = resolve_sid(con, spec)
        if not sid:
            print(f"[跳过·{sname}] key 解析不到现役 session_id（会话可能未开/已清）")
            continue
        # 水位按 session_id 分账：新 id 从 0 补全段（换代补课），老 id 沿用旧水位
        sv = st["sessions"].setdefault(sid, {"rowid": 0, "turn": 0,
                                            "last_feed_ms": now_ms})
        sv.setdefault("turn", 0)
        sv.setdefault("last_feed_ms", now_ms)
        sv.setdefault("first_seen_ms", now_ms)   # 查询计数以此为界（补课旧行不计）
        rows = con.execute(
            "SELECT rowid, role, text, timestamp, message_id FROM session_transcript_fts "
            "WHERE session_id=? AND rowid>? ORDER BY rowid LIMIT ?",
            (sid, sv.get("rowid", 0), RUN_CAP)).fetchall()
        if rows:
            print(f"[{'灌历史' if backfill else '收增量'}·{sname}/{sid[:12]}] "
                  f"{len(rows)} 条新消息（自 rowid {sv.get('rowid', 0)}）")
        else:
            print(f"[无新消息·{sname}/{sid[:12]}]"
                  + ("（空转不冲）" if not fed_n else ""))
        # 喂料档位：回灌/大批量＝攒轮定稿（不计查询）；日常＝逐轮编译＋计自然查询
        accumulate = backfill or len(rows) > 20
        sess_fed = 0
        for rowid, role, text, rts, mid in rows:
            # 同文去重（平行流共享 message_id，如专利双流 394 重叠）：近期窗口查重，中即跳
            if mid and mid in fed_mid_set:
                sv["rowid"] = rowid
                continue
            # 自然查询口径：仅计 first_seen_ms 之后的新提问（补课旧行不污染 M3 计数）
            count_q = (not backfill) and (
                int(float(rts or 0)) >= int(sv.get("first_seen_ms", 0)))
            text = (text or "").strip()
            sv["rowid"] = rowid
            if not text:
                continue
            if is_internal_block(text):
                # 内部块污染过滤（2026-11-12）：不计自然查询、不喂 observe（水位已推，只跳本行）
                continue
            if count_q and role == "user":
                # 自然查询：先 recall（吃既有记忆），再 observe（防吃自己）
                q = text[:200].replace("\n", " ")
                r = bridge("recall", "--signature", q, "--k", "6")
                hits = r.get("hits") or []
                summ = [h for h in hits
                        if (h.get("entry") or {}).get("kind") == "summary"]
                rec = {"rowid": rowid, "session": sid, "query": q,
                       "hits": len(hits), "summary_hits": len(summ)}
                os.makedirs(os.path.dirname(QLOG), exist_ok=True)
                with open(QLOG, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                st["queries"] += 1
            sv["turn"] = sv.get("turn", 0) + 1
            obs = ["--text", text[:4000], "--session", sname,
                   "--turn-id", str(sv["turn"])]
            if accumulate:
                obs.append("--accumulate")   # 攒轮：满闩锁/收尾才定稿
            r = bridge("observe", *obs)
            if mid:
                fed_mid_set.add(mid)
                st["fed_mids"].append(mid)
            if (r.get("observe") or {}).get("entry"):
                produced_n += 1
            st["fed"] += 1
            fed_n += 1
            sess_fed += 1
            if st["fed"] % 50 == 0:
                save_state(st)
        if sess_fed:
            sv["last_feed_ms"] = now_ms
            sv.pop("cold_alerted", None)
        # 收尾定稿：空转不冲（v2），但缓冲有残量仍冲（防丢）；本轮有喂料必冲
        need_flush = bool(sess_fed)
        if not need_flush:
            try:
                b = json.load(open(os.path.join(
                    os.path.dirname(LANDING), "summarize-buffer.json"),
                    encoding="utf-8"))
                need_flush = bool(b.get("turns"))
            except Exception:
                pass
        if need_flush:
            e = bridge("summarize-flush", "--session", sname)
            flush_n += 1
            ent = e.get("entry") if isinstance(e, dict) else None
            if ent:
                produced_n += 1
                print(f"收尾定稿·{sname}: {ent.get('id', '')[:12]} "
                      f"body={len(ent.get('body', ''))}字 anchor={ent.get('source_anchor')}")
        # 冷源告警：水位 COLD_HOURS 小时无新料 ⇒ 报「源已冷」（新冷源退出码 2）
        idle_h = (now_ms - int(sv.get("last_feed_ms") or now_ms)) / 3_600_000
        if idle_h >= COLD_HOURS:
            if not sv.get("cold_alerted"):
                sv["cold_alerted"] = now_ms
                cold_alerts.append(f"{sname}（已 {idle_h:.1f}h 无新料，sid={sid[:12]}）")
            print(f"⚠ [冷源·{sname}] 水位 {idle_h:.1f}h 未动——源可能停更/结束")
        else:
            sv.pop("cold_alerted", None)
    con.close()
    st["fed_mids"] = st["fed_mids"][-2000:]   # 窗口封顶，state 不膨胀
    save_state(st)
    print(f"本轮计数: fed_n={fed_n} flush_n={flush_n} produced_n={produced_n} "
          f"｜累计 fed={st['fed']} queries={st['queries']}")
    if cold_alerts:
        print("⚠ 源已冷: " + "; ".join(cold_alerts))
        sys.exit(2)   # 新冷源＝退出码 2，交自动化 failureAlert 报警


if __name__ == "__main__":
    main()
