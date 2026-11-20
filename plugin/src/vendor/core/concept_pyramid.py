#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""concept_pyramid.py — 多级概念金字塔 (2026-09-03)

立项: knowledge/concept_pyramid_proposal.md — 系统已有一层抽象
(类别涌现→物化→规则回退, 全专利化), 但金字塔第二层即断:
抽象/类别规则的涌现原料 = events 的对象字面名, 类别物化后从不
进 events → 类别无法成为更高阶抽象原料 → 元类别永不自动涌现。

研究 (experiments/exp_concept_pyramid.py, v1-v4 全记录, 33/33 绿):
  pairwise 类别 = 2对象共享任意键的完全图 (非真簇), 在其上层叠键
  集 → 无终止; 真金字塔 = 长在「对象经受动作 → 转移键」的共享
  签名上 — 这正是 _abstract_emerge 的结构 (键 → 支持对象集):
    · 键支持集 ⊊ 全体 → 具体层对象分组 (材料: 熔/凝→蜡铁钢;
      食物: 煮/晾→米豆面)
    · 键支持集 = 全体 → 顶层共享 (实体: 唤/抚→全体)
    · 层嵌套 = 支持集包含关系 (蜡 ∈ 材料 ∈ 实体) — 层数 = 树深,
      数据驱动非预置; 新对象/新键 → 支持集变化 → 树自动重排
    · 类别规则 = 组共享键的展平; 双向路由 (下行: 对象→具体类→
      …→顶层共享→全局; 上行: 实例证据经 _abstract_dirty 脏标记
      惰性重扫, 树重建自动吸收)

五部件:
  ① 类别级事件源: 对象经受动作 → 转移键 → 支持对象集 (抽象级
     事件视图, 复用 _abstract_emerge 结构, 不改 events 主结构)
  ② 递归聚簇: 键支持对象集的包含嵌套树 (层数数据驱动)
  ③ 层间双向路由: route (下行 实例→类→…→顶层) + 脏标记上行
  ④ 金字塔容量管理: _pyramid_vitality 每层类别活性/代谢/休眠
     (与 _category_vitality + 概念 θ 同构, 多层不无界堆积)
  ⑤ 行为环主路径装配: 高层规则作为假设候选进深推置信闸口
     (BehaviorLoop 装配端 + run_lifeform 经受动作域显式启用)

默认状态 (数据前提驱动装配, 2026-09-03 修订 — 判断标准 = 是否让项目
更好, 非'改动小/零破坏'): 金字塔装配于 run_lifeform 自治域 (fusion/
eco/trio/noise) 推理执行端 (deep_gate/active_reason 同族), 开启条件 =
「对象经受外部动作 → 共享状态转移键」数据前提存在 (生产回归基线式 我 加热
泪/水/铁 / 工具世界: 成员经受动作 → 键支持集 → 类别嵌套树可涌现)。
数据前提不在时 (eco/fusion 生态事件 = 事件标签结构, 不经受动作 →
无共享键 → 金字塔空转) 不装配 — 结构隔离 = 数据前提不在, 非保守。
因该前提在多数自治域世界不成立, 实际为显式开启: run_lifeform
--pyramid 旗标 或 env PYRAMID=1 启用 (--no-pyramid 对照回退);
生产回归基线 = 生产行为锚不默认改。cs 级 pyramid_enabled 供任何装配方显式
控制。pyramid_sleep_on 随装配开启 (容量代谢生效, 多层不无界堆积
— 这是机制本身, 非'纯沉淀')。

三铁律: 树构建/键统计 = 统计测量 (感知层), 纯查询零写 (route 零
写, 永不写回对象链/边表); 消费端 (深推/决策) 经置信闸口才产生
假设推演 (来源标注 abstract 系, 不污染实例链)。

