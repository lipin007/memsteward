"""
ObservedEnv — 通用零侵入观察包装器

抽象环境接口：任何提供 get_frame() 和 step() 的环境都能用。
ARC-AGI / 自动驾驶 / 具身机器人 / 运维系统 都适配。

通用接口约定：
  env.get_frame() -> dict    # 当前状态快照（任意格式）
  env.step(action, data) -> result
  frame.get("pos") -> tuple  # 位置（可选）
"""

import time


class ObservedEnv:
    """零侵入观察包装器。不改 agent，不改环境。"""

    def __init__(self, env, learner=None, mem=None,
                 rolling_planner=None, memsteward=None):
        self._env = env
        self._learner = learner
        self._mem = mem
        self._rolling = rolling_planner
        self._ms = memsteward
        self._last_world = None
        self._step_count = 0

    def get_frame(self):
        return self._env.get_frame() if hasattr(self._env, "get_frame") else {}

    def step(self, *args, **kwargs):
        result = self._env.step(*args, **kwargs)
        current = self.get_frame()
        self._step_count += 1

        if self._last_world is not None and self._learner:
            action_label = str(args[0]) if args else str(kwargs.get("action", "?"))
            pos = current.get("pos") or (0, 0)
            changes = self._learner._detect_changes(self._last_world, current)
            if changes:
                self._learner.observe(
                    pos=pos, action=action_label,
                    world_before=self._last_world, world_after=current,
                )
                # 写入本地 MemSteward
                if self._ms:
                    for ch in changes:
                        self._ms.deposit(
                            obj=f"change@{pos}", act=action_label,
                            actual=str(ch), kind="mechanism")
            else:
                self._learner.check_no_effect(
                    pos=pos, action=action_label,
                    world_before=self._last_world, world_after=current)

        self._last_world = current

        # 滚动 replan
        if self._rolling and self._mem:
            pos = current.get("pos") or (0, 0)
            self._rolling.on_observation(self._mem, pos=pos)

        return result

    def __getattr__(self, name):
        return getattr(self._env, name)

    def get_mechanism_summary(self):
        if self._learner:
            return self._learner.get_mechanism_summary()  # C5 修复(2026-11-19): 方法名对齐
        return {"total": 0, "confirmed": [], "testing": []}

    def save_learned(self):
        if self._learner:
            self._learner.save_to_memsteward()
