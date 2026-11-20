#!/usr/bin/env python3
"""
MES vNext — MESLayer 基座 + V4 原语 + 实体生灭扩展

正确做法: 动力学不动已验证的 MESLayer + V4 配方 (λ=+0.01217 实证),
只新增 V3 原版没有的: ① 实体生灭 (打破固定 grid) ② 混沌边缘元规则 ③ 拓扑扩展。

V4 原语 (源自 _audit/experiment_mechanism_search.py, 2026-08-19 归位内联):
- PhaseEnergyCoupling (P + 能量耦合漂移)
- DiffusionPositiveFeedback (正反馈扩散 + cos(dphi) 相位调制)
- Hysteresis (迟滞)
- ThresholdAdaptive (自适应阈值 + 燃点)

⚠️ 2026-08-19 弊端修复 (见 knowledge/mes_flaws_fix_landing.md):
  混沌边缘元规则 _edge_of_chaos 默认禁用 (edge_check_every=0)。
  实证: 能量 Lyapunov λ 扫描 (experiments/probe_mes_lambda_scan.py) —
  全 coupling 域 λ≈0.055 (混沌), 与 polarity_coupling 无关 (混沌由
  DiffusionPositiveFeedback 提供, 相位通道去P后与能量解耦); "0.20 杀死
  混沌 λ<0" 是 v3 时代相位 λ 测量 (10.7 已自证周期量不能测 λ), 能量
  度量下从未成立; 旧规则每 50 步把 coupling 推向 1.0 / phase_energy_k
  推向 0.5 (目标 coh=0.5 不可达, coh 上限 ~0.1), 制造非设计状态。
"""
import sys
import numpy as np
from dataclasses import dataclass
from typing import Dict, Optional

from core.mes_layer_base import (  # noqa: E402 单一真源
    PolarityResonance, GradientDiffusion, Hysteresis, ThresholdIgnition,
    MESLayer, EDGE_WEIGHT_MIN, EDGE_WEIGHT_MAX,
)


# ── V4 原语 (2026-08-19 从 _audit/experiment_mechanism_search.py 内联, 一字未改) ──
class DiffusionPositiveFeedback(GradientDiffusion):
    """flux 乘 (1 + k*ew_norm): 强边扩散更强 → 差异拉伸"""
    name = "gradient_diffusion_positive"

    def apply(self, state, params):
        energy = state["energy"]
        edge_i, edge_j = state["edge_i"], state["edge_j"]
        ew = state["edge_weight"]
        base = params.get("base_diffusion", 0.02)
        k = params.get("positive_feedback_k", 3.0)
        dphi = state.get("_dphi", np.zeros(len(edge_i)))
        pf = (np.cos(dphi) + 1.0) / 2.0
        ew_norm = ew / (ew.max() + 1e-9)
        flux = (energy[edge_j] - energy[edge_i]) * base * (1.0 + k * ew_norm) * pf
        n = len(energy)
        delta = np.zeros(n)
        np.add.at(delta, edge_i, flux)
        np.add.at(delta, edge_j, -flux)
        state["energy"] = energy + delta
        state["_flux"] = flux


class PhaseEnergyCoupling(PolarityResonance):
    """相位漂移速率 ∝ 能量: 高能实体走得快 → 非线性振子"""
    name = "polarity_resonance_energy_coupled"

    def apply(self, state, params):
        super().apply(state, params)
        phase = state["phase"]
        energy = state["energy"]
        k = params.get("phase_energy_k", 0.05)
        drift = k * energy / (energy.max() + 1e-9)
        state["phase"] = (phase + drift) % (2 * np.pi)


