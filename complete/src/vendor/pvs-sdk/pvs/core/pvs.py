#!/usr/bin/env python3
"""PVS 治理中间件 — 主控制器 (治理编排层)。

把 LLM 治理能力编排成一个可用中间件:
    任务 → [LLM 提出(带治理/预算/记忆先验)] → [确定性验证闸门] → [置信选择 top-2] → 结果

领域无关: 任务通过 TaskAdapter 提供"示范对 + 真值 + 产出格式指令"。
模型可插拔: 任何 LLMBackend 经 LLMGate 接入。

对齐 ARC agent_v1 机制 (提出-验证-选择环的通用化):
  * 多阶段提出 (散文→代码 / 降档 / 家族定向) — 可配置
  * 验证闸门 = 确定性执行, 零假阳性
  * 反例修复: verify 失败 → 把差异喂回 LLM 修正 (真正的"修正"环)
  * 记忆先验: 结构门控召回 + 失败负先验
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence, Tuple

from .budget import Budget, BudgetGovernor
from .llm_gate import LLMGate, LLMResponse
from .memory import GateMemory
from .verifier import Verifier


class TaskAdapter(Protocol):
    """通用任务适配接口 (领域无关):
       - demos: [(input, expected_output), ...]  真值对 (验证闸门的数据源)
       - prompt_build(demos, hints) -> str      提出 prompt
       - extract_fn(content) -> fn | None       从 LLM 产出解析可执行候选
       - run(fn, input) -> output               执行候选
       - test_inputs() -> [input,...]           待求解输入
    """
    def demos(self) -> Sequence[Tuple[Any, Any]]: ...
    def prompt_build(self, demos, hints: str = "") -> str: ...
    def extract_fn(self, content: str) -> Any: ...
    def run(self, fn, inp: Any) -> Any: ...
    def test_inputs(self) -> Sequence[Any]: ...
    def digest(self) -> str: ...


class PVS:
    """治理中间件主控制器。

    用法:
        pvs = PVS(backend, adapter, memory_path="memory.json")
        result = pvs.solve(task_id="t1")   # 或 pvs.solve_many([...])
        # result: {"a1": [...], "a2": [...], "win": bool, "calls": n, "tokens": n, ...}
    """

    def __init__(self, backend, adapter_factory: Callable[[Any], TaskAdapter],
                 *, timeout: float = 420, hard_calls: int = 0, hard_tokens: int = 0,
                 memory_path: Optional[str] = None, max_retries: int = 3,
                 effort_levels: Sequence[str] = ("medium", "low"),
                 on_log: Optional[Callable[[dict], None]] = None):
        self.gate = LLMGate(backend, timeout=timeout, max_retries=max_retries)
        self.governor = BudgetGovernor(Budget(hard_calls=hard_calls, hard_tokens=hard_tokens))
        self.memory = GateMemory(memory_path)
        self.verifier = Verifier()
        self._adapter_factory = adapter_factory
        self._levels = effort_levels
        self._on_log = on_log or (lambda r: None)

    # ---------- 单任务求解 ----------
    def solve(self, task: Any, task_id: str = "") -> Dict[str, Any]:
        adapter = self._adapter_factory(task)
        demos = adapter.demos()
        budget = self.governor.budget
        rec = {"tid": task_id, "calls": 0, "tokens": 0, "stages": [], "win": False}

        # ① 记忆先验 (相关性门控)
        hints = ""
        q = adapter.digest()
        recalled = self.memory.recall(q)
        warns = self.memory.recall_fails(q)
        if recalled:
            hints += ("\n【记忆中相似的既往规则(仅供参考, 冲突以真值为准)】\n"
                      + "\n".join(f"(sim{s:.2f})\n{e.code[:300]}" for s, e in recalled))
        if warns:
            hints += ("\n【⚠ 历史失败模式(同结构曾失败, 规避)】\n"
                      + "\n".join(f"stage:{e.stage}" for _, e in warns))

        # ② CallDecay 直连查表: 固化条目命中 → 零 token 交卷
        for s_m, e_m in recalled:
            if s_m < 0.3:
                break
            try:
                fn_m = adapter.extract_fn(e_m.code)
            except Exception:
                fn_m = None
            if fn_m is not None and self.verifier.verify(fn_m, demos):
                self.memory.boost_used([e_m])
                outs = self._apply(fn_m, adapter)
                rec.update({"win": True, "a1": outs, "a2": outs, "stage": "MEM",
                            "mem_sim": round(s_m, 3), "calls": 0, "tokens": 0})
                self._on_log(rec)
                return rec

        # ③ 提出 (多档位 + 降档 + 反例修复)
        cands = []
        prompt = adapter.prompt_build(demos, hints)
        for level in self._levels:
            if budget.exhausted():
                break
            resp = self.gate.call_resilient(
                prompt, max_tokens=12000, temperature=0.15,
                extra=self.governor.effort_param(level))
            budget.add(1, resp.usage.get("total_tokens", 0))
            rec["calls"] += 1
            rec["tokens"] += resp.usage.get("total_tokens", 0)
            rec["stages"].append(level)
            self._on_log({"tid": task_id, "stage": level, "len": len(resp.content),
                          "finish": resp.finish})

            if resp.error:
                continue
            fn = adapter.extract_fn(resp.content)
            if fn is not None and self.verifier.verify(fn, demos):
                outs = self._apply(fn, adapter)
                rec.update({"win": True, "a1": outs, "a2": outs,
                            "stage": level, "code": resp.content})
                # 成功规则入库 (只存抽象规则, 不存答案)
                self.memory.deposit(resp.content, q, tid=task_id, stage=level, success=True)
                self._on_log(rec)
                return rec

            # 反例修复: verify 失败 → 差异喂回
            if fn is not None:
                prompt = self._repair_prompt(prompt, fn, adapter, demos)
                budget.add(1, 0)
                rec["calls"] += 1
                rec["stages"].append(level + "-repair")
                resp2 = self.gate.call_resilient(
                    prompt, max_tokens=12000, temperature=0.15,
                    extra=self.governor.effort_param("low"))
                budget.add(1, resp2.usage.get("total_tokens", 0))
                rec["tokens"] += resp2.usage.get("total_tokens", 0)
                fn2 = adapter.extract_fn(resp2.content)
                if fn2 is not None and self.verifier.verify(fn2, demos):
                    outs = self._apply(fn2, adapter)
                    rec.update({"win": True, "a1": outs, "a2": outs,
                                "stage": level + "-repair", "code": resp2.content})
                    self.memory.deposit(resp2.content, q, tid=task_id,
                                        stage=level + "-repair", success=True)
                    self._on_log(rec)
                    return rec
                # 修复失败 → 记失败负先验
                self.memory.deposit_fail(q, tid=task_id, stage=level)

        rec["win"] = False
        self._on_log(rec)
        return rec

    # ---------- 辅助 ----------
    def _apply(self, fn, adapter) -> List[Any]:
        outs = []
        for ti in adapter.test_inputs():
            try:
                outs.append(adapter.run(fn, ti))
            except Exception:
                outs.append(None)
        return outs

    def _repair_prompt(self, base: str, fn, adapter, demos) -> str:
        return (base + "\n\n【你上次的产出没通过真值验证。请修正: 它必须把每个示范输入映射到期望输出。"
                "只输出修正后的最终结果。】")

    # ---------- 批量 ----------
    def solve_many(self, tasks: Dict[str, Any]) -> List[Dict[str, Any]]:
        results = []
        for tid, task in tasks.items():
            results.append(self.solve(task, task_id=tid))
        if self.memory._path:
            self.memory.persist(self.memory._path)
        return results