验证纪律: 变更依据 = 指标对比 (verify + 生产基线确认无意外破坏);
期望行为随装配变化是合法的, 无意外破坏 ≠ 逐位不变。
"""
from collections import defaultdict


class ConceptPyramidMixin:
    """多级概念金字塔 (mixin 进 ConceptSpace).

    默认关仅在未装配时成立 (未启用前零操作); 装配 = run_lifeform
    自治域内经受动作世界以 --pyramid/PYRAMID=1 显式启用, 或装配方
    直接设 pyramid_enabled=True。开启条件见模块文档「默认状态」。
    """

    # ── 开关/容量 (装配方控制) ──
    pyramid_enabled: bool = False
    pyramid_metab: float = 0.9       # 每批代谢率 (与 _category_vitality 同构)
    pyramid_sleep_th: float = 0.3    # 休眠阈值 (低于 → 规则不涌现)
    pyramid_vitality_gain: float = 0.2   # 成员观察注入
    pyramid_sleep_on: bool = False   # 代谢生效开关 (装配方开, 见类文档)

    def _init_pyramid(self):
        """金字塔状态表 (默认全空, 启用才写)."""
        self._pyramid_tree = {}       # level → {name: info}
        self._pyramid_info = {}       # name → info (全局索引)
        self._pyramid_vitality = {}   # name → 活性
        self._pyramid_obj_path = {}   # 对象 → [(name, level)]
        self._pyramid_dirty = True
        self._pyramid_meta = {'n_emerged': 0, 'n_sleep': 0}

    # ── 键支持集 → 金字塔树 (递归聚簇, 数据驱动) ──────────────
    def _pyramid_key_objects(self):
        """① 类别级事件源视图: 抽象规则键 → 支持对象集.

        对象经受动作 → 边表过滤 → 共享转移键 (abstract_rules
        的 objects 字段 = 验证过该键的对象集合)。对象自身转移
        链的经验被 _abstract_emerge 统计聚合 — 类别概念 (超类)
        不需直接进 events: 其经受动作 = 成员对象经受动作的统计
        视图 (成员经受的动作即类别经受的动作, 聚合无损)。
        """
        out = {}
        for (s, a), v in self.abstract_rules().items():
            objs = tuple(sorted(v.get('objects', [])))
            if len(objs) >= 2:
                out[(s, a, v.get('result'), objs)] = v
        return out

    def pyramid_emerge(self) -> dict:
        """② 递归聚簇: 键支持对象集的包含嵌套树 → 层.

        支持集 ⊊ 全体 → 具体层 (材料: 熔→蜡铁钢); = 全体 →
        顶层共享 (实体: 唤→全体)。层 = 包含链深度 (根=全体共享
        层 1, 专属键组逐层向下细分)。含 concept 叶子即成员
        (成员经受动作的类别级事件源视图)。对象路径 = 该对象
        自上而下的具体类序列 (下行路由依据)。

        数据驱动: 无预置层数/无预置类别 — 树完全由键支持集
        决定; 对象集相同/嵌套自动归组; 新键 (实例新证据) →
        支持集变化 → 下次重扫自动更新 (脏标记惰性)。

        Returns:
            层表 {level: {name: info}} (同 self._pyramid_tree)
        """
        if not self.pyramid_enabled:
            return {}
        # 抽象规则脏 → 树必须重扫 (实例证据经 abstract_rules 吸收)
        if getattr(self, '_abstract_dirty', False):
            self._pyramid_dirty = True
        if not self._pyramid_dirty and self._pyramid_tree:
            return self._pyramid_tree
        keys = self._pyramid_key_objects()
        if not keys:
            self._pyramid_tree = {}
            self._pyramid_info = {}
            self._pyramid_obj_path = {}
            self._pyramid_dirty = False
            return self._pyramid_tree
        # 键 → 支持对象集 → 归组
        set_keys = defaultdict(list)
        for (s, a, res, objs) in keys:
            set_keys[frozenset(objs)].append((s, a, res))
        fss = list(set_keys)
        # 包含树: 父 = 最小包含超集; 根 = 无超集 (最大支持集 = 全体共享)
        children = defaultdict(list)
        roots = []
        for fs in fss:
            supers = [g for g in fss if g != fs and fs < g]
            if not supers:
                roots.append(fs)
            else:
                children[min(supers, key=len)].append(fs)
        # 层分配: 根 (最大集) = 1, 逐层向下 +1 (具体层号更大)
        self._pyramid_tree = {}
        self._pyramid_info = {}
        self._pyramid_obj_path = {}
        self._pyramid_meta['n_emerged'] = 0
        # 对象路径重建
        self._pyramid_obj_path = {}

        def walk(fs, lvl):
            nm = '_'.join(sorted(fs))
            info = {'objects': sorted(fs), 'keys': sorted(set_keys[fs]),
                    'level': lvl, 'name': nm, 'children': []}
            self._pyramid_tree.setdefault(lvl, {})[nm] = info
            self._pyramid_info[nm] = info
            self._pyramid_meta['n_emerged'] += 1
            # 活力保留 (休眠恢复: 再涌现不重置历史 — 对象观察注入恢复)
            self._pyramid_vitality.setdefault(nm, 1.0)
            # 对象路径: 每对象挂在含它的每个类别下 (路由链)
            for obj in fs:
                self._pyramid_obj_path.setdefault(obj, []).append((nm, lvl))
            for child in children.get(fs, []):
                info['children'].append('_'.join(sorted(child)))
                walk(child, lvl + 1)

        for fs in roots:
            walk(fs, 1)
        # 对象路径: 具体 (深层) → 抽象 (浅层=顶层) — walk 内已建,
        # 此处按 level 降序排序
        for obj in self._pyramid_obj_path:
            self._pyramid_obj_path[obj].sort(key=lambda x: -x[1])
        self._pyramid_dirty = False
        return self._pyramid_tree

    # ── ③ 下行路由: 对象 → 自身经验 → 具体类 → … → 顶层 ──
    def pyramid_route(self, concept: str, state, act: str):
        """高层规则回退查询 (纯查询零写).

        顺序: ① 对象自身链经验 (process_infer 零抽象, 事实优先)
        ② 含 concept 的类别自具体层向顶层 (键命中且类别未休眠)
        ③ 全局抽象兜底。

        Returns dict {'result', 'level', 'cat', 'source'}
          source: 'own' | 'pyramid' | 'global'; 永不写回对象链.
        """
        inf = self.process_infer(concept, [act], state=state)
        if inf.get('known') and inf.get('final') is not None:
            return {'result': inf['final'], 'level': 0, 'cat': concept,
                    'source': 'own'}
        if not self.pyramid_enabled or not self._pyramid_info:
            return None
        # 含 concept 的对象路径: 最具体 (深层) → 顶层 (浅层)。类规则
        # = 该类共享键; 逐级查 (state,act) → ('__any__',act) 兜底
        # (det 无条件键同款)。最具体类命中 = 最精确 (类别优先语义),
        # 顶层共享键 = 领域无关兜底 (如 全体共享 唤→动)。
        path = sorted(self._pyramid_obj_path.get(concept, []),
                      key=lambda x: -x[1])   # level 大 = 具体先
        for (nm, lvl) in path:
            info = self._pyramid_info.get(nm)
            if info is None:
                continue
            res = None
            for (s, a, r) in info['keys']:
                if a == act and (s == state or s == '__any__'):
                    res = r
                    break
            if res is not None:
                vit = self._pyramid_vitality.get(nm, 1.0)
                if vit >= self.pyramid_sleep_th:   # ④ 休眠类不消费
                    # strength = 键支撑证据 (类别规则无独立强度 —
                    # 键由多成员共享, 保守 0.5; 上层消费端调制折扣)
                    return {'result': res, 'level': lvl, 'cat': nm,
                            'source': 'pyramid', 'strength': 0.5}
                break   # 休眠 → 跳到更抽象层? 否 — 抽象层更弱,
                # 休眠即整条含此类的具体语义不可用 → 走全局兜底
        # 全局抽象兜底 (跨类泛化)
        ar = self.abstract_rules()
        g = ar.get((state, act)) or ar.get(('__any__', act))
        if g is not None:
            return {'result': g.get('result'), 'level': -1, 'cat': '全局',
                    'source': 'global',
                    'strength': g.get('strength', 0.5)}
        return None

    # ── ④ 容量管理 (与概念活性场同构) ──
    def pyramid_metabolize(self):
        """每批代谢: 全类别活性 × pyramid_metab (冷却).

        pyramid_sleep_on 装配方随 pyramid_enabled 开启 (run_lifeform
        经受动作域启用时同步置 True):
        不活跃高层类别 → 活性 < pyramid_sleep_th → 休眠
        (pyramid_route 跳过 = 规则不涌现), 成员再观察注入恢复。
        多层容量管理 = 机制本身 (多层不无界堆积), 代谢在装配域
        恒生效。
        """
        if not self.pyramid_enabled or not self.pyramid_sleep_on:
            return
        for k in list(self._pyramid_vitality):
            self._pyramid_vitality[k] *= self.pyramid_metab

    def pyramid_observe(self, obj):
        """成员观察 → 含该对象的类别活性注入 (上行活化)."""
        if not self.pyramid_enabled:
            return
        for nm, info in self._pyramid_info.items():
            if obj in info['objects']:
                self._pyramid_vitality[nm] = (
                    self._pyramid_vitality.get(nm, 1.0)
                    + self.pyramid_vitality_gain)

    # ── ⑤ 装配查询 (深推/决策读, 来源标注 pyramid) ──
    def pyramid_assume(self, concept: str, state, act: str,
                       conf_gate: float = 0.5):
        """行为环装配: 高层抽象作为假设候选 → 置信闸口.

        假设置信 (与 _abstract_confidence 同族): own=1.0;
        pyramid/global 规则 = 统计共享转移, 越上层越保守
        (strength 证据 × (0.9^(level-1)))。conf < conf_gate
        不消费 (防污染闸口: 高层统计假设不直接驱动行为)。
        """
        r = self.pyramid_route(concept, state, act)
        if r is None:
            return None
        if r['source'] == 'own':
            conf = 1.0
        else:
            strength = r.get('strength', 0.5)
            base = 0.3 if strength < 1.0 else (0.65 if strength >= 3.0
                                               else 0.5)
            conf = base * (0.9 ** max(0, r.get('level', 0)))
        r['conf'] = round(conf, 4)
        return r if conf >= conf_gate else None

    # ── 持久化 (金字塔树/活力, 供 save/load 全息) ──
    def _pyramid_to_dict(self) -> dict:
        if not self.pyramid_enabled:
            return {}
        return {
            'vitality': dict(self._pyramid_vitality),
            'meta': dict(self._pyramid_meta),
        }

    def _pyramid_from_dict(self, d: dict):
        if not d:
            return
        self._pyramid_vitality = dict(d.get('vitality', {}))
        self._pyramid_meta = dict(d.get('meta', {}))
        self._pyramid_dirty = True   # 树由事件流重扫 (统计可重建)
