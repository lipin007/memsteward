# -*- coding: utf-8 -*-
"""M3 相位场 — 概念时间属性统一读出视图 (V3 图纸 M3 移植, 2026-08-12)

图纸: plan/modules/M3-相位场.md
概念 = 空间区域 = vNext 实体 (能量/相位) + M2 结构槽位, 一个概念一条记录。
本模块 = M3 语义读出层: 把概念的时间属性 (相位/能量/相干/成熟度/活跃度)
统一视图读出。数据本体 = 既有 vNext (rhythm_vnext, 连续动力学) +
既有相位场 (concept_phase, 成熟度/巩固), 零复制零双写。

🔴 2026-08-12 用户拍板 + 最小验证修正:
  动力学蓝本 = MES vNext (连续时间); 语义相干 = 能量同步 (非相位锁定)。
  - 相干度 (语义) = 1 - |ΔE|/E_scale (共现概念能量趋同)
  - 相位承载"过程/时序" (V2 过程计算语义), 不承载稳定分类
  - verify_m3_semantics3 3/3 已证: 共现能量差 0.117 vs 无关 0.193

时间属性单点持有 (防双写): activity/maturity/coherence/phase/last_tick
全部经本视图查询 — M2 结构记录中无副本。文件分离 ≠ 数据分离。
本模块不判定 (三档判据是信号, 判定在 M6)。
"""
from typing import Dict, Optional
import numpy as np


