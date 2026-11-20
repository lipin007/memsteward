#!/usr/bin/env python3
"""PVS 治理中间件 — 预算控制器 (把模型能力上限变成可调度资源)。

从 ARC-AGI-2 agent_v1 提炼:
  * 硬预算: calls / tokens 双硬卡, 超限即停 (防止烧穿/超成本)
  * 降档重试: 烧穿/空且无产出 → 降推理档 + 强制出码重试
  * 倒 U 曲线调度依据: 慢归纳配 medium, 快执行配 low (思考深度是可调度资源)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Budget:
    """预算记账器。"""
    calls: int = 0
    tokens: int = 0
    downshifts: int = 0
    hard_calls: int = 0          # 0 = 不限
    hard_tokens: int = 0         # 0 = 不限

    def add(self, calls: int = 0, tokens: int = 0) -> None:
        self.calls += calls
        self.tokens += tokens

    def exhausted(self) -> bool:
        return (self.hard_calls and self.calls >= self.hard_calls) or \
               (self.hard_tokens and self.tokens >= self.hard_tokens)

    def summary(self) -> dict:
        return {"calls": self.calls, "tokens": self.tokens,
                "downshifts": self.downshifts}


class BudgetGovernor:
    """预算调度器: 按认知阶段配思考档位, 烧穿自动降档。

    档位 (对齐 ARC 倒 U 曲线):
        high   — 深思考 (慢归纳/超难题)
        medium — 标准 (主力)
        low    — 快执行/强制出码 (烧穿救回)
    """

    def __init__(self, budget: Optional[Budget] = None,
                 on_event: Optional[Callable[[str, dict], None]] = None):
        self.budget = budget or Budget()
        self._on_event = on_event or (lambda *a: None)

    # ---------- 档位映射 ----------
    @staticmethod
    def effort_param(level: str) -> Dict[str, Any]:
        """档位 → 后端 extra 参数。后端不同 (DeepSeek reasoning_effort / 本地) 各自解释。"""
        if level == "high":
            return {"reasoning_effort": "high"}
        if level == "medium":
            return {"reasoning_effort": "medium"}
        return {"reasoning_effort": "low"}

    # ---------- 降档决策 ----------
    def should_downshift(self, resp, finish: Optional[str]) -> bool:
        """烧穿/空且无产出 → 该降档。"""
        return (finish == "length" or not resp.content.strip())

    def downshift(self, level: str) -> str:
        """降到下一档 (high→medium→low), 返回新档。"""
        order = ["high", "medium", "low"]
        idx = order.index(level) if level in order else 1
        new = order[min(idx + 1, 2)]
        self.budget.downshifts += 1
        self._on_event("downshift", {"from": level, "to": new})
        return new

    # ---------- 强制出码 (烧穿救回的核心修复) ----------
    @staticmethod
    def force_code_instruction(prompt: str, family_hint: str = "") -> str:
        """烧穿重试时追加硬指令: 跳过长分析直接出代码。agent_v1 实证 93% 出码成功。"""
        extra = ("\n\n【强制】上次输出烧穿预算且没有可用结果。这次跳过长分析,"
                 "思考不超过200字后直接输出最终结果。")
        if family_hint:
            extra += f"\n【定向】本次重点尝试: {family_hint}"
        return prompt + extra
