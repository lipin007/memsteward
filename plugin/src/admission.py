# -*- coding: utf-8 -*-
"""admission —— MemGate 写入侧准入过滤（五病成熟度缺口 #1：治「回声污染合格面」）。

设计原则
- 不注≠删：**绝不删除任何既有条目**。本模块只判新写入（拒收/隔离）；
  既有条目只由 `quarantine-mark` 子命令**显式 opt-in** 打标记（默认 dry-run）。
- 拒收（reject）＝确定性横幅/信封残片——剥掉已知传输铬后残余 < REJECT_RESIDUAL_MAX，
  这类文本不是记忆内容而是传输外壳，写入即污染，返回明确原因。
- 隔离（quarantine）＝疑似回声/污染——收下写入但打 `admit="quarantine"` 标记，
  默认出召回合格面；审计面（--include-transcripts / --audit-quarantine）可查。

垃圾模式清单（全部实据锚定，见 experiments/对照臂_20261112/ledger_copy.json；
计数可由 experiments/写入准入_20261112/pattern_scan.py 重跑）：
  inter_session_envelope   [Inter-session message] 传输信封头
                           实据 b6b9f025 / 9fa9ac6e / d08e657f / c2184276（summary 体）
  exec_completion_banner   [OpenClaw exec completion] 运行横幅
                           实据 318ae811（body=「OpenClaw」即该横幅的词汤摘要）
  session_event_banner     [OpenClaw session event] 会话事件横幅
                           实据 5d53c6d0 / b7e9974e（commitTurn/ingest 转录）
  subagent_context_banner  [Subagent Context] 子代理上下文横幅
                           实据 807432dd / 5d2db2bc
  internal_context_tag     <<<BEGIN/END_OPENCLAW_INTERNAL_CONTEXT>>> 信封头尾标签
                           实据 ffe0d935（body 词汤含 BEGIN_/END_ 残片）
  prompt_data_tag          <prompt-data> 传输信封标签（任务给定；
                           账本字面 0 命中——负结果照登，防御性收录）
  section_banner           ===X=== 分节横幅（===GAMEARG=== / ===END=== 实据
                           aca974bc / 0825ca4e；===LOG===/===CURL===/===GIT===
                           同族但账本 0 命中——负结果照登）
  envelope_header_fields   sourceSession=/sourceChannel=/sourceTool=/isUser= 信封字段
                           实据同 inter_session 族
  envelope_key_token       sourceSession 等裸键名词汤（无 = 值）
                           实据 b6b9f025 body 词汤
  routed_boilerplate       This content was routed by OpenClaw… 路由样板句
                           实据 probe_gap24 qi38 题源 / b6b9f025 族
  chrome_word_soup         横幅词序打乱后的词汤（无 CJK 且全部单词落在已知横幅
                           词集内）实据 318ae811 signature=「completion OpenClaw exec」
  echo_fragment            超短回声碎片（≤ ECHO_MAX_CHARS 字符）
                           实据 0504f503=「测」/ 92626deb=「好」/ 1935b2f8=「那就开测吧」
"""

import json
import re
import time

# 剥铬后残余 < 该值 ⇒ 拒收（确定性残片）；≥ 该值 ⇒ 隔离（混了实质内容）
REJECT_RESIDUAL_MAX = 20
# 超短回声碎片阈（实据最大 5 字符「那就开测吧」，留 1 字符余量）
ECHO_MAX_CHARS = 6

CHROME_RULES = [
    ("inter_session_envelope", re.compile(r"\[Inter-session message\]")),
    ("exec_completion_banner", re.compile(r"\[OpenClaw exec completion\]")),
    ("session_event_banner", re.compile(r"\[OpenClaw session event\]")),
    ("subagent_context_banner", re.compile(r"\[Subagent Context\]")),
    ("internal_context_tag",
     re.compile(r"<<<(?:BEGIN|END)_OPENCLAW_INTERNAL_CONTEXT>>>|"
                r"(?:BEGIN|END)_OPENCLAW_INTERNAL_CONTEXT")),
    ("prompt_data_tag", re.compile(r"</?prompt-data>")),
    ("section_banner", re.compile(r"===\w+===")),
    ("envelope_header_fields",
     re.compile(r"(?:sourceSession|sourceChannel|sourceTool|isUser)=\S+")),
    ("envelope_key_token",
     re.compile(r"\b(?:sourceSession|sourceChannel|sourceTool|sessions_send|isUser)\b")),
    ("routed_boilerplate", re.compile(r"This content was routed by OpenClaw[^\n]*")),
]

# 词汤判据的横幅词集（chrome_word_soup：文本单词全部落在某一横幅词集内）
CHROME_PHRASES = [
    "[OpenClaw exec completion]",
    "[Inter-session message]",
    "[Subagent Context]",
    "[OpenClaw session event]",
    "This content was routed by OpenClaw from another session",
]
CHROME_WORDSETS = [frozenset(re.findall(r"[a-z]+", p.lower())) for p in CHROME_PHRASES]

_STRIP_RESIDUAL = re.compile(
    r"[\s，。；：、,.:;|/\\()\[\]{}<>\"'`~!?？！…—\-+*=#@$%^&]+")
_CJK = re.compile(r"[\u4e00-\u9fff]")


