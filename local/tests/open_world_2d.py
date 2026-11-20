#!/usr/bin/env python3
"""
open_world_2d.py — 2D 开放世界测试游戏（MemSteward 中间件测试床）

特性：
  - 无限地形（程序生成）
  - 资源收集（木/石/铁/金）
  - 危险区域（岩浆/深水/怪物）
  - 昼夜循环
  - 程序化 API（agent 可完全控制）
  - 结构化观测（JSON 可序列化）

用法：
    world = OpenWorld2D(size=100, seed=42)
    obs = world.reset()
    obs, reward, done, info = world.step(action)
"""

import random
import json
from dataclasses import dataclass, field, asdict
from typing import Optional


# === 地形类型 ===
TERRAIN = {
    0: "空地", 1: "草地", 2: "森林", 3: "水域",
    4: "岩浆", 5: "山地", 6: "沙地", 7: "矿脉",
}

# === 资源类型 ===
RESOURCES = {
    "wood": {"icon": "🌳", "terrain": [2], "value": 1},
    "stone": {"icon": "🪨", "terrain": [5], "value": 2},
    "iron": {"icon": "⛏️", "terrain": [7], "value": 5},
    "gold": {"icon": "✨", "terrain": [7], "value": 10},
}

# === 危险 ===
HAZARDS = {
    "lava": {"terrain": [4], "damage": 20},
    "water": {"terrain": [3], "damage": 2},
    "monster": {"icon": "👾", "damage": 10},
}

# === 动作 ===
ACTIONS = {
    0: "不动",
    1: "上", 2: "下", 3: "左", 4: "右",
    5: "收集",  # 收集当前格资源
    6: "攻击",  # 攻击相邻怪物
}


@dataclass
class AgentState:
    x: int = 25
    y: int = 25
    hp: int = 100
    max_hp: int = 100
    energy: int = 100
    inventory: dict = field(default_factory=lambda: {"wood": 0, "stone": 0, "iron": 0, "gold": 0})
    step_count: int = 0
    kills: int = 0


