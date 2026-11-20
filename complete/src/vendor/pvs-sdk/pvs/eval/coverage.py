# -*- coding: utf-8 -*-
"""pvs.eval.coverage —— 三分账评测件（整合施工方案_v1.md C 段）——治"池挖掘自欺"。

三分账：直解(direct) / 搜索(chain) / 库外(out) ＋ **同源命中剔除**（same_source）。
移植母本：arc-agi-2/tools/coverage_report.py（战场三分账：直解48/链0/库外192）。

两定律入评测纪律（任何评测报告必须带这两行声明）：
  L-POOL 池挖掘定律：评测池被收割过的命中是假命中——同源命中（规则来源题==被解题）
    必须剔除后再算泛化率。战场实锤：22% 名义命中 96.7% 是同源件，真跨题仅 13/240≈5%。
  L-STRUCT 结构定律：LLM 猜机制，结构错则分永远 0——评测时结构正确性 > 候选数量。
    战场实锤：27B 提假设过 admit 7 次、demo 门 0/7；0/26 题。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

LAW_POOL_MINING = ("L-POOL 池挖掘定律: 同源命中=假命中, 泛化率必须剔同源后计算")
LAW_STRUCTURE = ("L-STRUCT 结构定律: 结构错则永远 0, 结构正确性 > 候选数量")


def three_way_account(hits: Iterable[dict]) -> dict:
    """三分账：hits=[{source_task, hit_task, kind: direct|chain, ...}]。
    同源命中（source_task==hit_task）单列，不算泛化。
    返回 {n, direct, chain, out_note, same_source, cross_source, nominal_rate, true_rate}。"""
    rows = list(hits)
    n = len(rows)
    direct = sum(1 for r in rows if r.get("kind") == "direct")
    chain = sum(1 for r in rows if r.get("kind") == "chain")
    same = [r for r in rows if r.get("source_task") and r.get("source_task") == r.get("hit_task")]
    same_n = len(same)
    cross_n = n - same_n
    return {
        "n": n, "direct": direct, "chain": chain, "same_source": same_n,
        "cross_source": cross_n,
        "nominal_rate": round(n and (direct + chain) / n or 0.0, 4),
        "true_rate": round(n and cross_n / n or 0.0, 4),   # 剔同源后真泛化
        "pool_mining_ratio": round(n and same_n / max(1, direct + chain) or 0.0, 4),
        "laws": [LAW_POOL_MINING, LAW_STRUCTURE],
    }


def audit_memory(entries: Iterable[dict]) -> dict:
    """自审账本（C2 第一个吃螃蟹=我们自己）：覆盖率/同源率/缺口清单。
    entries=[{rule_id, signature, provenance, verify, source_task, ...}]
    - 覆盖率 completeness = 四字段齐全（signature/provenance/verify/source_task）
    - 同源率 = 派生自"它自己解决的那道题"的条目占比（池挖掘在自家账本里的份额）
      判据：provenance.via 含 register/induction 且 source_task 非空 ⇒ 自产自销（same_source 候选）
    - 缺口清单 = 缺字段/无签名/无验证的条目 id
    """
    es = [dict(e) for e in entries]
    n = len(es)
    if n == 0:
        return {"n": 0, "coverage": 0.0, "same_source_rate": 0.0, "gaps": ["账本为空"],
                "laws": [LAW_POOL_MINING, LAW_STRUCTURE]}
    gaps: List[str] = []
    complete = 0
    same = 0
    for e in es:
        rid = e.get("rule_id") or e.get("id") or "?"
        sig = e.get("signature")
        prov = e.get("provenance")
        verify = e.get("verify")
        st = e.get("source_task")
        missing = [k for k, v in (("signature", sig), ("provenance", prov),
                                  ("verify", verify), ("source_task", st)) if not v]
        if not missing:
            complete += 1
        else:
            gaps.append(f"{rid} 缺 {','.join(missing)}")
        via = str((prov or {}).get("via", "")) if isinstance(prov, dict) else str(prov or "")
        if st and ("induction_loop" in via or "register" in via or "induced" in via):
            same += 1                       # 自产自销: 来源题==自己解的题 ⇒ 池挖掘嫌疑
    return {
        "n": n,
        "coverage": round(complete / n, 4),
        "same_source": same,
        "same_source_rate": round(same / n, 4),
        "cross_source": n - same,
        "gaps": gaps[:40],
        "gap_n": len(gaps),
        "laws": [LAW_POOL_MINING, LAW_STRUCTURE],
    }
