#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""concept_opposition.py — 符号层对立结构 (2026-09-04, B 路线落地)

立项: knowledge/opposition_selectivity_research_conclusion_20260904.md
(对立选择性研究 5 实验链收束) + knowledge/second_order_coupling_
verification_20260904.md (二阶普适崩实验)。

研究结论 (勿重做):
  1. 语义对立属于**符号层 (结构)**, 不是相位动力学: 对立端 (冷↔沸)
     初始置 π 跑流 400 步被一阶传导拉回同相 (dφ=0.000), 符号互斥
     边存活 True 稳定不被冲 (research_opposition_where.py 决定性对照)。
  2. **对立发现 = 对象状态转移图端点 (度=1 状态) 零标签涌现**:
     泪 {冷,沸}, 火 {旺,灭} 识别正确。
  3. 二阶 sin(2Δφ) 是维持器非创造器; 概念层普适加二阶 = 相干崩溃
     (08-07 历史重演); 合理位置只剩"已符号化对立对的动力学投影"
     或 MES 独立原语层。概念耦合核保持纯一阶 (生产零变化)。
  4. 对立结构认知正解 = 符号层负关系/互斥边; 相位差 π 至多是它的
     可选动力学读数/投影, 不参与概念同步学习。

本模块 = 符号层对立边集合的**真实实现** (研究 b 路线增强落地):
  - `_oppose_edges: set[tuple[str,str]]` — 符号对立边 (规范化排序元组)
  - `opposition_enabled` — 默认 False 零破坏 (最终默认裁定在主会话;
    未开启时生产 observe 路径一字不变, 统计零维护)
  - 端点涌现: observe() 内**在线增量**维护每对象状态轨迹统计
    (选项A, O(1)/事件, 数据源 = 状态谓词事件 (obj,'在'|'变'|'是',s)
    与结构谓词事件 — 与 _last_obs 同挂点同条件, 只读既有判定);
    惰性 sync (脏标记) 从轨迹转移图算端点 (distinct-neighbor 度=1)
    → 确认门槛 (端点出现频次/转移样本量) → 写 _oppose_edges。
  - 读口: oppose_edges() / opposites_of() / opposition_count() /
    opposition_report() — 与 phase_structure().opposite_pairs 同构的
    消费面, 供行为环/元认知/语义定向消费。
  - 相位关系: 符号边与一阶同步学习完全共存 (互不写)。对立边概念
    对若相位差远 = 可选二阶投影读数的天然候选; 若相位差近 (被一阶
    拉回), 对立语义**仍由符号边承载** (研究结论: 符号稳定相位不稳)。
    可选投影 = 只读读数 opposition_phase_report(), 概念耦合核零改动。

算法修正说明 (诚实记录, 与研究报告一致但实现取更鲁棒形式):
  研究报告 learn_endpoints 读 cs.events (唯一三元组插入序) = first-
  appearance 链伪迹; 研究流生成器含直跳 旺→灭 (fire_idx 误用
  tear_idx) → 该伪迹下恰好成立。真实生产流 (泪 冷温 热沸 相邻 /
  火 旺↔灭 相邻, wm.observe_state/observe_context 变化驱动) →
  distinct-neighbor 转移图度=1 才正确给出谱两端。实现采用后者:
  **状态轨迹去连续重复 → 无向转移图 → distinct-neighbor 度**。
  对相邻转移的真实状态维度, 端点 = 谱两端 = 对立候选, 与生产
  生产回归基线 (泪{冷,沸} 火{旺,灭}) 一致。

