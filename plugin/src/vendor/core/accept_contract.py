#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""core/accept_contract.py — accept 契约兼容入口 (薄垫片; 单一来源 = authority_kernel).

【单一来源】F1/F3/闸门的全部实现都在 shared/authority_kernel (contract/verdict/
provenance); 本文件只做 re-export, 历史 import 路径与签名逐位不变:
    from core.accept_contract import accept, admit      # core 作包
    from accept_contract import accept, admit           # core/ 在 sys.path

【演进】B4 (2026-10-22) "两层共享公共内核" → (2026-10-28) **跨中间件单一来源**:
治理中间件 (pvs-sdk / CallDecay) 与解题中间件 (arc-agi-2) 共享同一 authority_kernel.
验收判据: accept.__module__ == 'authority_kernel.contract' 且三处 shim md5 一致
(模板 shared/authority_kernel/shim/accept_contract.py 为源, 一键审计见
shared/authority_kernel/verify.py)。

许可: 通用治理逻辑 (LLM 候选边界校验), 属工具层 = Apache-2.0 友好,
不含认知内核专利 (core/ 内核的 concept_space/role_graph 仍是 v1.2).
"""
from __future__ import annotations


def _bootstrap_authority_kernel() -> None:
    """定位 authority_kernel: 先常规 import; 失败则向上查找 <root>/shared/."""
    try:
        import authority_kernel  # noqa: F401
        return
    except ImportError:
        pass
    import os
    import sys
    start = os.path.dirname(os.path.abspath(__file__))
    here = start
    for _ in range(8):
        here = os.path.dirname(here)
        cand = os.path.join(here, "shared")
        if os.path.isdir(os.path.join(cand, "authority_kernel")):
            if cand not in sys.path:
                sys.path.insert(0, cand)
            return
    raise ImportError(
        "authority_kernel not found: 需可 import 或位于 <workspace>/shared/authority_kernel "
        f"(垫片位置: {start})")


_bootstrap_authority_kernel()

from authority_kernel import (  # noqa: E402
    RejectReason,
    Source,
    Verdict,
    accept,
    admit,
    admit_candidate,
    check_candidate,
    gate,
    gate_bool,
    pass_rate,
    truth_pairs,
)
from typing import Any  # noqa: E402,F401  (历史 __all__ 含 Any)

__all__ = [
    "accept", "admit", "Any",
    "check_candidate", "admit_candidate",
    "gate", "gate_bool", "pass_rate", "truth_pairs",
    "Verdict", "RejectReason", "Source",
]
