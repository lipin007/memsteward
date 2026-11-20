#!/usr/bin/env python3
"""
core/hebbian.py — Hebbian 学习家族 (阶段 B: 学习统一, 第二十五课)

定位 (mechanization_design.md 统一② + system_audit_report.md §5.3):
  大脑只有一条学习规则: fire together, wire together (Hebb 1949)。
  全系统"共激活→加权增强"都是它的实例 — 同一动力学, 不同载体:

    strengthen 家族五载体 (学习统一前, 各自裸更新, 互不知晓):
      ① 符号边     ConceptSpace.strengthen   edges[(a,rel,b)] += Δ
      ② 突触权重   DualSpaceV2._stdp_update   W += lr·(pre⊗post − post⊗pre)
      ③ 记忆重要性 ConceptMemory.retrieve     importance *= 1.01 (被检索→微增)
      ④ 使用频率   LongTermMemory.read        usage += 1 (被读取→用进废退)
      ⑤ 学习总线   ReasoningCore._bus_steps   预测误差超额 → 变换学习步数

统一后:
  - 每一处增强都带家族签名 (载体名 + 事件源), 可统一观测/审计
  - 行为不变硬约束: 数值语义完全不动, 只加签名与计数
  - 联动准备: 载体注册表 = 未来跨载体广播 (符号增强 → 突触/记忆同步) 的挂点

反形式主义判据 (机制化必须带来新能力, 本模块新能力):
  - 全系统机制观测: mechanism_stats() 一处看到五载体活动
  - 联动钩子: strengthen_event() 返回结构化事件, 供 StateBridge 把
    符号增强广播到神经侧 (阶段 B 二期: 跨载体联动)
"""
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Optional


# ── 家族语义表 ─────────────────────────────────────────
CARRIERS = {
    "symbol_edge": "符号边 (ConceptSpace.strengthen)",
    "synaptic_weight": "突触权重 (STDP, DualSpaceV2)",
    "memory_importance": "记忆重要性 (ConceptMemory)",
    "memory_usage": "使用频率 (LongTermMemory)",
    "learn_bus": "学习总线 (ReasoningCore)",
}


@dataclass
class StrengthenEvent:
    """一次 Hebbian 增强的结构化记录 (联动钩子的载荷)

    carrier : 载体名 (CARRIERS 键)
    a / b   : 共激活的两方 (符号: 概念名; 神经: 神经元/槽索引描述)
    rel     : 关系 (符号: 边标签; 神经: 机制名)
    delta   : 增强量
    source  : 触发源 (观察/检索/读取/预测误差/固化/绑定...)
    """
    carrier: str
    a: str
    b: str
    rel: str
    delta: float
    source: str = ""


class HebbianFamily:
    """Hebbian 家族内核: 统一签名 + 统一观测 (行为不变)

    用法: 各载体增强处调 family.boost(...), 内部只计数+记录,
    不修改任何数值语义 — 数值仍由各载体自己的公式决定。
    """

    def __init__(self):
        self._counts: Dict[str, int] = defaultdict(int)
        self._last_events: list = []       # 最近事件环形 (可观测)
        self._max_events = 200
        # 联动钩子 (阶段 B 二期: 符号增强 → 神经侧广播)
        self._listeners: list = []

    def boost(self, carrier: str, a: str, b: str, rel: str,
              delta: float, source: str = "") -> None:
        """一次增强的家族签名入口 (数值仍由载体决定, 本方法不改语义)"""
        if carrier not in CARRIERS:
            carrier = "unknown"
        self._counts[carrier] += 1
        ev = StrengthenEvent(carrier, a, b, rel, delta, source)
        self._last_events.append(ev)
        if len(self._last_events) > self._max_events:
            self._last_events = self._last_events[-self._max_events:]
        # 联动广播 (若注册)
        for fn in self._listeners:
            try:
                fn(ev)
            except Exception:
                pass

    # (归档 2026-08-16: on_strengthen → _archive_legacy/dead_interfaces_20260816.py)

    # ── 观测 ───────────────────────────────────────────
    def stats(self) -> dict:
        """五载体活动统计 (机制化观测: 一处看全系统学习)"""
        return {
            "carriers": {k: self._counts[k] for k in CARRIERS},
            "total": sum(self._counts.values()),
        }

    def recent(self, n: int = 10) -> list:
        """最近 n 次增强事件 (可审计)"""
        return [{
            "carrier": e.carrier, "a": e.a, "b": e.b,
            "rel": e.rel, "delta": round(e.delta, 4), "source": e.source,
        } for e in self._last_events[-n:]]


# ── 全局单例 (模块级共享; 各载体 import 即用) ──────────
_family: Optional[HebbianFamily] = None


def get_family() -> HebbianFamily:
    """获取全局 Hebbian 家族 (懒创建单例)"""
    global _family
    if _family is None:
        _family = HebbianFamily()
    return _family
