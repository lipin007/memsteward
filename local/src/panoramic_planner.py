"""
PanoramicPlanner — 通用全景计划器

目标类型通用化：POI（兴趣点）替代 food/gate/exit。
任何需要「目标序列+动作序列+预案链」的场景都能用：
  自动驾驶：POI=充电站/出口/收费站
  具身机器人：POI=物体/工具/目标位置
  运维系统：POI=服务节点/数据库/监控点
"""

import time
from dataclasses import dataclass, field


@dataclass
class PlanGoal:
    target: tuple
    kind: str               # 通用 POI 类型（任意字符串）
    priority: float = 0.5
    budget: int = 50
    status: str = "pending"
    action_sequence: list = field(default_factory=list)
    path_found: bool = False
    _step_idx: int = 0


@dataclass
class Contingency:
    trigger: str
    action: str
    fallback_target: tuple = None
    threshold: int = 3


@dataclass
class Plan:
    goals: list = field(default_factory=list)
    contingencies: list = field(default_factory=list)
    total_budget: int = 200
    resource_state: dict = field(default_factory=dict)
    created: float = 0.0
    log: list = field(default_factory=list)

    def active_goal(self):
        for g in self.goals:
            if g.status == "active":
                return g
        for g in self.goals:
            if g.status == "pending":
                g.status = "active"
                return g
        return None

    def next_action(self):
        g = self.active_goal()
        if not g or not g.action_sequence:
            return None
        if g._step_idx < len(g.action_sequence):
            action_id, from_pos, to_pos = g.action_sequence[g._step_idx]
            g._step_idx += 1
            return {"action": action_id, "from": from_pos, "to": to_pos,
                    "goal": g.kind, "step": g._step_idx,
                    "total_steps": len(g.action_sequence)}
        return None

    def mark_done(self, goal):
        goal.status = "done"
        self.log.append(f"done: {goal.kind}@{goal.target}")

    def mark_failed(self, goal, reason=""):
        goal.status = "failed"
        self.log.append(f"failed: {goal.kind}@{goal.target} ({reason})")

    def summary(self):
        return {
            "n_goals": len(self.goals),
            "done": sum(1 for g in self.goals if g.status == "done"),
            "failed": sum(1 for g in self.goals if g.status == "failed"),
            "with_paths": sum(1 for g in self.goals if g.path_found),
            "total_actions": sum(len(g.action_sequence) for g in self.goals),
        }


