#!/usr/bin/env python3
"""
core/concept_phase.py — ConceptSpace phase 子模块 (mixin)

S3 拆分 (2026-08-11 施工, 用户拍板 P2①): ConceptSpace 单文件 3656 行
→ 5 子模块 mixin (ontology/phase/principle/state/space), 保持
`from core.concept_space import ConceptSpace` 重导出兼容。

零机制变更: 方法体一字未改, 仅按 C1 14 区块边界归位。
"""
from collections import defaultdict, Counter
from types import SimpleNamespace as _SN
from typing import List, Dict, Tuple, Optional
import math
import numpy as np

# 概念类型 (自动涌现的类别)
PERSON, ACTION, OBJECT, EMOTION = "人物", "动作", "物体", "情感"

# 相位场阈值 (质询点 7 命名化, 默认值一字不改):
PHASE_INCLUDE_COH = 0.5    # 与已知类相干≥0.5 → 并入 (低档响应)
PHASE_MATURE_MAIN = 0.35   # 主簇相干≥0.35 → 独立稳定 (高档响应)


class ConceptSpacePhaseMixin:
    # ══ 相位真源代理层 (2026-08-19 用户拍板 A: mes.phase 唯一真源) ══
    # 设计 (镜像同步, 蝴蝶效应最小化):
    #   - 有实体 (concept_idx 映射) → 读写真源 mes.phase[idx]
    #   - 同时写 _phases 镜像 → guard/遍历/len/持久化语义与现状逐位一致
    #     (镜像 = 耦合过概念 + 类别概念, 与旧 _phases 同集合)
    #   - 无实体概念 (类别等) → _phases 回退 (唯一真源的降级路径)
    #   - _init_phase 保持 np.random 全局序列 → 概念空间内部行为不变;
    #     唯一行为变化 = chaos_guard 读 mes.phase 从静态随机变学习相位
    #     (这正是拍板 A 的目标语义, 基线重锚 = 统一语义的应有之义)
    def _phase_entity_idx(self, concept: str) -> Optional[int]:
        """概念 → MES 实体索引 (None = 无实体概念) """
        rv = getattr(self, '_rhythm', None)
        if rv is None:
            return None
        cidx = getattr(rv, 'concept_idx', None)
        if cidx is None:
            return None
        idx = cidx.get(concept)
        if idx is None:
            return None
        mes = getattr(rv, 'mes', None)
        if mes is None or idx >= mes.phase.shape[0]:
            return None
        return idx

    def _phase_get(self, concept: str, default=None):
        """读相位: 有实体 → mes.phase (真源); 无实体 → _phases 回退"""
        idx = self._phase_entity_idx(concept)
        if idx is not None:
            return float(self._rhythm.mes.phase[idx])
        return self._phases.get(concept, default)

    def _phase_set(self, concept: str, value: float) -> None:
        """写相位: 有实体 → mes.phase (真源) + _phases 镜像; 无实体 → _phases"""
        v = float(value) % (2 * np.pi)
        idx = self._phase_entity_idx(concept)
        if idx is not None:
            self._rhythm.mes.phase[idx] = v
        self._phases[concept] = v
        # 锚缓存失效 (2026-08-31 步级缓存配套): 相位写入 → 旧锚作废
        self._anchor_cache = None
        self._anchor_cache_key = None
        self._wc_cache = None
        self._wc_cache_key = None

    def _init_phase(self, concept: str):
        """惰性初始化: 新概念随机初相 (np.random 序列保持)

        两条时序都保数值链 (概念相位首次 = np.random.uniform,
        与旧实现逐位一致):
          1. 镜像无值 → np.random 消费 + _phase_set (有实体覆盖
             register/网格初相, 无实体写镜像) — 与旧 _phases 同值。
          2. 镜像已有值但实体后注册 (先 phase_couple_batch 后
             observe 的时序): register 把 mes.phase 设成网格初相
             (mes.rng), 与镜像 np.random 值分叉 → 回填真源 = 镜像值,
             恢复一致性。np.random 零消费 (guard 保持)。
        """
        if concept not in self._phases:
            self._phase_set(concept, float(np.random.uniform(0, 2 * np.pi)))
        else:
            # 镜像已有但实体可能后注册 (先耦合后注册时序):
            # 回填真源, 保证 _phase_get 读 mes.phase 与镜像一致
            idx = self._phase_entity_idx(concept)
            if idx is not None:
                self._rhythm.mes.phase[idx] = self._phases[concept] % (2 * np.pi)

    def _category_phase_sync(self, obj: str) -> None:
        """类别概念相位聚合 (缺口 3, B 层, 2026-08-18): obj 属类别 C
        → C 相位 = 成员相位圆形均值 (同类对象动作同步 → 类别区域相位
        对齐成员 — 类别有真实时间维度活性, 非静态标签)。只写类别概念
        自身相位 (走 _phases 回退路径, 类别未注册 rhythm 实体), 成员
        零改动 (零破坏); 无类别/无成员相位 → 跳过。
        """
        members = getattr(self, '_category_members', None)
        cats = getattr(getattr(self, 'emergence', None), 'categories', None)
        if not members or not cats:
            return
        field = getattr(self, 'field', None)
        pf = field() if field is not None else None
        for name, objs in cats.items():
            if obj in objs and name in members:
                phs = []
                for m in members[name]:
                    ph = pf.phase(m) if pf is not None else self._phase_get(m)
                    if ph is not None:
                        phs.append(ph)
                if phs:
                    z = np.mean(np.exp(1j * np.array(phs)))
                    self._phase_set(name, float(np.angle(z)))

    # ══ ④ 状态复用: 反相=抑制态 (spike_couple_v3 上限④落地) ══

    def _phase_anchor(self) -> float:
        """相位场主簇锚点: 全部相位的圆形均值 (主节奏参考)

        集合 = 镜像 keys (耦合过概念 + 类别概念, 与旧 _phases 同集合
        — 不混入 MES 背景实体), 值 = 真源 (_phase_get)。

        步级缓存 (2026-08-31 9600 超线性优化): monitor/_focus_members/
        global_focus 每步高频调用, 每次全扫 _phases = O(概念数) → 总
        O(n²) (9600 步 41min, cProfile 实证 _phase_anchor 48 万次调用
        114s)。缓存键 = (rhythm._step_count, _n_phase_steps) 双信号:
        _step_count 每步 +1 (MES 演化失效), _n_phase_steps 相位耦合
        步 +1 (耦合写入失效) — 任一变化即重算, 步内多次调用共享
        同锚 → 精确逐位等价 (纯数值缓存, 零行为语义变化)。
        """
        if not self._phases:
            return 0.0
        _rh = getattr(self, '_rhythm', None)
        _rk = getattr(_rh, '_step_count', 0) if _rh is not None else 0
        _pk = getattr(self, '_n_phase_steps', 0)
        _ck = (getattr(self, '_anchor_cache', None),
               getattr(self, '_anchor_cache_key', None))
        if _ck[1] == (_rk, _pk) and _ck[0] is not None:
            return _ck[0]
        vals = [self._phase_get(c) for c in self._phases]
        z = np.mean(np.exp(1j * np.array(vals)))
        _a = float(np.angle(z))
        self._anchor_cache = _a
        self._anchor_cache_key = (_rk, _pk)
        return _a

    def _local_anchor(self, concept: str) -> float:
        """分簇局部锚: 概念参与事件成员组的圆形均值 (边界1 C 方案落地)

        背景: 全局均值锚 (_phase_anchor) 在批量涌现注入后漂移最大
        1.15 rad 持久不恢复, 消费端相干 Δ-0.364 可跨 M6 阈值
        (research_boundary1_anchor_drift + research_boundary1_cluster_anchor)。
        真实 107 世界实测 (3 seed): 事件共现簇锚漂移 0.0000 全免疫 +
        消费端 coh 保持 0.86-0.95 (全局锚掉到 0.36-0.53 会误拦)。

        设计: 概念参与的事件 (p,a,o) 三成员 = 事件共现簇 (谁在同一个
        事件 = 一簇); 簇锚 = 成员相位均值。批量注入的新概念 (随机初相)
        各有专属事件成员 → 不进已学概念的簇 → 锚零受影响。

        注意: 不用 identity_members (对象身份组) — 身份组只在宾语位
        建立, 主语/动作位概念无组 → 簇={自己} → 锚=自身相位 = 平凡解
        假象 (coh 恒 1.0, M6 噪声门失效)。

        无事件证据概念 → 回退全局锚 (零破坏, 与现状一致)。
        """
        if not self._phases:
            return 0.0
        members = set()
        for (p, a, o), _c in getattr(self, 'events', {}).items():
            if concept in (p, a, o):
                members.add(p)
                members.add(a)
                if o:
                    members.add(o)
        phs = [self._phase_get(m) for m in members if m in self._phases]
        if len(phs) >= 2:
            z = np.mean(np.exp(1j * np.array(phs)))
            return float(np.angle(z))
        return self._phase_anchor()


    def set_anti_phase(self, concept: str, for_steps: int = 10):
        """④ 状态复用: 刚学概念置反相 (抑制态), for_steps 步后自动恢复

        反相概念在 gate 模式下天然被拦 (绝对相位差相干≈0 < 1-gate)
        → 避开重复回答刚学内容 (状态复用: 同相/反相=两套正交模式)。

        生命周期: _anti_phase_until 记录过期步; 过期后 restore_phase
        恢复原相位 → 重新参与传播。纯加法, 不改变任何现有行为。

        M4/M6 相位纯净修复 (2026-08-08, verify_m6_phase_reconsolidate):
          原实现直接改 _phases[concept] = anchor+π (反相), 污染相位场:
          - M6 phase_noise_gate 把"反相"误读为"噪声" (误伤 75% 是反相集)
          - 再编码轮与 cooldown 反复翻转相位 → 误伤升到 39%
          修复: 只登记 _anti_phase_until 标志 (传播层 L967/972 跳过 =
          抑制语义真正载体), 不再改相位 → 相位场纯净归 M6/M5 用。
          实测: M4 开时 gate 误伤 25%→7% (3-trial 均值)。
        """
        self._init_phase(concept)
        # 记录原相位 (restore_phase 恢复语义保留)
        self._anti_phase_from[concept] = self._phase_get(concept, 0.0)
        self._anti_phase_until[concept] = self._n_phase_steps + for_steps
        return self


