# -*- coding: utf-8 -*-
"""M2 概念空间本体 — 四类原生结构视图 (V3 图纸 M2 移植, 2026-08-12)

图纸: plan/modules/M2-概念空间本体.md
M2 = 主动演化的认知本体 (从事件学习、参与主链、持有因果结构);
M7 = 被动派生视图 (事件流只读投影)。两者根本区别。

四类原生结构:
  ObjectC   — 对象概念 (id/维度槽/动作偏好/类别/时间锚)
  ActionC   — 动作概念 (id/前置条件/效果)
  CauseEdge — 因果边 (src/dst/kind/evidence/last_seen/confidence)
  Dim       — 状态维度 (name/values/emerged_from/evidence)

C2 修复 (单一存储): 概念 = 一条记录, 结构槽位 + 相位字段共存。
施工: 本模块 = 类型化视图层 — 结构数据本体 = 实验体既有存储
(events/types/causal_edges = 学习成果单份), 相位 = 既有相位场,
视图经 id 联合访问, 零复制零双写。文件分离 ≠ 数据分离。

铁律:
  - 零预载: category=None / act_pref 空 / dims 空 (涌现前只有 id+时间锚)
  - 时间属性单点: activity/maturity/coherence/phase 全部经 M3 相位场查询,
    本模块结构记录中无副本 (防双写)
  - 纯结构管理: align/query 只查只建, 不统计不判定 (三铁律)
  - 零语言依赖: 本模块不 import tokenizer/word_bind/ask/PMI
"""
from typing import Dict, List, Optional, Set, Tuple


class ObjectC:
    """对象概念 — 结构骨架 (M2 域), 无相位字段 (归 M3)"""

    def __init__(self, obj_id: str, t: int):
        self.id = obj_id
        self.dims: Dict[str, 'Dim'] = {}      # 状态维度槽 (状态进观察通道)
        self.act_pref: Dict[str, float] = {}  # 动作偏好 (涌现填充, 初始空)
        self.category: Optional[str] = None   # 类别标签 (涌现填充, 不预载!)
        self.first_seen: int = t              # 首次出现 t (身份时间锚)
        self.last_seen: int = t               # 最近出现 t

    def __repr__(self):
        return (f"ObjectC({self.id}, act_pref={dict(self.act_pref)}, "
                f"cat={self.category}, dims={list(self.dims)})")


class ActionC:
    """动作概念 — 结构骨架 (M2 域), 无相位字段"""

    def __init__(self, act_id: str, t: int):
        self.id = act_id
        self.pre: Tuple = ()      # 前置状态条件 ((dim, value), ...)
        self.effect: Tuple = ()   # 效果 ((dim, new_value), ...)


class CauseEdge:
    """因果边 — 证据时效三件套"""

    def __init__(self, src: str, dst: str, kind: str,
                 evidence: int = 1, last_seen: int = 0,
                 confidence: float = 0.0):
        self.src = src
        self.dst = dst
        self.kind = kind          # 'action' | 'state' | 'dmit'
        self.evidence = evidence  # 证据计数 (累积)
        self.last_seen = last_seen  # 最近证据 t
        self.confidence = confidence  # 可信度 (消费端过滤死边)


class Dim:
    """状态维度 — 预测失败涌现的隐藏维度"""

    def __init__(self, name: str, emerged_from: str = '', evidence: int = 1,
                 last_seen: int = 0):
        self.name = name
        self.values: Set[str] = set()   # 已观察值集合
        self.emerged_from = emerged_from  # 涌现来源 (哪类预测失败冲突)
        self.evidence = evidence
        self.last_seen = last_seen


class ConceptStore:
    """概念空间本体视图 — 四类结构 + 相位联合访问 (单一存储)

    数据本体 = 注入的 ConceptSpace 既有存储 (学习成果单份);
    本类只提供类型化视图 (ObjectC/ActionC/CauseEdge/Dim), 零复制。
    M2 写结构字段 (经概念空间既有学习路径), M3 写相位 (经相位场),
    本视图只读联合 — 字段域分工, 不双写。
    """

    def __init__(self, cs):
        self.cs = cs

    # ── 联合访问: ObjectC = 结构 + 相位 (M3 读出) ────────────
    def get(self, concept_id: str, t: int = 0) -> Optional[ObjectC]:
        """按 id 取概念记录 (结构槽位 + 经 M3 读出的相位)"""
        cs = self.cs
        # 结构域: 事件计数/类型 (学习成果)
        acts = {}
        for (p, a, o), cnt in getattr(cs, 'events', {}).items():
            if p == concept_id:
                acts[a] = acts.get(a, 0) + cnt
        obj = ObjectC(concept_id, t)
        obj.act_pref = acts
        # 维度域: emergence state_dims (若有)
        em = getattr(cs, 'emergence', None)
        if em is not None:
            dims = getattr(em, 'state_dims', {})
            pf = getattr(em, '_pred_fail', {}) or {}
            if isinstance(dims, dict):
                for subj, dim_list in dims.items():
                    if subj != concept_id:
                        continue
                    for dim_info in (dim_list if isinstance(dim_list, list) else []):
                        if not isinstance(dim_info, dict):
                            continue
                        d = Dim(dim_info.get('name', subj),
                                emerged_from=dim_info.get('source', ''))
                        for (s, a, state), n in pf.items():
                            if s == subj and n >= 1:
                                d.values.add(state)
                        obj.dims[d.name] = d
        return obj
    def edges(self, kind: Optional[str] = None,
              min_evidence: int = 1) -> List[CauseEdge]:
        """因果边视图 (三套边集合一, 证据时效三件套)"""
        cs = self.cs
        out: List[CauseEdge] = []
        # 确定性边 (action/state)
        for (src, dst), info in (getattr(cs, '_causal_edges', {}) or {}).items():
            e = CauseEdge(src, dst, 'action',
                          evidence=info.get('count', 1),
                          last_seen=info.get('last_seen', 0),
                          confidence=info.get('confidence', 0.0))
            out.append(e)
        # 条件边 (state)
        for (src, act, dst), info in (getattr(cs, '_state_cond_edges', {}) or {}).items():
            e = CauseEdge(f"{src}+{act}", dst, 'state',
                          evidence=info.get('count', 1),
                          last_seen=info.get('last_seen', 0),
                          confidence=info.get('confidence', 0.0))
            out.append(e)
        if kind:
            out = [e for e in out if e.kind == kind]
        if min_evidence > 1:
            out = [e for e in out if e.evidence >= min_evidence]
        return out

    def dims(self) -> Dict[str, Dim]:
        """全部状态维度视图 (值集合从预测失败状态键投影)"""
        em = getattr(self.cs, 'emergence', None)
        out: Dict[str, Dim] = {}
        if em is None:
            return out
        dims = getattr(em, 'state_dims', {}) or {}
        pf = getattr(em, '_pred_fail', {}) or {}
        for subj, dim_list in dims.items():
            for dim_info in (dim_list if isinstance(dim_list, list) else []):
                if isinstance(dim_info, dict):
                    name = dim_info.get('name', subj)
                    d = Dim(name, emerged_from=dim_info.get('source', ''))
                    # 值集合: 该主体预测失败出现过的状态值
                    for (s, a, state), n in pf.items():
                        if s == subj and n >= 1:
                            d.values.add(state)
                    out[name] = d
        return out

    # ── 零预载检查 (验收用) ──────────────────────────────────
    # (归档 2026-08-16: fresh_object → _archive_legacy/dead_interfaces_20260816.py)