def strip_chrome(text):
    """剥掉已知传输铬（横幅/信封/标签/字段/样板句）→ (残余长度, 命中模式名列表)。"""
    s = str(text or "")
    hits = []
    for name, rx in CHROME_RULES:
        if rx.search(s):
            hits.append(name)
            s = rx.sub(" ", s)
    residual = _STRIP_RESIDUAL.sub("", s)
    return len(residual), hits


def _word_soup(text):
    """词汤判据（实据 318ae811）：纯 ASCII 且全部单词落在某一横幅词集内。"""
    s = str(text or "")
    if not s.strip() or _CJK.search(s):
        return False
    words = set(re.findall(r"[a-z]+", s.lower()))
    return bool(words) and any(words <= cw for cw in CHROME_WORDSETS)


def classify_text(text, echo=False, soup_text=None):
    """对自由文本下准入判定。

    echo=True 时启用超短回声碎片规则（observe 轮次/摘要正文这类对话文本）；
    soup_text 覆盖词汤判据的输入（条目分类时排除 base 骨架词干扰）。"""
    s = str(text or "")
    if not s.strip():
        return {"verdict": "ok", "patterns": [], "reason": None, "residual_len": 0}
    residual, hits = strip_chrome(s)
    if hits:
        if residual < REJECT_RESIDUAL_MAX:
            return {"verdict": "reject", "patterns": hits,
                    "reason": (f"传输横幅/信封残片（{','.join(hits)}），"
                               f"剥除后残余 {residual} 字符 < {REJECT_RESIDUAL_MAX}"),
                    "residual_len": residual}
        return {"verdict": "quarantine", "patterns": hits,
                "reason": (f"传输铬混实质内容（{','.join(hits)}）→ 疑似回声污染，"
                           f"收下隔离（残余 {residual} 字符）"),
                "residual_len": residual}
    if _word_soup(soup_text if soup_text is not None else s):
        return {"verdict": "quarantine", "patterns": ["chrome_word_soup"],
                "reason": "横幅词汤（单词全部落在已知横幅词集）→ 疑似横幅回声",
                "residual_len": residual}
    if echo and len(s.strip()) <= ECHO_MAX_CHARS:
        return {"verdict": "quarantine", "patterns": ["echo_fragment"],
                "reason": (f"超短回声碎片（{len(s.strip())} 字符 "
                           f"≤ {ECHO_MAX_CHARS}）→ 疑似对话回声"),
                "residual_len": residual}
    return {"verdict": "ok", "patterns": [], "reason": None, "residual_len": residual}


def classify_entry(e):
    """对账本条目下准入判定（quarantine-mark 复核用；不改条目）。

    chrome 判据看全字段（含 base 词面）；词汤判据只看内容字段（base 骨架词会
    干扰子集判定——实据 318ae811 的 base 含 decision/number 等骨架键）；
    回声判据只看 body（实据 0504f503/92626deb/1935b2f8 均为短 body 摘要）。"""
    content = " ".join(str(e.get(k) or "")
                       for k in ("obj", "act", "actual", "signature", "topic", "body"))
    blob = content
    b = e.get("base")
    if b:
        try:
            blob += " " + json.dumps(b, ensure_ascii=False)
        except (TypeError, ValueError):
            pass
    v = classify_text(blob, echo=False, soup_text=content)
    if v["verdict"] != "ok":
        return v
    body = str(e.get("body") or "").strip()
    if body and len(body) <= ECHO_MAX_CHARS:
        return {"verdict": "quarantine", "patterns": ["echo_fragment"],
                "reason": (f"疑似回声碎片（body {len(body)} 字符 "
                           f"≤ {ECHO_MAX_CHARS}）"),
                "residual_len": v.get("residual_len", 0)}
    return v


def is_quarantined(e):
    """隔离标记判定（recall 合格面过滤用）。"""
    return str((e or {}).get("admit") or "") == "quarantine"


def mark_quarantine(store, entry, reason, by="admission", save=True):
    """打隔离标记（标记≠删除；原字段逐字保留）。"""
    entry["admit"] = "quarantine"
    entry["admit_reason"] = str(reason or "")[:200]
    entry["admit_ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    entry["admit_by"] = by
    if save:
        store.save()
    return entry


def scan_quarantine(store, apply=False, sample_limit=20):
    """既有条目复核（quarantine-mark 子命令后端）。

    默认 dry-run：只报告，零写入；apply=True 才打标记（只加字段，不删不改）。"""
    report = {"scanned": 0, "matched": 0, "applied": 0, "already": 0,
              "by_pattern": {}, "samples": []}
    matches = []
    for e in store.entries.values():
        report["scanned"] += 1
        if is_quarantined(e):
            report["already"] += 1
            continue
        v = classify_entry(e)
        if v["verdict"] == "ok":
            continue
        report["matched"] += 1
        for p in (v["patterns"] or ["unknown"]):
            report["by_pattern"][p] = report["by_pattern"].get(p, 0) + 1
        if len(report["samples"]) < sample_limit:
            report["samples"].append({
                "id": str(e.get("id"))[:16],
                "verdict": v["verdict"], "patterns": v["patterns"],
                "excerpt": str(e.get("body") or e.get("signature") or "")[:80]})
        matches.append((e, v))
    if apply:
        for e, v in matches:
            mark_quarantine(store, e, "reclass:" + (v["reason"] or ""),
                            by="quarantine-mark", save=False)
            report["applied"] += 1
        if matches:
            store.save()   # 只增标记字段；条目数/原字段零变化（不注≠删）
    return report