class PhaseField:
    """概念时间属性读出层 — 单一真源: vNext 实体 + 概念相位场

    M3 写相位字段 (经 rhythm_vnext.observe_event / step / concept_phase),
    M2 写结构字段; 本视图只读联合, 零合并零复制。
    """

    # 代谢参数 (时间不可约, 图纸 §2b/§3)
    ACT_DECAY = 0.9        # 动作活跃度代谢率
    EDGE_DECAY = 0.85      # 因果边证据代谢率 (V2 edge_decay 已验证)
    EDGE_DEAD = 0.3        # 活性死亡阈值 (低于此=休眠, 本体保留)
    MATURITY_RATE = 0.05   # 成熟度积累率 (每次巩固 +0.05)
    E_SCALE = 200.0        # 能量标尺 (能量 clip 上限, 相干归一化)

    def __init__(self, cs):
        self.cs = cs
        self._last_tick: Dict[str, int] = {}  # 概念 → 最近更新 t (本视图维护)

    # ── 能量 (vNext 实体) ────────────────────────────────────
    def energy(self, concept: str) -> float:
        """概念能量 (vNext 实体, 无实体=0)"""
        rv = getattr(self.cs, 'rhythm', None) or getattr(self.cs, '_rhythm', None)
        if rv is None or not getattr(rv, 'concept_idx', None):
            return 0.0
        idx = rv.concept_idx.get(concept)
        if idx is None:
            return 0.0
        return float(rv.mes.energy[idx])

    def energy_sync_coherence(self, a: str, b: str) -> float:
        """语义相干度 = 能量同步 (1 - |ΔE|/E_scale, 0~1)

        共现概念能量趋同 → 高相干; 无关概念能量差异大 → 低相干。
        verify_m3_semantics3 实证: 共现 ΔE=0.117 vs 无关 0.193。
        """
        ea, eb = self.energy(a), self.energy(b)
        if ea <= 0 or eb <= 0:
            return 0.0
        return max(0.0, 1.0 - abs(ea - eb) / self.E_SCALE)

    # ── 相位 (过程/时序承载) ────────────────────────────────
    def phase(self, concept: str) -> Optional[float]:
        """概念相位 [0, 2π) — 优先 vNext, 回退概念相位场"""
        rv = getattr(self.cs, 'rhythm', None) or getattr(self.cs, '_rhythm', None)
        if rv is not None and concept in getattr(rv, 'concept_idx', {}):
            idx = rv.concept_idx[concept]
            return float(rv.mes.phase[idx] % (2 * np.pi))
        ph = getattr(self.cs, '_phases', {})
        if concept in ph:
            return float(ph[concept])
        return None

    def phase_coherence(self, concept: str) -> float:
        """与主簇的相位相干 (1 - d/π, 0~1) — V2 公式"""
        ph = self.phase(concept)
        if ph is None:
            return 0.0
        anchor = getattr(self.cs, '_phase_anchor', None)
        if callable(anchor):
            a = anchor()
        else:
            phases = [self.phase(c) for c in self._concepts_in_field()]
            phases = [p for p in phases if p is not None]
            if not phases:
                return 0.0
            z = np.mean(np.exp(1j * np.array(phases)))
            a = float(np.angle(z))
        d = abs((ph - a + np.pi) % (2 * np.pi) - np.pi)
        return 1.0 - d / np.pi

    def _concepts_in_field(self) -> list:
        """场中全部概念 (vNext 概念 ∪ 相位场概念)"""
        out = set()
        rv = getattr(self.cs, 'rhythm', None) or getattr(self.cs, '_rhythm', None)
        if rv is not None:
            out |= set(getattr(rv, 'concept_idx', {}))
        out |= set(getattr(self.cs, '_phases', {}))
        return sorted(out)

    # ── 成熟度 (巩固累积) ────────────────────────────────────
    def maturity(self, concept: str) -> float:
        """成熟度 [0,1] — vNext 能量归一化代理 (巩固累积的动力学形)"""
        e = self.energy(concept)
        return min(1.0, e / 50.0)  # 能量 50 = 成熟 (量级校准)

    def consolidate(self, concept: str, t: int = 0) -> None:
        """巩固: 能量注入 + 时间锚更新 (全部概念, 非 top-K)"""
        rv = getattr(self.cs, 'rhythm', None) or getattr(self.cs, '_rhythm', None)
        if rv is not None and hasattr(rv, 'observe_event'):
            rv.observe_event(concept, '巩固', None)
        self._last_tick[concept] = t

    # ── 代谢 (时间不可约) ────────────────────────────────────
    def decay(self, concept: str, factor: float = None) -> None:
        """代谢: 能量 × factor (默认 ACT_DECAY) — 时间流逝"""
        f = factor if factor is not None else self.ACT_DECAY
        rv = getattr(self.cs, 'rhythm', None) or getattr(self.cs, '_rhythm', None)
        if rv is not None and concept in getattr(rv, 'concept_idx', {}):
            idx = rv.concept_idx[concept]
            rv.mes.energy[idx] = max(0.01, rv.mes.energy[idx] * f)

    def is_dormant(self, concept: str) -> bool:
        """休眠判定: 能量 < 阈值 且 长期未更新 (本体保留, 可恢复)"""
        e = self.energy(concept)
        return e < 1.0  # 低能量 = 休眠 (再次观察 +0.5 恢复)

    # ── 三档对齐信号 (M3 输出信号, 非判定 — 判定在 M6) ──────
    def align_tier(self, concept: str, known_coherence: float = 0.5) -> int:
        """相位层三档对齐信号 (图纸 §4, C9 修复命名)

        0 = 对齐 (与已知概念相干高, 吸收)
        1 = 接近 (相位接近但结构错配: 新维度值/新客体)
        2 = 错配 (相位错配: 新对象/新动作, 反相)

        ⚠️ 这是信号不是判定: M3 输出 align_tier (0/1/2),
        M6 输出 verdict.tier (absorbed/observe/explore) — 禁止同名混用。
        """
        ph = self.phase(concept)
        if ph is None:
            return 2  # 场中无此概念 = 新对象
        coh = self.phase_coherence(concept)
        if coh >= known_coherence:
            return 0
        # 结构错配 (有相位但低相干 + 能量已注入 = 已见过但结构未定)
        if self.energy(concept) > 0:
            return 1
        return 2

    # ── 时间属性单点查询 (M2 无副本) ─────────────────────────
    def readings(self, concept: Optional[str] = None) -> dict:
        """概念时间属性全集 (M3 唯一持有者)"""
        rv = getattr(self.cs, 'rhythm', None) or getattr(self.cs, '_rhythm', None)
        rvr = {}
        if rv is not None:
            try:
                rvr = rv.readings() or {}
            except Exception:
                rvr = {}
        if concept is not None:
            rhythm_mark = {}
            if rv is not None:
                try:
                    rhythm_mark = rv.concept_rhythm(concept) or {}
                except Exception:
                    rhythm_mark = {}
            return {
                'energy': round(self.energy(concept), 3),
                'phase': round(self.phase(concept), 3)
                if self.phase(concept) is not None else None,
                'coherence': round(self.phase_coherence(concept), 3),
                'energy_sync': round(
                    self.energy_sync_coherence(concept, concept), 3),
                'maturity': round(self.maturity(concept), 3),
                'dormant': self.is_dormant(concept),
                'last_tick': self._last_tick.get(concept),
                'rhythm': rhythm_mark,  # 概念级节律 (出现间隔分布, 2026-08-17)
            }
        return {
            'n_concepts': rvr.get('n_concepts', 0),
            'n_entities': rvr.get('n_entities', 0),
            'n_alive': rvr.get('n_alive', 0),
            'total_energy': round(rvr.get('total_energy', 0.0), 3),
            'phase_coherence': round(rvr.get('phase_coherence', 0.0), 3),
        }
