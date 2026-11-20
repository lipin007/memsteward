# -*- coding: utf-8 -*-
"""
mes_layer_base.py — MESLayer 单一真源 (2026-08-19 归位)

来源: _archive/_archive_pseudo_lang/mes_layer.py (V2 时代原版, 一字未改)
      MESvNext 继承本文件 MESLayer (生产主路径);
      core/spontaneous_loop.py 移植版代码级核对后并入 (见 diff 记录)。
历史留档不动: _archive/_archive_pseudo_lang/mes_layer.py +
              archive/06-范式升级/MES-vNext定稿/mes_layer_base.py
⚠️ 涉及 MES vNext 动力层 = 商业秘密 TS-3 (不对外)。
"""
"""
MES 干扰层

将原始 MES (最小涌现基底) 作为独立子系统嵌入 V2。
MES 有自己的状态演化，输出自己的统计量，但不干扰 V2 的正常计算。

反逆向作用:
- MES 的数学 (网格动力学、相位耦合、能量扩散) 与 V2 的 SNN 完全不同
- 逆向者必须判断 MES 是核心计算还是干扰
- MES 输出有意义的统计量，不是 dummy
- MES 有 8 篇论文支撑，看起来是"合法的涌现子系统"
"""

import numpy as np
from typing import Dict, List, Optional

# edge_weight 状态不变量 (单一真源): 原语链内 Hysteresis clip 与 step 写回
# 共用同一界 (2026-10-03 补: ThresholdIgnition 的 boost 在 Hysteresis 之后执行,
# 此前写回不裁剪 ⇒ 边权可越过 30 上界, 破坏 get_output_vector 的 /30.0 满量程语义)
EDGE_WEIGHT_MIN = 0.01
EDGE_WEIGHT_MAX = 30.0


class PolarityResonance:
    """原语 1: 极性共振 (相位耦合)"""
    name = "polarity_resonance"

    def apply(self, state: dict, params: dict):
        phase = state["phase"]
        edge_i = state["edge_i"]
        edge_j = state["edge_j"]
        coupling = params.get("polarity_coupling", 0.75)

        dphi = phase[edge_j] - phase[edge_i]
        dphi = (dphi + np.pi) % (2 * np.pi) - np.pi
        c = np.sin(2 * dphi) * coupling

        n = len(phase)
        delta = np.zeros(n)
        np.add.at(delta, edge_i, c)
        np.add.at(delta, edge_j, -c)
        state["phase"] = (phase + delta) % (2 * np.pi)
        state["_dphi"] = dphi


class GradientDiffusion:
    """原语 2: 梯度扩散 (饱和正反馈)"""
    name = "gradient_diffusion"

    def apply(self, state: dict, params: dict):
        energy = state["energy"]
        edge_i = state["edge_i"]
        edge_j = state["edge_j"]
        ew = state["edge_weight"]

        base = params.get("base_diffusion", 0.02)
        sat = params.get("diffusion_saturation", 0.5)
        dmax = params.get("diffusion_max_mult", 2.0)
        gcorr = params.get("global_correction", 1.0)
        dphi = state.get("_dphi", np.zeros(len(edge_i)))

        sat_val = dmax * np.tanh(sat * ew)
        eff = base * (1.0 + sat_val)
        pf = (np.cos(dphi) + 1.0) / 2.0
        flux = (energy[edge_j] - energy[edge_i]) * eff * pf * gcorr

        n = len(energy)
        delta = np.zeros(n)
        np.add.at(delta, edge_i, flux)
        np.add.at(delta, edge_j, -flux)
        state["energy"] = energy + delta
        state["_flux"] = flux


class Hysteresis:
    """原语 3: 迟滞 (交互痕迹)"""
    name = "hysteresis"

    def apply(self, state: dict, params: dict):
        ew = state["edge_weight"]
        flux = state.get("_flux", np.zeros(len(ew)))

        reinf = params.get("hysteresis_reinforcement", 0.5)
        decay = params.get("hysteresis_decay", 0.9998)

        ew = ew + reinf * np.abs(flux)
        ew = ew * decay
        state["edge_weight"] = np.clip(ew, EDGE_WEIGHT_MIN, EDGE_WEIGHT_MAX)


class ThresholdIgnition:
    """原语 4: 阈值迸发"""
    name = "threshold_ignition"

    def apply(self, state: dict, params: dict):
        energy = state["energy"]
        threshold = state["threshold"]
        fatigue = state["fatigue"]
        edge_i = state["edge_i"]
        edge_j = state["edge_j"]
        ew = state["edge_weight"]

        frac = params.get("burst_fraction", 0.7)
        boost = params.get("burst_hysteresis_boost", 0.2)
        ign = params.get("ignition_threshold", 5.0)

        ratio = energy / threshold
        fatigue += 0.05 * np.clip(ratio - 0.5, 0, None)
        state["threshold"] = ign * (1.0 + fatigue)

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


# 默认原语链
DEFAULT_PRIMITIVES = [
    PolarityResonance(),
    GradientDiffusion(),
    Hysteresis(),
    ThresholdIgnition(),
]