# 2026-08-17 决策: 休眠即正确 — 非独立开关, 机制链上:
    #   _phase_coh_gate 由 propagate 的 gate 参数消费 (gate=0.8 已默认生效,
    #   仅传播链不接而无调用方); 开 = 传播链接生产那天自动活。
    #   restore_phase 由 set_anti_phase 驱动 (对抗场景); 开 = set_anti_phase 启用那天。
    def restore_phase(self, concept: str):
        """④ 状态复用: 反相抑制到期 → 恢复原相位 (生命周期结束)"""
        if concept in self._anti_phase_from:
            self._phase_set(concept, self._anti_phase_from.pop(concept))
        self._anti_phase_until.pop(concept, None)
        return self


    # (归档 2026-08-16: anti_phase_stats → _archive_legacy/dead_interfaces_20260816.py)

    # ══ M4 冷概念冷却 (2026-08-08, MES 深度集成, 默认关=零破坏) ══

    def cooldown_scan(self, energy_threshold: float = 5.0,
                      inactive_steps: int = 100,
                      for_steps: int = 10) -> int:
        """冷概念冷却: 开放世界收敛 (H4 中期抑制落地)

        ⚠️ 归位标注 (2026-08-22 实测更新): 生产已接线 — 08-21 起
        cooldown_observe_enabled=True + run_lifeform sleep_every=200
        (R21d 装配) → sleep() 每 200 步调本方法。2000 步生产生产回归基线
        实测: 10 睡眠周期 → cooldown 触发 7 次, 抑制 7 概念全为已
        结束题对象 (题35/41/42/43/45/56/57), 核心概念零被抑
        (内啡肽豁免实证: 68/74 能量低但仅 7 冷却)。08-16 注释
        "生产零调用"已过时 (当时 cooldown_observe_enabled 默认关)。

        缺失环节 (mes_hysteresis_forgetting_research.md):
          不应期 (秒级) + 遗忘 (小时级) 之间缺"分钟级中期抑制"
          → 长期未激活且能量低的概念 → 抑制态 (anti_phase)
          → 传播衰减 → 给活跃概念腾出资源; 再次激活时恢复

        判定 (双条件, 无人工先验):
          能量低: burst_energy < energy_threshold
          不活跃: 最近 inactive_steps 步无观察事件
        （能量由 accumulate_burst/observe 自然累积 — 观测事实）

        补全 (2026-08-16, 用户拍板): 原实现只有能量条件 — 注释
        声称双条件但代码未实现"不活跃"检查 (半成品修复)。补全后
        语义: 能量低 **且** 最近 inactive_steps 步未观察 → 冷却;
        活跃概念 (vNext _recency = 实体idx→最后观察步, 用进即
        活跃) 即使能量低也豁免 — 不冷却"刚见过"的概念。
        默认调用方不触发 = 逐位不变 (能量池默认空); 无 vNext
        层/概念未注册 → 跳过不活跃检查 (退化单条件, 零破坏)。

        纯加法: 默认调用方不触发 = 逐位不变; 触发仅置反相,
        不删概念/不删边 — 抑制可恢复, 不是死亡 (中期抑制语义)
        """
        n = 0
        _rh = getattr(self, '_rhythm', None)
        # 2026-08-16 回归修正: 时间基准用回合时钟 (_step_count) —
        # 08-16 半成品修复改用事件时钟 (_event_count) 后, 无新事件时
        # 事件时钟停滞 → 活跃豁免永不解除 → 时间流逝不再冷却 (M4 原始
        # 语义"时间流逝即代谢"破坏, verify_o2_o3_fix D6 实证)。
        # 配对: recency 用回合时钟 (_recency), now 用 _step_count。
        now = getattr(_rh, '_step_count', 0)
        recency = getattr(_rh, '_recency', None) or getattr(_rh, '_recency_event', None)
        cidx = getattr(_rh, 'concept_idx', None)
        for c in list(self._burst_energy.keys()):
            if self._burst_energy.get(c, 0.0) < energy_threshold:
                if c in self._anti_phase_until:
                    continue  # 已在抑制期, 不重复置
                # 不活跃条件: 最近 inactive_steps 步无观察事件
                if recency is not None and cidx is not None \
                        and c in cidx:
                    last = recency.get(cidx[c], -1)
                    if now - last < inactive_steps:
                        continue  # 最近还活跃 → 不冷却
                # 内啡肽盖章 (endocrine_drive_layer.md): 高满足概念豁免冷却
                # = 价值标尺 — 搞懂了(成熟/重对齐/巩固)的留下, 没搞懂的遗忘
                if (self.endorphin_reward_enabled
                        and self._satisfaction.get(c, 0.0)
                        >= self.satisfaction_threshold):
                    continue
                self.set_anti_phase(c, for_steps=for_steps)
                n += 1
        return n

    # ══ A1 概念死亡 (冻结, 2026-08-19, 默认关 concept_death_enabled=False) ══
    # 立项: knowledge/a1_concept_lifecycle_proposal.md (方案②保守冻结)
    # 分层语义: 冷却 (cooldown_scan, 分钟级, 反相可恢复) < 死亡 (小时/天级,
    # types 冻结可重激活)。同读数 (recency+能量) 两档尺度, 同一价值标尺
    # (内啡肽豁免: 搞懂的永不判死)。

    def death_scan(self, energy_threshold: float = 5.0,
                   death_horizon_steps: int = 2000,
                   theory_calibrated: bool = False,
                   theta: float = 0.05,
                   half_life_steps: int = 425,
                   lambda_scale: Optional[float] = None) -> int:
        """概念死亡扫描: 长期零观察 + 低能量 → 冻结 (types 移除, 本体保留)

        方案② (用户拍板): 保守冻结 — 死亡 = 查询面不可见 (types 移除),
        本体全保留 (边/相位/历史/统计), 再观察即重激活 (生灭闭环)。
        符号层无 V2 码本容量压力 → 不强制槽位复用, 新概念走自然涌现。

        判定 (双条件, 无人工先验, 与 cooldown_scan 同读数):
          1. 长期零观察: 最近 death_horizon_steps 步无观察 (回合时钟
             _recency; 无 recency 记录的概念跳过 — 类别概念等未进
             rhythm 实体的不误杀)
          2. 低能量: burst_energy < energy_threshold (同一能量池)
        豁免: 内啡肽满足 (搞懂的) 永不判死 (价值标尺, 同 cooldown)

        理论校准 (2026-08-25, E 完整版): theory_calibrated=True 时
        零观察容忍度 = T_life = ln(θ)/ln(d), d = 0.5^(1/half_life)
        (Miller 锚定: 半衰期 425 步 ≈ 5011 事件 ≈ 3.5 天)。
        巅峰性发现: 工程魔数 2000 步 → 隐含 θ = d^2000 ≈ 0.038,
        与理论 θ=0.05 的 T_life=1835 步 (21657 事件) 同点 —
        工程直觉被理论公式解释, 理论被 Miller 实证独立验证。

        动作 (冻结): types.pop(concept) (查询面不可见) + _frozen[concept]
        = 冻结步 (审计/元认知可读); 不删边/相位/历史/统计 (重激活即恢复)。
        默认调用方不触发 (sleep 挂点跟随 concept_death_enabled) = 逐位不变。

        λ 内容层调制 (2026-08-25, 理论 8 兑现): lambda_scale 非 None 且
        theory_calibrated → T_life_eff = T_life × clamp(λ/λ_ref, 0.25, 4)。
        K* = λ·ln2/β (理论 8): λ 高 (知识扩展期) → 容量高 → 概念活更久
        (淘汰宽容, 多学); λ 低 (饱和) → 早淘汰过气概念 (聚焦巩固)。
        基准 λ_ref = 会话内滑动平均 (自适应, 无设计者常数)。默认 None
        → 零破坏 (逐位等价)。
        """
        n = 0
        if theory_calibrated:
            # T_life = ln(θ)/ln(d), d = 0.5^(1/half_life)
            # = half_life × ln(θ)/ln(0.5)
            _hl = max(1, half_life_steps)
            death_horizon_steps = int(_hl * math.log(theta) / math.log(0.5))
            if lambda_scale is not None:
                # λ 内容层: T_life ∝ λ (K* = λ·ln2/β), 上下限防极端
                _s = max(0.25, min(4.0, lambda_scale))
                death_horizon_steps = max(1, int(death_horizon_steps * _s))
        _rh = getattr(self, '_rhythm', None)
        now = getattr(_rh, '_step_count', 0)
        recency = getattr(_rh, '_recency', None)
        cidx = getattr(_rh, 'concept_idx', None)
        for c in list(self.types.keys()):
            if c in self._frozen:
                continue  # 已冻结
            # 条件1: 长期零观察 (缺失 recency → 从未活跃, 跳过不误杀)
            if recency is None or cidx is None or c not in cidx:
                continue
            last = recency.get(cidx[c], -1)
            if last < 0 or now - last < death_horizon_steps:
                continue  # 还活跃
            # 条件2: 低能量
            if self._burst_energy.get(c, 0.0) >= energy_threshold:
                continue
            # 豁免: 内啡肽满足 (搞懂的留下, 同 cooldown 价值标尺)
            if (self.endorphin_reward_enabled
                    and self._satisfaction.get(c, 0.0)
                    >= self.satisfaction_threshold):
                continue
            saved_types = set(self.types.get(c, set()))
            self.types.pop(c, None)  # 冻结: 查询面不可见
            # 类型快照: 重激活时完整恢复 (不依赖观察涌现条件 — 人物位
            # 类型涌现需 emergent_subjects 预标集, 冻结后 key 没了会
            # 丢人物类型; 快照恢复保证生灭闭环零信息损失)
            self._frozen[c] = (now, frozenset(saved_types))
            n += 1
        return n

    def _temp_signal(self, mature_window: Optional[int] = None,
                     mode: Optional[str] = None) -> float:
        """T* 温度读数 (2026-08-25, 纯只读): 1 − 平均活性 — 稳态温度
        定律 T* = 1−h* (h* = 平均存活率) 的生产实现。淘汰进行时
        非恒零 (0,1); 无活性场 (完整版未开) → 0。

        mode (2026-08-26, T* 第三层 — 6G 缓存替换反哺, 修自激):
          'dead_frac' (默认): 1 − 平均活性 (旧语义, verify 兼容)。
            自激缺陷: 调节器 (新概念降权) 的足迹直接进读数 →
            读数与调节器强度正相关 → 正反馈 (MEMORY 已记录待修)。
          'redundancy': R̄ 平均概念冗余度 (与擦除编码淘汰共享计算)。
            观测-控制完全解耦: 调节器动活性场 (1−k·R̄ 写初始活性),
            边结构不受影响 → 读数无调节器足迹 → 无自激。高 R̄ =
            概念库同质化 (重复相似关联) → 新概念脆弱 → 抑制同质堆积
            → R̄ 降 = 负反馈闭环。
          'growth_rate': dN/dt 归一化 (窗口内新概念数 / 参照库 10%)。
            过热 (概念堆积快) → 新概念脆弱 → 少堆积 → 负反馈。
            mature_window=None → 默认 100 (速率需窗口)。
            参照库 = max(当前库, 窗口) (2026-08-26 修复: 原分母=当前库
            ×10% 在冷启动期库<窗口时恒饱和 1.0 — 任何注入速率判过热 →
            调节器恒最大压制 + 零区分度, 稀疏对照实证 (acd6628 负结果)。
            max(库, 窗口) 语义: 库<100 视为冷启动积累期 (基础概念建立,
            不该判过热), 参照=窗口规模; 库≥窗口 → 原语义 (10% 热阈值)。
            修复后冷启动 signal ≤ 0.5 (初始活性 ≥ 0.75), 堆积激增仍触发
            1.0)。

        mature_window=N: 只算出生 ≥ N 步的成熟概念 (v2, 自参考环
        修复)。无 birth 记录 (旧存档) → fallback 全量 (零破坏)。"""
        _mode = mode or getattr(self, 'temp_signal_mode', 'dead_frac')
        if _mode == 'redundancy':
            try:
                st = self.concept_redundancy_stats()
                return max(0.0, min(1.0, st['mean']))
            except Exception:
                return 0.0
        if _mode == 'growth_rate':
            _b = getattr(self, '_concept_birth', None)
            if not _b:
                return 0.0
            _rh = getattr(self, '_rhythm', None)
            _now = (getattr(_rh, '_step_count', 0)
                    if _rh is not None else 0)
            _win = mature_window or 100
            _born = sum(1 for t in _b.values()
                        if _now - _win < t <= _now)
            # 净堆积率纯化 (2026-08-27, #3 growth_rate 信号纯化):
            # 原信号 = 窗口内出生数 — 自激污染: 调节器压制新概念
            # (初始活性低) → 更早跌破 θ 冻结 → 重生仍计"出生" →
            # dN/dt 保持高 → 信号高 → 调节器继续压制 = 正反馈
            # (与 dead_frac 同病, MEMORY 已记录)。
            # 纯化 = 净堆积 = 出生 − 窗口内冻结: 调节器压制的概念
            # 死亡 → 净留存降 → 信号降 → 负反馈闭环成立。
            # 过热语义 = 概念堆积 (写入 > 淘汰), 非写入本身。
            _fz = getattr(self, '_frozen', None) or {}
            _died = sum(1 for _ft in _fz.values()
                        if isinstance(_ft, tuple) and _ft
                        and _now - _win < _ft[0] <= _now)
            _born = max(0, _born - _died)
            _total = max(1, len(self.types))
            # 参照库 = max(当前库, 窗口): 冷启动保底 (见 docstring)
            _ref = max(_total, _win)
            return max(0.0, min(1.0,
                                _born / max(1.0, _ref * 0.1)))
        _ls = getattr(self, '_life_strength', None)
        if not _ls:
            return 0.0
        _b = getattr(self, '_concept_birth', None)
        if mature_window and _b:
            _rh = getattr(self, '_rhythm', None)
            _now = (getattr(_rh, '_step_count', 0)
                    if _rh is not None else 0)
            _v = [v for c, v in _ls.items()
                  if _now - _b.get(c, 0) >= mature_window]
        else:
            _v = list(_ls.values())
        if not _v:
            return 0.0
        return max(0.0, min(1.0, 1.0 - sum(_v) / len(_v)))

    def _decay_life(self) -> int:
        """概念淘汰完整版: 连续活性场指数衰减 → 阈值淘汰 (强度衰减语义)

        理论: K*-T* 对偶的连续版本 — 概念活性 act(t) = d^(t−last),
        d = 0.5^(1/half_life) (Miller 锚定: 半衰期 425 步 ≈ 5011 事件
        ≈ 3.5 天)。act < θ (默认 0.05, E 校准理论点) → 冻结
        (types.pop + _frozen, 本体保留可重激活 — 同 death_scan 语义)。
        θ_eff = θ / clamp(λ/λ_ref, 0.25, 4) (λ 内容层调制: λ 高 → θ 小
        → 活更久; λ 低 → θ 大 → 早淘汰)。

        默认 concept_life_full=False → 调用方不调 (零操作零破坏);
        本方法被调但开关关 → 直接返回 0 (防御)。
        """
        if not getattr(self, 'concept_life_full', True):
            return 0
        import math as _m
        # 主动复习调度 (2026-08-29, 实验59 反哺): 周期扫描濒危概念 →
        # 冻结前自动复习 (零信息损失保障层)。rehearse_enabled 默认关 →
        # 零操作零影响 (生产回归基线等未装配世界逐位保持); 装配世界每
        # rehearse_every 步扫一次 (预算限流防每步全表)。
        if getattr(self, 'rehearse_enabled', False):
            _rrh = getattr(self, '_rhythm', None)
            _rstep = (getattr(_rrh, '_step_count', 0)
                      if _rrh is not None else 0)
            if _rstep % max(1, getattr(self, 'rehearse_every', 200)) == 0:
                try:
                    self.rehearse_scan()
                except Exception:
                    pass  # 复习失败零破坏 (防御)
        _hl = max(1, getattr(self, 'life_half_life', 425))
        d = 0.5 ** (1.0 / _hl)  # 单步衰减率
        theta = getattr(self, 'life_theta', 0.05)
        # λ 内容层调制 (① 落地复用): θ_eff = θ / λ_scale
        # ⚠️ 2026-08-28 实验27 定论 (勿加外部 s 旋钮): 此消费点已是
        # 双重自适应分域之一 — λ1 机制域 (θ↑→λ1↓→探索率降, 差分
        # −0.246 时滞≈0) + 饥饿补偿域 (知识缺口独立驱动, 两机制方向
        # 相反时自然抵消)。外部"查表+慢环+死区"三合一设计不落地:
        # 在 λ1 域多余 (已自动跟随), 在饥饿域有害 (干扰知识补偿)。
        # 详见 info_theory_lab/knowledge/experiment_27_emergent_adaptation.md
        _dl = getattr(self, 'death_lambda', None)
        _dlr = getattr(self, 'death_lambda_ref', None)
        if _dl is not None and _dlr not in (None, 0.0):
            _s = max(0.25, min(4.0, _dl / _dlr))
            theta = theta / _s
        n = 0
        _exempt = getattr(self, 'info_revive_exempt', 2)
        # 擦除编码淘汰 (2026-08-26): 开关默认关零影响; 候选收集 + 冗余
        # 排序 + 独有豁免 (③ 第三标准)。_pending 收集后统一冻结。
        erase_code = bool(getattr(self, 'erase_code_evict', False))
        _red_exempt = float(getattr(self, 'redundancy_exempt', 0.15))
        # 批量邻居索引 (2026-08-31 分层记忆第二刀 — 概念容量扩大
        # 平方级主犯): 原每濒危概念 _concept_redundancy(c) 内部
        # 对全概念×全边 O(n·m) 遍历 (概念 1081 × 边 9798 实测
        # 16% 热点) → 本分支预构建邻居索引一次 O(m), 查询 O(1)
        # (同一邻居集逐位等价 — 结果不变只提速)。非 erase_code
        # 分支零构建零影响。
        _nb = None
        if erase_code:
            from collections import defaultdict as _dd
            _nb = _dd(set)
            for (a, _r, b), _w in self.edges.items():
                if _w > 0:
                    _nb[a].add(b)
                    _nb[b].add(a)
        _pending: list = []
        for c in list(self.types.keys()):
            if c in self._frozen:
                continue
            act = self._life_strength.get(c, 1.0)
            if act >= theta:
                continue
            # ② θ 双标准 (2026-08-26, 概念=信息): 活性 < θ 但轮回史
            # ≥ info_revive_exempt → 豁免冻结 (低活性驻留)。信息价值
            # 代理 = 重激活历史: 反复需要 = 可复用规律/工具 (石头/
            # 开采), 与过时实例 (题N) 区分。生产默认 2 (用户拍板默认开)。
            if (_exempt > 0
                    and self._revive_count.get(c, 0) >= _exempt):
                continue
            # ③ 擦除编码第三标准 (2026-08-26, 6G 信道编码反哺): 概念
            # = 信息, 淘汰 = 擦除信道 — 应优先擦除信息冗余度高的
            # (有替身概念承载相同关联 → 删除损失最小, 喷泉码冗余
            # 分布思想)。R(c) < redundancy_exempt = 信息独有 (无替身,
            # 删了无法重建) → 豁免冻结 (与②轮回史豁免互补: ②=行为
            # 价值代理, ③=信息独有价值)。默认 erase_code_evict=False
            # → 跳过 (零影响, 生产回归基线/直构逐位保持)。
            if erase_code:
                try:
                    _r = self._concept_redundancy(c, _nb)
                except Exception:
                    _r = 1.0  # 防御: 计算失败 → 不豁免 (正常淘汰)
                if _r < _red_exempt:
                    self._unique_evict_exempt += 1
                    continue
                _pending.append((c, _r))
            else:
                _pending.append((c, 1.0))
        # 擦除编码删除排序 (2026-08-26): 候选按冗余度降序优先冻结
        # (高冗余 = 有替身 = 损失最小先删; 保留独有/低冗余)。
        # 开关关 → 原序 (等同旧行为逐位)。
        _pending.sort(key=lambda kv: kv[1], reverse=True)
        # 压缩逃生舱 (2026-08-29, 实验54 组件 C): 冻结前先尝试抽象上移
        # — 实例统计并入类别 (脏标记重扫 + 类别活力吸收 + 上移标记),
        # 冻结降级为「压缩态」(统计已在类别规则里, 未来 use_abstract
        # 装配时类别规则含实例贡献 = 样本效率 7.6x 兑现前提)。
        # 消费端关 (use_abstract=False) → 纯沉淀零行为; 生产回归基线无冻结
        # → 本块零执行逐位不变。
        _abs_up = getattr(self, 'abstract_up', None)
        for c, _r in _pending:
            if _abs_up is not None:
                try:
                    _abs_up(c)
                except Exception:
                    pass  # 防御: 上移失败不阻塞冻结
            # 阈值跌破 → 冻结 (本体保留, 可重激活)
            saved = self.types.get(c)
            self.types.pop(c, None)
            _rh = getattr(self, '_rhythm', None)
            _now = getattr(_rh, '_step_count', 0) if _rh is not None else 0
            # 2026-08-26 死亡 = 相位退场 (超线性增长主因修复):
            # 冻结概念从相位实体索引/镜像退出 → 相位查询面有界
            # (phase_structure/_phase_get/分时传播自动跳过), 同时
            # 记录旧 idx 供重激活恢复 (同一概念轮回保留旧相位,
            # 零 rng 消费)。生产回归基线无冻结 → 本块零执行逐位不变。
            _fidx = None
            if _rh is not None:
                _cidx = getattr(_rh, 'concept_idx', None)
                _iidx = getattr(_rh, 'idx_concept', None)
                if _cidx is not None and c in _cidx:
                    _fidx = _cidx.pop(c, None)
                    if _fidx is not None and _iidx is not None:
                        _iidx.pop(_fidx, None)
                    _mes = getattr(_rh, 'mes', None)
                    if (_mes is not None and _fidx is not None
                            and _fidx < _mes.alive.shape[0]):
                        _mes.alive[_fidx] = False
                if c in self._phases:
                    self._phases.pop(c)
            self._frozen[c] = (_now,
                               frozenset(saved) if saved else frozenset(),
                               _fidx)
            self._life_total += 1
            n += 1
        # 活概念活性衰减 (types 面) — 冻结概念 = 死亡 = 代谢停止:
        # 不再消耗每步衰减成本 (O(全概念) → O(活概念), 有界面),
        # 活性冻结在死亡瞬间 (保留在 _life_strength 供 T* 读数,
        # 重激活时 observe 回满 1.0)。Landauer 预算彻底化:
        # 只有活概念付代谢成本。
        # 有限复习模型 (2026-08-27, 默认关零影响): 每概念独立衰减率
        # d_eff = d^(1−min(m·k, 0.95)) — 巩固强度 m 高 → 衰减慢
        # (Bjork: 检索难→巩固强→记忆持久)。默认关 → d_eff = d 逐位。
        _fr = bool(getattr(self, 'finite_review', False))
        _frk = float(getattr(self, 'fr_decay_k', 1.0))
        for c in list(self.types.keys()):
            if _fr:
                _m = min(self._review_strength.get(c, 0.0) * _frk, 0.95)
                _d_eff = d ** (1.0 - _m) if _m > 0 else d
                self._life_strength[c] = (
                    self._life_strength.get(c, 1.0) * _d_eff)
            else:
                self._life_strength[c] = self._life_strength.get(c, 1.0) * d
        return n

    def _maybe_revive(self, concept: str) -> bool:
        """重激活: 冻结概念再次被观察 → 解除冻结 (生灭闭环)

        types 注册 = 冻结时保存的类型快照直接恢复 (人物/动作/对象
        全类型零信息损失), 不依赖观察时的类型涌现条件。本体 (边/相位/
        历史/统计) 从未删除, 恢复即完整可用。默认关 (调用方在
        concept_death_enabled 下才调) 零破坏。
        """
        if concept in self._frozen:
            # ② 轮回史计数 (信息价值豁免数据源): 每次重激活 = 概念
            # 被系统再次需要 = 可复用性证据。冻结 → 重激活 → 再冻结
            # → 再重激活 的循环次数反映概念跨生命周期价值。
            self._revive_count[concept] = (
                self._revive_count.get(concept, 0) + 1)
            # ★ 重激活 = 一次真实出生事件 (2026-09-13 #7 修复):
            # _concept_birth 用 setdefault, 重生不更新它 ⇒ 只看它会把
            # '出生' 永久低估为 '曾见过的唯一概念数'. 纯仪器计数.
            self._birth_events = getattr(self, '_birth_events', 0) + 1
            _entry = self._frozen.pop(concept)
            # 兼容 2 元旧格式 (存档/旧版)
            if len(_entry) >= 3:
                _, saved, _fidx = _entry
            else:
                _, saved = _entry
                _fidx = None
            # 2026-08-25 完整版修复: 无条件恢复 (空类型快照也建键 —
            # person 无证据概念 types 值可能为空集, 冻结后键丢失则
            # 查询面永久消失, 生灭闭环断链)
            self.types[concept] = set(saved) if saved else set()
            # 2026-08-26 相位恢复 (死亡 = 相位退场的逆): 旧实体
            # 重新注册 (concept_idx/idx_concept/alive=True), 相位
            # 保留旧值 = 同一概念轮回, 零 rng 消费。无旧 idx (旧
            # 格式/无 rhythm) → 跳过, observe 路径自动新注册。
            if _fidx is not None:
                _rh = getattr(self, '_rhythm', None)
                if _rh is not None:
                    _cidx = getattr(_rh, 'concept_idx', None)
                    _iidx = getattr(_rh, 'idx_concept', None)
                    _mes = getattr(_rh, 'mes', None)
                    if _cidx is not None and concept not in _cidx:
                        _cidx[concept] = _fidx
                        if _iidx is not None:
                            _iidx[_fidx] = concept
                        if (_mes is not None
                                and _fidx < _mes.alive.shape[0]):
                            _mes.alive[_fidx] = True
                            _mes.energy[_fidx] = max(
                                _mes.energy[_fidx], 1.0)
            return True
        return False

    # ══ ⑤ 噪声滤波: 低相干拦截 (spike_couple_v3 上限⑤落地) ══

    def phase_noise_gate(self, concept: str,
                         coh_threshold: float = 0.3) -> bool:
        """⑤ 噪声滤波: 概念与相位场主簇相干度 < 阈值 → 噪声

        与感知链路 detect_novelty 互补: 那是输入级 (编码误差),
        这是概念级 (与已有知识主簇的相位相干)。
        低相干概念被 gate 模式天然拦截 (干扰不传播)。

        M4/M6 概念冲突修复 (2026-08-08, verify_m6_phase_reconsolidate):
          实测 gate 误伤 20 个核心概念中 15 个 (75%) 正处于 M4 cooldown
          反相抑制态 — M4 把休息者翻反相, M6 把"反相"误读为"噪声"。
          同一物理状态 (反相), 两个机制解释相反。
          修复: 反相抑制中的概念 = M4 休息者 (非噪声), 豁免 gate;
          语义分工: gate 只拦真噪声 (纯相干), M4 管休息衰减 (少传播)。

        三分解升级 (2026-08-08, 阶段3+5+6 研究落地, 用户批准废除零破坏铁律):
          旧判据 (单相干 < 阈值) 误拦率 59%: 低相干 ≠ 噪声 —
          相位错配 (真实但反相) + 结构错配 (成熟新颖) 都被误拦。
          新判据 (三分解, 触发条件选择性):
            - 有角色位证据 (过程匹配) + 低相干 = 相位错配 (真实反相)
              → 不拦, 自动相位重对齐 (50 步向主簇拉回)
            - 无角色位 + 相位成熟 (相干≥0.2) = 结构错配 (新颖候选)
              → 不拦, 交三档响应 (阶段4: 并入/新锚/新类)
            - 无角色位 + 相位不成熟 (相干<0.2) = 存在错配 (真幻觉)
              → 拦 (M6 拦截保持)
          结果: 误拦率 59% → 0%, 真幻觉漏拦 0 (5-seed 稳健)。
          重对齐本身无选择性 (存在错配也被救回) — 选择性来自触发条件:
          只对有角色位证据 (过程匹配) 的触发, 存在错配不触发。
        """
        if concept not in self._phases or len(self._phases) < 3:
            return False  # 相位场未建立/概念无相位 → 不判噪声
        if self._anti_phase_until.get(concept, 0) > self._n_phase_steps:
            return False  # M4 休息者豁免 (反相=抑制态, 非噪声, 不重对齐)
        anchor = self._local_anchor(concept)
        d = abs((self._phase_get(concept) - anchor + np.pi) % (2 * np.pi) - np.pi)
        coh = max(0.0, 1.0 - d / np.pi)
        if coh >= coh_threshold:
            return False  # 与主簇同步 → 非噪声
        # 低相干: 三分解 (触发条件选择性)
        if self._has_process_slot(concept):
            # 相位错配: 真实但反相 (有角色位证据) → 重对齐救回, 不拦
            self._realign_phase(concept)
            return False
        # 成熟度 = max(主簇相干, 最近已知类相干) (边界2 优化 2026-08-16)
        local_coh = self._known_class_coherence(concept)
        if coh >= 0.2 or local_coh >= 0.2:
            # 结构错配: 相位成熟 (主簇或类内连贯) + 无过程匹配
            # = 新颖候选 → 交三档响应
            return False
        return True  # 存在错配: 相位不成熟 + 无过程匹配 = 真幻觉 → 拦


    def _has_process_slot(self, concept: str) -> bool:
        """过程匹配: 概念是否出现在事件角色位 (主语/动作/宾语)

        角色位证据 = 感知到真实参与过程 → 真实概念 (即使反相)。
        三铁律延伸: 感知不判定 — 角色位是观测 (事件结构), 不是判定。
        """
        for (p, a, o) in self.events:
            if p == concept or a == concept or o == concept:
                return True
        return False


    def _known_class_coherence(self, concept: str) -> float:
        """局部成熟判据 (边界2 优化, 2026-08-16): 与最近已知类的相位相干

        主簇相干 = 与全局注意力中心的一致性; 类分布宽时 (107 世界
        物体类成员相位跨度 4.76 rad), 远离主簇但类内连贯的边缘概念
        会被 `_coh >= 0.2` 漏检 (新颖性看不见)。
        局部判据: 与某已知类 (人物/动作/物体事件成员) 平均相位
        相干高 → 局部成熟 = 该类的边缘候选 (虚拟成员), 非噪声。
        幻觉 (随机相位) 距所有类都远 → 局部相干低 → 仍被 gate 拦。
        """
        if concept not in self._phases:
            return 0.0
        subj = set(); act = set(); obj = set()
        for (p, a, o), _c in self.events.items():
            subj.add(p); act.add(a)
            if o:
                obj.add(o)
        proc = subj | act | obj
        classes = {k: [w for w in proc if k in self.types.get(w, set())]
                   for k in (PERSON, ACTION, OBJECT)}
        best = 0.0
        for members in classes.values():
            phs = [self._phase_get(m) for m in members if m in self._phases]
            if not phs:
                continue
            ds = [abs((self._phase_get(concept) - pm + np.pi)
                      % (2 * np.pi) - np.pi) for pm in phs]
            d = float(np.mean(ds))
            best = max(best, max(0.0, 1.0 - d / np.pi))
        return best


    def _realign_phase(self, concept: str, steps: int = 50,
                       coupling: float = 0.3) -> float:
        """相位重对齐: 把真实但反相的概念拉回主簇 (阶段5 研究落地)

        Kuramoto 耦合: 向主簇 anchor 逐步耦合。
        50 步 = 反相极值 (Δφ≈π, sin≈0, 慢收敛区) 也收敛 (5-seed 全救回)。
        返回对齐后的相干度。
        """
        if concept not in self._phases:
            return 0.0
        anchor = self._local_anchor(concept)
        ph = self._phase_get(concept)
        for _ in range(steps):
            dphi = (anchor - ph + np.pi) % (2 * np.pi) - np.pi
            ph = (ph + coupling * np.sin(dphi)) % (2 * np.pi)
        self._phase_set(concept, ph)
        d = abs((ph - anchor + np.pi) % (2 * np.pi) - np.pi)
        return max(0.0, 1.0 - d / np.pi)


    def novelty_response_scan(self) -> dict:
        """三档新颖响应 (阶段4 研究落地): 结构错配 → 并入/新锚/新类

        结构错配 = 相位成熟 (相干≥0.2) + 无过程匹配 (不在事件角色位)
        = 新颖候选。三档判据 (可容纳性 + 独立稳定性, 不建在语言统计上):
          低档: 与某已知类相位相干 ≥0.5 → 可容纳 → 并入最近类
                (types 加类标签 + 相位向类质心耦合, 成为普通一员)
          中档: 其余 (独立但弱) → 建新锚 + 待观察登记 (元认知可读)
          高档: 与类相干均<0.5 且主簇相干≥0.35 → 独立稳定
                → 建新类 + 注意加权 (不立即写语义网络, 警觉语义)

        返回最近一次扫描结果 (novelty_scan, 供 Metacognition 消费)。
        概念先行原则: 判据建在相位结构 (可容纳/独立稳定) 上,
        不建在词频/角色后验 (暴力灌输) 上。
        """
        if not self.novelty_scan_enabled:
            return self.novelty_scan
        subj = set(); act = set(); obj = set()
        for (p, a, o), _c in self.events.items():
            subj.add(p); act.add(a)
            if o:
                obj.add(o)
        proc = subj | act | obj
        anchor = self._phase_anchor()

        def _coh(w: str) -> float:
            if w not in self._phases:
                return 0.0
            anchor = self._local_anchor(w)
            d = abs((self._phase_get(w) - anchor + np.pi) % (2 * np.pi) - np.pi)
            return max(0.0, 1.0 - d / np.pi)

        # 结构错配集 (阶段 3 同款)
        # 成熟度 = max(主簇相干, 最近已知类相干) (边界2 优化 2026-08-16):
        # 类分布宽时远离主簇但类内连贯的边缘概念不再漏检
        struct = [w for w in self.types
                  if w in self._phases and w not in proc
                  and (_coh(w) >= 0.2
                       or self._known_class_coherence(w) >= 0.2)]
        # 已知类成员 (有过程匹配的概念, 按涌现类型)
        classes = {k: [w for w in proc if k in self.types.get(w, set())]
                   for k in (PERSON, ACTION, OBJECT)}

        def _phase_dist(w: str, members) -> float:
            if w not in self._phases or not members:
                return np.pi
            ds = []
            for m in members:
                if m not in self._phases:
                    continue
                d = abs((self._phase_get(w) - self._phase_get(m) + np.pi)
                        % (2 * np.pi) - np.pi)
                ds.append(d)
            return float(np.mean(ds)) if ds else np.pi

        # 三档判定 (阶段 4 同款)
        tier_low = {}; tier_mid = []; tier_high = []
        for w in struct:
            best_cls, best_d = None, np.pi
            for cls_name, members in classes.items():
                d = _phase_dist(w, members)
                if d < best_d:
                    best_cls, best_d = cls_name, d
            coh_cls = max(0.0, 1.0 - best_d / np.pi)
            main_coh = _coh(w)
            if coh_cls >= PHASE_INCLUDE_COH:
                tier_low[w] = (best_cls, coh_cls)
            elif main_coh >= PHASE_MATURE_MAIN:
                tier_high.append(w)
            else:
                tier_mid.append(w)
        # 低档并入: 系统自贴推测标签 (带置信度) + 相位向类质心耦合
        # 用户裁决 (08-08 21:40): "标签让项目自己贴是最好的, 应该让他自己
        # 纠正, 不能不让系统犯错, 但是犯错会改" — 允许犯错 (推测性贴标),
        # 错误由 label_self_correct 检测并纠正 (事件结构真源优先)。
        # 已有标签保留状态 (跨轮次持续检验, 不被新扫描重置)。
        for w, (cls_name, coh0) in tier_low.items():
            if w not in self._novelty_labels:
                self._novelty_labels[w] = {'class': cls_name,
                                           'coh': round(coh0, 3),
                                           'src': '相位推测',
                                           'status': '待验证'}
                # 系统自己贴标签 (推测性, 允许错) — 真源检验后纠正
                self.types[w].add(cls_name)
            members = classes[cls_name]
            ph_members = [self._phase_get(m) for m in members if m in self._phases]
            if ph_members:
                centroid = float(np.angle(np.mean(np.exp(1j * np.array(ph_members)))))
                ph = self._phase_get(w)
                for _i in range(50):
                    dphi = (centroid - ph + np.pi) % (2 * np.pi) - np.pi
                    ph = (ph + 0.3 * np.sin(dphi)) % (2 * np.pi)
                self._phase_set(w, ph)
        # 中档: 建新锚 + 待观察登记 (候选① 收尾: 证据等待调度)
        # 跨轮次追踪 — 不是一次性快照: 上一轮 pending 的中档概念若仍在
        # 结构错配 (尚未进事件角色位), 保留待观察状态, 证据持续累积;
        # 相位场自然演变决定结局 (等待期间不干预, 无 explore 增益):
        #   - 主簇相干升过 0.35 → 升级高档 (交 explore 注意加权)
        #   - 与已知类对齐 (相干≥0.5) → 并入低档 (自贴标签)
        #   - 进入事件角色位 (不再结构错配) → 事件结构真源接管
        #   - 仍在结构错配 → 继续待观察 (evidence_rounds+1)
        # 上一轮 pending 中本轮已在事件角色位 = 等待自然结束 (证据成熟)
        new_pending = {}
        upgraded = []
        merged = []
        for w in tier_mid:
            new_pending[w] = {'status': '待观察',
                              'main_coh': round(_coh(w), 3),
                              'evidence_rounds': 1}
        for w, info in self._novelty_pending.items():
            if w in tier_mid:
                # 持续结构错配 (本轮仍在中档): 保留待观察 + 轮次累积
                # (原实现 continue 跳过 → rounds 永远重置为 1, 与注释
                #  "证据持续累积" 矛盾; 2026-08-13 人物一致性清理暴露:
                #   真实持续错配的词轮次停在 1, 等待调度失去时间维度)
                new_pending[w] = {'status': '待观察',
                                  'main_coh': round(_coh(w), 3),
                                  'evidence_rounds': info.get('evidence_rounds', 0) + 1}
                continue
            if w in tier_high or w in tier_low:
                continue  # 本轮已重新分档 (三档判定优先)
            if w in proc:
                # 进入事件角色位: 事件结构真源接管, 等待自然结束
                self._pending_resolved.append((w, '事件结构'))
                continue
            if w not in self._phases:
                continue
            # 仍结构错配: 检查相位演变
            c = _coh(w)
            if c >= PHASE_MATURE_MAIN:
                # 主簇相干成熟 → 升级高档 (注意加权)
                self._novelty_attention[w] = 1.0 + (c - 0.2) * 2.0
                upgraded.append(w)
                self._pending_resolved.append((w, '升级高档'))
            else:
                # 检查是否与已知类对齐 (可容纳 → 并入低档)
                best_cls, best_d = None, np.pi
                for cls_name, members in classes.items():
                    d = _phase_dist(w, members)
                    if d < best_d:
                        best_cls, best_d = cls_name, d
                coh_cls = max(0.0, 1.0 - best_d / np.pi)
                if coh_cls >= PHASE_INCLUDE_COH and best_cls:
                    self._novelty_labels[w] = {'class': best_cls,
                                               'coh': round(coh_cls, 3),
                                               'src': '相位推测',
                                               'status': '待验证'}
                    self.types[w].add(best_cls)
                    merged.append(w)
                    self._pending_resolved.append((w, '并入' + best_cls))
                else:
                    # 继续待观察: 保留原状态 + 轮次累积
                    new_pending[w] = {'status': '待观察',
                                      'main_coh': round(c, 3),
                                      'evidence_rounds': info.get('evidence_rounds', 0) + 1}
        self._novelty_pending = new_pending
        # 高档: 注意加权 (增益 = 1 + 主簇相干增量, 不写语义网络)
        self._novelty_attention = {}
        for w in tier_high:
            mc = _coh(w)
            self._novelty_attention[w] = 1.0 + (mc - 0.2) * 2.0
        # 结果登记 (供 Metacognition 消费)
        self.novelty_scan = {
            'struct_mismatch': len(struct),
            'tier_low': {w: {'class': c, 'coh': round(cc, 3)}
                         for w, (c, cc) in tier_low.items()},
            'tier_mid': len(tier_mid),
            'tier_high': len(tier_high),
            'attention': dict(self._novelty_attention),
            'pending': dict(self._novelty_pending),
            'pending_resolved': list(self._pending_resolved),
        }
        return self.novelty_scan


    def label_self_correct(self) -> int:
        """标签自我纠正: 事件结构真源检验推测标签, 错误自动纠正

        用户裁决 (08-08 21:40): "不能不让系统犯错, 但是犯错会改"。
        系统自贴的推测标签 (相位证据) 允许错, 但事件结构 (角色位)
        是唯一真源 — 概念出现在事件中时, 以事件结构类型为准:
          - 真源类型含标签类 → 确认 (status: 已确认)
          - 真源类型不含标签类 → 纠正: 撤回旧标签, 重贴真源
            (真源唯一则重贴; 多义则转待观察, 不武断)
          - 无事件证据 → 保留待验证 (持续检验, 不撤销)

        返回本次纠正数 (纠正史写 _label_corrections, 元认知可读)。
        """
        if not self._novelty_labels:
            return 0
        subj = set(); act = set(); obj = set()
        for (p, a, o), _c in self.events.items():
            subj.add(p); act.add(a)
            if o:
                obj.add(o)
        n_fix = 0
        for w, lab in list(self._novelty_labels.items()):
            if lab['status'] not in ('待验证', '相位推测'):
                continue
            # 事件结构真源类型
            truth = set()
            if w in subj: truth.add(PERSON)
            if w in act: truth.add(ACTION)
            if w in obj: truth.add(OBJECT)
            if not truth:
                continue  # 无证据: 保留待验证
            old = lab['class']
            if old in truth:
                lab['status'] = '已确认'
                lab['src'] = '事件结构'
            elif len(truth) == 1:
                new = truth.pop()
                self.types[w].discard(old)
                self.types[w].add(new)
                lab.update({'class': new, 'src': '事件结构',
                            'status': '已纠正'})
                self._label_corrections.append((w, old, new))
                n_fix += 1
            else:
                # 多义 (多真源): 撤回推测, 转待观察 (不武断)
                self.types[w].discard(old)
                lab.update({'status': '转待观察'})
                self._label_corrections.append((w, old, None))
                n_fix += 1
        self.novelty_scan['label_corrections'] = n_fix
        return n_fix


    def _step_phase_coupling(self, a: str, b: str, times: int = 1,
                             coupling_scale: float = 1.0):
        """MES 极性共振: a 与 b 共激活 → 相位耦合 (sin(Δφ))

        2026-08-07 相位同步学习修复 (遗留③落地):
          sin(2Δφ) → sin(Δφ): 原双固定点 (同相+反相均稳定) 导致
          一半概念落反相, 全局相干≈0 — 相位同步学习失效。
          一阶 Kuramoto 只有同相固定点 (Δφ→0), 反相不稳定退化。
          实证: 真实语料学完 p50 相干 -0.13 → +0.55。

        物理: 两个激活的概念相互拉拢相位 (单固定点: 同相)。
        传导: 多跳链自动同步 (传递性绑定 — 涌现, 非规则)。
        times: 共现次数 → 耦合次数 (共现强度→同步强度, Hebbian)。
        coupling_scale (候选① 延伸, 默认 1.0 零破坏): 执行层消费 —
        元认知 explore 建议 (高档注意增益) 放大耦合力度, 注意资源倾斜。
        """
        for _ in range(max(1, times)):
            self._init_phase(a)
            self._init_phase(b)
            dphi = self._phase_get(b) - self._phase_get(a)
            dphi = (dphi + np.pi) % (2 * np.pi) - np.pi
            c = np.sin(dphi) * self._phase_coupling * coupling_scale
            self._phase_set(a, (self._phase_get(a) + c) % (2 * np.pi))
            self._phase_set(b, (self._phase_get(b) - c) % (2 * np.pi))
        # 阶段D (2026-08-13): 相位足迹新鲜度 — per-concept 最后耦合步
        # (时间维度不可约: 焦点 = 同步∧最近活跃的时空结构; 锚点均值
        #  无法区分两个同步组, 新鲜度给'此刻正在共振'时间语义)
        if not hasattr(self, "_last_active"):
            self._last_active = {}
        self._last_active[a] = self._n_phase_steps
        self._last_active[b] = self._n_phase_steps
        # 局部噪声: 仅对耦合的概念加漂移 (频率高则噪声比例低)
        self._phase_set(a, self._phase_get(a) + float(np.random.normal(0, self._phase_noise)))
        self._phase_set(b, self._phase_get(b) + float(np.random.normal(0, self._phase_noise)))
        # 跨通道锚定 (2026-08-19 用户拍板): 感知概念向世界簇中心弱耦合
        # 每次事件一次 (不随 times 放大, 避免高频过冲); 感知侧被拉,
        # 世界观事侧零改动。平衡: 感知簇中心 → 世界簇中心 (同步)。
        if self._cross_channel_anchor and (self._is_sensor_concept(a)
                                           or self._is_sensor_concept(b)):
            wc = self._world_center()
            if wc is not None:
                for c in (a, b):
                    if self._is_sensor_concept(c):
                        d = (wc - self._phase_get(c) + np.pi) % (2 * np.pi) - np.pi
                        self._phase_set(c, (self._phase_get(c)
                                            + np.sin(d) * self._cross_anchor_scale)
                                        % (2 * np.pi))
        self._n_phase_steps += 1

    # ══ 跨通道同步 (2026-08-19 用户拍板) ══
    # 感知-世界同步: 感知簇中心向世界簇中心漂移 → 相位差可检测。
    # 语义: 0 = 感知与世界同步 (感知通道节奏对齐世界观事),
    # π = 反相 (感知事件流与世界事件流交替错位)。
    # 边界: 感知概念 = 名称含预置片段 (F2 PerceptionAdapter name_prefix
    # + act_known), 环境预置命名约定; 无感知概念 → None (通道不存在)。
    _SENSOR_FRAGMENTS = ('感知对象', '读到', '看到', '感到', '触发', '感知',
                         'continuous')

    def _is_sensor_concept(self, concept: str) -> bool:
        if concept is None:
            return False  # 脏概念防御 (连续世界 obj 涌现间隙)
        return any(f in concept for f in self._SENSOR_FRAGMENTS)

    def sync_energy_scale(self) -> float:
        """通道同步 → 感知能量增益 (快通道, 处理层): 与 sync_learning_scale
        同源 (channel_sync) 不同参数 — 同步时感知事件活跃证据注入增强,
        感知信息实时更活跃 (传播/注意/冷却受影响); 失同步零增强。
        无感知概念 (数学世界) 或开关关 → 1.0 零影响。
        """
        if not getattr(self, '_sync_energy_enabled', True):
            return 1.0
        s = self.channel_sync()
        if s is None:
            return 1.0
        gain = getattr(self, '_sync_energy_gain', 0.5)
        return 1.0 + gain * (1.0 - s / np.pi)

    def _world_center(self) -> Optional[float]:
        """世界簇中心: 非感知概念相位圆形均值 (None = 无世界概念)

        步级缓存 (2026-08-31 超线性优化): _step_phase_coupling 每次
        事件调一次, 每次全扫 _phases = O(概念数); 同 _phase_anchor
        缓存键 = (rhythm._step_count, _n_phase_steps) 双信号, 步内
        多次调用共享同值 → 精确逐位等价 (纯数值缓存)。
        """
        if not self._phases:
            return None
        _rh = getattr(self, '_rhythm', None)
        _rk = getattr(_rh, '_step_count', 0) if _rh is not None else 0
        _pk = getattr(self, '_n_phase_steps', 0)
        _ck = (getattr(self, '_wc_cache', None),
               getattr(self, '_wc_cache_key', None))
        if _ck[1] == (_rk, _pk) and _ck[0] is not None:
            return _ck[0]
        vals = [self._phase_get(c) for c in self._phases
                if not self._is_sensor_concept(c)]
        if not vals:
            self._wc_cache = None
            self._wc_cache_key = (_rk, _pk)
            return None
        _w = float(np.angle(np.mean(np.exp(1j * np.array(vals)))))
        self._wc_cache = _w
        self._wc_cache_key = (_rk, _pk)
        return _w

    def channel_sync(self) -> Optional[float]:
        """感知-世界同步度: 两簇中心相位差 [0, π], 0 = 完全同步
        跨通道耦合后为动力学量 (非初相残留); 无感知概念 → None"""
        wc = self._world_center()
        if wc is None:
            return None
        svals = [self._phase_get(c) for c in self._phases
                 if self._is_sensor_concept(c)]
        if not svals:
            return None
        sc = float(np.angle(np.mean(np.exp(1j * np.array(svals)))))
        return float(abs((sc - wc + np.pi) % (2 * np.pi) - np.pi))

    def sync_learning_scale(self) -> float:
        """通道同步 → 感知事件学习增益: sync=0 (完全同步, 感知忠实反映
        世界) → 1+gain; sync=π (反相, 感知与世界错位) → 1.0 零增强。
        无感知概念 (数学世界) 或开关关 → 1.0 零影响。

        消费端: observe 感知事件 (person=='感知') 的 strengthen delta。
        只调关联学习, 不调相位耦合 — 避免"同步→学习强→相位更贴近→
        更同步"正反馈闭环饱和 (sync 恒 0 失去区分度)。
        """
        if not getattr(self, '_sync_learning_enabled', True):
            return 1.0
        s = self.channel_sync()
        if s is None:
            return 1.0
        gain = getattr(self, '_sync_learning_gain', 0.5)
        return 1.0 + gain * (1.0 - s / np.pi)


    def phase_coherence(self, a: str, b: str) -> float:
        """相位相干度: 0-1, 1=完全锁相 (同相或反相), 0=随机

        同时接受同相同步 (Δφ≈0) 和反相同步 (Δφ≈π)。
        """
        if a not in self._phases or b not in self._phases:
            return 0.0
        dphi = self._phase_get(b) - self._phase_get(a)
        dphi = abs((dphi + np.pi) % (2 * np.pi) - np.pi)
        locked_d = min(dphi, np.pi - dphi)
        return max(0.0, float(1.0 - locked_d / (np.pi / 2)))


