# -*- coding: utf-8 -*-
"""MES vNext 节律层适配器 — 概念空间的时间维度 (战略矫正第六刀)

架构: 概念空间 = 结构侧 (对象身份/状态/动作/事件, 五刀已完成);
vNext 节律层 = 时间侧 (能量/相位/生灭/混沌边缘, 时间维度不可约)。

对接:
  - register(concept): 概念 → vNext 实体 (复用初始网格实体, 严格映射)
  - observe_event(p, a, o): 事件 → 三概念能量注入 + 共现边增强
  - step(): vNext 动力学演化 (V4 原语 + 混沌边缘自调参)
  - readings(): 节律读数 → 主链判定 (时间维度)

第六刀范围: 严格映射 (概念注册=实体, 关分裂); 分裂→新概念
(概念从节律动力学诞生) = 第七刀候选。

第十一刀验证结论 (2026-08-12): 分裂→新概念 不可行作为"概念
诞生"机制 — 分裂偏向高频枢纽 (产生复制品), 复制品能量无分层
(无法识别哪个新), 低频新对象不分裂 (酒/茶仍靠词面注册)。
概念诞生正确路径 = 观察注册 + 拓扑分化 (第七/八刀已验证)。
_lineage/emergent_concepts 保留为分裂谱系事实记录。

vNext 代码: core/mes_vnext.py (2026-08-19 归位真源, 原 _audit/mes_vnext_v3.py;
定稿归档见 archive/06-范式升级/MES-vNext定稿/)
"""
import numpy as np
from operator import itemgetter
from typing import Optional, Dict, List, Tuple

try:
    from core.mes_vnext import MESvNext, MESvNextConfig  # type: ignore
    _HAS_VNEXT = True
except Exception:  # pragma: no cover - 依赖缺失降级
    MESvNext = None  # type: ignore
    MESvNextConfig = None  # type: ignore
    _HAS_VNEXT = False