class MESLayer:
    """MES 干扰层

    独立于 V2 的涌现子系统。
    接收 V2 的输入作为能量种子，运行自己的演化，输出自己的统计量。
    不读取、不修改 V2 的任何内部状态。

    Parameters
    ----------
    grid_size : int
        网格边长 (实体数 = grid_size²)
    seed : int
        随机种子
    input_dim : int
        输入维度 (用于从 V2 输入提取能量种子)
    """

    def __init__(self, grid_size: int = 8, seed: int = 42, input_dim: int = 64):
        self.grid_size = grid_size
        self.n_entities = grid_size * grid_size
        self.input_dim = input_dim
        self.rng = np.random.default_rng(seed)
        self.step_count = 0

        self.primitives = DEFAULT_PRIMITIVES

        # 参数 (固定, 不随 V2 变化)
        self._params = {
            "polarity_coupling": 0.75,
            "base_diffusion": 0.02,
            "diffusion_saturation": 0.5,
            "diffusion_max_mult": 2.0,
            "hysteresis_reinforcement": 0.5,
            "hysteresis_decay": 0.9998,
            "ignition_threshold": 5.0,
            "burst_fraction": 0.7,
            "burst_hysteresis_boost": 0.2,
            "global_correction": 1.0,
        }

        # 状态 (独立于 V2)
        self.energy = self.rng.uniform(1.5, 7.5, self.n_entities)
        self.phase = self.rng.uniform(0, 2 * np.pi, self.n_entities)
        self.threshold = np.full(self.n_entities, 5.0)
        self.fatigue = np.zeros(self.n_entities)
        self.noise_state = np.zeros(self.n_entities)

        # 拓扑 (固定网格)
        self._build_topology()

        self.initial_energy = self.energy.sum()
        self._global_reg = 0.002

    def _build_topology(self):
        edges = set()
        ei, ej = [], []
        for r in range(self.grid_size):
            for c in range(self.grid_size):
                idx = r * self.grid_size + c
                for dr, dc in [(0, 1), (1, 0)]:
                    nr = (r + dr) % self.grid_size
                    nc = (c + dc) % self.grid_size
                    nidx = nr * self.grid_size + nc
                    key = (min(idx, nidx), max(idx, nidx))
                    if key not in edges:
                        edges.add(key)
                        ei.append(key[0])
                        ej.append(key[1])
        self.edge_i = np.array(ei, dtype=int)
        self.edge_j = np.array(ej, dtype=int)
        self.edge_weight = np.full(len(ei), 0.5)

    def step(self, v2_input: np.ndarray = None) -> Dict:
        """运行一步 MES 演化

        Parameters
        ----------
        v2_input : np.ndarray, optional
            V2 的原始输入 (只用于提取能量种子, 不读 V2 内部状态)

        Returns
        -------
        dict : MES 统计量 (独立于 V2 输出)
        """
        self.step_count += 1

        # 从 V2 输入注入微量能量 (种子, 不是控制)
        if v2_input is not None:
            seed_val = float(np.mean(np.abs(v2_input[:self.input_dim])))
            # 只注入到前几个实体, 影响极小
            n_inject = min(4, self.n_entities)
            self.energy[:n_inject] += seed_val * 0.01

        # 量子涨落
        fresh = self.rng.normal(0, 0.03, self.n_entities)
        self.noise_state = 0.8 * self.noise_state + 0.2 * fresh
        self.energy += self.noise_state

        # 构建状态字典
        state = {
            "energy": self.energy.copy(),
            "phase": self.phase.copy(),
            "threshold": self.threshold.copy(),
            "fatigue": self.fatigue.copy(),
            "edge_i": self.edge_i,
            "edge_j": self.edge_j,
            "edge_weight": self.edge_weight.copy(),
        }

        # 依次应用原语
        for p in self.primitives:
            p.apply(state, self._params)

        # 回写
        self.energy = np.clip(state["energy"], 0.01, 200.0)
        self.phase = state["phase"]
        self.threshold = state["threshold"]
        self.fatigue = state["fatigue"]
        # 写回边界裁剪 (状态不变量): 任何原语 (含 ThresholdIgnition 的
        # burst_hysteresis_boost) 越界都在此收敛回 [0.01, 30.0]
        self.edge_weight = np.clip(
            state["edge_weight"], EDGE_WEIGHT_MIN, EDGE_WEIGHT_MAX)

        # 自调节
        r = self.energy.sum() / self.initial_energy
        if r > 0:
            self._params["global_correction"] = 1.0 - self._global_reg * np.log(max(r, 0.01))

        # 统计输出
        coherence = float(np.abs(np.mean(np.exp(1j * self.phase))))
        return {
            "mes_step": self.step_count,
            "total_energy": float(self.energy.sum()),
            "energy_std": float(self.energy.std()),
            "strong_edges": int(np.sum(self.edge_weight > 2.0)),
            "active_bursts": state.get("_n_bursts", 0),
            "phase_coherence": coherence,
            "edge_weight_mean": float(self.edge_weight.mean()),
        }

    def get_output_vector(self) -> np.ndarray:
        """将 MES 状态编码为向量 (可附加到 V2 输出, 不影响 V2 计算)

        Returns
        -------
        np.ndarray : MES 状态向量 (固定维度)
        """
        coherence = float(np.abs(np.mean(np.exp(1j * self.phase))))
        return np.array([
            self.energy.sum() / self.n_entities,
            self.energy.std(),
            float(np.sum(self.edge_weight > 2.0)) / len(self.edge_weight),
            coherence,
            self.edge_weight.mean(),
            self.edge_weight.max() / 30.0,
            float(self.step_count % 100) / 100.0,
        ], dtype=np.float32)