三铁律: 轨迹统计 = 感知层测量 (纯观测); 端点判定 = 结构涌现
(不是行为判定 — 消费端 (行为环/元认知) 才做行为选择); 边只写
自身新表, 不碰 events/相位/边表/链。
"""
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple


class ConceptSpaceOppositionMixin:
    """符号层对立结构 (mixin 进 ConceptSpace).

    默认关 = 零破坏: opposition_enabled=False 时 observe 钩子只做
    一次布尔判断即返回, 不维护任何统计、不消耗 rng、不写任何结构
    → 生产路径一字不变。开启后从该时刻起增量收集轨迹统计。
    """

    # ── 开关/门槛 (装配方控制) ──
    opposition_enabled: bool = False   # 最终默认裁定在主会话 (本项目
    # 哲学 = 机制默认开, 但对立边消费端尚未装配 → 先默认关零破坏;
    # 裁决开时置 True 即全量生效)
    opposition_min_occ: int = 2        # 端点确认门槛: 状态访问 (去连续
    # 重复后的离散停留) 频次 ≥ 此值 — 防单次噪声状态冒充端点
    opposition_min_edge: int = 2       # 端点确认门槛: 该端点与其唯一
    # 邻居间的转移样本量 (双向和) ≥ 此值 — 防一次触碰即算谱端

    def _init_opposition(self):
        """符号对立状态表 (默认全空; 启用才写, 零破坏)."""
        # 每对象在线轨迹统计 (选项A, 增量 O(1)/状态事件):
        self._opp_last: Dict[str, str] = {}       # obj → 上次状态 (去连续重复锚)
        self._opp_occ: Dict[str, Dict[str, int]] = defaultdict(
            lambda: defaultdict(int))             # obj → {状态: 访问频次}
        self._opp_de: Dict[str, Dict[Tuple[str, str], int]] = defaultdict(
            lambda: defaultdict(int))             # obj → {(前,后): 有向转移计数}
        # 符号对立边 (规范化: 排序元组 (a,b) == (b,a))
        self._oppose_edges: Set[Tuple[str, str]] = set()
        self._opp_dirty: bool = False     # 有新增轨迹 → 下次读需 sync
        self._opp_synced: bool = False    # 已 sync 过 (空数据也标记, 防重复扫)

    # ══ 在线增量收集 (observe 状态谓词分支调用, 门控) ═════════
    def _opp_observe(self, obj: str, state: str) -> None:
        """状态事件进入 → 轨迹统计增量 (去连续重复).

        obj = 对象, state = 其状态 (observe 内已判定为状态谓词宾语,
        与 _last_obs 同条件同挂点)。连续重复 (变+在 双发 / 变化驱动
        断言) 只算一次离散停留 — 防 在/变 双事件把转移样本量虚增。
        """
        last = self._opp_last.get(obj)
        if state == last:
            return  # 连续重复: 非新停留, 零记录 (零噪声)
        self._opp_occ[obj][state] += 1
        if last is not None:
            # 有向转移 (前→后); 反向在后续事件自然计入 (无向边样本
            # 量 = 双向和, sync 时聚合)
            self._opp_de[obj][(last, state)] += 1
            self._opp_dirty = True
        self._opp_last[obj] = state

    # ══ 端点涌现 + 对立边写入 (惰性 sync) ═════════════════════
    def opposition_sync(self) -> bool:
        """从轨迹统计重算对立候选 → 写 _oppose_edges (整体替换).

        端点判定 (研究已验证的正确算法, 实现取 distinct-neighbor 鲁棒
        形式): 每对象状态轨迹去连续重复 → 无向转移图; 状态 s 的度 =
        其 distinct 邻居数; **度=1 且出现在转移中 = 端点** (谱端)。
        同一连通分量 (同一状态维度) 内端点 ≥2 → 取排序后首尾对为
        对立候选 (研究报告同款; 分量由转移图连通性天然限定, 跨维度
        端点不配对 — identity_learn 已保证同名对象状态单维度连通,
        此处分量约束为第二道防线)。

        确认门槛: 端点访问频次 ≥ opposition_min_occ 且 端点↔唯一邻居
        转移样本量 (双向和) ≥ opposition_min_edge — 防噪声单次状态
        冒充谱端 (研究教训: 真实生态对立端罕至但确有多次可达;
        单次状态 = 噪声非结构)。

        整体替换语义: 世界维度变化 (新中间态出现/维度重组) → 端点集
        变化 → 边自动更新 (结构跟随真实轨迹); 稳定流 → 边稳定
        (研究对照: 符号层稳定不被冲)。

        Returns: 本次是否发生写入 (False = 门控关/无新增/无候选).
        """
        if not self.opposition_enabled:
            return False
        if not self._opp_dirty and self._opp_synced:
            return False
        self._opp_synced = True
        self._opp_dirty = False
        new_edges: Set[Tuple[str, str]] = set()
        for obj, de in self._opp_de.items():
            # 无向转移图: state → set(邻居)
            adj: Dict[str, Set[str]] = defaultdict(set)
            for (a, b), n in de.items():
                if n > 0:
                    adj[a].add(b)
                    adj[b].add(a)
            if not adj:
                continue
            # 连通分量 (并查集) — 跨维度端点不配对
            par = {}
            def _find(x):
                while par[x] != x:
                    par[x] = par[par[x]]
                    x = par[x]
                return x
            def _union(x, y):
                rx, ry = _find(x), _find(y)
                if rx != ry:
                    par[ry] = rx
            for s in adj:
                par[s] = s
            for a, nbrs in adj.items():
                for b in nbrs:
                    _union(a, b)
            comps: Dict[str, List[str]] = defaultdict(list)
            for s in adj:
                comps[_find(s)].append(s)
            occ = self._opp_occ.get(obj, {})
            for members in comps.values():
                if len(members) < 2:
                    continue  # 单状态分量无转移 → 无端点
                ends = []
                for s in members:
                    if len(adj[s]) != 1:
                        continue  # 度≠1: 中间态/分叉, 非谱端
                    (nb,) = adj[s]
                    # 确认门槛: 频次 + 双向转移样本量
                    if occ.get(s, 0) < self.opposition_min_occ:
                        continue
                    if (de.get((s, nb), 0) + de.get((nb, s), 0)) \
                            < self.opposition_min_edge:
                        continue
                    ends.append(s)
                if len(ends) >= 2:
                    ends_sorted = sorted(ends)
                    new_edges.add((ends_sorted[0], ends_sorted[-1]))
        self._oppose_edges = new_edges
        return True

    # ══ 读口 (消费面, 与 phase_structure().opposite_pairs 同构) ══
    def oppose_edges(self) -> List[Tuple[str, str]]:
        """符号对立边列表 [(a, b), ...] (规范化排序元组)."""
        self.opposition_sync()
        return sorted(self._oppose_edges)

    def opposites_of(self, concept: str) -> List[str]:
        """概念 c 的符号对立概念列表 (无 → [])."""
        self.opposition_sync()
        out = []
        for a, b in self._oppose_edges:
            if a == concept:
                out.append(b)
            elif b == concept:
                out.append(a)
        return sorted(out)

    def opposition_count(self) -> int:
        """符号对立边数."""
        self.opposition_sync()
        return len(self._oppose_edges)

    def opposition_report(self) -> dict:
        """对立结构报告 (元认知/语义定向消费):

        {'edges': [(a,b)], 'by_obj': {对象: [(端点对...)]},
         'stats': {对象: {状态: {occ, deg}}}}
        """
        self.opposition_sync()
        by_obj: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        stats: Dict[str, dict] = defaultdict(dict)
        for obj, de in self._opp_de.items():
            adj: Dict[str, Set[str]] = defaultdict(set)
            for (a, b), n in de.items():
                if n > 0:
                    adj[a].add(b)
                    adj[b].add(a)
            occ = self._opp_occ.get(obj, {})
            for s in adj:
                stats[obj][s] = {'occ': occ.get(s, 0),
                                 'deg': len(adj[s])}
        for a, b in self._oppose_edges:
            # 归属对象 = 边端点所在轨迹对象 (同一对象维度内)
            for obj in self._opp_de:
                if a in self._opp_occ.get(obj, {}) \
                        and b in self._opp_occ.get(obj, {}):
                    by_obj[obj].append((a, b))
        return {'edges': sorted(self._oppose_edges),
                'by_obj': {k: sorted(v) for k, v in by_obj.items()},
                'stats': {k: dict(v) for k, v in stats.items()}}

    # ══ 相位投影读数 (可选特征, 零写) ═════════════════════════
    def opposition_phase_report(self, anti_thr: float = 2.5) -> dict:
        """已符号化对立对的相位差投影读数 (纯只读, 不参与耦合).

        研究定位: 二阶/反相至多是"已符号化对立对"的可选动力学投影,
        不是对立本源; 一阶同步学习会把对立端拉回同相 (中间态传导),
        故对立语义永远由符号边承载。本读数让消费端看到每个符号对立
        对当前的相位关系:
          - dφ ≥ anti_thr (≈π): 反相 (对立 + 相位分离 — 可选二阶
            投影的天然候选, 但概念耦合核不加二阶, 见模块文档)
          - dφ 小: 被一阶拉同相 — 语义对立仍由符号边表达 (正常态)
        零写: 不碰相位/耦合/任何动力学结构。无 rhythm / 概念未注册
        → dφ None。
        """
        self.opposition_sync()
        rhythm = getattr(self, '_rhythm', None)
        out = []
        for a, b in sorted(self._oppose_edges):
            dphi = None
            if rhythm is not None and hasattr(rhythm, 'phase_diff'):
                try:
                    dphi = rhythm.phase_diff(a, b)
                except Exception:
                    dphi = None
            out.append({'a': a, 'b': b, 'dφ': dphi,
                        'anti': dphi is not None and dphi >= anti_thr})
        return {'pairs': out,
                'note': '符号边承载对立; dφ 仅投影读数 (一阶可拉回同相)'}

    # ══ 持久化 (供 to_dict/from_dict 全息) ═════════════════════
    def _opposition_to_dict(self) -> dict:
        if not self.opposition_enabled:
            return {}
        return {
            'edges': sorted(self._oppose_edges),
            'occ': {k: dict(v) for k, v in self._opp_occ.items()},
            'de': {k: {f'{a}\t{b}': n for (a, b), n in v.items()}
                   for k, v in self._opp_de.items()},
            'last': dict(self._opp_last),
        }

    def _opposition_from_dict(self, d: Optional[dict]) -> None:
        if not d:
            return
        self._oppose_edges = {tuple(e) for e in d.get('edges', [])}
        self._opp_occ = defaultdict(lambda: defaultdict(int))
        for k, v in d.get('occ', {}).items():
            self._opp_occ[k].update(v)
        self._opp_de = defaultdict(lambda: defaultdict(int))
        for k, v in d.get('de', {}).items():
            for kk, n in v.items():
                a, b = kk.split('\t')
                self._opp_de[k][(a, b)] = n
        self._opp_last = dict(d.get('last', {}))
        self._opp_dirty = False
        self._opp_synced = True   # 已载入完整边/统计, 无需重扫