class RhythmVNext:
    """vNext 节律层: 概念 ↔ 实体桥 (概念空间的时间维度载体)"""

    def __init__(self, seed: int = 42, env_rate: float = 0.0,
                 env_mode: str = "per_entity", decay_rate: float = 0.995,
                 birth_cost: float = 0.3, birth_cost_alpha: float = 0.4,
                 substep=None, death_threshold: float = 0.0,
                 dormant_after: int = 0):
        # MES 第二波阶段 1 (2026-08-18): 亚步动力学引擎挂接点。
        # 默认 None = 零破坏 (step() 不执行任何亚步逻辑); 传入
        # SubstepDynamics 且 enabled=True 时, step() 内 mes.step()
        # 之后做连续相位演化 (事件步之间不再空白)。
        self.substep = substep
        if not _HAS_VNEXT:
            raise RuntimeError("MES vNext 依赖缺失 (core/mes_vnext.py)")
        cfg = MESvNextConfig(seed=seed, env_rate=env_rate, env_mode=env_mode)
        # 严格映射模式 (第六刀): 概念注册 = 实体, 关分裂
        cfg.birth_mult = 1e9    # 能量分裂阈值拉高 → 永不自发分裂
        # ② 实体生命周期 (2026-08-23): 冷概念休眠阈值参数化。
        # 默认 0.0 = 永不休眠 (现状逐位不变); >0 时能量低于阈值
        # 的实体休眠 (断边+alive=False, 本体保留), 再次 observe
        # 自动复活 (register 恢复 alive)。休眠 = 用进废退的"退"
        # 端: 长时间未观察的概念退出相位动力学, 不参与传播。
        cfg.death_threshold = death_threshold  # 概念寿命由概念空间管
        # ② 实体生命周期 (2026-08-23): 用进废退的"退"端 — 未观察
        # 步数阈值休眠。
        #   dormant_after=0 (默认): 永不休眠 (现状逐位不变)。
        #   dormant_after=N>0: 概念连续 N 步未被观察 → 休眠
        #     (alive=False: 退出相位相干统计 + 停止 env 能量注入,
        #     本体/相位/边保留); 再次 observe 自动复活 (register
        #     恢复 alive + 能量基线)。
        # 判据用 recency (活跃度) 不用能量 — MES 开放系统能量被
        # 量子涨落+env注入+V4扩散推平, 绝对能量阈值不可触发
        # (2026-08-23 实测: 冷概念能量 ~120 vs 活跃 ~130)。
        self.dormant_after = dormant_after
        # T4 开放系统 (2026-08-14): 引擎不自发出生 (概念出生 =
        # 观察注册, 不是引擎分裂 — 第十一刀结论; pool 模式的
        # 资源驱动出生若不禁用, 会消耗资源池生成无概念映射的
        # 背景实体, 池被耗尽 → 概念注册反而无资源可用)
        cfg.max_births_per_step = 0
        # T4 开放系统 (2026-08-14): 出生成本随规模 (Heaps 配方,
        # vNext 定稿 BEST: birth_cost=0.3, alpha=0.4 → β=0.568)
        cfg.birth_cost = birth_cost
        cfg.birth_cost_alpha = birth_cost_alpha
        self.mes = MESvNext(cfg)
        self.decay_rate = decay_rate  # 记忆代谢: 每步能量 × decay (时间流逝即遗忘)
        # ② 实体生命周期诊断 (2026-08-23): 休眠/复活计数 (报告行用)
        self.dorm_count: int = 0
        self.revive_count: int = 0
        self._last_alive = None  # 上步 alive 快照 (休眠计数差分)
        self.concept_idx: dict = {}   # 概念名 → 实体索引
        self.idx_concept: dict = {}   # 实体索引 → 概念名
        self._reserved = int(self.mes.energy.shape[0])  # 初始网格实体数
        self._cooccur: dict = {}   # 共现计数 (未饱和证据, 类别涌现信号源)
        self._subject_bind: dict = {}  # 主体绑定 (subj,obj)→次数, 个体化信号
        self._lineage: dict = {}   # 分裂谱系: 子实体idx → 父实体idx (概念从动力学诞生)
        self._last_n: int = None   # 上一步实体数 (分裂检测)
        self._recency: dict = {}   # 记忆: 实体idx → 最后观察步 (用进废退遗忘)
        self._recency_event: dict = {}  # 实体idx → 最后观察事件 (cooldown_scan 用)
        # 概念级节律显式化 (2026-08-17, 方向1): 出现间隔 → 显式节律标记
        # 前置研究 (rhythm_phase_assoc): 节律频率存在但隐式 (能量序列),
        # 无概念级显式结构 — 本字段把“扣球每 10 步出现一次”变成可读属性。
        # 默认空结构零破坏; 滚动窗口固定 32, 记录纯增量不改既有输出。
        self._appear_last: dict = {}   # 概念idx → 上次出现事件号
        self._appear_ivals: dict = {}  # 概念idx → 最近出现间隔列表 (滚动)
        self._appear_max: int = 32     # 滚动窗口 (稳态周期需 ≥2 样本)
        self._step_count: int = 0  # 内部步计数 (代谢 recency 用, step() 推进)
        self._event_count: int = 0  # 事件时钟 (observe_event 推进, cooldown_scan 用)
    def register(self, concept: str) -> int:
        """概念注册: 新概念 → vNext 实体 (复用初始网格实体)

        休眠概念复活 (2026-08-23, ②实体生命周期): 概念再次被
        观察 = 活跃证据 → 若实体已休眠 (alive=False), 恢复 alive
        + 重置能量 (回到基线 1.0)。无休眠时逐位不变 (alive 恒
        True, 本分支零执行)。
        """
        if concept in self.concept_idx:
            idx = self.concept_idx[concept]
            # 休眠复活: 被再次观察 → 恢复活跃 (能量重置基线 +
            # recency 重置 → 退出休眠窗口)
            if idx < self.mes.energy.shape[0] and not self.mes.alive[idx]:
                self.mes.alive[idx] = True
                self.mes.energy[idx] = max(self.mes.energy[idx], 1.0)
                self._recency[idx] = self._step_count
                self.revive_count += 1
            return idx
        idx = len(self.concept_idx)  # 注册序 = 实体号
        if idx >= self._reserved:
            # 超过初始网格 → 追加实体
            idx = int(self.mes.energy.shape[0])
            self.mes.energy = np.append(self.mes.energy, 1.0)
            self.mes.phase = np.append(self.mes.phase,
                                       self.mes.rng.uniform(0, 2 * np.pi))
            self.mes.threshold = np.append(self.mes.threshold, 5.0)
            self.mes.fatigue = np.append(self.mes.fatigue, 0.0)
            self.mes.alive = np.append(self.mes.alive, True)
            self.mes.generation = np.append(self.mes.generation, 0)
            self.mes.noise_state = np.append(self.mes.noise_state, 0.0)
            j = int(self.mes.rng.integers(0, idx))
            self.mes.edge_i = np.append(self.mes.edge_i, min(idx, j))
            self.mes.edge_j = np.append(self.mes.edge_j, max(idx, j))
            self.mes.edge_weight = np.append(self.mes.edge_weight, 0.5)
        else:
            self.mes.energy[idx] = 1.0
            self.mes.alive[idx] = True
        self.concept_idx[concept] = idx
        self.idx_concept[idx] = concept
        # T4 开放系统 (2026-08-14): 出生成本随规模 (仅新注册扣费)
        # 概念出生 = 观察注册 (词面/结构信号, 非引擎分裂 — 第十一刀
        # 结论), 消耗资源池 (Heaps: N ∝ t^(1/(1+α)), 认知资源有限)。
        # 资源不足不阻断注册 (感知不阻断), 新概念低能量待成长。
        # 默认 per_entity 模式零破坏 (池=0, 不扣费不降能量)。
        if self.mes.cfg.env_mode == "pool":
            n = len(self.concept_idx)
            cost = self.mes.cfg.birth_cost * (n ** self.mes.cfg.birth_cost_alpha)
            if self.mes.resource_pool >= cost:
                self.mes.resource_pool -= cost
                self.mes.energy[idx] = max(self.mes.energy[idx], cost * 0.5)
            else:
                self.mes.energy[idx] = 0.2  # 资源不足: 待成长 (低能量)
        return idx

    def observe_event(self, p: str, a: str, o: str = None,
                      drive: float = 0.0, channel: str = "env",
                      energy_scale: float = 1.0) -> None:
        """事件 → 能量注入 + 共现边增强 + 共现计数 (观察 = 概念活跃证据)

        energy_scale (通道同步→能量增益, 2026-08-20): 活跃证据注入
        乘数 — 默认 1.0 逐位不变 (零破坏); 感知事件由调用方传
        sync_energy_scale() (同步→感知事件概念能量更高 = 感知忠实
        反映世界时感知信息实时更活跃)。只调 0.5 活跃证据部分, drive
        新颖通道不动。

        channel (观察事件通道分离, 2026-08-17 机制级升级): 区分
        环境事件 ("env", 默认) 与观察事件 ("obs")。
          - env: 环境自发发生的事件 (对象在环境中出现/状态变化),
            更新概念级节律 _appear_ivals — 节律 = 环境事件间隔。
          - obs: 系统自身观察/行为事件 (行为者每步执行动作),
            能量/共现/recency 全部保留 (零行为变更), 但**不更新
            _appear_ivals** — 观察不是环境出现, 若进会污染环境
            节律 (interval 被拉到 1 → 调度基准失真 → 正反馈失控,
            attention_schedule 第一版 C 退化 12 步实证; 装配层
            实锤: '我' 每步被观察 → interval≈1 → cv 尺度失真)。
        默认 "env" 零破坏: 旧调用全走 env, 逐位不变。

        drive (端到端耦合通道, 2026-08-16): 事件→动力层注入强度。
        默认 0.0 = 逐位不变 (零破坏)。drive>0 时, 事件三概念在 +0.5
        活跃证据之上额外获得 drive 能量 — 事件显著性调制: 由调用方
        (感知层/元认知) 决定信号强度, 让事件流能驱动 MES 混沌产生
        节律结构 (端到端缺口落地: 生产注入 +0.5 不足以驱动混沌,
        验证见 knowledge/end_to_end_coupling_landing.md)。

        共现计数 (第七刀): 不经 V4 演化的未饱和证据, 类别涌现的
        信号源。V4 扩散会把边权全部拉平 (饱和), 不能当类别信号。

        时间推进 (2026-08-16 接线, 4ee1d2d + 修正): 每事件
        _event_count += 1 — 事件时钟 (cooldown_scan 不活跃判定用)。
        修正 (本次): 4ee1d2d 误用 _step_count 双推进 — 原 commit
        声称 step() 生产零调用, 但 interfaces/lifeform.py 每回合调
        rhythm.step() (回合时钟) → 双时钟破坏 step() 内 recency
        代谢判定 (R23 回归 24/27 实证)。修: 回合时钟 (_step_count,
        step() 推进) 与事件时钟 (_event_count, observe_event 推进)
        分离, 各归其位 — step() 代谢用回合, cooldown_scan 用事件。
        """
        idxs = [self.register(x) for x in (p, a, o) if x]
        self._event_count += 1  # 事件时钟 (cooldown_scan 时间线)
        trio = [x for x in (p, a, o) if x]
        for i in range(len(trio)):
            for j in range(i + 1, len(trio)):
                key = tuple(sorted([trio[i], trio[j]]))
                self._cooccur[key] = self._cooccur.get(key, 0) + 1
        # 主体绑定 (第八刀): p 作用 o — 谁在什么时间点作用于它
        if o is not None and p is not None and a is not None:
            bind = (p, o)
            self._subject_bind[bind] = self._subject_bind.get(bind, 0) + 1
        for i in idxs:
            self.mes.energy[i] = min(self.mes.energy[i] + 0.5 * energy_scale, 200.0)
            self._recency[i] = self._step_count  # 用进: 观察 = 最近激活 (回合时钟)
            self._recency_event[i] = self._event_count  # 事件时钟 (cooldown_scan 用)
            # 概念级节律 (2026-08-17): 出现间隔 = 本次观察步 - 上次观察步
            # (步时钟 _step_count, 与 step() 代谢/FFT 研究同时间线 — “扣球
            # 每 10 步出现一次”的语义)。滚动窗口, 纯增量。
            # 2026-08-17 修正: gap==0 (同一步内重复 observe 同一概念) 不
            # 记录 — 步内多次观察 = 一次出现 (观察通道多次写入合并), 否则
            # interval 被 0 拉低 → std 巨大 → cv 恒爆 (实景生活体每步多次
            # observe, 阈值 0.25 永触发, 异常通道失效)。跨步出现才计间隔。
            # 2026-08-17 通道分离: channel=="obs" 时跳过节律更新 —
            # 观察事件不反映环境出现 (行为者每步执行动作 ≠ 环境事件),
            # 若计入 → _appear_ivals 被观察节奏污染 (interval→1) →
            # 调度/监控基准失真 (装配层实锤: 焦点被 '我' 霸占)。
            if channel == "env":
                last = self._appear_last.get(i)
                if last is not None:
                    gap = self._step_count - last
                    if gap > 0:  # 步内重复观察不记录 (同一步 = 一次出现)
                        lst = self._appear_ivals.setdefault(i, [])
                        lst.append(gap)
                        if len(lst) > self._appear_max:
                            lst.pop(0)  # 滚动: 只保留最近 32 个间隔 (稳态节奏)
                self._appear_last[i] = self._step_count
        # 端到端注入通道 (2026-08-16): drive>0 时事件显著性调制 —
        # 额外注入 drive 能量 (clip 200 保护), 驱动混沌产生节律结构。
        # 默认 drive=0.0 走上面 +0.5 活跃证据路径, 逐位不变。
        if drive > 0.0:
            for i in idxs:
                self.mes.energy[i] = min(self.mes.energy[i] + drive, 200.0)
        # 共现边增强 (事件结构 → 拓扑耦合)
        for i in range(len(idxs)):
            for j in range(i + 1, len(idxs)):
                mask = ((self.mes.edge_i == min(idxs[i], idxs[j])) &
                        (self.mes.edge_j == max(idxs[i], idxs[j])))
                if mask.any():
                    self.mes.edge_weight[mask] += 0.5
                else:
                    self.mes.edge_i = np.append(
                        self.mes.edge_i, min(idxs[i], idxs[j]))
                    self.mes.edge_j = np.append(
                        self.mes.edge_j, max(idxs[i], idxs[j]))
                    self.mes.edge_weight = np.append(
                        self.mes.edge_weight, 0.5)

    def step(self) -> dict:
        self._step_count += 1  # 回合时钟 (step() 唯一推进, 原版语义)
        r = self.mes.step()
        # ② 实体生命周期诊断 (2026-08-23): 休眠计数 — 本步新休眠 =
        # 上步 alive 但本步 !alive。仅死亡阈值 >0 时有意义, 零开销。
        if self.mes.energy.shape[0] and hasattr(self.mes, 'alive'):
            _a = self.mes.alive
            if self._last_alive is not None and _a.shape == self._last_alive.shape:
                self.dorm_count += int((self._last_alive & ~_a).sum())
            self._last_alive = _a.copy()
        # MES 第二波阶段 1 (2026-08-18): 亚步连续相位演化 — 事件步
        # 之后 (原语已演化) 再按 Kuramoto + 固有频率平滑推进 S 亚步。
        # 默认 substep=None → 本块零执行, 逐位不变。
        if self.substep is not None and self.substep.enabled:
            self.substep.sync_omega_from_rhythm()  # 节律 interval → ω
            self.substep.advance()
        # 记忆代谢 (2026-08-12): 时间流逝即遗忘 — 用进废退
        # 最近被 observe 的概念 (recency 记录) 不衰减; 久未出现的
        # 概念能量 × decay (遗忘=不用就忘, 与 M4 冷概念冷却同哲学)。
        # 只作用于已注册概念 (概念场的遗忘才是记忆的遗忘)。
        if self.decay_rate < 1.0 and self.concept_idx:
            idxs = np.array(list(self.concept_idx.values()), dtype=int)
            idxs = idxs[idxs < self.mes.energy.shape[0]]
            if len(idxs):
                # recency: 最近活跃 (上一步观察过) 的概念跳过代谢
                rec = np.array([self._recency.get(i, -1) for i in idxs])
                fresh = rec >= self._step_count - 1
                idxs = idxs[~fresh]
                if len(idxs):
                    self.mes.energy[idxs] *= self.decay_rate
        # ② 实体生命周期 (2026-08-23): 未观察步数阈值 → 休眠。
        # 用进废退的"退": 概念久未被观察 = 淡出动力学 (alive=False,
        # 退出 coh/env; 相位/边保留可复活)。判据 = _recency 距当前
        # 回合步数; 新注册未观察概念 recency=-1 → 同样进入休眠窗。
        if self.dormant_after > 0 and self.concept_idx:
            _idxs = np.array(list(self.concept_idx.values()), dtype=int)
            _idxs = _idxs[_idxs < self.mes.energy.shape[0]]
            if len(_idxs):
                _rec = np.array([self._recency.get(i, -1) for i in _idxs])
                _stale = (self._step_count - _rec) > self.dormant_after
                _idxs = _idxs[_stale]
                if len(_idxs):
                    _a = self.mes.alive
                    _new = _idxs[~_a[_idxs]]  # 已休眠的跳过
                    _fresh = _idxs[_a[_idxs]]  # 活跃 → 本次休眠
                    if len(_fresh):
                        self.mes.alive[_fresh] = False
                        self.dorm_count += int(len(_fresh))
                    if len(_new):
                        # 已休眠概念保持休眠 (除非 revive 重置 recency)
                        pass
        # 第十一刀 (2026-08-12): 分裂谱系 — 检测新实体并记录父代
        if self._last_n is not None and self.mes.energy.shape[0] > self._last_n:
            for idx in range(self._last_n, int(self.mes.energy.shape[0])):
                if idx not in self._lineage:
                    # 子实体与反相最远的活跃实体配对 = 父 (分裂机制: 子相位 = 父+π)
                    best_p, best_d = -1, 1e9
                    for pi in range(idx):
                        d = abs(self.mes.phase[idx] - self.mes.phase[pi])
                        d = min(d, 2 * np.pi - d)
                        if d > np.pi / 2 and d < best_d:
                            best_d = d
                            best_p = pi
                    self._lineage[idx] = best_p if best_p >= 0 else None
        self._last_n = int(self.mes.energy.shape[0])
        return r

    # ── 第十一刀 (2026-08-12): 概念从动力学诞生 — 分裂实体识别 ──
    def emergent_concepts(self, min_energy: float = 2.0) -> list:
        """新概念前身: 未注册但活跃的分裂实体

        分裂 (能量超阈值自发分化) 产生新实体, 它们不是从词面
        注册的 (concept_idx 里没有), 而是从动力学诞生的。

        概念空间读到这些实体 → 给它们命名 (注册为新概念) = 概念
        从动力学诞生, 非词面、非设计。min_energy 过滤昙花一现
        的弱分裂体 — 持续观察的实体能量高, 才有资格成为概念。

        返回: [实体idx, ...] (按能量降序, 已注册概念除外)
        """
        out = []
        for idx in self._lineage:
            if idx in self.idx_concept:
                continue  # 已注册 = 词面给的身份
            if idx >= self.mes.energy.shape[0]:
                continue
            if not self.mes.alive[idx]:
                continue
            e = self.mes.energy[idx]
            if e >= min_energy:
                out.append((int(idx), float(e)))
        out.sort(key=lambda x: -x[1])
        return out

    # ── 第八刀+ (2026-08-12): 个体化 — 归属从分布涌现 ──
    def ownership_profile(self) -> dict:
        """归属谱: 每个对象的作用占比分布 + 排他性 (连续量)

        从事件方向性 (谁在什么时间点作用于什么) 涌现, 非词面、
        非阈值。机制层零硬编码: 分布本身 = 认知结构。

        排他性 = 1 - 归一化熵 (H_max = log n):
          - 单峰 1.0     → 熵 0      → 排他性 1.0 (独占)
          - 双峰 50/50   → 熵最大    → 排他性 0.0 (共享)
          - 均匀铺开     → 熵最大    → 排他性 0.0 (公共)
          - 90/10       → 熵中等    → 排他性 0.53 (强归属+借用)

        返回: {对象: {"shares": {主体: 占比}, "exclusivity": float}}
        """
        obj_total: dict = {}
        for (s, o), v in self._subject_bind.items():
            obj_total[o] = obj_total.get(o, 0) + v
        profile: dict = {}
        for (s, o), v in self._subject_bind.items():
            t = obj_total.get(o, 0)
            if t == 0:
                continue
            prof = profile.setdefault(o, {"shares": {}, "exclusivity": 0.0})
            prof["shares"][s] = v / t
        import math
        for o, prof in profile.items():
            shares = list(prof["shares"].values())
            n = len(shares)
            if n <= 1:
                prof["exclusivity"] = 1.0
                continue
            h = -sum(p * math.log(p) for p in shares if p > 0)
            h_max = math.log(n)
            prof["exclusivity"] = 1.0 - (h / h_max if h_max > 0 else 0.0)
        return profile

    def ownership(self, semantics: bool = False):
        """个体化读出 (向后兼容 + 语义命名层)

        semantics=False: 返回原始归属谱 (ownership_profile)。
        semantics=True: 由分布形状涌现语义 — 独占/共享/公共/强归属。
          命名层 (非机制): 排他性连续谱上的自然断点, 供仲裁消费。
        """
        prof = self.ownership_profile()
        if not semantics:
            return prof
        out = {}
        for o, p in prof.items():
            e = p["exclusivity"]
            if e >= 0.9:
                sem = "独占"
            elif e >= 0.45:
                sem = "强归属"
            elif len(p["shares"]) >= 3:
                sem = "公共"
            else:
                sem = "共享"
            dom = max(p["shares"], key=p["shares"].get)
            out[o] = {"语义": sem, "主导": dom, "排他性": round(e, 3),
                      "分布": {k: round(v, 3) for k, v in p["shares"].items()}}
        return out

    # ── 记忆化 (2026-08-12): MES = 记忆本体 — 工作记忆 + 长期记忆 ──
    # 记忆 = 动力学状态: 写入=能量累积, 遗忘=代谢衰减, 巩固=能量稳定,
    # 新记忆=实体诞生。MemoryHub 四层 (TemporalBuffer/HistoryBuffer/
    # ConceptMemory/LongTermMemory) 由此可整体退役 — 一个动力学同时是
    # 认知/节律/记忆, 无第二个存储本体。
    def save_state(self, path: str) -> None:
        """长期记忆持久化: MES 动力学状态 + 概念映射 → npz

        序列化全部动态状态 (能量/相位/边/共现/绑定), 跨会话恢复
        = 长期记忆。不序列化引擎内部 RNG/参数 (恢复时按 seed 重建,
        动力学演化路径不要求逐位重现 — 记忆要的是状态不是轨迹)。
        """
        m = self.mes
        arrays = {
            "energy": m.energy,
            "phase": m.phase,
            "threshold": m.threshold,
            "fatigue": m.fatigue,
            "alive": m.alive,
            "generation": m.generation,
            "noise_state": m.noise_state,
            "edge_i": m.edge_i,
            "edge_j": m.edge_j,
            "edge_weight": m.edge_weight,
        }
        np.savez(path, **arrays)
        # 映射 + 共现 + 绑定 → json (字符串数据)
        import json
        meta = {
            "concept_idx": self.concept_idx,
            "idx_concept": {str(k): v for k, v in self.idx_concept.items()},
            "cooccur": {f"{a}|{b}": v for (a, b), v in self._cooccur.items()},
            "subject_bind": {f"{a}|{b}": v for (a, b), v in self._subject_bind.items()},
            "recency": {str(k): v for k, v in self._recency.items()},
            "step_count": self._step_count,
            "decay_rate": self.decay_rate,
            # 概念级节律 (2026-08-17 持久化接线补全): 跨会话恢复
            # 环境事件间隔滚动窗口 — 缺则恢复后节律空白,
            # 调度/监控基准丢失 (通道分离后的环境节律是唯一基准)
            "appear_ivals": {str(k): list(v)
                             for k, v in self._appear_ivals.items()},
            "appear_last": {str(k): v
                            for k, v in self._appear_last.items()},
        }
        with open(path + ".meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)

    def load_state(self, path: str) -> None:
        """长期记忆恢复: npz + meta.json → 动力学状态 + 映射

        恢复到当前实例 (与 register 的初始网格对齐: 前 _reserved
        个实体是初始网格, 恢复时按注册序重建映射)。
        """
        import json
        m = self.mes
        d = np.load(path + ".npz")  # np.savez 自动加 .npz 后缀
        # 恢复动态数组 (按当前初始网格大小对齐)
        n0 = m.energy.shape[0]
        for key in ("energy", "phase", "threshold", "fatigue", "alive",
                    "generation", "noise_state"):
            arr = d[key]
            if arr.shape[0] >= n0:
                setattr(m, key, arr.astype(
                    np.bool_ if key == "alive" else np.float64))
            else:
                cur = getattr(m, key)
                setattr(m, key, np.concatenate([cur[:arr.shape[0]], arr]))
        # 边数组可能更长 (追加实体) → 直接替换
        m.edge_i = d["edge_i"]
        m.edge_j = d["edge_j"]
        m.edge_weight = d["edge_weight"]
        d.close()
        with open(path + ".meta.json", "r", encoding="utf-8") as f:
            meta = json.load(f)
        self.concept_idx = {str(k): int(v) for k, v in meta["concept_idx"].items()}
        self.idx_concept = {int(k): str(v) for k, v in meta["idx_concept"].items()}
        self._cooccur = {tuple(k.split("|")): v for k, v in meta["cooccur"].items()}
        self._subject_bind = {tuple(k.split("|")): v for k, v in meta["subject_bind"].items()}
        self._recency = {int(k): int(v) for k, v in meta.get("recency", {}).items()}
        self._step_count = int(meta.get("step_count", 0))
        self.decay_rate = float(meta.get("decay_rate", 0.995))
        # 概念级节律恢复 (2026-08-17 持久化接线补全): 旧存档无此
        # 字段 → 默认空, 零破坏 (节律从恢复后重新积累)
        self._appear_ivals = {int(k): list(v) for k, v in
                              meta.get("appear_ivals", {}).items()}
        self._appear_last = {int(k): int(v) for k, v in
                             meta.get("appear_last", {}).items()}
        self._reserved = max(self._reserved, n0)

    # ── 第七刀    # ── 第七刀 (2026-08-12): 类别从拓扑涌现 — 角色等价分组 ──

    # ── T4 开放系统 (2026-08-14): 睡眠调度信号 + 加工成本 ──
    # (归档 2026-08-16: sleep_signal → _archive_legacy/dead_interfaces_20260816.py)

    # (归档 2026-08-16: spend → _archive_legacy/dead_interfaces_20260816.py)

    def concept_rhythm(self, concept: str = None,
                       min_samples: int = 2) -> dict:
        """概念级节律显式化 (2026-08-17, 方向1): 出现间隔 → 显式节律标记

        前置研究 (rhythm_phase_assoc 诚实负结果): 节律频率存在但隐式
        (能量序列 FFT 可测), 无概念级显式结构 — 本接口把“扣球每
        10 步出现一次”变成可读属性。

        节律 = 出现间隔分布 (事件时钟):
          - interval: 平均出现间隔 (步/事件) — 概念的出现节奏
          - interval_std: 间隔波动 — 稳定性 (节奏规律性)
          - frequency: 1/interval — 每步出现率 (快/慢)
          - n_samples: 窗口样本数 (证据量, 过滤未成熟节律)

        消费端: 元认知/注意力/决策可读概念级时间结构 (时间维度
        进概念空间本体)。默认 None/空 = 零破坏 (旧路径不读)。
        """
        if concept is not None:
            i = self.concept_idx.get(concept)
            if i is None:
                return {}
            lst = self._appear_ivals.get(i, [])
            if len(lst) < min_samples:
                return {}
            arr = np.array(lst, dtype=float)
            return {
                'interval': float(arr.mean()),
                'interval_std': float(arr.std()),
                'frequency': float(1.0 / arr.mean()),
                'n_samples': int(len(lst)),
            }
        out = {}
        for c, i in self.concept_idx.items():
            lst = self._appear_ivals.get(i, [])
            if len(lst) < min_samples:
                continue
            arr = np.array(lst, dtype=float)
            out[c] = {
                'interval': float(arr.mean()),
                'interval_std': float(arr.std()),
                'frequency': float(1.0 / arr.mean()),
                'n_samples': int(len(lst)),
            }
        return out

    def concept_rhythm_anomalies(self, min_samples: int = 8,
                                 cv_thr: float = 0.4) -> list:
        """概念级节奏突变检测 (2026-08-20, 消费端接线 — 08-17 假说落地)

        时间维度异常信号: 概念出现节奏在变 (interval 波动增大) =
        环境动力学变化的早期信号。判据 = 变异系数 CV = std/mean
        (E1 实证: 稳态完全规律 CV≈0, 突变期 10→25 CV≈0.5;
        E2 消失: n_samples 冻结; E3 隔离: 只报突变概念自身)。
        返回 [{'concept','interval','interval_std','cv'}] 按 cv 降序。
        零写只读; 无异常 → []。
        """
        out = []
        for c, i in self.concept_idx.items():
            lst = self._appear_ivals.get(i, [])
            if len(lst) < min_samples:
                continue
            arr = np.array(lst, dtype=float)
            mean = float(arr.mean())
            if mean <= 0:
                continue
            cv = float(arr.std()) / mean
            if cv >= cv_thr:
                out.append({'concept': c, 'interval': mean,
                            'interval_std': float(arr.std()), 'cv': cv})
        out.sort(key=lambda d: -d['cv'])
        return out

    # ── P4 相位差结构消费 (2026-08-23, 问题全排列 P4): ──
    # 概念相位差 = 语义关系 (同步=同簇相近 / 反相=对立)。语义簇已
    # 自涌现 (生产回归基线 37 概念两簇 ~180°), 但只有 coh 聚合量被消费,
    # 相位差向量 (谁和谁对立/同步) 零读取。本接口 = 纯只读读数:
    # 相位差矩阵 + 语义簇分桶 + 对立对检测, 供消费端 (元认知/
    # 表达/行为) 使用。零写, 不改变任何动力学路径 (生产回归基线逐位)。
    def phase_structure(self, n_bins: int = 8, anti_thr: float = 2.5,
                        need_pairs: bool = True) -> dict:
        """概念相位结构读数 (P4, 2026-08-23):

        概念对相位差 dφ ∈ [0, π] — 语义关系的动力学表示:
          - dφ ≈ 0   → 同步 (同簇, 语义相近)
          - dφ ≈ π   → 反相 (对立语义)
          - 中间     → 正交 (弱关联)

        返回:
          - clusters: {bin: [概念...]} 相位分桶 = 语义簇 (簇内 dφ 小)
          - pairs: 概念对相位差表 {f"{a}|{b}": dφ} (只含已注册概念)
          - opposite_pairs: 对立对 [(a, b, dφ)] 按 dφ 降序 (dφ ≥ anti_thr)
          - n_clusters: 非空簇数
          - coherence: 与 readings() 同口径的聚合 coh (校验用)

        2026-08-26 提速 (need_pairs=False): 行为环/元认知热路径每步
        多次调用只消费 opposite_pairs (不读 pairs 表) → 跳过 pairs
        dict 全构建 (k² Python 迭代)。verify/教学用默认 True 不变。
        零写只读; 无概念实体 → 空结构。
        """
        out = {"clusters": {}, "pairs": {}, "opposite_pairs": [],
               "n_clusters": 0, "coherence": 0.0}
        if not self.concept_idx:
            return out
        idxs = np.array([i for i in self.concept_idx.values()
                         if i < self.mes.phase.shape[0]
                         and self.mes.alive[i]], dtype=int)
        if len(idxs) == 0:
            return out
        names = [c for c, i in self.concept_idx.items()
                 if i < self.mes.phase.shape[0] and self.mes.alive[i]]
        ph = self.mes.phase[idxs]
        out["coherence"] = float(abs(np.mean(np.exp(1j * ph))))
        # 相位分桶 → 语义簇 (桶 = 相位相近的概念组)
        n_bins = max(2, int(n_bins))
        bins = np.floor(ph / (2 * np.pi) * n_bins).astype(int) % n_bins
        for b in range(n_bins):
            members = [names[k] for k in np.where(bins == b)[0]]
            if members:
                out["clusters"][int(b)] = members
        out["n_clusters"] = len(out["clusters"])
        # 概念对相位差 (只算已注册概念对, O(k²), k=概念数)
        # 2026-08-26 提速 (cProfile: phase_structure = fusion 第二热点
        # 2.2s): Python 双层循环 → numpy 矩阵 (同公式同序逐位, 上三角
        # row-major 键序与双重循环一致)。
        k = len(idxs)
        if k >= 2:
            ph = np.asarray(ph, dtype=float)
            dph = np.abs((ph[:, None] - ph[None, :] + np.pi)
                         % (2 * np.pi) - np.pi)
            iu = np.triu_indices(k, 1)
            if need_pairs:
                for t in range(len(iu[0])):
                    i, j = int(iu[0][t]), int(iu[1][t])
                    out["pairs"][f"{names[i]}|{names[j]}"] = float(dph[i, j])
                # 对立对 (dφ ≥ anti_thr rad, 默认 ~143°)
                opp = [(a, b, d) for kp, d in out["pairs"].items()
                       for a, b in [kp.split("|")] if d >= anti_thr]
                opp.sort(key=lambda t: -t[2])
            else:
                # 热路径 (行为环/元认知每步多次): 只提对立对, 跳过
                # pairs dict 全构建 — 消费端只读 opposite_pairs,
                # 键序同 row-major + 同降序排序 → 逐位一致。
                # 稀疏化 (2026-08-31 v13 分层记忆第一刀 — 概念容量
                # 扩大的成本根因): 全 k²/2 概念对遍历 = O(k²) 平方级
                # 主犯 (概念 637 → 20 万对 × 1687 次 = phase_structure
                # 22% 热点, 概念 1610 封顶时 130 万对爆炸). 对立对
                # (dφ ≥ anti_thr=2.5) 只可能出现在相位差接近 π 的
                # 桶间: 8 桶 (每桶 π/4) → 桶距 3/4/5 覆盖 dφ ∈
                # [2.36, 3.93] 全部 ≥ 2.36 区域 (桶距 ≤2 最大 2.36
                # < 2.5 无漏) → 只算候选桶间对 (k²×3/64) + 精确
                # dφ 阈值过滤 → 结果逐位等价 (候选覆盖全部可能
                # 过阈值对, 过滤条件同原). 概念 637 → 20万→~2万
                # 候选 (numpy 矩阵), Python 循环只走 np.where 命中
                # (对立对少) → 10x+ 提速.
                opp = []
                _bins_ph = np.floor(ph / (2 * np.pi) * n_bins).astype(int) % n_bins
                # 2026-08-31 容量扩大第三刀: 桶距 3/4/5 候选对合并为
                # 一次 numpy 计算 — 原实现每桶对一次小矩阵 (8 桶 ×
                # 3 桶距 ≈ 24 次 numpy, 小矩阵 overhead 主导: 519 活跃
                # 实测 14.55ms/次, 700 活跃 29.58ms — O(k²) 平方增长
                # 是年为单位运转的减缓主犯)。meshgrid 生成候选对索引
                # (同桶对序 row-major) + 单次广播计算 + 单次 where →
                # 同公式同浮点序逐位等价。
                _ii, _jj = [], []
                for _b in range(n_bins):
                    _ib = np.where(_bins_ph == _b)[0]
                    if len(_ib) == 0:
                        continue
                    for _db in (3, 4, 5):
                        _b2 = (_b + _db) % n_bins
                        if _b2 <= _b:
                            continue  # 上三角去重 (每对只算一次)
                        _ib2 = np.where(_bins_ph == _b2)[0]
                        if len(_ib2) == 0:
                            continue
                        _g = np.meshgrid(_ib, _ib2)
                        _I_ = _g[0].ravel()
                        _J_ = _g[1].ravel()
                        # FIX 2026-09-01: 强制 i<j 上三角 (旧版语义) —
                        # 原实现生成有向对, 消费端 f"{a}|{b}" 键方向
                        # 翻转 → 行为漂移 (钟摆 19→0 第二刀)
                        _lo = np.minimum(_I_, _J_)
                        _hi = np.maximum(_I_, _J_)
                        _ii.append(_lo); _jj.append(_hi)
                if _ii:
                    _I = np.concatenate(_ii)
                    _J = np.concatenate(_jj)
                    _d = np.abs((ph[_I] - ph[_J] + np.pi)
                                % (2 * np.pi) - np.pi)
                    # 命中处理提速 (2026-08-31 容量扩大第三刀):
                    # 生产相位分散 (trio coh 0.035 — 概念持续新增 →
                    # 同步不收敛) → 对立对 O(k²×20%) 大量 (519 概念
                    # ~2 万对) → Python 循环 append + lambda sort 为
                    # 主成本。列表推导 + itemgetter 快 ~2×。
                    _mt = np.where(_d >= anti_thr)[0]
                    _ii_ = _I[_mt]
                    _jj_ = _J[_mt]
                    _dd = _d[_mt]
                    # 降序: numpy argsort (负值) 替代 Python list.sort
                    # (2 万元素 Python sort 2.9ms → argsort 0.1ms)
                    # FIX 2026-09-01: 不稳定排序 + 桶序 → 同 dφ 顺序
                    # 与旧版 row-major 不同 → lexsort 主键 -dφ 次键
                    # (i, j) 恢复旧版稳定排序语义
                    _order = np.lexsort((_jj_, _ii_, -_dd))
                    opp = [(names[int(_ii_[t])], names[int(_jj_[t])],
                            float(_dd[t])) for t in _order]
        else:
            opp = []
        out["opposite_pairs"] = opp
        return out

    def phase_diff(self, c1: str, c2: str) -> Optional[float]:
        """单对相位差 (语义距离, P4): 无概念 → None。零写只读。"""
        i = self.concept_idx.get(c1)
        j = self.concept_idx.get(c2)
        if i is None or j is None:
            return None
        if i >= self.mes.phase.shape[0] or j >= self.mes.phase.shape[0]:
            return None
        pi, pj = self.mes.phase[i], self.mes.phase[j]
        return float(abs((pi - pj + np.pi) % (2 * np.pi) - np.pi))

    def readings(self) -> dict:
        """节律读数 → 主链判定 (时间维度)

        只统计已注册概念的实体 (概念场): 初始网格背景振荡器
        (未注册实体) 的随机相位会稀释相干度, 概念场才是
        "概念的时间维度"。
        """
        if not self.concept_idx:
            return {
                "n_concepts": 0, "n_entities": int(self.mes.energy.shape[0]),
                "n_alive": 0, "total_energy": 0.0, "energy_std": 0.0,
                "phase_coherence": 0.0,
                "polarity_coupling": float(
                    self.mes._params.get("polarity_coupling", 0.0)),
                "phase_energy_k": float(
                    self.mes._params.get("phase_energy_k", 0.0)),
            }
        idxs = [self.concept_idx[c] for c in self.concept_idx]
        idxs = np.array([i for i in idxs if self.mes.alive[i]], dtype=int)
        if len(idxs) == 0:
            return {
                "n_concepts": len(self.concept_idx),
                "n_entities": int(self.mes.energy.shape[0]),
                "n_alive": 0, "total_energy": 0.0, "energy_std": 0.0,
                "phase_coherence": 0.0,
                "polarity_coupling": float(
                    self.mes._params.get("polarity_coupling", 0.0)),
                "phase_energy_k": float(
                    self.mes._params.get("phase_energy_k", 0.0)),
            }
        e = self.mes.energy[idxs]
        return {
            "n_concepts": len(self.concept_idx),
            "n_entities": int(self.mes.energy.shape[0]),
            "n_alive": int(len(idxs)),
            "total_energy": float(e.sum()),
            "energy_std": float(e.std()),
            "phase_coherence": float(
                abs(np.mean(np.exp(1j * self.mes.phase[idxs])))),
            "polarity_coupling": float(
                self.mes._params.get("polarity_coupling", 0.0)),
            "phase_energy_k": float(
                self.mes._params.get("phase_energy_k", 0.0)),
        }