# 2026-08-17 决策: 休眠即正确 — 非独立开关, 机制链上:
    #   _phase_coh_gate 由 propagate 的 gate 参数消费 (gate=0.8 已默认生效,
    #   仅传播链不接而无调用方); 开 = 传播链接生产那天自动活。
    #   restore_phase 由 set_anti_phase 驱动 (对抗场景); 开 = set_anti_phase 启用那天。
    def _phase_coh_gate(self, a: str, b: str, weight: Optional[float] = None) -> float:
        """传播门控用相干度: 绝对相位差定义 (CTC 语义)

        与 phase_coherence() 的分工 (spike_couple_v3 教训):
          - phase_coherence = 物理锁定 (同相/反相都算锁相, 双稳定固定点)
          - _phase_coh_gate  = 传播时机 (只有同相才传, 反相=不传)

        2026-08-07 置信度门控 (gate_normal_talk 发现):
          弱共现边 (weight < phase_conf_threshold) 耦合步数不足,
          相位停在随机初相 = 噪声 → 返回 1.0 (放行, 退回频率序);
          强共现边才用相位相干 — 只信任可靠信号, 噪声不参与重排。

        无相位信息 → 返回 1.0 (放行): gate 是可选相干性增益,
        无相位信息就没有增益, 退回默认行为 (纯加法安全)。
        """
        if weight is not None and weight < self.phase_conf_threshold:
            return 1.0  # 弱共现边: 相位不可靠, 不拦截 (保持频率序)
        if a not in self._phases or b not in self._phases:
            return 1.0
        dphi = self._phase_get(b) - self._phase_get(a)
        dphi = abs((dphi + np.pi) % (2 * np.pi) - np.pi)
        return max(0.0, float(1.0 - dphi / np.pi))

    def _phase_coh_routing(self, a: str, b: str,
                           weight: Optional[float] = None,
                           phase_source: Optional[str] = None) -> float:
        """路由用相干度: 相位源可选 (M4 消费端接线, 2026-08-18)

        phase_source=None → _phase_coh_gate (concept_space._phases
        事件步相位, 现状逐位不变); 'substep' → 亚步连续演化相位
        (rhythm.mes.phase, 经 concept_idx 映射, 无相位实体对回退
        1.0 放行)。边界语义与 gate 共享: 弱共现边 (weight <
        phase_conf_threshold) 不调制 (相位不可靠, 只信任可靠信号)。
        """
        if weight is not None and weight < self.phase_conf_threshold:
            return 1.0
        if phase_source != 'substep':
            return self._phase_coh_gate(a, b, weight)
        rhythm = getattr(self, '_rhythm', None)
        if rhythm is None:
            return 1.0
        mes = getattr(rhythm, 'mes', None)
        cidx = getattr(rhythm, 'concept_idx', None)
        if mes is None or cidx is None:
            return 1.0
        i = cidx.get(a)
        j = cidx.get(b)
        if i is None or j is None:
            return 1.0  # 未注册实体: 无连续相位, 放行 (退回静态)
        alive = getattr(mes, 'alive', None)
        if alive is not None and (not alive[i] or not alive[j]):
            return 1.0  # 死实体: 相位冻结, 不参与调制
        if i >= mes.phase.shape[0] or j >= mes.phase.shape[0]:
            return 1.0
        dphi = mes.phase[j] - mes.phase[i]
        dphi = abs((dphi + np.pi) % (2 * np.pi) - np.pi)
        return max(0.0, float(1.0 - dphi / np.pi))


    # @deprecated — 接口预留 (ee9b601 设计): 锁相便捷封装, phase_coherence 直用足够
    # (归档 2026-08-16: is_phase_locked → _archive_legacy/dead_interfaces_20260816.py)


    # (归档 2026-08-16: phase_stats → _archive_legacy/dead_interfaces_20260816.py)

    # ══ 意识阶段D (2026-08-13): 全局焦点 GlobalFocus (GWT 广播内容) ══

    def _focus_members(self) -> tuple:
        """轻量焦点读数 (O(n)): 同步∧新鲜成员, 不算 coherence 矩阵

        供执行层消费端 (ConceptSpace.observe 注意增益) 高频调用;
        global_focus property 复用此结果 + 补 coherence 矩阵
        (低频/展示用)。零写只读。
        """
        if len(self._phases) < 3:
            return None, [], 0, 0
        anchor = self._phase_anchor()
        dists = {c: abs(((self._phase_get(c) - anchor + np.pi) % (2 * np.pi)) - np.pi)
                 for c in self._phases}
        synced = {c: d for c, d in dists.items()
                  if d < np.pi / 4.0 and c != '我'
                  and '动作' not in self.types.get(c, set())}
        if not synced:
            return None, [], 0, 0
        last_active = getattr(self, '_last_active', {})
        now = self._n_phase_steps
        horizon = max(50, int(now * 0.3))  # 最近活跃窗口 (全局步数后 1/3)
        fresh = {c: d for c, d in synced.items()
                 if (now - last_active.get(c, 0)) <= horizon}
        pool = fresh if fresh else synced  # 兜底: 无新鲜成员退回同步簇
        members = sorted(pool, key=lambda c: dists[c])
        focus = min(pool, key=lambda c: (now - last_active.get(c, 0)))
        return focus, members, len(fresh), len(synced) - len(fresh)

    @property
    def global_focus(self) -> dict:
        """当前焦点 = 相位场同步 ∧ 最近活跃的内容概念簇 (时空结构)

        意识 = 信息全局广播 (GWT, Baars/Dehaene): 系统'此刻正在处理
        什么'有全局可读状态。焦点不需要新设计 — 相位场同步区天然
        就是焦点 (谁在共振谁就是'当下'), 完全从相位动力学涌现:
          - 空间: 相位距离 < π/4 (与主簇锚点同步共振)
          - 时间: 新鲜度 (最后耦合步 _last_active) — 锚点是全体
            均值, 无法区分多个同步组; 新鲜度给'此刻正在共振'时间
            语义 (核心命题: 时间维度不可约)
          - 通道词排除: '我' + ACTION 类型 (谓词通道, 频率伪影)
        三铁律: 只读零写 (不改变相位场); 供感知采样偏向 (M6 扩展) /
        记忆检索锚定 / 语言表达主题 / EnvLoop focus 钩子消费。
        """
        focus, members, n_fresh, n_stale = self._focus_members()
        if focus is None:
            anchor = self._phase_anchor()
            return {'focus': None, 'members': [], 'coherence': 0.0,
                    'phase': round(anchor, 4), 'strength': 0.0,
                    'fresh': 0, 'stale': 0}
        anchor = self._phase_anchor()
        names = members[:50]
        cohs = [self.phase_coherence(names[i], names[j])
                for i in range(len(names)) for j in range(i + 1, len(names))]
        coh = float(np.mean(cohs)) if cohs else 0.0
        return {'focus': focus, 'members': members,
                'coherence': round(coh, 4), 'phase': round(anchor, 4),
                'strength': round(len(members) * coh, 4),
                'fresh': n_fresh, 'stale': n_stale}


    def phase_couple_batch(self, concepts: List[str]):
        """批次共现: 在同一上下文中出现的概念互相耦合 (文本窗口)

        用于从语料中提取概念共现模式。
        O(n²) 遍历列表内所有概念对。
        """
        n = len(concepts)
        for i in range(n):
            for j in range(i + 1, n):
                self._step_phase_coupling(concepts[i], concepts[j])

    # ── 推理攻坚: 因果边 (2026-08-09) ──────────────────

    def phase_reconsolidate(self, top_n: Optional[int] = None, rounds: int = 1):
        """M6 相位场成熟机制: 巩固期再编码 → 相位再同步

        research_m6_phase_maturity (2026-08-08, 真实语料):
          随机初相 + 耦合步数不足 (1143 步/412 概念) → 相位未收敛主簇
          → phase_noise_gate 误伤 32% 核心概念 (国见/岩泉一/扣球等)。
          对 top200 共现对补 1 轮耦合: 误伤 50→4 (8%), 主簇 R 0.14→0.20。
          机制洞察: consolidate 只 re-observe count>=3 达标情景
          (低频对不达标 → 相位停在随机初相); 再编码轮覆盖所有主要共现对。

        认知依据: 标准巩固模型 (Squire) 巩固期 (SWS) 海马体重放
        = 对已编码经验的再次编码 → 相位再次同步 (共现结构强化)。

        候选② 落地 (2026-08-08): top_n 默认 None = 全部共现对
        (含低频对, 非只选高频) — 低频相位随机是真实不确定性,
        巩固覆盖全部对 (睡眠重放全部经历, 非设计者只巩固高频);
        learn_from_novel 默认执行 (rounds=5, 取代默认关/研究层人工调用)。
        """
        if not self.events:
            return 0
        pairs: Counter = Counter()
        for (p, a, o), c in self.events.items():
            if p and a:
                pairs[(p, a)] += c
            if a and o:
                pairs[(a, o)] += c
        if top_n is None:
            top_pairs = list(pairs)
        else:
            top_pairs = [pr for pr, _ in pairs.most_common(top_n)]
        n = 0
        for _ in range(max(1, rounds)):
            for (a, b) in top_pairs:
                self._step_phase_coupling(a, b, times=1)
                n += 1
                # 内啡肽输入源 (endocrine_drive_layer.md): 巩固重放覆盖
                # 的概念, 相位成熟 (coh≥0.5=搞懂了) → 满足注资。
                # 重放=经历沉淀, 成熟=理解达成 — 满足感的两大来源。
                if self.endorphin_reward_enabled:
                    for c in (a, b):
                        if self.coherence_of(c) >= PHASE_INCLUDE_COH:
                            self.reward_satisfaction(c, amount=0.5)
        return n