class OpenWorld2D:
    """2D 开放世界：无限地形 + 资源 + 危险 + 昼夜循环"""

    def __init__(self, size: int = 100, seed: int = 42, max_steps: int = 500):
        self.size = size
        self.seed = seed
        self.max_steps = max_steps
        self.rng = random.Random(seed)
        self.agent = AgentState()
        self.time_of_day = 0  # 0=白天 1=夜晚
        self.terrain_map = {}
        self.resource_map = {}
        self.monster_map = {}
        self._generate_world()

    def _generate_world(self):
        """程序生成世界"""
        rng = self.rng
        for x in range(self.size):
            for y in range(self.size):
                # 地形
                r = rng.random()
                if r < 0.4:
                    t = 1  # 草地
                elif r < 0.6:
                    t = 2  # 森林
                elif r < 0.7:
                    t = 3  # 水域
                elif r < 0.75:
                    t = 4  # 岩浆
                elif r < 0.85:
                    t = 5  # 山地
                elif r < 0.9:
                    t = 6  # 沙地
                else:
                    t = 7  # 矿脉
                self.terrain_map[(x, y)] = t

                # 资源
                if t == 2 and rng.random() < 0.3:
                    self.resource_map[(x, y)] = "wood"
                elif t == 5 and rng.random() < 0.2:
                    self.resource_map[(x, y)] = "stone"
                elif t == 7 and rng.random() < 0.4:
                    self.resource_map[(x, y)] = rng.choice(["iron", "gold"])

                # 怪物
                if t in [1, 6] and rng.random() < 0.02:
                    self.monster_map[(x, y)] = {"hp": 30, "damage": HAZARDS["monster"]["damage"]}

        # 确保出生点安全
        cx, cy = self.size // 2, self.size // 2
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                pos = (cx + dx, cy + dy)
                self.terrain_map[pos] = 1
                self.resource_map.pop(pos, None)
                self.monster_map.pop(pos, None)

    def reset(self) -> dict:
        """重置环境，返回初始观测"""
        self.agent = AgentState(x=self.size // 2, y=self.size // 2)
        self.time_of_day = 0
        self.rng = random.Random(self.seed)
        self._generate_world()
        return self._observe()

    def step(self, action: int) -> tuple:
        """执行动作，返回 (obs, reward, done, info)"""
        if self.agent.step_count >= self.max_steps:
            return self._observe(), 0, True, {"reason": "max_steps"}

        reward = 0.0
        done = False
        info = {"action": ACTIONS.get(action, "unknown")}

        # 执行动作
        if action == 1:  # 上
            self.agent.y = max(0, self.agent.y - 1)
        elif action == 2:  # 下
            self.agent.y = min(self.size - 1, self.agent.y + 1)
        elif action == 3:  # 左
            self.agent.x = max(0, self.agent.x - 1)
        elif action == 4:  # 右
            self.agent.x = min(self.size - 1, self.agent.x + 1)
        elif action == 5:  # 收集
            reward += self._collect()
        elif action == 6:  # 攻击
            reward += self._attack()

        # 环境反馈
        terrain = self.terrain_map.get((self.agent.x, self.agent.y), 0)

        # 危险
        if terrain == 4:  # 岩浆
            self.agent.hp -= HAZARDS["lava"]["damage"]
            reward -= 5
            info["hazard"] = "lava"
        elif terrain == 3:  # 水域
            self.agent.hp -= HAZARDS["water"]["damage"]
            reward -= 1
            info["hazard"] = "water"

        # 怪物攻击
        if (self.agent.x, self.agent.y) in self.monster_map:
            self.agent.hp -= HAZARDS["monster"]["damage"]
            reward -= 3
            info["hazard"] = "monster"

        # 能量消耗
        self.agent.energy = max(0, self.agent.energy - 1)

        # 时间推进
        self.agent.step_count += 1
        if self.agent.step_count % 50 == 0:
            self.time_of_day = 1 - self.time_of_day  # 昼夜切换

        # 死亡判定
        if self.agent.hp <= 0:
            done = True
            reward -= 50
            info["reason"] = "death"

        # 奖励：探索新区域
        if action in [1, 2, 3, 4]:
            reward += 0.1  # 移动奖励

        return self._observe(), reward, done, info

    def _collect(self) -> float:
        """收集当前格资源"""
        pos = (self.agent.x, self.agent.y)
        if pos in self.resource_map:
            res = self.resource_map.pop(pos)
            self.agent.inventory[res] += 1
            return RESOURCES[res]["value"]
        return 0

    def _attack(self) -> float:
        """攻击相邻怪物"""
        for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
            pos = (self.agent.x + dx, self.agent.y + dy)
            if pos in self.monster_map:
                monster = self.monster_map[pos]
                monster["hp"] -= 15
                if monster["hp"] <= 0:
                    del self.monster_map[pos]
                    self.agent.kills += 1
                    return 10
                return 2
        return 0

    def _observe(self) -> dict:
        """生成结构化观测（JSON 可序列化）"""
        x, y = self.agent.x, self.agent.y
        # 视野 5x5
        visible = []
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                vx, vy = x + dx, y + dy
                if 0 <= vx < self.size and 0 <= vy < self.size:
                    t = self.terrain_map.get((vx, vy), 0)
                    res = self.resource_map.get((vx, vy))
                    mob = (vx, vy) in self.monster_map
                    visible.append({
                        "dx": dx, "dy": dy,
                        "terrain": TERRAIN.get(t, "?"),
                        "terrain_id": t,
                        "resource": res,
                        "monster": mob,
                    })

        return {
            "agent": {
                "x": x, "y": y,
                "hp": self.agent.hp, "max_hp": self.agent.max_hp,
                "energy": self.agent.energy,
                "inventory": dict(self.agent.inventory),
                "step": self.agent.step_count,
                "kills": self.agent.kills,
            },
            "time": "day" if self.time_of_day == 0 else "night",
            "visible": visible,
            "actions": list(ACTIONS.values()),
        }

    def get_state_json(self) -> str:
        """完整状态 JSON（用于日志/分析）"""
        return json.dumps(self._observe(), ensure_ascii=False, indent=2)


# === 测试 ===
if __name__ == "__main__":
    world = OpenWorld2D(size=50, seed=42, max_steps=200)
    obs = world.reset()

    print("=== 2D 开放世界 ===")
    print(f"地图: {world.size}x{world.size}")
    print(f"出生点: ({obs['agent']['x']}, {obs['agent']['y']})")
    print(f"初始 HP: {obs['agent']['hp']}")
    print(f"时间: {obs['time']}")
    print(f"视野内格子数: {len(obs['visible'])}")

    # 随机走 50 步
    total_reward = 0
    for i in range(50):
        action = random.choice([1, 2, 3, 4, 5])
        obs, reward, done, info = world.step(action)
        total_reward += reward
        if done:
            print(f"\n💀 第 {i+1} 步结束: {info.get('reason', '?')}")
            break

    print(f"\n=== 50 步后 ===")
    print(f"总奖励: {total_reward:.1f}")
    print(f"位置: ({obs['agent']['x']}, {obs['agent']['y']})")
    print(f"HP: {obs['agent']['hp']}/{obs['agent']['max_hp']}")
    print(f"背包: {obs['agent']['inventory']}")
    print(f"步数: {obs['agent']['step']}")
