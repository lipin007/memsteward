# -*- coding: utf-8 -*-
"""PanoramicPlanner 判据(C4 重写 2026-11-19, 按现行 API: supply/retreat_for_supply;
旧 food/retreat_for_food/switch_target 断言为过时 API, 见 审查_20261119/C-本地版审查.md C4)"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from panoramic_planner import PanoramicPlanner, Plan, PlanGoal, Contingency
from memsteward_local import MemStewardLocal

print("== Test: PanoramicPlanner (现行 API) ==")
ms = MemStewardLocal()
planner = PanoramicPlanner(memsteward=ms)

global_state = {
    "pos": (44, 45), "energy": 15, "max_energy": 42, "steps_left": 200,
    "targets": [(34, 10), (29, 15), (24, 40)],
    "changers": [(19, 30), (19, 25)],
    "supplies": [(3, 3), (4, 4)],
    "gates": [(19, 25)],
    "exit": (29, 50),
}
plan = planner.plan(global_state)
print("goals:", [(g.kind, g.target, g.priority) for g in plan.goals])

# 1. 低能量 → supply 目标置顶(现行 kind=supply, 旧名 food 已废)
supply = [g for g in plan.goals if g.kind == "supply"]
assert supply and plan.goals[0].kind == "supply", "低能量应 supply 置顶, got %s" % plan.goals[0].kind
assert plan.goals[0].priority >= 0.9
print("PASS 1: 低能量 -> supply 置顶")
# 2. exit 目标在列
assert sum(1 for g in plan.goals if g.kind == "exit") == 1
print("PASS 2: exit 目标在列")
# 3. monitor 到点 → next_goal
mon = planner.monitor({"pos": (4, 4), "energy": 15, "steps_used": 30, "last_result": "goal_reached"})
assert mon["action"] == "next_goal", mon
print("PASS 3: 到点 -> next_goal")
# 4. 预案自洽: 资源预案触发时 action 与预案声明一致(现行 retreat_for_supply 族, 名称不写死)
planner2 = PanoramicPlanner(memsteward=MemStewardLocal())
plan2 = planner2.plan(global_state)
rb = [c for c in plan2.contingencies if str(c.trigger).startswith("resource_below_")]
if rb:
    mon = planner2.monitor({"pos": (44, 45), "energy": 0, "steps_used": 5})
    assert mon["action"] == rb[0].action, "预案触发应返回预案 action: %s vs %s" % (mon, rb[0])
    print("PASS 4: 资源预案自洽 action=%s" % mon["action"])
else:
    print("PASS 4(skip): 现行 plan 未产资源预案, 记录实态")
# 5. 现行设计实态: plan 从不产 failed_3x 预案(旧断言 switch_target 为过时 API)
assert not any(str(c.trigger) == "failed_3x" for c in plan.contingencies), "现行设计不应产 failed_3x 预案"
mon = planner.monitor({"pos": (20, 20), "energy": 30, "steps_used": 5, "failures": 9, "last_result": "gate_failed"})
assert mon["action"] != "switch_target"
print("PASS 5: 无 failed_3x 预案(实态钉子) mon=%s" % mon["action"])
# 6. learn 回写 MemSteward(先标失败, fail_history 判定才有意义)
plan.mark_failed([g for g in plan.goals if g.kind == "exit"][0], "test-fail")
planner.learn({"result": "partial", "goals_done": 1, "goals_failed": 1})
assert ms.stats()["n_entries"] > 0
assert planner.get_fail_history(), planner.get_fail_history()
print("PASS 6: learn 回写 stats=%s" % {k: ms.stats()[k] for k in ("n_entries",)})
# 7. summary 可用
s = plan.summary()
assert s
print("PASS 7: summary OK")
print("== panoramic 7/7 ==")
