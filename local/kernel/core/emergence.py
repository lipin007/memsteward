# -*- coding: utf-8 -*-
"""涌现引擎 — 概念空间默认路径 (V3 图纸 M5 施工件移植, 2026-08-12)

涌现科学: 设计功能是傲慢的, 涌现的功能才是科学的。
角色/类别/状态维度 从事件流自然长出, 不靠手工标注。

M5 既定任务: 涌现唯一家 — 三路涌现收口到单类 EmergenceEngine。
实验体 v2-fix 现状: 角色/类别/维度散落 (concept_ontology._subj_act_counts /
rhythm_vnext 第七刀 / concept_state 107)。本模块 = 唯一家入口,
增量统计喂入, emerge() 默认路径产出; 与既有机制并存 (零行为变更),
元认知可读 (roles/categories/state_dims)。

零破坏: 引擎独立, 注入使用; 写入只经概念空间既有 API (观察/绑定/相位)。
"""
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple


class EmergenceEngine:
    """涌现引擎: 角色/类别/状态维度 三路默认涌现

    - 角色: (主体, 动作) 事件统计 → 对象-动作绑定 (谁做什么)
    - 类别: 共享动作模式的对象聚簇 → 类别概念 (相位聚簇的统计近似)
    - 状态维度: 预测失败检测 (同样状态+动作 → 不同结果 → 隐藏维度)

    分层共享 (2026-08-21): 概念层共享 + 统计层隔离 — 全局桶
    (_res_count/_pred_fail/_res_seen) 供单环/认知聚合; per-world 桶
    (_world_buckets) 供多环环读自己的 (view(world_id))。高频世界不
    再主导低频世界统计。
    """

    def __init__(self, cs, min_role_support: int = 3,
                 role_pref: float = 0.6, min_cat_size: int = 2,
                 min_dim_conflict: int = 3):
        self.cs = cs
        self.min_role_support = min_role_support   # 角色最小支持度 (次数)
        self.role_pref = role_pref                 # 角色偏好阈值 (占比)
        self.min_cat_size = min_cat_size           # 类别最小对象数
        self.min_dim_conflict = min_dim_conflict   # 维度冲突最小次数
        # 增量统计 (时间维度: 事件流累积)
        self._role_counts: Counter = Counter()     # (subject, action) → n
        self._subj_acts: Dict[str, Counter] = defaultdict(Counter)  # subject → {action: n}
        self._pred_fail: Dict[Tuple, int] = defaultdict(int)  # (obj, action, cond) → 违背次数
        self._res_count: Dict[Tuple, Counter] = defaultdict(Counter)  # 结果频率 (动态预期)
        self._violation_step: Dict[Tuple, int] = {}  # 最近违背的观察步号 (修复确认门)
        self._n_obs = 0  # 观察计数 (步号代理)
        self._res_seen: Dict[Tuple, set] = defaultdict(set)   # (obj, action, cond) → 结果集合
        # per-world 统计桶 (2026-08-21 分层共享: 概念层共享 + 统计层
        # 隔离): 多环并行时每环事件双写自己的桶 → 高频世界不再主导
        # 低频世界的统计 (事件量主导/学习节奏失配的解法)。全局桶
        # (_res_count/_pred_fail/_res_seen) 保持原样 = 单环 (world_id
        # None) 逐位不变; 多环经 em.view(world_id) 读世界桶。
        self._world_buckets: Dict[str, dict] = {}  # world_id → 桶
        # world_id 事件日志 (2026-08-21, 多环归因追溯): 观察事件带世界
        # 标签 → 可追溯"哪条知识来自哪个世界的经历" (变化可归因纪律的
        # 基础设施)。默认 None 不记录 (零开销零行为变化); run_multiloop
        # 传 world_id → 记录。纯只读新增, 不动任何现有计数/统计逻辑。
        self._world_events: List[Tuple] = []  # (world_id, step, subj, action, state, result)
        # 涌现产出 (元认知可读)
        self.roles: Dict[str, str] = {}            # subject → role
        self.categories: Dict[str, List[str]] = {} # cat_name → [objects]
        self.state_dims: Dict[str, List[dict]] = {}  # obj → [dim 猜测]

    # ── 增量观察 (事件流进入时调用, 时间维度累积) ──────────────
    def observe(self, subj: str, action: str,
                obj: Optional[str] = None,  # 半成品: 预留隐藏维度冲突检测 (同 obj/action/cond 不同 result), 现仅 state/result 检测
                cond: Optional[str] = None,
                result: Optional[str] = None,
                state: Optional[str] = None,
                world_id: Optional[str] = None) -> None:
        """事件进入: 角色统计 + 预测失败检测 (状态维度涌现源)

        state/result 语义: 动作发生在 state 条件下, 观察到 result。
        同样 (obj, action, cond) 不同 result → 隐藏维度冲突。

        world_id (2026-08-21 多环归因): 非 None → 事件追加进
        _world_events (世界标签日志, 归因追溯用)。None → 不记录
        (默认零开销, 生产行为一字不动)。
        """
        if world_id is not None:
            self._world_events.append(
                (world_id, self._n_obs, subj, action, state, result))
            # 分层共享: 世界桶双写 (统计层隔离, 2026-08-21)
            b = self._world_buckets.setdefault(world_id, {
                'res_count': defaultdict(Counter),
                'pred_fail': defaultdict(int),
                'res_seen': defaultdict(set),
            })
            if state is not None and result is not None:
                wkey = (subj, action, state)
                wseen = b['res_seen'][wkey]
                wcnt = b['res_count'][wkey]
                wexp = wcnt.most_common(1)[0][0] if wcnt else None
                if wexp is not None and result != wexp:
                    b['pred_fail'][wkey] += 1
                wcnt[result] += 1
                wseen.add(result)
        self._role_counts[(subj, action)] += 1
        self._subj_acts[subj][action] += 1
        # 预测失败检测: 同条件不同结果
        if state is not None and result is not None:
            key = (subj, action, state)
            seen = self._res_seen[key]
            cnt = self._res_count[key]
            # 动态预期 = 当前最频繁结果 (Rescorla-Wagner); 违背 =
            # 非预期结果每次 +1 (RPE 计数, 2026-08-15 R22: 原版只在
            # 新结果首次 +1, 上限=结果种类-1 → 低频冲突永远到不了阈值)
            expected = cnt.most_common(1)[0][0] if cnt else None
            self._n_obs += 1
            if expected is not None and result != expected:
                self._pred_fail[key] += 1
                self._violation_step[key] = self._n_obs
            cnt[result] += 1
            if result not in seen:
                seen.add(result)

    # ── 预期自评 (M4, 2026-08-20): 预期可靠性置信度 ──────
    def view(self, world_id: Optional[str]):
        """世界视图 (2026-08-21 分层共享: 统计层隔离的查询口).

        world_id None → 全局桶 (单环现状, 逐位不变); world_id 非 None
        → 该世界的隔离统计桶 (多环环读自己的, 高频世界不稀释自己的
        信号)。消费方 (intent/behavior_loop) 读 _pred_fail/_res_count
        前过 view 一处分流, 内部逻辑一字不动。纯查询零写。"""
        return self if world_id is None else _WorldView(self, world_id)

    def world_trace(self, subj: Optional[str] = None,
                    action: Optional[str] = None,
                    state: Optional[str] = None) -> Dict[str, int]:
        """归因追溯 (2026-08-21 多环世界标签): 按 (subj/action/state)
        过滤事件日志 → 各世界观察计数分布。回答"这条知识来自哪个世界
        的经历" — 变化可归因纪律的查询口。纯查询零写。world_id 未启用
        (日志空) → 返回空 dict。"""
        out: Dict[str, int] = defaultdict(int)
        for wid, _step, s, a, st, _r in self._world_events:
            if subj is not None and s != subj:
                continue
            if action is not None and a != action:
                continue
            if state is not None and st != state:
                continue
            out[wid] += 1
        return dict(out)

    def expectation_confidence(self, subj: str, action: str,
                               state: Optional[str] = None,
                               min_exec: int = 5) -> Optional[float]:
        """预期可靠性置信度 (元预期读数, 纯查询零写零判定)

        置信度 = top1 概率 × 历史命中率:
        - top1: 最频繁结果占比 (分布确定性 — 结果越分散预期越模糊)
        - 命中率: 1 - 违背次数/执行次数 (动态预期命中 — 结果经常
          偏离最频繁结果 = 预期频繁落空)
        - 两者相乘: 预期既确定又常命中才算可靠。

        min_exec 支持度不足 → None (样本不足 = 未知, 消费端按
        默认信任处理 — 截断器语义: 只冷却被数据明确判不可靠的
        预期, 不惩罚新键)。

        三铁律: 纯测量, 不判定 — 判定 (冷却/降权) 在消费端。
        """
        cnt = self._res_count.get((subj, action, state))
        if not cnt:
            return None
        n_exec = sum(cnt.values())
        if n_exec < min_exec:
            return None
        top1 = cnt.most_common(1)[0][1] / n_exec
        n_viol = self._pred_fail.get((subj, action, state), 0)
        hit = 1.0 - n_viol / n_exec
        return top1 * hit

    # ── 默认路径: 三路涌现 (每批事件后调用) ───────────────────
    def emerge(self) -> Dict[str, dict]:
        """涌现默认路径: 角色 → 类别 → 状态维度"""
        out = {}
        out['roles'] = self.emerge_roles()
        out['categories'] = self.emerge_categories()
        out['state_dims'] = self.emerge_state_dims()
        return out

    def emerge_roles(self) -> Dict[str, str]:
        """角色涌现: 主体动作占比 → 角色 (谁做什么)

        角色 = 对象-动作绑定: 某主体对某动作占比 ≥ role_pref 且
        支持度 ≥ min_role_support → 该动作是它的角色。
        """
        new_roles: Dict[str, str] = {}
        for subj, acts in self._subj_acts.items():
            total = sum(acts.values())
            if total < self.min_role_support:
                continue
            top_act, top_n = acts.most_common(1)[0]
            if top_n / total >= self.role_pref and top_n >= self.min_role_support:
                new_roles[subj] = top_act
        self.roles.update(new_roles)
        return dict(new_roles)

    def emerge_categories(self) -> Dict[str, List[str]]:
        """类别涌现: 共享动作模式的对象聚簇

        类别 = 动作模式相同的对象集合 (相位聚簇的统计近似:
        概念在动作维度上邻近 → 同一类别区域)。
        """
        # 动作 → 执行者集合 (角色反向索引)
        act_members: Dict[str, set] = defaultdict(set)
        for subj, acts in self._subj_acts.items():
            for act, n in acts.items():
                if n >= self.min_role_support:
                    act_members[act].add(subj)
        # 共享 ≥2 动作的集合 → 类别
        pairs: Dict[frozenset, set] = defaultdict(set)
        for act, members in act_members.items():
            members = sorted(members)
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    pairs[frozenset({members[i], members[j]})].add(act)
        new_cats: Dict[str, List[str]] = {}
        for pair, acts in pairs.items():
            if len(pair) >= self.min_cat_size and len(acts) >= 2:
                name = '_'.join(sorted(pair))
                new_cats[name] = sorted(pair)
        self.categories.update(new_cats)
        # 类别本体化 (缺口 3, A 层, 2026-08-18): 新类别注册为概念空间实体
        # — 相位惰性初始化 (B 层聚合成员) + 成员集合表。纯新增零破坏:
        # 类别概念是独立字符串 (对象名不含 '_'), 相位字段独立; 成员对象
        # 自身零改动; 不碰 rhythm 实体计数 (能量实体留到 C 层传播接入)。
        if new_cats:
            self._register_category_concepts(new_cats)
        return new_cats

    def _register_category_concepts(self, new_cats: Dict[str, List[str]]) -> None:
        """类别 → 概念空间实体 (A 层): 相位 + 成员集合表"""
        cs = self.cs
        members = getattr(cs, '_category_members', None)
        if members is None:
            return  # 宿主无本体化支持 (防御)
        init_phase = getattr(cs, '_init_phase', None)
        vitality = getattr(cs, '_category_vitality', None)
        for name, objs in new_cats.items():
            members.setdefault(name, set()).update(objs)
            if init_phase is not None:
                init_phase(name)  # 惰性初始化 (随机初相, B 层聚合到成员)
            if vitality is not None:
                vitality.setdefault(name, 1.0)  # 刚涌现 = 活跃

    def emerge_state_dims(self) -> Dict[str, List[dict]]:
        """状态维度涌现: 预测失败 → 隐藏维度猜测

        同样 (主体, 动作, 状态) 观察到不同结果 → 存在未观察的
        隐藏状态维度 (107 教训: "冷" 从未进观察通道)。产出
        维度猜测, 等证据 (时间维度) 确认或放弃。
        """
        new_dims: Dict[str, List[dict]] = {}
        for (subj, action, state), n in self._pred_fail.items():
            if n >= self.min_dim_conflict:
                dim = {'name': f'{state}?', 'source': 'prediction_failure',
                       'conflict': n, 'evidence': len(self._res_seen[(subj, action, state)])}
                new_dims.setdefault(subj, []).append(dim)
        self.state_dims.update(new_dims)
        return new_dims

    # ── 持久化 (2026-08-21 记忆闭环: 预期统计落盘) ──────
    def to_dict(self) -> dict:
        """全部统计桶 → dict (可 json)。键 (subj, action, state) 含
        None → \x00 占位 (与 concept_space 同约定); world_buckets
        同格式。"""
        def kstr(k):
            return '\t'.join(x if x is not None else '\x00' for x in k)
        wb = {}
        for wid, b in self._world_buckets.items():
            wb[wid] = {
                'res_count': {kstr(k): dict(c)
                              for k, c in b['res_count'].items()},
                'pred_fail': {kstr(k): v
                              for k, v in b['pred_fail'].items()},
                'res_seen': {kstr(k): list(v)
                             for k, v in b['res_seen'].items()},
            }
        return {
            'n_obs': self._n_obs,
            'role_counts': {kstr(k): v
                            for k, v in self._role_counts.items()},
            'subj_acts': {s: dict(c)
                          for s, c in self._subj_acts.items()},
            'pred_fail': {kstr(k): v
                          for k, v in self._pred_fail.items()},
            'res_count': {kstr(k): dict(c)
                          for k, c in self._res_count.items()},
            'res_seen': {kstr(k): list(v)
                         for k, v in self._res_seen.items()},
            'violation_step': {kstr(k): v
                               for k, v in self._violation_step.items()},
            'world_buckets': wb,
        }

    def from_dict(self, d: dict):
        """恢复统计状态 (就地覆盖; 缺失字段保持默认零破坏)。"""
        def ktup(s):
            return tuple(None if x == '\x00' else x for x in s.split('\t'))
        self._n_obs = int(d.get('n_obs', 0))
        self._role_counts = Counter(
            {ktup(k): v for k, v in d.get('role_counts', {}).items()})
        self._subj_acts = defaultdict(
            Counter, {s: Counter(c)
                      for s, c in d.get('subj_acts', {}).items()})
        self._pred_fail = defaultdict(
            int, {ktup(k): v for k, v in d.get('pred_fail', {}).items()})
        self._res_count = defaultdict(
            Counter, {ktup(k): Counter(c)
                      for k, c in d.get('res_count', {}).items()})
        self._res_seen = defaultdict(
            set, {ktup(k): set(v)
                  for k, v in d.get('res_seen', {}).items()})
        self._violation_step = {
            ktup(k): v for k, v in d.get('violation_step', {}).items()}
        self._world_buckets = {}
        for wid, b in d.get('world_buckets', {}).items():
            self._world_buckets[wid] = {
                'res_count': defaultdict(
                    Counter, {ktup(k): Counter(c)
                              for k, c in b['res_count'].items()}),
                'pred_fail': defaultdict(
                    int, {ktup(k): v for k, v in b['pred_fail'].items()}),
                'res_seen': defaultdict(
                    set, {ktup(k): set(v)
                          for k, v in b['res_seen'].items()}),
            }
        return self


class _WorldView:
    """per-world 统计桶视图 (2026-08-21 分层共享).

    world_id 非 None → 只暴露该世界的隔离统计桶 (res_count/pred_fail/
    res_seen), 消费方 (intent/behavior_loop) 读法不变 — 一处分流。
    世界桶不存在时惰性创建 (setdefault), 纯读视图零写全局。"""

    def __init__(self, em, world_id: str):
        self._em = em
        self._wid = world_id

    def _b(self) -> dict:
        return self._em._world_buckets.setdefault(self._wid, {
            'res_count': defaultdict(Counter),
            'pred_fail': defaultdict(int),
            'res_seen': defaultdict(set),
        })

    @property
    def _res_count(self):
        return self._b()['res_count']

    @property
    def _pred_fail(self):
        return self._b()['pred_fail']

    @property
    def _res_seen(self):
        return self._b()['res_seen']

    # ── 元认知可读 ────────────────────────────────────────────
