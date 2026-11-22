"""
MechanismAdvisor — 把学到的机制假设变成决策输入。

核心问题：MechanismLearner 是旁观者（观察 19 个假设，0 影响决策）。
MechanismAdvisor 是顾问（查询假设，给出行动建议）。

使用方式（在决策循环里）：
    advisor = MechanismAdvisor(learner)
    suggestion = advisor.suggest_action(pos, available_actions, goal)
    # suggestion = {"action": 2, "reason": "confirmed: ACTION2@(44,45) → target", "confidence": 1.0}

原则：顾问只给建议，不替 agent 做决定。agent 保留最终决策权。
"""

from mechanism_learner import MechanismLearner


class MechanismAdvisor:
    def __init__(self, learner: MechanismLearner):
        self._learner = learner

    def suggest_action(self, pos, available_actions, goal=None):
        """根据已学机制建议下一步动作。

        优先级：
        1. confirmed 机制中匹配当前 pos + goal 的动作
        2. testing 机制中匹配的（低置信度）
        3. 避开 known-failed 的动作
        4. 随机（无信息时）
        """
        pos_key = f"{pos[0]},{pos[1]}"
        confirmed = self._learner.get_hypotheses(status="confirmed")
        testing = self._learner.get_hypotheses(status="testing")
        refuted = self._learner.get_hypotheses(status="refuted")

        # 1. 找 confirmed 匹配
        for h in confirmed:
            if pos_key in h.cause:
                for act in available_actions:
                    if f"act:{act}" in h.cause or f"act:GameAction.ACTION{act}" in h.cause:
                        return {
                            "action": act,
                            "reason": f"confirmed: {h.cause} -> {h.effect}",
                            "confidence": h.confidence,
                            "source": "confirmed",
                        }

        # 2. 找 testing 匹配（高置信度优先）
        best_testing = None
        for h in testing:
            if pos_key in h.cause and h.confidence > (best_testing.confidence if best_testing else 0):
                best_testing = h
        if best_testing:
            for act in available_actions:
                if f"act:{act}" in best_testing.cause or f"act:GameAction.ACTION{act}" in best_testing.cause:
                    return {
                        "action": act,
                        "reason": f"testing: {best_testing.cause} -> {best_testing.effect}",
                        "confidence": best_testing.confidence,
                        "source": "testing",
                    }

        # 3. 避开 refuted 动作
        refuted_actions = set()
        for h in refuted:
            if pos_key in h.cause:
                for act in available_actions:
                    if f"act:{act}" in h.cause or f"act:GameAction.ACTION{act}" in h.cause:
                        refuted_actions.add(act)

        safe_actions = [a for a in available_actions if a not in refuted_actions]
        if not safe_actions:
            safe_actions = available_actions  # 全被否决时全试

        # 4. 返回未探索的候选
        import random
        chosen = random.choice(safe_actions)
        return {
            "action": chosen,
            "reason": f"unexplored ({len(safe_actions)} safe of {len(available_actions)})",
            "confidence": 0.0,
            "source": "explore",
        }

    def should_skip_gate(self, pos, gate_action, max_failures=3):
        """判断是否应该跳过推门尝试（避免重复失败）。

        如果同一位置同一动作已失败 >= max_failures 次，建议跳过。
        """
        pos_key = f"{pos[0]},{pos[1]}"
        failure_count = 0
        for h in self._learner.hypotheses.values():
            if pos_key in h.cause and f"act:{gate_action}" in h.cause:
                # 检查反证次数
                n_ref = sum(1 for e in h.evidence if not e["supports"])
                if n_ref >= max_failures:
                    return True, f"gate failed {n_ref} times at {pos_key}"
        return False, ""

    def get_exploration_guidance(self, pos, known_positions):
        """给探索方向建议（哪里没去过）。"""
        x, y = pos
        candidates = [(x-1, y), (x+1, y), (x, y-1), (x, y+1)]
        unexplored = [c for c in candidates if c not in known_positions]
        return {
            "unexplored": unexplored,
            "known": [c for c in candidates if c in known_positions],
        }

    def suggest_toward_target(self, pos, targets, edges=None, action_map=None):
        """非 LLM 目标引导：建议朝最近目标移动。

        当 LLM 额度用完时的寻路兜底——用 BFS 在已知边上找路。
        action_map: {action_id: (dx, dy)} 动作→位移映射
        """
        if not targets:
            return {"action": None, "reason": "no targets", "confidence": 0.0}
        if action_map is None:
            # 默认：1=上 2=下 3=左 4=右（对应 arc_agent 的方向）
            action_map = {1: (0, -1), 2: (0, 1), 3: (-1, 0), 4: (1, 0)}

        x, y = pos
        # 找最近目标（曼哈顿距离）
        def manhattan(p1, p2):
            return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])

        # 把 targets 转成 (int,int) tuples
        clean_targets = []
        for t in targets:
            if isinstance(t, (list, tuple)) and len(t) == 2:
                try:
                    clean_targets.append((int(t[0]), int(t[1])))
                except (ValueError, TypeError):
                    pass

        if not clean_targets:
            return {"action": None, "reason": "no valid targets", "confidence": 0.0}

        nearest = min(clean_targets, key=lambda t: manhattan((x, y), t))
        dist = manhattan((x, y), nearest)

        # BFS on known edges
        if edges:
            path = self._bfs_path((x, y), nearest, edges)
            if path and len(path) > 1:
                next_pos = path[1]
                # 找哪个 action 能到 next_pos
                dx, dy = next_pos[0] - x, next_pos[1] - y
                for act, (adx, ady) in action_map.items():
                    if (adx, ady) == (dx, dy):
                        return {
                            "action": act,
                            "reason": f"BFS path to target {nearest} (dist={dist})",
                            "confidence": 0.8,
                            "source": "bfs",
                        }

        # 贪心方向（BFS 不可用时）
        dx = nearest[0] - x
        dy = nearest[1] - y
        if abs(dx) > abs(dy):
            preferred = 4 if dx > 0 else 3  # 右 or 左
        else:
            preferred = 2 if dy > 0 else 1  # 下 or 上

        return {
            "action": preferred,
            "reason": f"greedy toward {nearest} (dx={dx} dy={dy})",
            "confidence": 0.5,
            "source": "greedy",
        }

    def _bfs_path(self, start, goal, edges):
        """在已知边上 BFS 找路。edges = {"x,y|action": "x',y'" or "blocked"}"""
        from collections import deque
        # 解析 edges 成邻接表
        adj = {}
        for key, val in edges.items():
            if val == "blocked":
                continue
            try:
                parts = key.split("|")
                pos_str = parts[0]
                px, py = map(int, pos_str.split(","))
                # val 是目标位置
                tx, ty = map(int, val.split(","))
                adj.setdefault((px, py), set()).add((tx, ty))
                adj.setdefault((tx, ty), set()).add((px, py))
            except (ValueError, IndexError):
                continue

        # BFS
        queue = deque([(start, [start])])
        visited = {start}
        while queue:
            current, path = queue.popleft()
            if current == goal:
                return path
            for neighbor in adj.get(current, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        return None