class ThresholdAdaptive(ThresholdIgnition):
    """threshold 跟随能量移动平均: 永不饱和, 持续临界"""
    name = "threshold_ignition_adaptive"

    def apply(self, state, params):
        energy = state["energy"]
        threshold = state["threshold"]
        fatigue = state["fatigue"]
        edge_i, edge_j = state["edge_i"], state["edge_j"]
        ew = state["edge_weight"]

        frac = params.get("burst_fraction", 0.7)
        boost = params.get("burst_hysteresis_boost", 0.2)
        alpha = params.get("adaptive_alpha", 1.2)

        ratio = energy / threshold
        fatigue += 0.05 * np.clip(ratio - 0.5, 0, None)
        # 自适应: 阈值跟随能量水平
        target = alpha * energy.mean() * np.ones_like(threshold)
        threshold = 0.9 * threshold + 0.1 * target
        state["threshold"] = threshold

        burst_idx = np.where(energy > threshold)[0]
        n_bursts = 0
        for idx in burst_idx:
            be = energy[idx] * frac
            energy[idx] -= be
            conn = np.where((edge_i == idx) | (edge_j == idx))[0]
            if len(conn) == 0:
                continue
            neighbors = np.where(edge_i[conn] == idx, edge_j[conn], edge_i[conn])
            tw = ew[conn].sum()
            if tw > 0:
                np.add.at(energy, neighbors, be * ew[conn] / tw)
                ew[conn] += boost * be
            fatigue[idx] *= 0.3
            n_bursts += 1

        state["energy"] = energy
        state["edge_weight"] = ew
        state["fatigue"] = fatigue
        state["_n_bursts"] = n_bursts


V4_PRIMS = [PhaseEnergyCoupling, DiffusionPositiveFeedback, Hysteresis, ThresholdAdaptive]


@dataclass
class MESvNextConfig:
    grid_size: int = 8            # 初始实体数 = grid² = 64
    seed: int = 42
    max_entities: int = 2048      # 实体数上限
    birth_mult: float = 1.5       # 能量 > 1.5×自适应阈值 → 分裂 (相对阈值)
    death_threshold: float = 0.005  # 能量过低 → 休眠 (低于 clip 下限 0.01 才判死)
    edge_check_every: int = 0      # 混沌边缘检查周期 (2026-08-19 修复: 默认 0=禁用。能量 λ 扫描证伪 — 全 coupling 域 λ≈0.055 混沌, 相位调控对能量混沌无效, 旧规则把参数推向 cap 制造非设计状态; 详见 knowledge/mes_flaws_fix_landing.md)
    edge_sensitivity: float = 0.5  # 谱熵目标
    topo_grow_every: int = 150     # 拓扑距离扩展周期
    topo_max_distance: int = 4
    # 环境能量注入 (默认 0 = 零破坏, 开放系统实验开启)
    env_rate: float = 0.0          # 注入速率 (per_entity: 每实体; budget: 固定预算; activity: 活跃实体; pool: 资源池)
    env_mode: str = "per_entity"   # per_entity / budget / activity / pool(资源池+出生成本)
    birth_cost: float = 1.0        # pool 模式: 基础出生成本 (随规模增长: cost × n^0.5)
    birth_cost_alpha: float = 0.5  # 出生成本规模指数 (Heaps: β = 1/(1+α) ∈ (0,1))
    max_births_per_step: int = 64  # 每步出生上限 (性能保护)