class PanoramicPlanner:
    """通用全景计划器。"""

    def __init__(self, memsteward=None, bfs_fn=None, step_fn=None):
        self.ms = memsteward
        self._bfs = bfs_fn
        self._step_to = step_fn
        self._current_plan = None
        self._fail_counts = {}

    def plan(self, global_state):
        """生成全景计划。global_state 是通用格式。"""
        pos = global_state.get("pos", (0, 0))
        energy = global_state.get("energy", 100)
        max_energy = global_state.get("max_energy", 100)
        steps_left = global_state.get("steps_left", 200)
        # 通用 POI 列表：每个元素是 {"pos": (x,y), "kind": "...", "priority": ...}
        pois = global_state.get("pois", [])
        # 资源补给点
        supplies = global_state.get("supplies", [])
        # 出口/终点
        exit_pos = global_state.get("exit")

        goals = []
        contingencies = []
        energy_ratio = energy / max(1, max_energy)

        # 策略 1: 低资源先补给
        if energy_ratio < 0.4 and supplies:
            nearest = self._nearest(pos, supplies)
            if nearest:
                goals.append(PlanGoal(target=nearest, kind="supply", priority=0.9, budget=30))
                contingencies.append(Contingency(
                    trigger="resource_below_10", action="retreat_for_supply",
                    fallback_target=nearest, threshold=10))

        # 策略 2: POI 按优先级
        for poi in pois:
            p = tuple(poi.get("pos", (0, 0))) if isinstance(poi, dict) else tuple(poi)
            kind = poi.get("kind", "poi") if isinstance(poi, dict) else "poi"
            pri = poi.get("priority", 0.5) if isinstance(poi, dict) else 0.5
            if p not in [g.target for g in goals]:
                goals.append(PlanGoal(target=p, kind=kind, priority=pri, budget=40))

        # 策略 3: 探索
        if not goals:
            goals.append(PlanGoal(target=pos, kind="explore", priority=0.1, budget=100))

        # 策略 4: 出口/终点
        if exit_pos:
            goals.append(PlanGoal(target=exit_pos, kind="exit", priority=1.0, budget=80))

        # ★ 用 bfs 生成动作序列
        for g in goals:
            if not g.target or g.kind == "explore":
                continue
            if self._bfs:
                try:
                    path = self._bfs(pos, g.target)
                    if path:
                        g.action_sequence = [(a, p, n) for p, a, n in path]
                        g.path_found = True
                except Exception:
                    pass
            # 贪心兜底
            if not g.path_found:
                try:
                    dx = g.target[0] - pos[0]
                    dy = g.target[1] - pos[1]
                    # C8 修(2026-11-19): 单轴步(act 与 next_pos 一致) + 编号收敛 canon
                    # (3=左(-1,0)/4=右(1,0)/1=上(0,-1)/2=下(0,1), 与 mechanism_advisor 默认 map 一致)
                    if abs(dx) >= abs(dy) and dx != 0:
                        act = 4 if dx > 0 else 3
                        next_pos = (pos[0] + (1 if dx > 0 else -1), pos[1])
                    elif dy != 0:
                        act = 2 if dy > 0 else 1
                        next_pos = (pos[0], pos[1] + (1 if dy > 0 else -1))
                    else:
                        act, next_pos = 0, pos
                    g.action_sequence = [(act, pos, next_pos)]
                    g.path_found = True
                except Exception as e:
                    import logging
                    logging.getLogger('memsteward').warning(f'贪心兜底降级: {e}')  # C9 修: 原静默吞

        # 排序
        for g in goals:
            if g.kind == "supply" and energy_ratio < 0.4:
                g.priority = max(g.priority, 1.1)
            elif g.kind == "exit" and energy_ratio < 0.4:
                g.priority = min(g.priority, 0.85)
        goals.sort(key=lambda g: (-g.priority, not g.path_found))

        self._current_plan = Plan(
            goals=goals, contingencies=contingencies,
            total_budget=steps_left,
            resource_state={"energy": energy, "steps_left": steps_left,
                           "energy_ratio": round(energy_ratio, 2)},
            created=time.time(),
        )
        return self._current_plan

    def monitor(self, current_state):
        if not self._current_plan:
            return {"action": "replan", "reason": "no plan"}
        plan = self._current_plan
        energy = current_state.get("energy", 0)
        steps_used = current_state.get("steps_used", 0)

        for cont in plan.contingencies:
            if cont.trigger.startswith("resource_below_") and energy < cont.threshold:
                return {"action": cont.action, "reason": cont.trigger, "target": cont.fallback_target}
            if cont.trigger == "failed_3x" and current_state.get("failures", 0) >= cont.threshold:
                ag = plan.active_goal()
                if ag:
                    plan.mark_failed(ag, "repeated failure")
                return {"action": cont.action, "reason": cont.trigger, "target": cont.fallback_target}

        if steps_used > plan.total_budget * 0.8:
            return {"action": "speed_up", "reason": f"budget {steps_used}/{plan.total_budget}"}

        ag = plan.active_goal()
        if ag:
            pos = current_state.get("pos", (0, 0))
            dist = abs(pos[0] - ag.target[0]) + abs(pos[1] - ag.target[1])
            if dist <= 1:
                plan.mark_done(ag)
                return {"action": "next_goal", "reason": f"reached {ag.kind}"}
        return {"action": "continue", "reason": "on track"}

    def learn(self, summary):
        if self.ms:
            self.ms.deposit(obj="plan:result", act="result", actual=str(summary), kind="planning")
        if self._current_plan:
            for g in self._current_plan.goals:
                if g.status == "failed":
                    key = f"{g.kind}:{g.target}"
                    self._fail_counts[key] = self._fail_counts.get(key, 0) + 1

    def _nearest(self, pos, candidates):
        if not candidates:
            return None
        def dist(p):
            if isinstance(p, dict):
                p = p.get("pos", (0, 0))
            if isinstance(p, (list, tuple)) and len(p) >= 2:
                return abs(pos[0] - int(p[0])) + abs(pos[1] - int(p[1]))
            return 999
        return min(candidates, key=dist)

    def get_current_plan(self):
        return self._current_plan

    def get_fail_history(self):
        return dict(self._fail_counts)
