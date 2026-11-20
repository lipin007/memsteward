"""
RollingPlanner — 滚动计划器（replan 循环）

核心问题：开局记忆为空 → 计划只有「探索」。
          局中发现 19 个目标 → 计划该更新但没更新。

解决方案：观察到新知识就触发 replan。ObservedEnv 钩子里调用。

流程：
  观察 → 有新目标/变换器/门？→ replan → 计划更新 → agent 用新计划
"""

import time
from panoramic_planner import PanoramicPlanner, PlanGoal


class RollingPlanner:
    """滚动计划器：知识增长时自动 replan。"""

    def __init__(self, planner: PanoramicPlanner):
        self._planner = planner
        self._last_known = {"targets": set(), "changers": set(), "gates": set()}
        self._replan_count = 0
        self._replan_triggers = []

    @staticmethod
    def _parse_coord(item):
        """把 Memory 里的坐标元素解析成 (int, int) tuple。"""
        if isinstance(item, (list, tuple)) and len(item) == 2:
            try:
                return (int(item[0]), int(item[1]))
            except (ValueError, TypeError):
                pass
        if isinstance(item, str):
            parts = item.split(",")
            if len(parts) == 2:
                try:
                    return (int(parts[0].strip()), int(parts[1].strip()))
                except ValueError:
                    pass
        return None  # 解析失败返回 None（后续过滤掉）

    def on_observation(self, mem, pos=None):
        """每步观察后调用。检测知识变化，决定是否 replan。"""
        # 从 Memory 读当前已知（解析坐标格式）
        targets = set()
        for t in (getattr(mem, "targets", None) or []):
            parsed = self._parse_coord(t)
            if parsed:
                targets.add(parsed)

        changers = set()
        for c in (getattr(mem, "changers", None) or []):
            parsed = self._parse_coord(c)
            if parsed:
                changers.add(parsed)

        gates = set()
        for g in (getattr(mem, "gates", None) or []):
            parsed = self._parse_coord(g)
            if parsed:
                gates.add(parsed)

        new_targets = targets - self._last_known["targets"]
        new_changers = changers - self._last_known["changers"]
        new_gates = gates - self._last_known["gates"]

        should_replan = False
        trigger = ""

        if new_targets:
            should_replan = True
            trigger = f"new_targets:{len(new_targets)}"
        if new_changers:
            should_replan = True
            trigger += f" new_changers:{len(new_changers)}"
        if new_gates:
            should_replan = True
            trigger += f" new_gates:{len(new_gates)}"

        if should_replan:
            self._last_known["targets"] = targets
            self._last_known["changers"] = changers
            self._last_known["gates"] = gates
            self._replan_count += 1
            self._replan_triggers.append({"ts": time.time(), "trigger": trigger.strip()})

            # 用新知识 replan
            _energy = getattr(mem, "energy", None)  # C14 修: 0 是合法能量, 不再被 or 抬成 42
            global_state = {
                "pos": pos or (0, 0),
                "energy": 42 if _energy is None else _energy,
                "max_energy": getattr(mem, "max_energy", None) or 42,
                "steps_left": getattr(mem, "steps_left", None) or 200,
                "targets": list(targets),
                "changers": list(changers),
                "supplies": list(getattr(mem, "supplies", None) or set()),
                "gates": list(gates),
                # C3 修复(2026-11-19): targets/changers/gates 映射成 plan() 认识的 pois（否则 replan 后只剩 explore）
                "pois": ([{"pos": tuple(t), "kind": "target", "priority": 0.8} for t in targets]
                         + [{"pos": tuple(c), "kind": "changer", "priority": 0.5} for c in changers]
                         + [{"pos": tuple(g), "kind": "gate", "priority": 0.6} for g in gates]),
                "exit": None,
            }
            plan = self._planner.plan(global_state)
            return plan

        return None

    def get_stats(self):
        return {
            "replans": self._replan_count,
            "triggers": self._replan_triggers[-5:],
            "known_targets": len(self._last_known["targets"]),
            "known_changers": len(self._last_known["changers"]),
            "known_gates": len(self._last_known["gates"]),
        }