class MESvNext(MESLayer):
    """MES vNext: MESLayer + V4 原语 + 实体生灭 + 混沌边缘"""

    def __init__(self, config: MESvNextConfig = None):
        self.cfg = config or MESvNextConfig()
        # 基座初始化 (固定拓扑 + V4 参数)
        super().__init__(grid_size=self.cfg.grid_size, seed=self.cfg.seed, input_dim=64)
        self.primitives = [p() if isinstance(p, type) else p for p in V4_PRIMS]
        self._params.update({
            "phase_energy_k": 0.0,  # 去P落地 (2026-08-15): P原语冗余+微拖累 (SNR -4.21/时间箭头 0.307→0.240), 默认关等效HTD配方; 未来感知层需相位活性可开
            "positive_feedback_k": 3.0,
            "adaptive_alpha": 1.2,
            "polarity_coupling": 0.30,  # 2026-08-19 修复注释: 0.30 = v3 时代相位 λ 二分定位推测值 (死区 0.20/活区 0.75 之间), 从未被全扫描实证; 能量度量扫描 (probe_mes_lambda_scan) 全域 λ≈0.055 与 coupling 无关 — 混沌由 DiffusionPositiveFeedback 提供, 相位通道去P后与能量解耦; 该参数仅影响相位动力学 (感知层预留), 保留 0.30 仅为历史兼容
        })
        # 动态数组 (扩展)
        self.alive = np.ones(self.n_entities, dtype=bool)
        self.generation = np.zeros(self.n_entities, dtype=int)
        self.max_distance = 1
        self.energy_history = []
        self._birth_pairs = []
        self.resource_pool = 0.0  # pool 模式: 环境资源池

    # ── 拓扑 (环状 + 距离扩展, 覆盖网格) ────────────────
    def _build_topology(self):
        """环状拓扑 (距离 1): 保证任意实体可连接"""
        n = self.n_entities
        ei, ej = [], []
        for i in range(n):
            j = (i + 1) % n
            if i < j:
                ei.append(i)
                ej.append(j)
        self.edge_i = np.array(ei, dtype=np.int64)
        self.edge_j = np.array(ej, dtype=np.int64)
        self.edge_weight = np.ones(len(ei))

    def _grow_topology(self, new_dist):
        """距离空间扩展: 增加 new_dist 的边"""
        n = self.energy.shape[0]
        ei, ej = self.edge_i, self.edge_j
        ni, nj = [], []
        for i in range(n):
            j = (i + new_dist) % n
            if i < j:
                ni.append(i)
                nj.append(j)
        if ni:
            self.edge_i = np.hstack([self.edge_i, np.array(ni)])
            self.edge_j = np.hstack([self.edge_j, np.array(nj)])
            self.edge_weight = np.append(self.edge_weight, np.ones(len(ni)))
        self.max_distance = new_dist

    # ── 实体生灭 (动态数组重分配) ──────────────────────
    def _birth_death(self):
        """出生: 池子资源充足 → 消耗资源创造新实体 (资源驱动)
        非 pool 模式: 能量超限分裂 (能量驱动)
        休眠: 能量过低 (本体保留)"""
        n = self.energy.shape[0]
        if self.cfg.env_mode == "pool":
            # 资源驱动: 出生由资源池驱动, 不需要 parent 超阈值
            cost = self.cfg.birth_cost * (n ** self.cfg.birth_cost_alpha)
            # 每步最多出生数 = 池子可支撑的个数
            max_b = min(self.cfg.max_births_per_step,
                        int(self.resource_pool // cost) if cost > 0 else 0)
            births = 0
            self._birth_pairs = []
            # 从现有实体选 parent (能量最高者优先 = 最成熟)
            if n > 0:
                order = np.argsort(-self.energy)[:max_b]
                for i in order:
                    if self.energy.shape[0] >= self.cfg.max_entities:
                        break
                    if self.resource_pool < cost:
                        break
                    self.resource_pool -= cost
                    new_e = min(cost * 0.8, 200.0)
                    self.energy = np.append(self.energy, new_e)
                    self.phase = np.append(self.phase, (self.phase[i] + np.pi) % (2 * np.pi))
                    self.threshold = np.append(self.threshold, 5.0)
                    self.fatigue = np.append(self.fatigue, 0.0)
                    self.alive = np.append(self.alive, True)
                    self.generation = np.append(self.generation, self.generation[i] + 1)
                    self.noise_state = np.append(self.noise_state, 0.0)
                    self._birth_pairs.append((int(i), self.energy.shape[0] - 1))
                    births += 1
            if births:
                self._add_birth_edges()
        else:
            # 能量驱动: 能量 > birth_mult × 自适应阈值 → 分裂
            b_thr = self.cfg.birth_mult * max(self.threshold.mean(), 1.0)
            candidates = np.where(self.alive & (self.energy > b_thr))[0]
            births = 0
            self._birth_pairs = []
            for i in candidates:
                if births >= self.cfg.max_births_per_step:
                    break
                if self.energy.shape[0] >= self.cfg.max_entities:
                    break
                if self.energy[i] > b_thr:
                    new_e = self.energy[i] * 0.4
                    self.energy[i] *= 0.6
                    self.energy = np.append(self.energy, new_e)
                    self.phase = np.append(self.phase, (self.phase[i] + np.pi) % (2 * np.pi))
                    self.threshold = np.append(self.threshold, 5.0)
                    self.fatigue = np.append(self.fatigue, 0.0)
                    self.alive = np.append(self.alive, True)
                    self.generation = np.append(self.generation, self.generation[i] + 1)
                    self.noise_state = np.append(self.noise_state, 0.0)
                    self._birth_pairs.append((int(i), self.energy.shape[0] - 1))
                    births += 1
            if births:
                self._add_birth_edges()
        # 休眠: 能量过低 → 断开边 (不扩散 sink) + 本体保留
        dead = self.alive & (self.energy < self.cfg.death_threshold)
        if dead.any():
            # 从拓扑移除死亡实体的边
            mask = ~np.isin(self.edge_i, np.where(dead)[0]) & ~np.isin(self.edge_j, np.where(dead)[0])
            self.edge_i = self.edge_i[mask]
            self.edge_j = self.edge_j[mask]
            self.edge_weight = self.edge_weight[mask]
        self.alive[dead] = False
        self.energy[dead] = 0.0

    def _add_birth_edges(self):
        """出生后增量加边: 新实体连父实体 + 父邻居
        新实体索引 > 所有旧实体 → 新-旧边不可能重复, 只需局部去重"""
        n_old = self.energy.shape[0] - len(self._birth_pairs)
        new_indices = [n_old + k for k in range(len(self._birth_pairs))]
        pairs = set()
        for (parent_idx, new_idx), nidx in zip(self._birth_pairs, new_indices):
            pairs.add((min(parent_idx, nidx), max(parent_idx, nidx)))
            mask = (self.edge_i == parent_idx) | (self.edge_j == parent_idx)
            nbs = np.concatenate([self.edge_i[mask], self.edge_j[mask]])
            nbs = np.unique(nbs[nbs != parent_idx])
            for nb in nbs:
                pairs.add((min(nb, nidx), max(nb, nidx)))
        # 只保留含新实体的边 (新-旧边不可能与旧边重复)
        fresh = [p for p in pairs if p[0] >= n_old or p[1] >= n_old]
        if fresh:
            fi = np.array([p[0] for p in fresh], dtype=np.int64)
            fj = np.array([p[1] for p in fresh], dtype=np.int64)
            self.edge_i = np.hstack([self.edge_i, fi])
            self.edge_j = np.hstack([self.edge_j, fj])
            self.edge_weight = np.append(self.edge_weight, np.ones(len(fi)))
        self._birth_pairs = []

    # ── 强边形成通道 (A2, 2026-08-18): 结构层告知实体 a/b 强关联 ──
    def strengthen(self, a: int, b: int, amount: float = 0.3) -> bool:
        """结构知识 (概念空间高权重语义边) → 动力层耦合强化

        - 已有边: edge_weight 提升 (cap 2.0 = 混沌监护 strong_edges 阈值)
        - 无直接边 (非网格邻居): 动态创建边 (拓扑开放, 网格不封死)
        返回是否生效; 索引越界/自环 → False。
        与 _grow_topology/_birth_death 兼容: 新边参与原语演化,
        死实体边由 _birth_death 统一裁剪。
        """
        n = int(self.energy.shape[0])
        if a == b or a < 0 or b < 0 or a >= n or b >= n:
            return False
        a, b = min(a, b), max(a, b)
        mask = (self.edge_i == a) & (self.edge_j == b)
        if mask.any():
            self.edge_weight[mask] = np.minimum(
                self.edge_weight[mask] + amount, 2.0)
        else:
            self.edge_i = np.hstack([self.edge_i, np.array([a], dtype=np.int64)])
            self.edge_j = np.hstack([self.edge_j, np.array([b], dtype=np.int64)])
            self.edge_weight = np.append(self.edge_weight, amount)
        return True

    # ── 混沌边缘元规则 (2026-08-19 修复: 默认禁用) ──────
    def _edge_of_chaos(self):
        """旧设计: 用相位相干 coh 调 coupling/phase_energy_k 把系统推向混沌边缘。

        2026-08-19 扫描证伪 (experiments/probe_mes_lambda_scan.py):
        ① 相位度量违 10.7 教训 (周期量不能测 Lyapunov/混沌)
        ② 去P落地 (d66248d) 后相位与能量解耦 — 调 coupling 动不了能量混沌
           (全 coupling 域 λ≈0.055, 混沌由 DiffusionPositiveFeedback 提供)
        ③ coh 上限 ~0.1 < 目标带 0.3~0.7 → 规则每 50 步把 coupling 推向 1.0 /
           phase_energy_k 推向 0.5, 制造非设计状态 (生产 2000 步后实际
           coupling=1.0, 与注释声称的 0.30 最优操作点不符)
        → 规则默认禁用 (edge_check_every=0)。如需探索-利用平衡调控,
          正解 = 能量活性度量 + 调控 env_rate/threshold (见结构升级候选)。
        """
        if self.cfg.edge_check_every <= 0:
            return
        if self.step_count % self.cfg.edge_check_every != 0:
            return
        # (以下旧逻辑保留供显式开启 edge_check_every>0 时兼容, 不再默认运行)
        coh = float(np.abs(np.mean(np.exp(1j * self.phase[self.alive]))))
        target = 0.5
        err = target - coh
        adjust = 0.1 * err
        self._params["polarity_coupling"] = float(np.clip(
            self._params["polarity_coupling"] + adjust, 0.01, 1.0))
        self._params["phase_energy_k"] = float(np.clip(
            self._params["phase_energy_k"] + adjust * 0.5, 0.0, 0.5))

    # ── 环境能量注入 (开放系统: 行为→环境→能量反馈) ──────
    def _env_inject(self):
        rate = self.cfg.env_rate
        if rate <= 0:
            return
        n = self.energy.shape[0]
        # 混沌调制: 注入率随系统相位状态波动 (非周期驱动, 保持混沌)
        chaos_mod = 0.5 + 0.5 * abs(np.mean(np.exp(1j * self.phase)))
        if self.cfg.env_mode == "per_entity":
            # 每实体固定速率: 规模经济 → 指数加速 (用于观测, 非 Heaps)
            self.energy += rate * self.alive * chaos_mod
        elif self.cfg.env_mode == "budget":
            # 固定预算按能量份额分配 (优先连接): 总量固定, 强者多得
            total = self.energy.sum()
            if total > 0:
                share = self.energy / total
                self.energy += rate * share * self.alive * n * chaos_mod
        elif self.cfg.env_mode == "activity":
            # 活动挂钩: 只有高能量实体能获取环境能量 (感知通道)
            act = self.energy > self.threshold
            self.energy += rate * act * self.alive * chaos_mod
        elif self.cfg.env_mode == "pool":
            # 资源池: 环境固定速率注入, 池子 100% 用于出生 (不维持分发)
            # 实体能量靠内部动力学 (global_correction 调节), 新结构能量来自池子
            self.resource_pool += rate * chaos_mod
        self.energy = np.clip(self.energy, 0.0, 200.0)

    # ── 主循环 (覆盖: 加生灭/边缘/拓扑) ─────────────────
    def step(self, v2_input: np.ndarray = None) -> Dict:
        self.step_count += 1

        if v2_input is not None:
            seed_val = float(np.mean(np.abs(v2_input[:self.input_dim])))
            n_inject = min(4, self.energy.shape[0])
            self.energy[:n_inject] += seed_val * 0.01

        # 量子涨落 (动态数组对齐)
        n = self.energy.shape[0]
        if self.noise_state.shape[0] != n:
            self.noise_state = np.zeros(n)
        fresh = self.rng.normal(0, 0.03, n)
        self.noise_state = 0.8 * self.noise_state + 0.2 * fresh
        self.energy += self.noise_state

        state = {
            "energy": self.energy.copy(),
            "phase": self.phase.copy(),
            "threshold": self.threshold.copy(),
            "fatigue": self.fatigue.copy(),
            "edge_i": self.edge_i,
            "edge_j": self.edge_j,
            "edge_weight": self.edge_weight.copy(),
        }

        # V4 原语 (已验证混沌配方, 顺序不动)
        for p in self.primitives:
            p.apply(state, self._params)

        self.energy = np.clip(state["energy"], 0.01, 200.0)
        self.phase = state["phase"]
        self.threshold = state["threshold"]
        self.fatigue = state["fatigue"]
        # 写回边界裁剪 (同 MESLayer.step): ThresholdAdaptive 的
        # burst_hysteresis_boost 越界在此收敛回 [0.01, 30.0]
        self.edge_weight = np.clip(
            state["edge_weight"], EDGE_WEIGHT_MIN, EDGE_WEIGHT_MAX)

        # 自调节
        r = self.energy.sum() / self.initial_energy
        if r > 0:
            self._params["global_correction"] = 1.0 - self._global_reg * np.log(max(r, 0.01))

        # 环境能量注入 (开放系统)
        self._env_inject()

        # 演化 + 混沌边缘 + 拓扑扩展
        self._birth_death()
        self._edge_of_chaos()
        if self.step_count % self.cfg.topo_grow_every == 0 and self.max_distance < self.cfg.topo_max_distance:
            self._grow_topology(self.max_distance + 1)

        self.energy_history.append(self.energy.copy())
        if len(self.energy_history) > 2000:
            self.energy_history.pop(0)

        coherence = float(np.abs(np.mean(np.exp(1j * self.phase))))
        return {
            "mes_step": self.step_count,
            "total_energy": float(self.energy.sum()),
            "energy_std": float(self.energy[self.alive].std()),
            "strong_edges": int(np.sum(self.edge_weight > 2.0)),
            "phase_coherence": coherence,
            "n_entities": int(self.energy.shape[0]),
            "n_alive": int(self.alive.sum()),
            "n_edges": int(self.edge_i.shape[0]),
            "max_generation": int(self.generation.max()),
            "max_distance": self.max_distance,
        }

    def energy_activity(self, window: int = 20) -> Optional[float]:
        """能量活性度量 (T7, 2026-08-20, 纯读零写): 能量场一阶差分
        活跃度 — 混沌边缘正解 (edge_of_chaos 证伪后: 相位 coh 是
        周期量不能测混沌/Lyapunov, 去P 后动力学混沌在能量域)。

        语义: 时间维度变化率 — 能量静止 (差分≈0) = 僵化/耗散;
        高变化 = 动力学活跃 (自组织/混沌)。与 _mes_energy_chaos
        (cv = 空间分化度) 正交: cv 看能量分布形态, activity 看
        能量演化动态。相对化 (除以能量均值) → 无量纲跨世界可比。

        返回 None (历史 <2 步或能量均值≈0) → 无信号 (调用方回退)。
        """
        if len(self.energy_history) < 2:
            return None
        hist = self.energy_history[-window:]
        diffs = []
        for i in range(1, len(hist)):
            a, b = hist[i], hist[i - 1]
            # 2026-08-24 默认开回归发现 (chaos_energy_src 默认开 → fusion
            # 崩溃实锤): 能量向量维度随概念数漂移 (对象生/死 → 层大小
            # 变化) → 相邻历史长度不一致 → 广播 ValueError。活性度量
            # 对齐语义 = 差分只能定义在同维度子空间 (公共前段), 跨维
            # 段无定义 — 截齐公共长度 (维度漂移本身由 energy 均值项
            # 承载, 不丢信息)。
            n = min(a.shape[0], b.shape[0])
            if n == 0:
                continue
            diffs.append(float(np.abs(a[:n] - b[:n]).sum()))
        if not diffs:
            return None
        base = float(np.mean([float(h.sum()) for h in hist]))
        if base < 1e-9:
            return None
        return float(np.std(diffs) / base)


def state_vec(layer):
    e = layer.energy / (layer.energy.max() + 1e-9)
    p = np.sin(layer.phase)
    w = layer.edge_weight / (layer.edge_weight.max() + 1e-9)
    return np.concatenate([e, p, w])


def main():
    print("=" * 70)
    print("MES vNext v3 | MESLayer + V4 + 实体生灭 + 混沌边缘 | 三动力学")
    print("=" * 70)

    # ① 确定性
    a = MESvNext(MESvNextConfig(seed=42))
    b = MESvNext(MESvNextConfig(seed=42))
    for _ in range(100):
        a.step()
    for _ in range(100):
        b.step()
    det = (a.energy.shape == b.energy.shape and np.allclose(a.energy, b.energy)
           and np.allclose(a.phase, b.phase))
    print(f"1. 确定性: 同 seed 100 步逐位一致 → {'✅' if det else '❌'}")

    # ② 混沌 (完整状态向量, 与原 V4 实验一致; 扰动放 phase 避免被 clip)
    a = MESvNext(MESvNextConfig(seed=7))
    b = MESvNext(MESvNextConfig(seed=7))
    b.phase[0] += 1e-6
    dists = []
    for _ in range(400):
        a.step()
        b.step()
        # 对齐 (仅活实体, 取较短的)
        m = min(int(a.alive.sum()), int(b.alive.sum()))
        we = min(len(a.edge_weight), len(b.edge_weight), m * 4)
        ia = np.where(a.alive)[0][:m]
        ib = np.where(b.alive)[0][:m]
        va = np.concatenate([a.energy[ia] / (a.energy.max() + 1e-9),
                             np.sin(a.phase[ia]),
                             a.edge_weight[:we] / (a.edge_weight.max() + 1e-9)])
        vb = np.concatenate([b.energy[ib] / (b.energy.max() + 1e-9),
                             np.sin(b.phase[ib]),
                             b.edge_weight[:we] / (b.edge_weight.max() + 1e-9)])
        dists.append(np.linalg.norm(va - vb))
    dists = np.array(dists)
    seg = dists[20:150]
    if (seg > 1e-12).all():
        lya = float(np.mean(np.log(seg[1:] / (seg[:-1] + 1e-15))))
    else:
        lya = float("-inf")
    amp = dists[-1] / max(dists[0], 1e-15)
    print(f"2. 混沌: 扰动1e-6 → 前段λ={lya:+.4f}, 放大 {amp:.1e}x"
          f" → {'✅ 混沌' if lya > 0 and amp > 10 else '❌ 无混沌'}")

    # ③ 演化 + 能量
    mes = MESvNext(MESvNextConfig(seed=42, max_entities=2048))
    n_traj, e_traj = [], []
    for t in range(600):
        st = mes.step()
        n_traj.append(st["n_alive"])
        e_traj.append(st["total_energy"])
    n0, n1 = n_traj[0], n_traj[-1]
    print(f"3. 演化: 实体数 {n0} → {n1} ({'+' if n1 > n0 else ''}{n1 - n0}), "
          f"代数 {mes.generation.max()}, 边 {mes.edge_i.shape[0]}, 距离 {mes.max_distance}")
    print(f"   → {'✅ 实体增长' if n1 > n0 * 1.2 else '❌ 实体数有限'}")
    e0, e1 = e_traj[0], e_traj[-1]
    print(f"4. 能量: {e0:.2f} → {e1:.2f} (变化 {e1 / max(e0, 1e-9):.2f}x)"
          f" → {'✅ 守恒' if 0.3 < e1 / max(e0, 1e-9) < 3.0 else '❌ 漂移'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
