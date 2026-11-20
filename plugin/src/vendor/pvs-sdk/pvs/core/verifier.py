#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PVS 治理中间件 — 确定性验证闸门 (零假阳性资产)。

这是"通用大模型中间件"最核心的治理层: LLM 产出不可靠, 必须经过
【可执行真值核对】才放行。零假阳性是架构资产, 永不放水。

设计铁律 (对齐 ARC agent_v1 + 事实基准实验教训):
  * 验证 = 确定性执行, 不是 LLM 语义判断 (语义自洽≠正确, 实测过错答案)。
  * 无可执行真值处, 不做验证闸门 —— 宁可不裁决, 不做 LLM 裁决。
  * 闸门只管"与示范/真值一致", 不承诺"泛化到新输入" (过闸≠答对)。

通用前提: 任务提供可执行的期望输出 (真值), 候选是可调用对象 fn(input)->output。

【单一来源 2026-10-28】验证语义收口到 shared/authority_kernel.gate ——
治理层 (pvs-sdk) / 记忆层 (CallDecay llm_arm) / 解题层 (arc-agi-2 primitives)
共享同一份「候选认知 ≠ 权威提交」边界实现; 本模块只保留 Verifier 类 API
(compare / on_error 钩子), 实现委托公共内核, 不再各自实现。
验收: shared/authority_kernel/tests + shared/authority_kernel/verify.py。
"""
from __future__ import annotations

from typing import Any, Callable, Optional, Sequence, Tuple


def _bootstrap_authority_kernel() -> None:
    """定位 authority_kernel: 先常规 import; 失败则向上查找 <root>/shared/."""
    try:
        import authority_kernel  # noqa: F401
        return
    except ImportError:
        pass
    import os
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):
        here = os.path.dirname(here)
        cand = os.path.join(here, "shared")
        if os.path.isdir(os.path.join(cand, "authority_kernel")):
            if cand not in sys.path:
                sys.path.insert(0, cand)
            return
    raise ImportError(
        "authority_kernel not found: 需可 import 或位于 <workspace>/shared/authority_kernel "
        f"(verifier 位置: {os.path.dirname(os.path.abspath(__file__))})")


_bootstrap_authority_kernel()

from authority_kernel import gate as _gate            # noqa: E402
from authority_kernel import pass_rate as _pass_rate  # noqa: E402
from authority_kernel import truth_pairs              # noqa: E402,F401


class Verifier:
    """确定性验证闸门: 候选 fn 必须把每个真值对 (input, expected) 映射对。

    compare: 期望 vs 实际是否相等; 默认 ==
    on_error: 候选执行抛异常时的处理; 默认 False (未通过)
    """

    def __init__(self, compare: Optional[Callable[[Any, Any], bool]] = None,
                 on_error: Optional[Callable[[Any, Exception], bool]] = None):
        self._cmp = compare or (lambda a, b: a == b)
        self._on_error = on_error or (lambda inp, err: False)

    def verify(self, fn: Callable, demos: Sequence[Tuple[Any, Any]]) -> bool:
        """全部真值对映射对 → True (零假阳性)。任一对不上 → False。"""
        return _gate(fn, demos, compare=self._cmp, on_error=self._on_error).ok

    def verify_detailed(self, fn: Callable, demos: Sequence[Tuple[Any, Any]]):
        """结构化裁决 (authority_kernel.Verdict): 拒收带 reason + fail_indices 诊断."""
        return _gate(fn, demos, compare=self._cmp, on_error=self._on_error)

    def pass_rate(self, fn: Callable, demos: Sequence[Tuple[Any, Any]]) -> float:
        """过闸率 (0..1), 供置信排序用。空集返回 0.0 (历史语义)。"""
        return _pass_rate(fn, demos, compare=self._cmp)
