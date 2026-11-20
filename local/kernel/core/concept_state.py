#!/usr/bin/env python3
"""
core/concept_state.py — ConceptSpace state 子模块 (mixin)

S3 拆分 (2026-08-11 施工, 用户拍板 P2①): ConceptSpace 单文件 3656 行
→ 5 子模块 mixin (ontology/phase/principle/state/space), 保持
`from core.concept_space import ConceptSpace` 重导出兼容。

零机制变更: 方法体一字未改, 仅按 C1 14 区块边界归位。
"""
from collections import defaultdict, Counter
from types import SimpleNamespace as _SN
from typing import List, Dict, Tuple, Optional, Sequence
import os
import numpy as np

# 概念类型 (自动涌现的类别)
PERSON, ACTION, OBJECT, EMOTION = "人物", "动作", "物体", "情感"

# 状态推演阈值 (质询点 7 命名化, 默认值一字不改):
CONF_DEFAULT = 0.9       # 状态边置信缺省 (p_ab, 无记录时高置信默认)
CONF_COND_DEFAULT = 0.8  # 条件边置信缺省 (p_acb, 与 p_ab 区分)
CONF_TIER_HIGH = 0.8     # 置信分层: 高 >= 0.8
CONF_TIER_MEDIUM = 0.5   # 置信分层: 中 >= 0.5 (低 < 0.5)


NAV_CHAIN_CONF_MIN = 0.15  # nav 概率链边频率门槛 (2026-08-31 第九刀 v2)
NAV_CHAIN_MIN_N_DET = 5  # nav det 无条件边样本量门槛 (2026-08-31 v8): 无条件泛化比条件边更严 — 吃失手=位置不变=无事件词 → 条件边 (稍远,吃) 永不建 → det (any,吃)→中食 兜底 (成功样本泛化, 21 次失手统计不到) → 死循环 22 次复现铁证. 移动边多结果不建 det (len(bcnt)==1 约束) → 门槛只打吃/等待盲区. 真 det 5 次确认后过.
NAV_CHAIN_MIN_N = 2  # nav 概率链边样本量门槛 (2026-08-31 第十刀): n<2 噪声边拒绝. n=3 实测误杀真实朝食边 ((中食,西)→近食 n=2 是真实物理可复现, known 0 全探索); 1 次成功 conf 1.0 的噪声 (食物再生踩点) 仍拒, 真实边 2 次后放行 (移动可复现 n 快涨)


class ConceptSpaceStateMixin:
    def state_chain(self, obj: Optional[str] = None,
                    context: Optional[Sequence[Tuple[str, str]]] = None,
                    extrapolate: bool = False,
                    keep_all: bool = False
                    ) -> Dict[str, dict]:
        # identity_learn 路由 (2026-08-30): 分裂对象 → 当前状态子节点
        if obj and obj in getattr(self, '_identity_route', {}):
            _hint = None
            if context:
                for _r, _s in context:
                    if _r == obj:
                        _hint = _s
                        break
            obj = self._identity_route_lookup(obj, _hint)
        """状态链涌现: 条件边 + 确定性无条件边 → (状态, 动作) → 下一状态

        context: 关联对象状态对 (世界模型, 2026-08-13) —
        情境已知时复合条件边进链: (自身状态, 关联对象状态)→转移
        (火上泪=冷 → 加热 → 温)。复合边覆盖同 key 单条件边
        (情境压制无条件, 同 infer 的 cond 逻辑): 火旺时
        (冷,旺)→温 取代被稀释的单条件 (冷)→温。context=None
        零破坏 (原逻辑一字不动)。

        链 = 两种真转移的合并 (研究层结论: 链边必须两者都含):
          1. 条件边 (动作, 结果, 条件): 多结果因果 (水 加热→温|冷),
             trans[(条件, 动作)] = 结果
          2. 确定性无条件边 (动作→结果, DMIT score>0 且 p_ab≈1):
             单结果因果 (门 推→开), trans[('__any__', 动作)] = 结果
             事件流设计差异: 真实认知体只在可做时做动作 (推只在
             关时推) → 无条件 p_ab=1.0, lift=1.0 不涌现条件边, 但
             转移本身是确定的链边
        链结构 (冷→温→热→沸) 从转移一致性涌现, 不预置顺序。
        """
        trans: Dict[Tuple[str, str], str] = {}
        conf: Dict[Tuple[str, str], float] = {}
        # 边样本量表 (2026-08-31 第十刀): keep_all 分支消费 — 噪声
        # 边早期 conf 虚高 (1/1=1.0) 频率门槛拦不住, n<5 拒绝路径.
        # 与 conf 同构: 单值 float 或列表 (keep_all 多结果逐项).
        n_tab: Dict[Tuple[str, str], Any] = {}
        # ── 动作 → 效果对象筛选 (2026-09-18, 方案 B) ──
        # 背景 (已实测坐实): acts_of() 对所有对象返回全集 ACTS, 而世界
        # 真实语义是每个动作作用于不同对象 (eco: 保护→兔 / 喂食,放牧→
        # 草 / 猎杀→狼) ⇒ 概念空间把 '放牧' (效果对象=草) 也挂到查询
        # 对象 '兔' 名下, 而它的转移记录的是 草/狼 的状态 (实测:
        # _state_trans_dist 中 '放牧' 3 条全挂 草/狼, 兔 0 条) ⇒
        # 查 '兔+放牧' 命中他对象边 ⇒ 计划首跳必错 ⇒ advanced 恒 0。
        # ⇒ 建链时只保留「动作的实际效果对象 == 当前查询对象」的边。
        # 零破坏: 世界未提供映射 (effect_obj_of=None, 其他世界) 或
        # obj is None (全局链) ⇒ 完全不筛 (逐位不变)。
        _eo_fn = getattr(self, '_effect_obj_of', None)
        _eo_q = obj if _eo_fn is not None else None

        def _eo_skip(_a: str) -> bool:
            """该动作的效果对象已知且 != 查询对象 ⇒ 跳过此边。"""
            if _eo_q is None:
                return False
            try:
                _e = _eo_fn(_a)
            except Exception:
                return False  # 映射不可用 ⇒ 不筛 (诚实回退)
            return _e is not None and _e != _eo_q
        # ── 复合条件边先执行 (2026-08-16 顺序修复) ──
        # 原顺序单条件边先写 → 复合边 (情境精确) 与单条件边 (情境
        # 稀释) 同 key 冲突时, 单条件 conf 基数更高 → 复合边被
        # SKIP → 情境调制永不生效 (物理考试 seed43: 单条件边
        # (采样,左,左) p_acb 高于复合边 (采样,中左,(左,(向正,率快)))
        # 0.57 → 查询答左 自环 而非 中左)。情境已知时复合边必须
        # 优先 — 先写复合边, 单条件段再跳过被 matched 覆盖的 key。
        # 复合条件边 (context 匹配): 关系进链 (世界模型, 2026-08-13)
        # 情境已知时复合边优先 — 覆盖同 (自身状态,动作) 的单条件边
        # (被火灭稀释的残边被关系结构取代); 关联对象状态不在当前
        # 情境 → 复合边不适用 (火灭时加热无效是真规则)
        if context is not None:
            ctx_map = {r: s for r, s in context if s}
            ctx_states = set(ctx_map.values())
            modulated = set()   # 被复合边调制的 (c1,a) — 结果依赖情境
            matched = set()     # 当前情境匹配的复合边 key
            for (a, b, cc), m in self._state_cond_edges2.items():
                if m.get('world') is not None \
                        and m.get('world') != getattr(self,
                                                      '_current_world',
                                                      None):
                    continue  # 世界模型隔离 (2026-09-18)
                if _eo_skip(a):
                    continue  # 动作→效果对象 不匹配 (2026-09-18 方案 B)
                if not m.get('auto'):
                    continue
                if m.get('strength', 1.0) < self._cond_edge_dead:
                    continue  # 证据过期: 活性死亡过滤
                c1 = cc[0] if isinstance(cc, tuple) else cc
                cond = cc[1] if isinstance(cc, tuple) else None
                modulated.add((c1, a))
                # N 条件槽 + rel 对象绑定 (2026-08-16): 复合条件 =
                # (rel, val) 对列表, AND 语义 — 每个 (rel,val) 都要
                # 满足: rel 对应 context 值 == val。修复多关联对象
                # 世界 (物理: 向+率) 之前只存值丢 rel → (左,正) 与
                # (左,快) 都匹配 ctx_states → 后写覆盖先写 → 系统
                # 性答错。旧格式 (c1, c2_str) 兼容: 通配 rel "?"
                # 匹配任意关联对象的值 (旧行为)。
                if isinstance(cond, str):
                    # 旧格式 (a,b,(c1,c2)): c2 是单值字符串
                    pairs = (("?", cond),)
                else:
                    pairs = tuple(cond)
                ok = True
                for rel, val in pairs:
                    if rel == "?":
                        if val not in ctx_states:
                            ok = False
                            break
                    elif ctx_map.get(rel) != val:
                        ok = False
                        break
                if not ok:
                    continue  # 条件组合未全满足 → 不适用
                matched.add((c1, a))
                key = (c1, a)
                # 2026-08-14 世界模型修复: 复合边优先覆盖单条件边 —
                # 同 key 冲突时复合边 (情境已知) 取代被稀释的单条件
                # 残边 (火灭时热+加热→温 是情境真规则, 单条件边
                # 热+加热→沸 是火旺占多数的统计残留)。原实现弃
                # 复合边保留单条件 → 情境调制永不生效 (世界模型
                # 关系投影断链)。
                # 2026-08-16 复合边同 key 冲突修复: 同一 (c1,a) 两
                # 结果都匹配 (箱量化下同组合非确定转移, 物理考试
                # seed=43 (左,正,慢)→左|中左 各半) → 后写覆盖先写
                # = 建边顺序偶然性。修: 保留 p_acb 强者 (主导转移
                # 语义, 与单条件边冲突弃边同构但保留多数派 — 精确
                # 条件下强者=统计主导, 弃掉会失去该组合全部知识)。
                if key in trans and trans[key] != b:
                    if m.get('p_acb', 0.0) <= conf.get(key, 0.0):
                        continue
                trans[key] = b
                conf[key] = m.get('p_acb', CONF_COND_DEFAULT)
                n_tab[key] = m.get('n_updates', 1)
            # 情境压制 (第四步, 2026-08-13): 被复合边调制的
            # (c1,a) 结果依赖情境 — 当前情境无匹配复合时, 单条件
            # 边不适用 (火灭时加热无效是真规则; 统计上单条件边可
            # 因火旺占多数而涌现, 但情境已知时必须尊重调制关系)
            for key in modulated - matched:
                trans.pop(key, None)
                conf.pop(key, None)
        # ── 单条件边段 (2026-08-16 移至复合边段之后) ──
        # 复合边 (情境已知) 优先: 被 matched 覆盖的 key 一律跳过
        # (情境精确取代情境稀释); 未被调制的 key 走保留强者语义
        # (同一 (条件,动作) 两结果 = 隐藏维度调制信号, 保留统计
        # 主导转移, 不确定性由复合边表达 — 冲突不再断链)。
        # 2026-08-16 判别实验 (exam_physics_v3 掩码) 修复: 跳过
        # 条件从 matched 扩到 modulated — 情境已知时被复合边调制
        # 过的 key, 单条件边一律不兜底。此前 modulated-matched 的
        # 压制 (第四步) 被单条件段重新写回 → 外推组合 (慢档复合
        # 边调制了 (箱,采样), 快档无匹配复合) 答自环而非诚实 None
        # — 情境稀释的统计在情境已知时直接产出判定 = 统计当认知。
        for (a, b, c), m in self._state_cond_edges.items():
            if m.get('world') is not None \
                    and m.get('world') != getattr(self,
                                                  '_current_world', None):
                continue  # 世界模型隔离 (2026-09-18)
            if _eo_skip(a):
                continue  # 动作→效果对象 不匹配 (2026-09-18 方案 B)
            if not m.get('auto'):
                continue
            if m.get('strength', 1.0) < self._cond_edge_dead:
                continue  # 证据过期: 长期未被 log 支持, 活性死亡
            if context is not None and (c, a) in modulated:
                continue  # 情境已知: 被调制的 key 单条件不兜底
                         # (有匹配复合→复合边已写; 无匹配→诚实 None)
            if (c, a) in trans and trans[(c, a)] != b:
                if keep_all:
                    # nav 档级聚合 (2026-08-31 真实任务): 同键多结果
                    # 保留全部 — 档是类 (同档格子异质: 近食档 19 格
                    # 有的格北移靠近食物有的远离), 低概率结果 (朝食
                    # 物边 p_acb 0.28) 是真实可达路径. 强者覆盖 =
                    # 链单向远离 (有食→近食→…→无食) → plan_state
                    # 反向 BFS 到有食无路径 → 导航断链 (深推 known
                    # 19/141 实锤). 列表化后路径存在性恢复, 概率由
                    # conf 列表承载 (消费端取高/解包). 默认关零变化.
                    _cur = trans[(c, a)]
                    _cc = conf.get((c, a), CONF_COND_DEFAULT)
                    _nn = n_tab.get((c, a), 1)
                    if not isinstance(_cur, list):
                        _cur, _cc = [_cur], [_cc]
                        _nn = [_nn]
                    if b not in _cur:
                        trans[(c, a)] = _cur + [b]
                        conf[(c, a)] = _cc + [m.get('p_acb', CONF_COND_DEFAULT)]
                        n_tab[(c, a)] = _nn + [m.get('n_updates', 1)]
                    continue
                if m.get('p_acb', 0.0) <= conf.get((c, a), 0.0):
                    continue
            trans[(c, a)] = b
            conf[(c, a)] = m.get('p_acb', CONF_COND_DEFAULT)
            n_tab[(c, a)] = m.get('n_updates', 1)
        # 确定性无条件边: 结构通道采集的动作→唯一状态转移
        # (p_ab >= 0.9 且无多结果分歧; 不需要条件调制; 只作后备,
        # 不覆盖条件边 — 条件边优先, 无条件下确定性边兜底)
        for (a, b), m in self._state_det_edges.items():
            if m.get('world') is not None \
                    and m.get('world') != getattr(self,
                                                  '_current_world', None):
                continue  # 世界模型隔离 (2026-09-18)
            if _eo_skip(a):
                continue  # 动作→效果对象 不匹配 (2026-09-18 方案 B)
            if not m.get('auto') or m.get('p_ab', 0) < CONF_DEFAULT:
                continue
            if m.get('strength', 1.0) < self._cond_edge_dead:
                continue  # 证据过期: 同上, 活性死亡过滤
            key = ('__any__', a)
            if key in trans and trans[key] != b:
                continue
            trans[key] = b
            conf[key] = m.get('p_ab', CONF_DEFAULT)
            n_tab[key] = m.get('n_updates', 1)
        # ── 外推段 (率调制跨组合泛化, 2026-08-16 范式攻坚第二步) ──
        # 触发 = 情境已知 + extrapolate 开启 + (c1,a) 被复合边调制过但
        # 当前情境无匹配 (零覆盖组合 = 9a67eb2 诚实 None 的位置)。
        # 调制律每查询现场从感知层无门槛证据 (_state_cond_raw) 的演示
        # 组结构比较中提取并验证 (形态1: 缺失率值继承已学分支非主导;
        # 形态2: 率值不影响结果 → 唯一继承); 全演示组一致且含形态1
        # → 律成立才应用, 不一致 → 诚实 None。调制内容 (哪个结果、
        # 哪些组合) 全由数据驱动, 零硬编码 (不设计功能, 锚3)。推断
        # 不写回边表 (同 analogize 保守原则: 不污染事实查询), 结果
        # 带 inferred 标记, conf = 非主导原始占比 (如实反映不确定性,
        # 非伪造高置信)。默认 extrapolate=False → 本节零执行, trans/
        # conf 与既有路径逐位一致 (零破坏)。
        inferred = set()
        if extrapolate and context is not None:
            raw = getattr(self, '_state_cond_raw', {})
            if raw:
                ctx_map = {r: s for r, s in context if s}
                # pairs 规范化 = (rel,val) 元组 (与 _ctx_pairs 同构):
                # 外推预测针对特定情境 (向正,率快), 核对必须同情境
                # (中左,正,慢) 的真实转移不是 (中左,正,快) 外推的
                # 证据 — 粒度粗会误杀/误证 (第一版实测 refute 爆炸)。
                _pairs = tuple(ctx_map.items())
                for (c1, a) in modulated - matched:
                    if (c1, a) in trans:
                        continue
                    # 推理验证回灌 (阶段 A, 2026-08-16): 已被世界证伪的
                    # 外推不再重复犯错 — 证伪 1 次即禁 (宁缺毋滥: 错误
                    # 推理比不给答案危害大, 行为会基于它执行);
                    # 已验证/待验证照常 (inferred 标记保持, 不写回)。
                    v = self._reasoning_verdicts.get((c1, a, _pairs))
                    if v is not None and v.get('status') == '不可靠':
                        continue
                    ext = self._modulation_extrapolate(raw, c1, a, ctx_map)
                    if ext is not None:
                        b, r = ext
                        trans[(c1, a)] = b
                        conf[(c1, a)] = r
                        inferred.add((c1, a))
                        # 登记预测对 (首次) / 刷新预测 (待验证期
                        # 快照漂移, 已验证则锁定预测不再漂移)
                        if v is None:
                            self._reasoning_verdicts[(c1, a, _pairs)] = {
                                'b': b, 'refute': 0, 'confirm': 0,
                                'status': '待验证'}
                        elif v.get('status') == '待验证':
                            v['b'] = b
        # 对象绑定: 从事件结构涌现 对象→动作集 + 对象→状态集
        # (身份恒存, 第1层核心): (我,动作,obj) → 该对象的可用动作;
        # (obj, 是|变, 状态) → 该对象的候选状态。零预置, 事件槽位
        # 结构直接给出对象身份的两个维度。obj 过滤 = 只保留该对象
        # 动作+状态 都匹配的链边 (跨对象虚假边自然淘汰)。
        # 2026-08-16 对象身份统一: obj 若有身份锚, 锚成员全部并入
        # 过滤 (同一物理对象多候选名共享链; 杯查得水杯的链)。
        # 零破坏: 无锚时行为逐位不变。
        if obj is not None:
            obj_actions = set()
            obj_states = set()
            # 身份锚成员 (含自身; 无身份结构时 = {obj})
            if getattr(self, '_identity_enabled', False):
                _objs = self.identity_members(obj)
            else:
                _objs = {obj}
            for (p, a, o), cnt in self.events.items():
                if o in _objs and a not in ('是', '变', '在'):
                    obj_actions.add(a)
                if p in _objs and a in ('是', '变', '在') and o is not None:
                    obj_states.add(o)
            if obj_actions and obj_states:
                keep = {}
                keep_conf = {}
                for (c, a), b in trans.items():
                    if a not in obj_actions:
                        continue
                    if c == '__any__':
                        if b in obj_states:
                            keep[(c, a)] = b
                            keep_conf[(c, a)] = conf.get((c, a), CONF_DEFAULT)
                    elif c in obj_states and b in obj_states:
                        keep[(c, a)] = b
                        keep_conf[(c, a)] = conf.get((c, a), CONF_DEFAULT)
                trans = keep
                conf = keep_conf
            else:
                # 2026-08-17 修 3 (宏观摸底): 对象身份数据不足
                # (从未作宾语/主语, 或动作侧/状态侧单侧缺失) →
                # 诚实空链, 不泄漏全局链。此前无过滤直接返回全局链
                # → 未操作对象 (如 demo 物0) 查询拿到别的对象的链
                # (物0 链 = 泪链假象), 污染规划/记忆目标决策。
                # 同时修正 state_chain 兜底调用方 (concept_state.py
                # L1388): 任意宾语词不再被误判"有转移表"。
                trans = {}
                conf = {}
        # ── ① 只保留【真推导】边 (2026-09-19 用户拍板 先1后2 之①) ──
        # 实测: 417 条条件边中 313 条 (75%) 结果 ⊆ 前提 ⇒ 是【观察重述】不是推导,
        #       淹没真信号 (差集=1 的仅 73 条)。解释: "表大而无用"/plan 长度恒 1/
        #       strict_obj 死结 (真关系太少)。门控 DERIV_ONLY=1; 默认不筛 ⇒ 零破坏。
        _fg = os.environ.get('FACT_GRAPH') == '1'
        _do = os.environ.get('DERIV_ONLY') == '1'
        if _fg or _do:
            _drop = []
            for _k in list(trans.keys()):
                try:
                    _c, _a = _k
                except Exception:
                    continue
                _b = trans.get(_k)
                if isinstance(_b, list):
                    _keep = [x for x in _b
                             if set(str(x).split(';')) - set(str(_c).split(';'))]
                    if _fg:
                        for _x in _keep:
                            self._fact_support_add(_c, _a, _x)
                    if _keep:
                        trans[_k] = _keep
                    elif _do:
                        _drop.append(_k)
                else:
                    _delta = set(str(_b).split(';')) - set(str(_c).split(';'))
                    if _delta:
                        if _fg:
                            self._fact_support_add(_c, _a, _b)
                    elif _do:
                        _drop.append(_k)
            if _do:
                for _k in _drop:
                    trans.pop(_k, None); conf.pop(_k, None); n_tab.pop(_k, None)
        return {'trans': trans, 'conf': conf, 'inferred': inferred,
                'n': n_tab}


    def observe_transition(self, prev, act, new) -> None:
        """(甲) 转移【直供】支撑图 (2026-09-19)。

        依据: 概念空间只收到【状态断言】(observe '在' X), 转移靠 state_chain
        间接重建 ⇒ 覆盖窄 — 实测 prove_plan 0/510 次成功, 而失败样本人手
        三步即可得证 (对顶⇒; +传递⇒; +传递⇒)。本接口让【世界】把
        (prev, act, new) 显式告知 ⇒ 直接建边, 不再依赖间接重建。
        门控: FACT_GRAPH=1 (与 ② 同门控); 默认不建 ⇒ 零破坏。
        """
        if os.environ.get('FACT_GRAPH') != '1':
            return
        try:
            self._fact_support_add(prev, act, new)
        except Exception:
            pass

    def prove_plan(self, goal, known, max_depth: int = 8):
        """④ 沿支撑图求【动作序列】(2026-09-19, 用户"继续" = 接消费端)。

        从 known 出发证明 goal: 递归取"该结论的支撑边 (前提, 规则)" ⇒
        先证明其前提、再执行该规则 ⇒ 拼成【有序动作序列】= plan_state 的契约。
        只读, 不改任何表 (对齐原设计铁律"推理产物 ≠ 事实")。
        返回 (actions, depth); 不可证 → (None, None)。
        """
        try:
            # ★ 2026-09-19 修: 键必须统一为【字符串规范化】(与 _fact_support 的键同型)。
            #   原实现用 self._eqp(...) 得到 tuple ⇒ 与 string 键永不相等
            #   ⇒ fg.get(tuple) 恒 None ⇒ 递归第一步即死 (实测 0/510)。
            def _canon(f):
                f = str(f).replace(' ', '')
                if '=' in f and '(' not in f.split('=', 1)[0]:
                    _a, _b = f.split('=', 1)
                    return '='.join(sorted([_a, _b]))
                return f
            _raw = getattr(self, '_fact_support', None) or {}
            # ★ (预注册 #15) 边的新鲜度门控: 只用【近期重新观测到】的边。
            # 非平稳环境下过期边会让规划给出过期方案 (实测 MAB 漂移 -298/seed)。
            # 默认 FACT_GRAPH_WINDOW 未设 ⇒ _win=0 ⇒ 行为完全不变 (零影响)。
            try:
                _win = int(os.environ.get('FACT_GRAPH_WINDOW', '0') or 0)
            except Exception:
                _win = 0
            _tnow = self.__dict__.get('_fs_t', 0)
            _rec = self.__dict__.get('_fs_recent') or {}
            fg = {}
            for _k, _d in _raw.items():
                _ck = _canon(_k)
                for (_pre, _act) in _d.keys():
                    if _win > 0 and (_tnow - _rec.get((_k, (_pre, _act)), 0)) > _win:
                        continue
                    fg.setdefault(_ck, {})[
                        (frozenset(_canon(x) for x in _pre), _act)] = 0
            if not fg:
                return None, None
            known_c = set(_canon(x) for x in known)
            memo = {}

            def rec(_f, _seen):
                if _f in known_c:
                    return ([], 0)
                if _f in memo:
                    return memo[_f]
                if _f in _seen or len(_seen) > 64:
                    return None
                _d = fg.get(_f)
                if not _d:
                    return None
                best = None
                for (_pre, _act) in _d.keys():
                    seqs = []
                    ok = True
                    for _q in _pre:
                        _qk = _canon(_q)
                        r = rec(_qk, _seen | {_f})
                        if r is None:
                            ok = False
                            break
                        seqs.append(r)
                    if not ok:
                        continue
                    _acts = []
                    _mx = 0
                    for (_sa, _sd) in seqs:
                        _acts.extend(_sa)
                        _mx = max(_mx, _sd)
                    _acts.append(str(_act))
                    if _mx + 1 <= max_depth:
                        if best is None or len(_acts) < len(best[0]):
                            best = (_acts, _mx + 1)
                if best is not None:
                    memo[_f] = best
                return best

            _r = rec(_canon(goal), frozenset())
            # rec 的失败路径返回 None (单值) ⇒ 必须包成 (None, None) 才能解包
            return _r if _r is not None else (None, None)
        except Exception:
            return None, None

    # ── ③ 沿支撑图"往上爬" (2026-09-19, 用户"继续"): 证明深度 ──
    def prove_plan_fwd(self, goal, known, max_steps: int = 8):
        """消融实验 (2026-09-19 预注册 #5): 【前向链】从 known 出发推, 直到命中 goal。

        与 prove_plan (从 goal 倒推) 对照; 只读, 不改任何表。
        BFS over 支撑边 (前提 ⊆ 已知 ⇒ 结论可推); 返回 (actions, steps)。
        """
        try:
            def _canon(f):
                f = str(f).replace(' ', '')
                if '=' in f and '(' not in f.split('=', 1)[0]:
                    _a, _b = f.split('=', 1)
                    return '='.join(sorted([_a, _b]))
                return f
            edges = []
            for _k, _d in (getattr(self, '_fact_support', None) or {}).items():
                _ck = _canon(_k)
                for (_pre, _act) in _d.keys():
                    edges.append((frozenset(_canon(x) for x in _pre),
                                  str(_act), _ck))
            if not edges:
                return None, None
            _g = _canon(goal)
            _start = frozenset(_canon(x) for x in known)
            from collections import deque
            q = deque([(_start, [])])
            seen = {_start}
            while q:
                facts, acts = q.popleft()
                if _g in facts:
                    return acts, len(acts)
                if len(acts) >= max_steps:
                    continue
                for (pre, act, concl) in edges:
                    if concl in facts or not (pre <= facts):
                        continue
                    nf = facts | {concl}
                    if nf in seen:
                        continue
                    seen.add(nf)
                    q.append((nf, acts + [act]))
            return None, None
        except Exception:
            return None, None

    def prove_depth(self, goal, known, max_depth: int = 8):
        """从【已知事实集】出发, 沿事实支撑图求 goal 的【最小推导深度】。

        只读 — 不改任何表 (对齐原设计铁律"推理产物 ≠ 事实")。
        known  : 当前已知事实 (可迭代字符串)
        返回   : 0 = 已知; 1..max_depth = 需几步推导; None = 不可证/超深
        语义: 这是"证据互相支撑、往上爬"的深度测量 — 与动作序列无关。
        """
        try:
            def _canon(f):
                """事实规范化: 等式两边排序 (∠6=∠3 == ∠3=∠6), 去空白。
                与 geom_world._canonical_fact 同构 — 缺它则 goal 与图键永不匹配
                (2026-09-19 实测: goal=raw False / canon True ⇒ 0/10 全 None)。"""
                f = str(f).replace(' ', '')
                if '=' in f and '(' not in f.split('=', 1)[0]:
                    _a, _b = f.split('=', 1)
                    return '='.join(sorted([_a, _b]))
                return f
            known = set(_canon(x) for x in known)
            fg = {}
            for _k, _d in (getattr(self, '_fact_support', None) or {}).items():
                _ck = _canon(_k)
                for (_pre, _act), _cnt in _d.items():
                    fg.setdefault(_ck, {})[
                        (frozenset(_canon(x) for x in _pre), _act)] = _cnt
            memo = {}

            def rec(f, seen):
                if f in known:
                    return 0
                if f in memo:
                    return memo[f]
                if f in seen or len(seen) > 64:
                    return None
                d = fg.get(f)
                if not d:
                    return None
                best = None
                for (pre, _act) in d.keys():
                    ds = []
                    okd = True
                    for q in pre:
                        r = rec(q, seen | {f})
                        if r is None:
                            okd = False
                            break
                        ds.append(r)
                    if not okd:
                        continue
                    cand = 1 + (max(ds) if ds else 0)
                    if cand <= max_depth and (best is None or cand < best):
                        best = cand
                if best is not None:
                    memo[f] = best
                return best

            return rec(_canon(goal), frozenset())
        except Exception:
            return None

    @staticmethod
    def _eqp(f):
        """等式 → 规范化二元组 (∠6=∠3 == ∠3=∠6); 非等式 → None。"""
        f = str(f).replace(' ', '')
        if '=' not in f or '(' in f.split('=', 1)[0]:
            return None
        a, b = f.split('=', 1)
        return tuple(sorted([a, b]))

    @staticmethod
    def _symset(t):
        """符号集 (去分隔符后的 token) —— 域无关的结构工具 (通用智能标尺)。"""
        z = str(t)
        for _ch in '(),=;|':
            z = z.replace(_ch, ' ')
        return set(z.split())

    def _learn_prem_evid(self, act, cond_facts, concl) -> None:
        """(预注册 #11) 记录【共现证据】: 与结论共享符号的候选事实各出现多少次。

        纯计数、无域名词; 供 `_min_premise` 在 LRN1 下选出【唯一一条】理由事实。
        """
        try:
            _sy = self._symset(concl)
            if not _sy:
                return
            _ev = self.__dict__.setdefault('_prem_evid', {})
            _cc = _ev.setdefault((str(act), str(concl)), {})
            for _x in cond_facts:
                if self._symset(_x) & _sy:
                    _xs = str(_x)
                    _cc[_xs] = _cc.get(_xs, 0) + 1
        except Exception:
            pass

    def _min_premise(self, act, cond_facts, concl):
        """按规则形式抽【最小前提】(2026-09-19)。

        传递: 前提里找 a=x 与 x=b 使 a=b == concl ⇒ 只留这两条;
        其它规则 / 找不到 ⇒ 原样返回 (诚实回退, 不假装抽到了)。
        目的: 支撑边的前提应是"这一步【必需】的证据", 而不是当时状态的全部。
        """
        try:
            c = self._eqp(concl)
            if not c:
                return list(cond_facts)
            a, b = c
            # ── 一阶规则最小前提 (2026-09-19, 修 ⑤ 未触发) ──
            # 对顶/平分/等腰/同位: 条件里【参数恰为 (a,b) 的那条关系事实】
            #   就是唯一必需的前提。此前未抽 ⇒ 递归遇到 '对顶(...)'
            #   不在已知 ⇒ 证明永远失败 ⇒ ⑤ 竞争 0 次触发。
            # ★ 2026-09-19 (通用智能标尺, 预注册 #13): 【元数自适应 + 链式】—— 零域名词。
            # 目标 = 最小充分前提集 (元数 1 或 2, 保真):
            #   ① 某候选【同时】触及结论两端 ⇒ 取它 (1 条)
            #   ② x 触及 a、y 触及 b 且共享中间符号 ⇒ 取这两条 (链式, 2 条)
            #   ③ 退化: 最强单候选 / 全部条件
            if os.environ.get('FACT_PROOF_ARITY') == '1':
                _A, _B = {str(a)}, {str(b)}
                _cd2 = [x for x in cond_facts if self._symset(x) & (_A | _B)]
                _cd2.sort(key=lambda z: (-len(self._symset(z) & (_A | _B)),
                                         len(str(z)), str(z)))
                for _x in _cd2:                      # ① 单条覆盖两端
                    _s = self._symset(_x)
                    if (_s & _A) and (_s & _B):
                        return [_x]
                _pairs = [(x, self._symset(x)) for x in _cd2]
                for (_x, _sx) in _pairs:             # ② 链式 (共享中间符号)
                    if not (_sx & _A):
                        continue
                    for (_y, _sy2) in _pairs:
                        if _y is _x or not (_sy2 & _B):
                            continue
                        if (_sx & _sy2) - _A - _B:
                            return [_x, _y]
                return [_cd2[0]] if _cd2 else list(cond_facts)
            # ★ 2026-09-19 (通用智能标尺, 预注册 #11): 【学习式单前提】—— 零域名词, 分支=1。
            # 依据: prove_plan 成本 = 分支^深度; _REL 的真作用是把前提压到 1 条。
            if os.environ.get('FACT_PROOF_LRN1') == '1':
                _sy1 = self._symset(a) | self._symset(b)
                _cc1 = ((self.__dict__.get('_prem_evid') or {})
                        .get((str(act), str(concl))) or {})
                _best1, _bc1 = None, 0
                for _x in cond_facts:
                    _xs1 = str(_x)
                    if _cc1.get(_xs1, 0) > _bc1:
                        _best1, _bc1 = _x, _cc1.get(_xs1, 0)
                if _best1 is not None:
                    return [_best1]
                _cand1 = [x for x in cond_facts if self._symset(x) & _sy1]
                if _cand1:
                    _cand1.sort(key=lambda z: (len(str(z)), str(z)))
                    return [_cand1[0]]
                return list(cond_facts)
            # ★ 2026-09-19 (通用智能标尺, 预注册 #10): 【有界+排序】前提抽取 —— 零域名词。
            # 候选 = 与结论共享符号的事实; 按【共享符号数】降序取前 k 条 (默认 2)。
            # 依据 (实测): prove_plan 耗时 83% 由其【前提集大小】驱动 ——
            #   默认 _REL ≤2 条 ⇒ 17s; LRN 长尾到 7 条 ⇒ 97s; STRUCT 更大 ⇒ 5min+ 未完。
            if os.environ.get('FACT_PROOF_BND') == '1':
                try:
                    _k = int(os.environ.get('FACT_PROOF_BND_K', '2'))
                except Exception:
                    _k = 2
                def _sy(_t):
                    _z = str(_t)
                    for _ch in '(),=;|':
                        _z = _z.replace(_ch, ' ')
                    return set(_z.split())
                _cs2 = _sy(a) | _sy(b)
                _cd = []
                for _x in cond_facts:
                    _ov = len(_sy(_x) & _cs2)
                    if _ov:
                        _cd.append((-_ov, len(str(_x)), str(_x), _x))
                _cd.sort()
                _sel = [c[3] for c in _cd[:_k]]
                return _sel if _sel else list(cond_facts)
            # ★ 2026-09-19 (通用智能标尺, 预注册 #9): 【学习式】最小前提 —— 零域名词。
            # 选【观测计数最高、且被当前状态满足】的前提集 (信号 = _fact_support 的计数)。
            if os.environ.get('FACT_PROOF_LRN') == '1':
                def _c(_t):
                    _z = str(_t).replace(' ', '')
                    if '=' in _z and '(' not in _z.split('=', 1)[0]:
                        _p, _q = _z.split('=', 1)
                        return '='.join(sorted([_p, _q]))
                    return _z
                _have = set(_c(_y) for _y in cond_facts)
                _act = str(act)
                _bc = 0
                _best = None
                for _cone, _d in (getattr(self, '_fact_support', None) or {}).items():
                    if _c(_cone) != _c(concl):
                        continue
                    for (_pre, _a), _cnt in _d.items():
                        if str(_a) != _act:
                            continue
                        _pl_ = [_c(_x) for _x in _pre]
                        try:
                            _ci = int(_cnt)
                        except Exception:
                            _ci = 0
                        if _pl_ and _ci > _bc and all(x in _have for x in _pl_):
                            _best, _bc = list(_pre), _ci
                if _best:
                    return _best
                return list(cond_facts)
            # ★ 2026-09-19 (通用智能标尺, 预注册 #8): 【结构式】最小前提 —— 零域名词。
            # 判据: 只保留"与结论共享符号"的条件事实 (符号 = 去分隔符后的 token 集)。
            if os.environ.get('FACT_PROOF_STRUCT') == '1':
                def _syms(_t):
                    _z = str(_t)
                    for _ch in '(),=;|':
                        _z = _z.replace(_ch, ' ')
                    return set(_z.split())
                _cs = _syms(a) | _syms(b)
                _keep = [x for x in cond_facts if _syms(x) & _cs]
                return _keep if _keep else list(cond_facts)
            # 2026-09-19 (通用智能标尺): 关掉【域特定】前提抽取 ⇒ 只用通用兜底。
            # 动机: _REL 是几何规则名硬编码; 通用性要求机制不依赖它。默认不设 ⇒ 零影响。
            if os.environ.get('FACT_PROOF_GENERIC') == '1':
                return list(cond_facts)
            _REL = ('对顶', '平分', '等腰', '同位')
            for _x in cond_facts:
                _xs = str(_x).replace(' ', '')
                if '=' in _xs or '(' not in _xs or ')' not in _xs:
                    continue
                _head = _xs.split('(', 1)[0]
                try:
                    _args = _xs.split('(', 1)[1].rstrip(')').split(',')
                except Exception:
                    continue
                if len(_args) != 2:
                    continue
                if tuple(sorted([_args[0], _args[1]])) == (a, b) and (
                        _head in _REL or str(act).startswith(_head)):
                    return [_x]
            if str(act) != '传递':
                return list(cond_facts)
            for x in cond_facts:
                ex = self._eqp(x)
                if not ex:
                    continue
                p, q = ex
                t = q if p == a else (p if q == a else None)
                if t is None:
                    continue
                need = tuple(sorted([t, b]))
                for y in cond_facts:
                    if y != x and self._eqp(y) == need:
                        return [x, y]
        except Exception:
            pass
        return list(cond_facts)

    # ── ② 事实支撑图 (2026-09-19 用户拍板 先1后2 之②) ──
    def _fact_support_add(self, cond, act, res) -> None:
        """一条【真推导】转移 → 支撑边: 结论 ⇐ (前提事实集, 动作)。

        只收「结果 − 前提 == 恰好 1 条事实」的转移 (即一步推导);
        事实用通用切分 (split(';')) ⇒ 域无关。
        形状: _fact_support[结论][(frozenset(前提), 动作)] = 次数
        ⇒ 可查"这个结论由谁支撑"。惰性建表; 异常零破坏。
        """
        try:
            cf = [x for x in str(cond).split(';') if x]
            delta = set(str(res).split(';')) - set(cf)
            if len(delta) != 1:
                return
            concl = next(iter(delta))
            # 2026-09-19 (用户"继续"): 抽【最小前提】而不是整条条件状态。
            # 依据: 前提中位 3 条(含无关事实) ⇒ ③ 要求"全部已知" ⇒ 假阴性 9/10。
            # (预注册 #11) 学习式: 先记共现证据, 再抽最小前提
            if os.environ.get('FACT_PROOF_LRN1') == '1':
                self._learn_prem_evid(act, cf, concl)
            cf = self._min_premise(act, cf, concl)
            if not hasattr(self, '_fact_support'):
                self._fact_support = {}
            d = self._fact_support.setdefault(concl, {})
            k = (frozenset(cf), str(act))
            d[k] = d.get(k, 0) + 1
            # (预注册 #15) 边的新鲜度: 记该边最近被观测的时刻 (t 单调递增)
            try:
                _t2 = self.__dict__.get('_fs_t', 0) + 1
                self.__dict__['_fs_t'] = _t2
                _rc2 = self.__dict__.get('_fs_recent')
                if _rc2 is None:
                    _rc2 = self.__dict__['_fs_recent'] = {}
                _rc2[(concl, k)] = _t2
            except Exception:
                pass
        except Exception:
            pass

    def _modulation_extrapolate(self, raw: dict, c1: str, a: str,
                                ctx_map: dict):
        """率调制跨组合外推 (现场结构验证, 零硬编码)

        从感知层无门槛证据聚合目标组 (c1, 向=d) 的全部率分支计数;
        演示组 = 同向且拥有 ≥2 个率分支的组。调制律从演示组结构比较
        提取并验证:
          形态1: 某分支结果集多元素, 另一分支单元素且 = 多元素集
                 非主导 → "缺失率值结果 = 已学分支的非主导"
          形态2: 全部分支单元素且相同 → "率值不影响结果"
        全演示组一致且含形态1 → 律成立, 应用于目标组:
          目标组单元素 → 唯一继承 (墙/同结果, 如 左+负+快→左)
          目标组多元素 → 非主导继承 (跨界外推, 如 中左+正+快→中右)
        否则 None (诚实)。只读, 不写任何表 (保守原则同 analogize)。

        返回 (结果, conf) 或 None。conf = 结果占目标组原始计数比例。
        """
        from collections import Counter, defaultdict
        d = ctx_map.get('向')
        s = ctx_map.get('率')
        if d is None or s is None:
            return None
        # 聚合全部同向组: demo[(c1k, 率值)] -> Counter(结果)
        groups = defaultdict(Counter)
        for (a2, b2, cc), m in raw.items():
            if a2 != a or not isinstance(cc, tuple) or len(cc) != 2:
                continue
            c1k, pairs = cc
            pairs = dict(pairs)
            if pairs.get('向') != d:
                continue
            r = pairs.get('率')
            if r is None:
                continue
            n = m.get('n_acb', 0)
            if n > 0:
                groups[(c1k, r)][b2] += n
        if not groups:
            return None
        # 分支视图: c1k -> {率值: Counter}
        branches = defaultdict(dict)
        for (c1k, r), cnt in groups.items():
            branches[c1k][r] = cnt
        target = branches.get(c1, {})
        if not target:
            return None
        if s in target:
            return None  # 查询率值在目标组已有证据 → 非外推场景
        # 演示组 = 同向双率组 (分支数 >2 不参与验证); 调制律现场验证
        # (主导比较, 不依赖脆弱的单元素计数 — 真实物理里快分支常是
        # 20/80 双结果, 小样本恰好单元素是偶然):
        #   形态2: 全部分支主导相同 → 率值不影响结果 (一致)
        #   形态1: 存在分支对 (rX,rY): dom[rY] ∈ 分支rX结果集 且
        #          ≠ dom[rX] → "率值切换结果从已学分支非主导取"
        #          (判别实验: (左,正) 慢主导=左, 快主导=中左=慢的
        #          非主导; (右,负) 同构 — 组内一致, 值随组不同 =
        #          数据驱动调制内容)
        #   矛盾: 主导不同且不满足形态1 → 律失败 (诚实 None)
        mode = None  # 'inherit_non_dominant' | 全形态2 (无调制内容)
        demos = {k: v for k, v in branches.items() if len(v) >= 2}
        for _c1k, bch in demos.items():
            if len(bch) != 2:
                continue  # 非 2 率组不参与验证 (保守略过)
            dom = {r: max(cnt.items(), key=lambda kv: kv[1])[0]
                   for r, cnt in bch.items()}
            if len(set(dom.values())) == 1:
                continue  # 形态2: 率值不影响主导结果
            rX, rY = tuple(bch.keys())
            ok_form1 = False
            for r_a, r_b in ((rX, rY), (rY, rX)):
                if dom[r_b] in bch[r_a] and dom[r_b] != dom[r_a]:
                    ok_form1 = True
                    break
            if not ok_form1:
                return None  # 矛盾
            mode = 'inherit_non_dominant'
        # 应用 (目标组)
        total_cnt = sum(target.values(), Counter())
        n_tot = sum(total_cnt.values())
        if n_tot <= 0:
            return None
        if len(total_cnt) == 1:
            (u,) = tuple(total_cnt.keys())
            return (u, total_cnt[u] / n_tot)  # 唯一继承 (墙/同结果)
        if mode == 'inherit_non_dominant':
            ranked = sorted(total_cnt.items(), key=lambda kv: -kv[1])
            if len(ranked) < 2 or ranked[1][1] == ranked[0][1]:
                return None  # 平票/无次大 → 无明确非主导 → 诚实
            return (ranked[1][0], ranked[1][1] / n_tot)
        return None  # 全形态2 但目标多元素 → 无调制内容可外推 (诚实)


    def process_infer(self, obj: str, actions: List[str],
                      state: Optional[str] = None,
                      context: Optional[Sequence[Tuple[str, str]]] = None,
                      use_abstract: bool = False,
                      keep_all: bool = False
                      ) -> dict:
        """过程推演: 对象当前状态 + 动作序列 → 逐步传播 (第3层)

        每步: 当前状态 + 动作 → 查状态转移表 → 下一状态。
        这是过程计算 (时间维度不可约): 结果依赖中间步骤,
        不能一步从起点跳到终点 (查表对照研究层已证失败)。

        context: 关联对象状态对 (世界模型, 2026-08-13) —
        透传 state_chain, 复合条件边进链 (火旺时冷→加热→温)。
        None 零破坏。

        use_abstract (2026-08-18 推理基础能力): True 时对象自身
        链无路可走 → 回退抽象规则表 (跨对象共享转移, 领域无关)
        → 假设推演 (来源标注 abstract, 不写回对象链)。默认 False
        零破坏 (原逻辑一字不动)。

        Args:
            obj: 对象名 (用于过滤链边, 支持对象绑定)
            actions: 动作序列 (按时间顺序)
            state: 初始状态 (None = 未知, 诚实不确定)
            context: 关联对象状态对 (世界模型, 可选)
            use_abstract: 是否启用抽象规则回退 (默认关零破坏)

        Returns:
            {'path': [(状态, 动作, 下一状态), ...], 'final': str|None,
             'conf': float, 'known': bool, 'abstract_used': bool}
        """
        chain = self.state_chain(obj, context=context, keep_all=keep_all)
        trans, conf = chain['trans'], chain['conf']
        path = []
        cur = state
        if cur is not None and cur not in self._state_words:
            cur = None  # 非状态词 → 未知
        # 关联对象状态 (世界模型, 2026-08-13 第六步): 跨对象推演 —
        # 动作先作用于关联对象 (灯链: 灭─拨开关→亮), 对象状态变化
        # 生成事件词 (灯变亮), 事件词边 (门链: 灯变亮→开) 级联回
        # 自身。级联世界 (门→灯→开关) 的 expected 由此推出;
        # 旧世界无事件词边 → 该分支恒 None → 零破坏。
        rel_states = dict(context or [])
        min_c = 1.0
        # 链置信传播 (阶段 B, 2026-08-16): 每步转移置信乘积 —
        # 时间维度不可约的量化: 信息沿链传递指数衰减 (对齐 R6
        # 实证: 互信息随链深指数衰减)。conf(min, 最弱环节) 保持
        # 供既有消费端; chain_conf = 乘积 (链越长越不确定)。
        prod_c = 1.0
        # 抽象规则回退标记 (2026-08-18): 假设≠事实 — 用过抽象
        # 规则即标注, 消费端可据此区分 事实推演/假设推演
        abstract_used = False
        for act in actions:
            nxt = None
            c_cur = 1.0
            if cur is not None:
                nxt = trans.get((cur, act))
                c_cur = conf.get((cur, act), 1.0)
                if isinstance(nxt, list):
                    # keep_all 列表值 (nav 档级聚合): 取 conf 最高 —
                    # conf 同键也是列表 (c_cur 直接引用, 规范化一致)
                    _cs = c_cur if isinstance(c_cur, list) else [c_cur] * len(nxt)
                    _idx = max(range(len(nxt)),
                               key=lambda i: _cs[i] if i < len(_cs) else 0.5)
                    c_cur = _cs[_idx] if _idx < len(_cs) else 0.5
                    nxt = nxt[_idx]
            if nxt is None:
                # 状态已知但无条件边: 确定性单结果后备
                nxt = trans.get(('__any__', act))
                if nxt is not None:
                    c_cur = min(c_cur, conf.get(('__any__', act), CONF_DEFAULT))
            if nxt is None and use_abstract and cur is not None:
                # 抽象规则回退 (2026-08-18 推理基础能力): 对象自身链
                # 无路 → 类别规则 (对象所属类别共享) → 全局抽象规则
                # (跨对象共享转移, 领域无关) → 假设推演。
                # 来源标注 abstract (返回 abstract_used=True), 不写回
                # 对象链 (假设≠事实, analogize 保守原则同款)。
                _ar_ = self._abstract_rule_for(obj, cur, act)
                if _ar_ is not None:
                    nxt = _ar_['result']
                    # 可靠性调制折扣 (三期): 验证证据量→折扣;
                    # 刚涌现重折扣, 充分验证轻折扣 (假设非事实,
                    # 越可靠越敢用)。
                    c_cur = min(c_cur, self._abstract_confidence(
                        _ar_.get('strength', 1.0), _ar_.get('kind', 'cond'),
                        _ar_.get('consistency')))
                    abstract_used = True
            if nxt is None and rel_states:
                # 跨对象级联: 动作作用于关联对象 → 对象变 → 事件词
                # → 自身链无条件边 (与 plan_multi 级联同构)
                for ro, rs in rel_states.items():
                    if rs is None:
                        continue
                    rchain = self.state_chain(ro, context=None)['trans']
                    rnxt = rchain.get((rs, act))
                    if rnxt is None:
                        rnxt = rchain.get(('__any__', act))
                    if rnxt is not None and rnxt != rs:
                        ev = f"{ro}变{rnxt}"
                        nxt = trans.get(('__any__', ev))
                        if nxt is not None:
                            rel_states[ro] = rnxt
                            c_cur = min(c_cur, 0.5)
                            break
            if nxt is None:
                # 状态未知或无链边: 诚实返回 None (不确定)
                path.append((cur, act, None))
                return {'path': path, 'final': None,
                        'conf': min_c, 'chain_conf': round(prod_c, 4),
                        'known': False, 'abstract_used': abstract_used}
            min_c = min(min_c, c_cur)
            prod_c *= c_cur
            path.append((cur, act, nxt))
            cur = nxt
        return {'path': path, 'final': cur,
                'conf': min_c, 'chain_conf': round(prod_c, 4),
                'known': True, 'abstract_used': abstract_used}


    def plan_state(self, obj: str, goal: str,
                   current: Optional[str] = None,
                   depth: int = 5,
                   context: Optional[Sequence[Tuple[str, str]]] = None,
                   use_abstract: bool = False,
                   keep_all: bool = False
                   ) -> dict:
        """反向状态规划: 目标状态 → 动作序列 (决策环接过程计算)

        与 plan() 的区别: plan() 反查条件边 (加热→沸|冷 一步直达,
        不知道中间态); plan_state 在状态空间反向推演 (过程计算):
        从目标状态沿转移表反推前驱 (状态, 动作) 序列, 得最少步
        动作序列 (冷→沸 = [加热,加热,加热], 中间态 温/热 显式)。

        context: 关联对象状态对 (世界模型, 2026-08-13) — 透传
        state_chain: 情境已知时复合条件边进链 (火旺时才能规划
        ［加热×3］→沸; 火灭时单条件链残缺 → 诚实无解)。None
        零破坏。

        机制:
          1. 反向 BFS: state_chain 转移表 → rev[下一状态] =
             [(前驱状态, 动作, conf)]
          2. 从目标反推候选序列 (按长度升序, depth 上限)
          3. 正向验证: process_infer 跑候选 → final==goal 才接受
             ('__any__' 无条件边允许任意前驱, 反向歧义由正向验证消解)
          4. 无解 → known=False 诚实不确定 (不瞎编计划)

        三铁律: 纯查询 (不写状态不判定) — 计划只供决策层参考
        (决策层决定是否执行)。

        Args:
            obj: 对象名 (状态链按对象过滤)
            goal: 目标状态
            current: 当前状态 (None = 未知 → 只报无条件边序列或不确定)
            depth: 最大反推深度

        Returns:
            {'plan': [动作...], 'known': bool, 'conf': float,
             'reason': str}
        """
        from collections import deque
        chain = self.state_chain(obj, context=context, keep_all=keep_all)
        trans, conf = chain['trans'], chain['conf']
        n_tab = chain.get('n', {})
        rev: Dict[str, list] = defaultdict(list)
        for (c, a), b in trans.items():
            if isinstance(b, list):
                # keep_all 列表值 (nav 档级聚合): 解包每个结果
                _cs = conf.get((c, a), [])
                if not isinstance(_cs, list):
                    _cs = [CONF_DEFAULT] * len(b)
                for _b, _c in zip(b, _cs):
                    rev[_b].append((c, a, _c))
            else:
                rev[b].append((c, a, conf.get((c, a), CONF_DEFAULT)))
        # 抽象规则入反向表 (2026-08-18 推理基础能力): 对象自身链
        # 无路 → 类别规则 (对象所属类别共享) → 全局抽象规则 (领域
        # 无关) 补路径, 正向验证时同样回退 (use_abstract 透传
        # process_infer)。来源标注 abstract — 计划基于假设 (对象无
        # 自身经验), 消费端可据此区分。类别规则优先 (更精确),
        # 全局兜底。
        if use_abstract:
            for _src in ('category', 'global'):
                _hit = 0
                if _src == 'category':
                    _rules_map = self.category_rules()
                    _my = [cn for cn, members
                           in getattr(getattr(self, 'emergence', None),
                                      'categories', {}).items()
                           if obj in members]
                    for _cn in _my:
                        for (c, a), m in _rules_map.get(_cn, {}).items():
                            # 可靠性调制折扣 (三期): 验证证据量→折扣
                            rev[m['result']].append(
                                (c, a, self._abstract_confidence(
                                    m.get('strength', 1.0),
                                    m.get('kind', 'cond'))))
                            _hit += 1
                else:
                    for (c, a), m in self.abstract_rules().items():
                        rev[m['result']].append(
                            (c, a, self._abstract_confidence(
                                m.get('strength', 1.0),
                                m.get('kind', 'cond'))))
                        _hit += 1
                if _hit:
                    break  # 有类别规则就不再叠加全局 (避免同键歧义)
        # 2026-09-19 (用户拍板「先1后2」第 1 步): 目标【已达成】短路 — 事实成员语义。
        #   geom: current = 事实集合规范串 (';'.join(sorted(set(facts)))), goal = 单事实串
        #   ⇒ 下方 goal not in rev 与该函数成功返回的 final==goal 都要求【精确串相等】
        #   ⇒ "已达成"判不出 ⇒ 报"goal 不在转移表"。
        #   本刀只短路"已达成"这一半; "多步推演"留给第 2 步。
        #   按【元素成员】判定 (split(';') 精确相等), 不用子串 (防 '冷' vs '冷血' 误判);
        #   ★ `_cur != goal` 这道门保证: 单值世界 (_cur == goal) 的原路径【一字不动】。
        if current is not None and goal:
            _cur = str(current)
            if _cur != goal and goal in _cur.split(';'):
                return self._with_plan_mem(
                    {'plan': [], 'known': True, 'conf': 1.0,
                     'chain_conf': 1.0, 'path': [_cur],
                     'reason': 'goal 已达成 (事实成员)'}, obj, goal, current)
        # 2026-09-19 (用户拍板「先1后2」第 2 步): 目标【成员语义】— 反向 BFS 从
        #   "所有含目标事实的节点"推演, 而非要求 goal 本身是节点。
        #   实证: geom 失败样本 36 条中,**29 条在失败【发生时】表里就有含目标的节点**
        #   (81%, 条件位/结果位都有) ⇒ 结构性取用缺陷 (精确串相等), 非冷启动。
        #   元素成员判定 (split(';') 精确相等, 非子串 ⇒ 防 '冷' vs '冷血' 误判);
        #   ★ 单值世界: 含 goal 的节点只有 goal 本身 ⇒ _goal_nodes == [goal] ⇒ 与原来一致。
        _goal_nodes = [n for n in rev if isinstance(n, str) and goal in n.split(';')]
        if goal in rev and goal not in _goal_nodes:
            _goal_nodes.append(goal)
        if not _goal_nodes:
            # ④ 支撑图证明回退 (2026-09-19, 用户"继续" = 给 ②③ 接消费端):
            #   转移表里没有含目标的节点 ⇒ 改用【事实支撑图】证明 goal,
            #   可证 ⇒ 取出证明树的【动作序列】(= plan_state 契约)。
            #   门控 FACT_PROOF=1; 默认关 ⇒ 零破坏; 只读。
            if os.environ.get('FACT_PROOF') == '1':
                _fs = [x for x in str(current).split(';') if x] if current else []
                _pa, _pd = self.prove_plan(goal, _fs)
                if _pa:
                    return self._with_plan_mem(
                        {'plan': list(_pa), 'known': True, 'conf': 0.5,
                         'chain_conf': 0.5, 'path': [],
                         'reason': '事实支撑图证明 (深度 %d)' % (_pd or 0)},
                        obj, goal, current)
            return self._with_plan_mem(
                {'plan': [], 'known': False, 'conf': 0.0,
                 'reason': 'goal 不在转移表'}, obj, goal, current)
        # BFS 按首动作分组 (2026-08-31 第十刀): 同状态不同首动作的
        # 最短路径都保留 — 死循环修复关键: 噪声吃边 (稍远吃→有食,
        # 食物再生瞬间 1 次成功) 让 best[稍远] = [吃,...] 最短; 被
        # 拒后若无后备 (真实 [南,南,西,西]) → known False → 探索
        # 随机 (低效但活). 分组保底: 首动作去重, 每组最短, 候选
        # 按 (长度, -conf) 排序逐条验证. keep_all=False 时首候选
        # 同旧 (最短通过即返回) — 仅最短无效时多看备选 (以前直接
        # known False → 计划质量提升, 生产回归基线确定性链无此场景零影响).
        best: Dict[str, dict] = {n: {'': ([], 1.0)} for n in _goal_nodes}
        q = deque(_goal_nodes)
        while q:
            s = q.popleft()
            for _acts0, _cm0 in list(best[s].values()):
                if len(_acts0) >= depth:
                    continue
                for prev, act, c in rev.get(s, []):
                    if '变' in act:
                        # 事件词 (灯变亮): 级联输入, 不是可执行动作 —
                        # 反向 BFS 不能把事件词当动作规划 (2026-08-13
                        # 第六步: 事件词由级联消费, plan_state 只返回
                        # 真实动作; 否则级联世界的 learn_from_result 会
                        # 用事件词观察 (我,灯变亮,门) 污染事件流)
                        continue
                    new_actions = [act] + _acts0
                    new_c = min(_cm0, c)
                    key = prev if prev != '__any__' else '<any>'
                    _g = best.setdefault(key, {})
                    _rec = _g.get(new_actions[0])
                    # 同首动作同长保留 conf 高者 (2026-08-31 第十刀
                    # v5): 先到先得丢真路径 — [西,东] (坏分支 (近食,
                    # 东)→有食 0.2 噪声) 先到覆盖 [西,西] (真实 (近
                    # 食,西)→有食 0.82 强者) → 候选全断 → known 0.
                    # 同 len 比 conf: [西,西] 0.28 > [西,东] 0.2 保留.
                    # keep_all=False (生产回归基线等) 保持先到先得 → 生产回归基线锚
                    # 逐位 (2026-08-31 实测: v5 通用化致 planned
                    # 1880→1917, 限定 keep_all 后恢复).
                    if _rec is None or len(_rec[0]) > len(new_actions) \
                            or (keep_all and len(_rec[0]) == len(new_actions)
                                and new_c > _rec[1]):
                        _g[new_actions[0]] = (new_actions, new_c)
                        q.append(key)
        candidates = []
        if current is not None and current in best:
            candidates.extend(best[current].values())
        if '<any>' in best:
            candidates.extend(best['<any>'].values())
        if os.environ.get('NAV_DBG_N') and current in ('中食', '远食') and goal == '有食':
            _cs_txt = sorted(
                f"{_a[0]}={round(_c,2)}" for _a, _c in candidates)
            print(f"[C-DBG] cur={current} all_cands={_cs_txt}", flush=True)
            for _ckey in ('中食', '近食', '远食', '稍远'):
                _e = trans.get((_ckey, '西'))
                if _e is not None:
                    print(f"[T-DBG] ({_ckey},西)->{_e} conf={conf.get((_ckey,'西'))} n={n_tab.get((_ckey,'西'))}", flush=True)
        # 集合可达性验证 (2026-08-31 第九刀 v2): keep_all 概率链候选
        # 的自洽性 + 频率检查 — 逐边推演 (多结果全算), 每步至少
        # 一个结果状态能继续下一条边, 终点状态集必须含 goal, 且
        # 每条边转移 conf ≥ NAV_CHAIN_CONF_MIN (0.15). 返回路径
        # 最小 conf (不可达/断裂 → 0.0).
        # 频率门槛必要性实锤: ('稍远','吃')→有食 噪声边 (偶然 1 次
        # 成功, 22 次失手, conf≈0.04 — 食物再生瞬间状态滞后) →
        # BFS 最短路径 [吃] → 稍远连续吃 16 次直到饿死 (NAV-T 44-59
        # 铁证); 纯存在性验证放行噪声. 0.15 = 成功 1/7 以上才算
        # 有效边 — 噪声 0.04 拒绝, keep_all 低概率朝食边 (0.28)
        # 保留 (keep_all 原始动机不破). 纯链内查表零副作用.
        def _nav_chain_ok(acts, cur0, g0):
            # 首动作自环检查 (2026-08-31 第十刀): (cur0, 首动作) 的
            # 最可能结果 == cur0 → 原地踏步计划 → 拒绝. 实锤: 稍远
            # 吃失手主导 (探索吃 22 次 0 效 + 死循环 16 次) → (稍远,
            # 吃) 最可能结果=稍远 → [吃,...] 计划拒绝; 真实朝食边
            # (近食,西)→有食 0.86 非自环 → 通过. 与 conf 门槛互补:
            # 门槛拦"低概率噪声", 自环拦"高概率原地踏步" (尝试少
            # 时 conf 虚高 1/1=1.0 门槛失效 → 自环检查兜底).
            if cur0 is not None and acts:
                _r0 = trans.get((cur0, acts[0]))
                if _r0 is None:
                    _r0 = trans.get(('__any__', acts[0]))
                if _r0 is not None:
                    # 首动作样本量门槛 (2026-08-31 第十刀 v2): 条件边
                    # n < 门槛 → 拒绝. 实锤: (稍远,吃)→有食 早期是
                    # 单值边 (1 次成功 conf 1.0 — 列表边 n 门槛只拦
                    # 多结果, 单值噪声边漏网 → 死循环吃 21 次复现).
                    # 路径中间步单值边 = 统计强者 (n 大才成强者) 不
                    # 需要; det 边 key ('__any__',a) 不在 n_tab →
                    # None 放行 (确定性唯一转移可信).
                    _n0 = n_tab.get((cur0, acts[0]))
                    if _n0 is not None:
                        if isinstance(_n0, list):
                            _n0 = min(_n0) if _n0 else 0
                        if _n0 < NAV_CHAIN_MIN_N:
                            if os.environ.get('NAV_DBG_N'):
                                print(f"[N-DBG] REJ cur={cur0} act={acts[0]} n={_n0}", flush=True)
                            return 0.0
                    else:
                        # det 无条件兜底 (2026-08-31 v8): 条件边无
                        # key → det 兜底边 — 无条件泛化 = 统计盲区
                        # 产物 (吃失手=位置不变=无事件词 → 失手边
                        # 永不建, det 只有成功样本) → 样本量门槛更
                        # 严 (5). 移动边多结果不建 det → 零误伤.
                        _n_any = n_tab.get(('__any__', acts[0]))
                        if _n_any is not None and _n_any < NAV_CHAIN_MIN_N_DET:
                            if os.environ.get('NAV_DBG_N'):
                                print(f"[N-DBG] REJ-DET cur={cur0} act={acts[0]} n_any={_n_any} r0={_r0}", flush=True)
                            return 0.0
                    _rs = _r0 if isinstance(_r0, list) else [_r0]
                    _cc0 = conf.get((cur0, acts[0]), 1.0)
                    _cs0 = _cc0 if isinstance(_cc0, list) else [_cc0] * len(_rs)
                    # 自环检查 v2 (2026-08-31 第十刀 v4): 原版看最
                    # 可能结果 — (中食,西) 列表 [中食 0.74, 近食
                    # 0.28] 最可能=中食 (失手自环) → 拒 — 误杀真实
                    # 朝食分支 0.28 (keep_all 存在意义, known 0 实
                    # 锤). 改为: 非自环分支最大 conf ≥ 门槛才放行 —
                    # (稍远,吃) 噪声分支 有食 0.045 < 0.15 拒 ✓ /
                    # (中食,西) 真实分支 近食 0.28 ≥ 0.15 过 ✓ /
                    # 单值纯自环 (远食,吃)→远食 无分支 → 拒 ✓.
                    _best_non_self = max(
                        (_c for _r, _c in zip(_rs, _cs0) if _r != cur0),
                        default=0.0)
                    if _best_non_self < NAV_CHAIN_CONF_MIN:
                        return 0.0
            # 概率递推 (2026-08-31 第十刀 v6): 原集合推演 + 每步
            # max conf 取 min = 乐观存在性 (只要有一条分支链可达
            # 就放行) — 执行是概率性的 (落最可能分支) → 计划 conf
            # 虚高 (0.83 的 3 步路径实际成功 ~0.57) → planned 大增
            # 但进食未超探索时代 (并行 4 组实锤). 改为: 每步所有
            # 结果按 conf 加权扩散 (P(s') = Σ P(s)×conf(s→s')), 终
            # 点累计概率 = 计划真实期望成功率. (中食,西)→近食 0.5
            # ×(近食,西)→有食 0.5 = 0.25 过 / (稍远,吃)→有食 0.045
            # 拒 / 3 步 0.5³ 链 0.125 < 0.15 拒 (长链本来就成功率低
            # — 系统应找短高概率路径或继续探索).
            _probs = {cur0: 1.0} if cur0 is not None else {}
            for _a in acts:
                _new = {}
                for _s, _p in _probs.items():
                    _r = trans.get((_s, _a))
                    _from_det = False
                    if _r is None:
                        _r = trans.get(('__any__', _a))
                        _from_det = True
                    if _r is None:
                        continue
                    if _from_det:
                        # det 无条件兜底 (2026-08-31 v8): 同首动作
                        # 门槛 — 无条件泛化边样本量 < 5 → 该步无效.
                        _nd = n_tab.get(('__any__', _a), 1)
                        if _nd < NAV_CHAIN_MIN_N_DET:
                            continue
                    _cc = conf.get((_s, _a), 1.0)
                    if isinstance(_r, list):
                        # 样本量门槛 (2026-08-31 第十刀): 只对列表边
                        # (keep_all 多结果 = 噪声来源) 生效 — 单值边
                        # 是统计强者 (主导转移) 不需要 (det 边无 n 字
                        # 段, 若默认 1 全拒 → k14/k15 known 0 实锤).
                        # 列表边 n 同步列表 (逐结果), 取 min 保守;
                        # n < 门槛 = 早期噪声 (食物再生瞬间 1 次成功
                        # conf 虚高 1.0) → 该 (s,a) 不算有效步.
                        _nn = n_tab.get((_s, _a), 1)
                        if isinstance(_nn, list):
                            _nn = min(_nn) if _nn else 0
                        if _nn < NAV_CHAIN_MIN_N:
                            continue
                        _cs = _cc if isinstance(_cc, list) else [_cc] * len(_r)
                        for _rr, _cc2 in zip(_r, _cs):
                            _new[_rr] = _new.get(_rr, 0.0) + _p * _cc2
                    else:
                        _cc2 = _cc if isinstance(_cc, (int, float)) else 1.0
                        _new[_r] = _new.get(_r, 0.0) + _p * _cc2
                _probs = _new
                if not _probs:
                    return 0.0
            if g0:
                return sum(_p for _s, _p in _probs.items() if _s == g0)
            return max(_probs.values()) if _probs else 0.0

        candidates.sort(key=lambda x: (len(x[0]), -x[1]))
        for actions, cmin in candidates:
            if keep_all:
                # nav 档级概率链 (2026-08-31): 反向 BFS 路径 → 集合
                # 可达性验证 (第九刀): 逐边推演, 每步结果 (keep_all
                # 多结果全算) 至少一个状态能继续下一条边, 终点可达
                # goal. 拒绝断裂路径 — 实锤: ('有食','吃')→更远 副
                # 作用边反向 → 更远状态候选 [吃] → 推演 更远吃→更远
                # 卡死 (吃在非有食 26 次浪费/撞墙死循环); 确定性正
                # 向验证取每步 conf 最高 → 低概率朝食边被误判不可达
                # (近食北→有食 28% → 验证走 74% 中食 → 失败实锤) →
                # 集合验证不按概率选边, 保留 keep_all 全部结果.
                _ck = _nav_chain_ok(actions, current, goal)
                if os.environ.get('NAV_DBG_N') and current in ('中食', '远食'):
                    print(f"[K-DBG] cur={current} goal={goal} cand={actions} ck={round(_ck,3)}", flush=True)
                if _ck < NAV_CHAIN_CONF_MIN:
                    continue
                return {'plan': actions, 'known': True,
                        'conf': min(cmin, _ck),
                        'chain_conf': min(cmin, _ck),
                        'reason': 'nav 概率链可达 (keep_all)'}
            res = self.process_infer(obj, actions, state=current,
                                     context=context,
                                     use_abstract=use_abstract,
                                     keep_all=keep_all)
            if keep_all:
                # keep_all (nav) 时确定性分支整体跳过 (2026-08-31
                # 第十刀 v7): process_infer 每步取最高 conf 分支 —
                # (稍远,吃) 列表 [稍远 0.955, 有食 0.045] 取 0.955
                # (失手分支) → min_c 乐观高 → 门槛拦不住 → 死循环
                # 21 次复现 (NAV-DEC 铁证 plan=['吃','北','东'] 连续
                # 12+ 次, k18 v3 门槛失效实锤). keep_all 分支的
                # _nav_chain_ok 概率递推已完整验证 (首动作 n + 自环
                # v2 + 每步加权扩散 + 终点概率) — 确定性分支是冗余
                # 且乐观 (存在性) — 全拒后直接放弃, 不落确定分支.
                # keep_all=False (生产回归基线/其他世界) 原逻辑一字不动.
                continue
            _fin = res.get('final')
            if _fin == goal or (isinstance(_fin, str) and goal in _fin.split(';')):
                # 轨迹显式化 (阶段 B, 2026-08-16): path = 中间状态
                # 序列 (时间维度可见: 冷→温→热 不是一步跳到热);
                # chain_conf = 正向验证路径的链置信 (每步乘积)。
                st_path = [current] if current is not None else []
                st_path += [nxt for (_, _, nxt) in res.get('path', [])]
                return self._with_plan_mem(
                    {'plan': actions, 'known': True,
                     'conf': min(cmin, res.get('conf', 1.0)),
                     'chain_conf': res.get('chain_conf', 0.0),
                     'path': st_path,
                     'reason': '状态链反向推演 + 正向验证'},
                    obj, goal, current)
        return self._with_plan_mem(
            {'plan': candidates[0][0] if candidates else [],
             'known': False, 'conf': 0.0,
             'chain_conf': 0.0, 'path': [],
             'reason': ('候选未通过正向验证' if candidates
                        else '无候选')},
            obj, goal, current)


    def plan_multi(self, obj: str, goal: str,
                   current: Optional[str] = None,
                   depth: int = 6,
                   context: Optional[Sequence[Tuple[str, str]]] = None,
                   keep_all: bool = False) -> dict:
        # keep_all 透传 (2026-08-31 v8 修复): decision_symbolic 传
        # keep_all → 内部 plan_state 透传. 原签名缺参数 → fusion 等
        # context 非空世界 TypeError 崩溃 (V12 verify 捕获).
        # 默认 False 零影响 (生产回归基线/fusion 原语义).
        """联合状态规划: (自身状态, 关联对象状态...) 联合空间 BFS

        单目标 BFS 的局限 (第三步 ⑪): 主目标无解时不会规划
        子目标 — 火灭时泪=冷, plan_state 诚实无解, 系统不知道
        要先加柴。联合状态空间把 (泪,火) 当整体过程状态:

          (冷,灭) --加柴→ (冷,旺) --加热→ (温,旺) --加热→
          (热,旺) --加热→ (沸,旺)

        子目标 (火=旺) 从过程涌现 (唯一路径上自动前置), 不预置
        不分层 — 时间维度不可约的又一次体现: 规划沿联合状态
        推进, 关联对象状态变化是路径的一部分 (过程计算)。

        转移表 = 自身对象链 (context=联合状态当前关联段) + 各
        关联对象链 (加柴作用于火 → 火状态维度更新)。动态 context:
        动作改变关联对象状态后, 后续自身转移查询用新联合状态。
        context=None → 退回 plan_state (零破坏)。

        三铁律: 纯查询 (零写零判定) — 同 plan_state。

        Returns:
            {'plan': [动作...], 'known': bool, 'conf': float,
             'reason': str}
        """
        from collections import deque
        if not context:
            return self.plan_state(obj, goal, current=current,
                                   depth=depth, keep_all=keep_all)
        rel_names = [r for r, _ in context]
        n = len(rel_names)
        start = (current, *[s for _, s in context])
        # 级联静态链 (事件词边无条件, context=None 查询即可)
        # 2026-08-13 第六步: 三对象因果链 — 门链 (灯变亮)→开 是
        # DMIT 无条件边, 不依赖联合状态 context (情境压制只作用于
        # 复合条件边, 事件词边无复合条件)
        cascade_chains = [self.state_chain(o, context=None)['trans']
                          for o in ([obj] + rel_names)]
        objs = [obj] + rel_names
        q = deque([(start, [], 1.0)])
        seen = {start}
        while q:
            st, acts, cmin = q.popleft()
            if st[0] == goal:
                return {'plan': acts, 'known': True, 'conf': cmin,
                        'reason': '联合状态正向 BFS (子目标从过程涌现)'}
            if len(acts) >= depth:
                continue
            ctx_now = [(rel_names[i], st[1 + i]) for i in range(n)]
            # 自身对象转移
            chain = self.state_chain(obj, context=ctx_now)
            trans, conf = chain['trans'], chain['conf']
            for (c, a), b in trans.items():
                if '变' in a:
                    continue  # 事件词 (灯变亮): 由级联消费, 不直接执行
                # DMIT 泛化防御 (P3 ②): 自身对象不用无条件边 —
                # ('__any__','冷却')→热 是 沸+冷却→热 的泛化, 对
                # 冷是幻觉 (冷+冷却→冷 自环无事件未观察 → 泛化边
                # 给出假路径 [冷却] → 火灭冷卡死实证)。自身状态
                # 转移的精确边 (冷+加热→温) 覆盖正常推进; 关联对
                # 象 (火) 保留无条件边 (加柴→旺 跨对象泛化可靠)。
                if c == '__any__':
                    continue
                if c != st[0]:
                    continue
                ns = self._cascade_apply(st, 0, b, objs, cascade_chains)
                if ns not in seen:
                    seen.add(ns)
                    q.append((ns, acts + [a],
                              min(cmin, conf.get((c, a), CONF_DEFAULT))))
            # 关联对象转移 (改变关联对象状态 — 加柴→火旺)
            for i, r in enumerate(rel_names):
                rchain = self.state_chain(r, context=ctx_now)
                for (c, a), b in rchain['trans'].items():
                    if '变' in a:
                        continue  # 事件词: 由级联消费, 不直接执行
                    if c != '__any__' and c != st[1 + i]:
                        continue
                    ns = self._cascade_apply(st, 1 + i, b, objs,
                                             cascade_chains)
                    if ns not in seen:
                        seen.add(ns)
                        q.append((ns, acts + [a],
                                  min(cmin, conf.get((c, a),
                                                     CONF_DEFAULT))))
        return self._with_plan_mem(
            {'plan': [], 'known': False, 'conf': 0.0,
             'reason': '联合状态无路径'}, obj, goal, current)

    def _plan_memory_evidence(self, obj: str, goal: str,
                              current: Optional[str] = None):
        """规划记忆旁路 (阶段 C, 2026-08-16): 影子检索相似情境 → 历史
        后续**可执行动作**倾向。规划无解时, 相似情境 (对象/当前状态/
        目标状态命中) 的历史后续动作提供候选 — "以前也遇到过这种
        局面, 当时做了什么" (时间维度: 事件流时间序, 非词频)。

        与 _memory_evidence (deduce 联想通道) 同构, 差异: 候选 =
        后续事件的 act 字段 (可执行动作, 过滤事件词 变/是/在/有),
        供决策层直接尝试 (试错探索, RPE 修正); 检索失败/无记忆 →
        None (零破坏回退)。铁律不变: 记忆只做候选采证 (感知层带宽),
        判定在仲裁层; 不进事实边 (推理零写)。
        """
        try:
            mem = self.memory()
        except Exception:
            return None
        if mem is None or not mem.episodic:
            return None
        # 相似情境检索: 对象 + 当前状态 + 目标状态 → 影子联合命中
        hits = {}
        for w in (obj, current, goal):
            if not w:
                continue
            for r in mem.retrieve(obj=w, limit=30):
                hits[r['id']] = hits.get(r['id'], 0) + 1
            for r in mem.retrieve(act=w, limit=30):
                hits[r['id']] = hits.get(r['id'], 0) + 1
        if not hits:
            return None
        # 相似情境后紧邻的可执行动作倾向 (时间序): 命中状态断言
        # (对象在冷) 之后紧邻的动作 (我加热) — “以前遇到这种局面,
        # 当时做了什么”。取紧邻 (next-hit 重置) 防跨轮次串扰。
        follow = Counter()
        after_hit = False
        # 2026-09-19 (用户拍板 A): 按【来源】排除认知自我事件 — 用调用点显式
        #   声明的 cog 标记 (self_model.observe(..., cog=True)), 取代按词表的
        #   临时门控 (NO_COG_CAND)。理由: '探索' 在系统里有 4 个来源 (自我事件 /
        #   fusion 真世界动作 / 决策侧主动添加 / 自省投影键), 按词排除会误伤,
        #   按来源不会。认知自我事件既不作命中源, 也不作候选。
        for r in sorted(mem.episodic, key=lambda r: r['t']):
            if r.get('cog'):
                continue
            if r['id'] in hits:
                after_hit = True
            elif after_hit:
                a = r.get('act')
                if a and a not in ('变', '是', '在', '有'):
                    follow[a] += 1
                after_hit = False
        if not follow:
            return None
        sim = [r for r in mem.episodic if r['id'] in hits]
        total = float(sum(follow.values()))
        actions = [(a, round(n / total, 3))
                   for a, n in follow.most_common(3)]
        return {'similar': len(sim), 'actions': actions,
                'evidence': [{'t': e['t'], 'subj': e.get('subj'),
                              'act': e.get('act'), 'obj': e.get('obj')}
                             for e in sim[-3:]]}

    def _with_plan_mem(self, r: dict, obj: str, goal: str,
                       current: Optional[str] = None) -> dict:
        """plan_state/plan_multi 出口统一附加记忆候选 (阶段 C)。

        检索失败/无记忆 → 原样返回 (零破坏, 键集合与基线一致);
        有记忆 → 附加 memory_evidence 键 (诚实标注, 不改变 plan/
        known/conf 判定 — 状态通道过程计算不被记忆污染)。
        """
        mem = self._plan_memory_evidence(obj, goal, current=current)
        if mem:
            r['memory_evidence'] = mem
        return r

    def _cascade_apply(self, st: tuple, idx: int, s_new: str,
                       objs: list, chains: list) -> tuple:
        """事件词级联: 对象状态变化 → 事件 → 其他对象链事件边应用

        2026-08-13 第六步 (三对象因果链): 灯变亮 → 门开 — 拨开关
        应用后灯变亮, 事件 f"灯变亮" 匹配门链 (灯变亮)→开 的事件
        边 → 门开 (同一联合状态内一步到位, 不动点)。

        事件 = f"{对象}变{新状态}" (与感知层 cascade 观察编码一致)。
        零破坏: 泪/火等旧世界无事件词边 (动作词不含 '变') →
        只改 idx 位, 与原 BFS 行为一致。
        """
        st = list(st)
        st[idx] = s_new
        events = {f"{objs[idx]}变{s_new}"}
        while True:
            added = False
            for j, o in enumerate(objs):
                for (c, a), b in chains[j].items():
                    if (a in events and (c == '__any__' or c == st[j])
                            and st[j] != b):
                        st[j] = b
                        events.add(f"{o}变{b}")
                        added = True
            if not added:
                break
        return tuple(st)


    def infer_local(self, context: List[str], top_k: int = 5,
                    min_strength: float = 0.0) -> dict:
        """局部推断 (2026-09-13 落地, 实验依据 G 段 / commit 32a3219)

        下一事件预测的**推荐入口**: 与 `infer` 的三点差别
        (全部经预注册外部裁判验证, 见 knowledge/external_anchor_master_table):

        1. **只用最后一个上下文概念** (nctx=1) — 远 token 的等权票是噪声
           (Δ: −0.0177 → −0.0524, ×3)
        2. **var_bind=False** — 变量绑定在自然语言上大量误借共享部件边,
           注入噪声 (Δ: → −0.0843, 再 ×1.6)
        3. 已在 10 部 Gutenberg (原 5 + 新 5) 上 10/10 越线;
           合成 markov50 上也不退化 (Δ 最优)

        ★ 为什么是**新方法**而不是改 `infer` 默认:
        `var_bind` 是为**多步语义联想链** (`_deduce_assoc_path`) 刻意加的
        (借共享部件"举一反三", 见源码注释 缺陷4), 那是**另一个任务**。
        用"下一 token 预测"的实验去改那个任务的默认 = 张冠李戴。
        ⇒ 需要预测能力的调用方走本方法; 需要联想链的调用方仍走 `infer`
        (默认 var_bind=True 不变)。

        本方法 **不做固定 nctx=1 的硬编码以外的事** — 就是 `infer`
        配 `context[-1:]` + `var_bind=False`, 可读且可审计。

        Args:
            context: 情境概念列表 (只用最后 1 个)
            top_k: 返回前 k 个预测
            min_strength: 边强度门槛

        Returns:
            与 `infer` 同构的 dict (predictions/confidence/sources/…)
        """
        if not context:
            return {'predictions': [], 'confidence': 0.0,
                    'sources': {}, 'n_activated': 0, 'mode': 'local'}
        r = self.infer(list(context)[-1:], top_k=top_k,
                       min_strength=min_strength, var_bind=False)
        r['mode'] = 'local'
        return r

    def infer(self, context: List[str], top_k: int = 5,
              min_strength: float = 0.0, var_bind: bool = True) -> dict:
        """推断消费端: 从已知推未知 (纯查询, 执行不决策)

        给定当前情境中已出现的概念 (context), 沿原理边 (DMIT
        方向边) 加权展开预测"接下来可能发生什么"。

        推理 = 用学过的原理对没见过的情境做推断 — 上下文里
        出现的概念激活其原理后继 (方向边), 加权投票选 top-k。
        这是"从已知推未知": 系统没见过这个组合, 但原理表
        (从经历涌现) 告诉它方向。

        变量绑定 (缺陷4, 08-10): 遇到无原理边的变体概念
        (重扣/左手扣球), 借共享部件的已知概念 (扣球) 的
        原理边, 权重按部件重合度 (Jaccard) 衰减 — 举一反三:
        见过扣球→飞, 重扣 也能推出飞。情境感知: 优先借
        相同条件下的条件边 (重扣+网前 → 借 扣球→飞|网前)。

        三铁律: 纯查询, 不写状态不判定不执行 — 推断结果只供
        决策层/内分泌层参考。

        Args:
            context: 当前已激活概念列表
            top_k: 返回预测数
            min_strength: 最低边强度过滤
            var_bind: 变量绑定 (默认开, 机制级增强)

        Returns:
            {'predictions': [(概念, 强度), ...], 'confidence': float,
             'sources': {概念: 来源边数}, 'n_activated': int}
        """
        votes: Dict[str, float] = defaultdict(float)
        sources: Dict[str, int] = defaultdict(int)
        ctx_set = set(context)
        # 推理记忆缓存 (②记忆检索驱动推理, 2026-08-29): 同情境
        # 完全命中 → 直接复用缓存结论 (跳过现推 = 记忆驱动推理).
        # 默认关零破坏 (返回结构不变, from_cache 新键诚实标注来源;
        # 不命中回退现推, 与 _memory_evidence 同构).
        if getattr(self, '_infer_mem_cache', False):
            cached = self.query_inference(context, top_k=top_k)
            if cached:
                preds = [(r, m['conf']) for r, m in cached
                         if r not in ctx_set]
                if preds:
                    return {'predictions': preds,
                            'confidence': cached[0][1]['conf'],
                            'sources': {r: m['hits']
                                        for r, m in cached},
                            'n_activated': len(context),
                            'from_cache': True}
        # 已知概念 = 有原理边的概念 (变量绑定借边候选)
        known_src = set()
        if var_bind:
            for (s, t), meta in self._causal_edges_dmit.items():
                if meta.get('auto') and meta.get('strength', 1.0) \
                        >= self._cond_edge_dead:
                    known_src.add(s)
            for (s, t, c), meta in self._causal_edges_cond.items():
                if meta.get('auto') and meta.get('strength', 1.0) \
                        >= self._cond_edge_dead:
                    known_src.add(s)
        for c in context:
            if not c:
                continue
            # 条件化原理优先: 上下文含条件 C 时, 条件边 (s→t|C)
            # 是"当前情境下更精确的预测" (缺陷1: 条件交替时无条
            # 件边被稀释成两可; 条件边 lift 高+确定性高 = 该情境
            # 下的真规则)。命中条件边的源概念只投条件边 (情境压
            # 制无条件 — 否则无条件边 score 高会淹没情境预测)。
            cond_votes = 0
            for (s, t, cond), meta in self._causal_edges_cond.items():
                if s == c and cond in ctx_set \
                        and meta.get('auto') \
                        and meta.get('lift', 0) >= self._cond_min_lift:
                    votes[t] += meta.get('lift', 1.0) * meta.get('strength', 1.0)
                    sources[t] += 1
                    cond_votes += 1
            if cond_votes:
                continue  # 情境已知 → 只投条件边 (精确预测)
            for (s, t), meta in self._causal_edges_dmit.items():
                if s == c and meta.get('score', 0) > 0 \
                        and meta.get('strength', 0) >= min_strength:
                    votes[t] += abs(meta['score']) * meta['strength']
                    sources[t] += 1
            for (s, t), meta in self._causal_edges.items():
                if s == c and meta.get('strength', 0) >= min_strength:
                    # K4: 活性过滤 (granger 边证据时效)
                    votes[t] += meta.get('strength', 0) * 0.5
                    sources[t] += 1
            # 变量绑定 (缺陷4): c 无直接原理边 → 借共享部件的
            # 已知概念原理边, 权重按 Jaccard 衰减。类型门槛:
            # - c 无类型 (新词/变体, 如 重扣) 或 动作类 → 借
            # - c 已知是物体/状态 (球/网前) → 不借 (防误借:
            #   球↔扣球共享{球})
            c_types = self.types.get(c, set())
            if var_bind and c not in known_src \
                    and (not c_types or ACTION in c_types):
                self._var_bind_borrow(c, ctx_set, votes, sources,
                                      known_src)
        # 活性场注意力 (②记忆检索驱动推理, 2026-08-29): 候选按
        # 目标概念活性加权 — 活性高的概念更容易被想起 (注意力 =
        # 活性场调制; 认知语义: 提取容易度 = 激活水平). 中性点 0.5:
        # 活性 1.0 → ×1.0 满权重, 活性 0 → ×0.5 半权重. 默认关
        # 零破坏 (只改排序不改结构).
        if getattr(self, '_infer_attn', False):
            for t in list(votes.keys()):
                life = self._life_strength.get(t, 0.5)
                votes[t] *= (0.5 + 0.5 * life)
        # 排除已在上下文中的概念 (推未知, 不推已知)
        ctx_set = set(context)
        ranked = sorted(votes.items(), key=lambda x: -x[1])
        preds = [(w, v) for w, v in ranked if w not in ctx_set][:top_k]
        total = sum(v for _, v in ranked) or 1.0
        confidence = (preds[0][1] / total if preds else 0.0)
        # 缺口1 收尾 (2026-08-11): RPE 自动闭环 — 记录推断快照,
        # observe 尾部检测到状态结果事件时自动 infer_feedback
        # (纯观测记录, 不写状态不判定; 零破坏: 不影响返回值)
        if self._auto_feedback:
            self._last_infer = {
                'context': list(context),
                'result': {'predictions': list(preds),
                           'confidence': confidence},
            }
        return {'predictions': preds, 'confidence': confidence,
                'sources': dict(sources), 'n_activated': len(context)}


    def explain(self, prediction: str, context: List[str],
                top_k: int = 10) -> dict:
        """可解释 (缺陷6): 追溯预测的推理链 (纯查询, 执行不决策)

        系统回答"为什么预测 X": 重放 infer 投票逻辑, 只收集
        投给 prediction 的来源, 每条来源形成可读的推理链。

        链类型:
        - 条件边: 上下文概念 c 有边 c→prediction|cond, 且
          cond 在上下文中 (情境匹配, 缺陷1)
        - 无条件边: c→prediction (DMIT 方向边)
        - 联想边: c→prediction (共现联想, 弱)
        - 借条件边/借无条件边: 变体 c 借共享部件概念 k 的边
          (变量绑定, 缺陷4, 带类型门槛)

        每条链: {来源, 类型, 边, 权重, 置信} — 置信用
        principle_confidence (缺陷5) 标注, 系统知道自己
        依据的原理有多可靠。

        三铁律: 纯查询, 不写状态不判定不执行。

        Args:
            prediction: 要解释的预测概念
            context: 推理时的上下文概念列表

        Returns:
            {'chains': [{
                'source': 来源概念, 'type': 边类型,
                'edge': '扣球→飞|网前', 'weight': float,
                'confidence': float}],
             'total_weight': float}  (链为空 = 无边支持, 诚实)
        """
        ctx_set = set(context)
        chains = []
        total = 0.0
        # 已知概念集合 (与 infer 一致)
        known_src = set()
        for (s, t), meta in self._causal_edges_dmit.items():
            if meta.get('auto'):
                known_src.add(s)
        for (s, t, c), meta in self._causal_edges_cond.items():
            if meta.get('auto'):
                known_src.add(s)
        for c in context:
            if not c:
                continue
            # 条件边 (情境匹配)
            cond_hit = False
            for (s, t, cond), meta in self._causal_edges_cond.items():
                if s == c and t == prediction and cond in ctx_set \
                        and meta.get('auto') \
                        and meta.get('lift', 0) >= self._cond_min_lift:
                    w = meta.get('lift', 1.0) * meta.get('strength', 1.0)
                    conf = self.principle_confidence((s, t, cond))
                    chains.append({'source': c, 'type': '条件边',
                                   'edge': f"{s}→{t}|{cond}",
                                   'weight': round(w, 3),
                                   'confidence': round(conf, 3)})
                    total += w
                    cond_hit = True
            if cond_hit:
                continue  # 情境已知 → 只投条件边 (与 infer 一致)
            # 无条件边
            for (s, t), meta in self._causal_edges_dmit.items():
                if s == c and t == prediction and meta.get('score', 0) > 0:
                    w = abs(meta['score']) * meta.get('strength', 1.0)
                    conf = self.principle_confidence((s, t))
                    chains.append({'source': c, 'type': '无条件边',
                                   'edge': f"{s}→{t}",
                                   'weight': round(w, 3),
                                   'confidence': round(conf, 3)})
                    total += w
            # 联想边
            for (s, t), meta in self._causal_edges.items():
                if s == c and t == prediction \
                        and meta.get('strength', 0) >= self._cond_edge_dead:
                    # K4: 活性过滤 (granger 边证据时效)
                    w = meta.get('strength', 0) * 0.5
                    chains.append({'source': c, 'type': '联想边',
                                   'edge': f"{s}~{t}",
                                   'weight': round(w, 3),
                                   'confidence': 0.0})
                    total += w
            # 变量绑定借边 (类型门槛与 infer 一致)
            c_types = self.types.get(c, set())
            if c not in known_src \
                    and (not c_types or ACTION in c_types):
                s1 = set(c)
                if s1:
                    borrow_any = not c_types
                    for k in known_src:
                        if k == c:
                            continue
                        if not borrow_any:
                            k_types = self.types.get(k, set())
                            if not (c_types & k_types):
                                continue
                        s2 = set(k)
                        jac = (len(s1 & s2) / len(s1 | s2)
                               if (s1 | s2) else 0.0)
                        if jac < self._var_bind_min_jac:
                            continue
                        borrowed_cond = False
                        for (s, t, cond), meta in \
                                self._causal_edges_cond.items():
                            if s == k and t == prediction \
                                    and cond in ctx_set \
                                    and meta.get('auto'):
                                w = (meta.get('lift', 1.0)
                                     * meta.get('strength', 1.0)
                                     * jac * 2.0)
                                chains.append({
                                    'source': c, 'type': '借条件边',
                                    'edge': f"{c}→借{s}→{t}|{cond}",
                                    'weight': round(w, 3),
                                    'confidence': round(jac, 3)})
                                total += w
                                borrowed_cond = True
                        if borrowed_cond:
                            continue
                        for (s, t), meta in self._causal_edges_dmit.items():
                            if s == k and t == prediction \
                                    and meta.get('score', 0) > 0:
                                w = (abs(meta['score'])
                                     * meta.get('strength', 1.0) * jac)
                                chains.append({
                                    'source': c, 'type': '借无条件边',
                                    'edge': f"{c}→借{s}→{t}",
                                    'weight': round(w, 3),
                                    'confidence': round(jac, 3)})
                                total += w
        chains.sort(key=lambda x: -x['weight'])
        return {'chains': chains[:top_k],
                'total_weight': round(total, 3)}


    def _var_bind_borrow(self, c: str, ctx_set, votes, sources, known_src):
        """变量绑定借边: 变体概念 → 借共享部件已知概念的原理边

        缺陷4 (08-10): 原理表是离散词对, 变体 (重扣/左手扣球)
        无直接原理边。借边规则:
        - Jaccard 部件重合度 >= _var_bind_min_jac (默认 0.25)
        - 情境感知: 优先借 k 在相同条件下的条件边 (重扣+网前
          → 借 扣球→飞|网前, 不借 扣球→弹|界内); 借到条件边
          则不再借无条件边 (情境精确)
        - 权重 = 原边强度 × Jaccard (×2.0 条件边增益: 情境
          已知时借边更可信)

        纯查询 (执行不决策): 只写局部 votes/sources, 不碰
        任何状态。三铁律保持。
        """
        s1 = set(c)
        if not s1:
            return
        c_types = self.types.get(c, set())
        # 变体 c 若已知类型: 只借同类 (动作变体借动作)
        borrow_any = not c_types  # 未知类型新词: 可借任何
        for k in known_src:
            if k == c:
                continue
            if not borrow_any:
                k_types = self.types.get(k, set())
                if not (c_types & k_types):
                    continue  # 类型不同不借 (球≠扣球)
            s2 = set(k)
            jac = len(s1 & s2) / len(s1 | s2) if (s1 | s2) else 0.0
            if jac < self._var_bind_min_jac:
                continue
            borrowed_cond = 0
            for (s, t, cond), meta in self._causal_edges_cond.items():
                if s == k and cond in ctx_set and meta.get('auto'):
                    votes[t] += meta.get('lift', 1.0) * meta.get('strength', 1.0) \
                        * jac * 2.0
                    sources[t] += 1
                    borrowed_cond += 1
            if borrowed_cond:
                continue
            for (s, t), meta in self._causal_edges_dmit.items():
                if s == k and meta.get('score', 0) > 0:
                    votes[t] += abs(meta['score']) * meta.get('strength', 1.0) * jac
                    sources[t] += 1


    def plan(self, goal: str, top_k: int = 5,
             exclude: Tuple[str, ...] = ("我",)) -> dict:
        """反向推理 (规划): 目标 → 手段 + 前置条件 (纯查询)

        正向 infer = 情境 → 预测结果; 反向 plan = 目标 → 找
        手段 (动作) 与前置条件 (情境)。原理表反查:
        - 条件边 (A→B|C) 中 B==goal → 手段 A + 前置条件 C
          ("扣球→飞|网前" 反查 goal=飞 → 扣球, 且需要网前)
        - 无条件边 (A→B) 中 B==goal → 手段 A
        - 同手段多条件合并: 条件按 lift 降序列出 (冗余等价条件
          如 "球飞后位置必界内" → 飞/界内 都是有效条件)

        三铁律: 纯查询, 不写状态不判定 — 计划只供决策层参考
        (决策层决定是否执行)。

        Args:
            goal: 目标概念 (想要达成的结果)
            top_k: 返回计划数
            exclude: 排除作为手段的概念 (默认排除主语"我")

        Returns:
            {'plans': [(手段, [前置条件], 强度, 类型), ...],
             'goal': goal}
        """
        from collections import defaultdict
        plans: Dict[str, dict] = {}
        # 条件边反查: (A→B|C) B==goal → 手段 A, 前置条件 C
        for (a, b, c), meta in self._causal_edges_cond.items():
            if b == goal and meta.get('auto') and a not in exclude:
                p = plans.setdefault(a, {'conds': [], 'best': 0.0,
                                         'type': 'cond'})
                p['conds'].append((c, meta.get('lift', 1.0),
                                   meta.get('p_acb', 0.0)))
                p['best'] = max(p['best'], meta.get('lift', 1.0)
                                * meta.get('strength', 1.0))
        # 无条件边反查: (A→B) B==goal → 手段 A
        for (a, b), meta in self._causal_edges_dmit.items():
            if b == goal and meta.get('auto') and a not in exclude:
                p = plans.setdefault(a, {'conds': [], 'best': 0.0,
                                         'type': 'plain'})
                p['best'] = max(p['best'], abs(meta.get('score', 0))
                                * meta.get('strength', 1.0))
                if p['type'] == 'plain' and not p['conds']:
                    p['conds'].append((None, abs(meta.get('score', 0)),
                                       meta.get('strength', 1.0)))
        # 排序: 条件边优先 (确定性高), 再按强度
        ranked = sorted(plans.items(),
                        key=lambda x: (-(x[1]['type'] == 'cond'),
                                       -x[1]['best']))
        result = []
        for a, p in ranked[:top_k]:
            conds = sorted(p['conds'], key=lambda x: -x[1])[:5]
            result.append((a, [c for c, _, _ in conds],
                           p['best'], p['type']))
        return {'plans': result, 'goal': goal}
    _confidence_ref_updates = 18.0  # 参考充分验证次数


    def principle_confidence(self, edge_key) -> float:
        """单条原理边置信 0~1: 验证充分度 × 结果确定性

        edge_key: 无条件 (a, b) 或条件 (a, b, c) 元组
        纯查询 (执行不决策)。

        2026-08-11 证据时效: 活性低于死亡阈值 (长期未被 log 支持,
        只衰减未回补) → 置信 0 (证据过期; 本体保留可恢复, 与
        state_chain 的活性过滤同构)。
        """
        meta = None
        if len(edge_key) == 3:
            meta = self._causal_edges_cond.get(edge_key)
            p = meta.get('p_acb', 0.0) if meta else 0.0
        else:
            meta = self._causal_edges_dmit.get(edge_key)
            p = meta.get('p_ab', 0.0) if meta else 0.0
        if meta is None:
            return 0.0
        if meta.get('strength', 1.0) < self._cond_edge_dead:
            return 0.0  # 证据过期: 活性死亡 (本体保留可恢复)
        n_norm = min(1.0, meta.get('n_updates', 0)
                     / self._confidence_ref_updates)
        return n_norm * p
    def deduce(self, context: List[str], steps: int = 4,
               top_k: int = 1, use_abstract: bool = False) -> dict:
        """多步因果演绎 (缺陷2): 沿原理边逐步推演 (纯查询)

        infer 是单步预测 (情境→下一结果); deduce 把上一步预测
        结果加入情境再推下一步 — 时间维度上的推演:
          [我,扣球,球,网前] → 飞 → [...,飞] → 网 → [...,网]
          → 到 → ...

        use_abstract (2026-08-18 推理基础能力): 状态推演通道
        中对象自身链无路 → 回退抽象规则 (跨对象共享转移, 领域
        无关) → 假设推演。默认 False 零破坏。

        与 infer_chain (联想链: 激活扩散找动作) 不同: deduce
        的每一步由原理边驱动, 且每步附 explain 链 (缺陷6) —
        因果链, 每一步可追溯 "为什么"。

        **路由统一 (2026-08-11)**: 情境含状态词 → 状态推演通道
        (state_chain 转移表, 条件边/确定性边驱动 = 过程计算,
        时间维度不可约); 否则 → 联想通道 (DMIT 方向边, 语义
        联想)。此前 deduce 名实不符: 声称原理边驱动, 实际循环
        调 infer (联想通道)。

        防循环: 预测已在链中出现过 → 停止 (不无限推演)。

        三铁律: 纯查询 (执行不决策) — 演绎链只供决策层参考。

        Args:
            context: 初始情境概念
            steps: 最大推演步数
            top_k: 每步取预测前几名 (默认 1 = 最可能路径)
            use_abstract: 是否启用抽象规则回退 (默认关零破坏)

        Returns:
            {'chain': [{
                'step': int, 'prediction': 概念, 'weight': float,
                'confidence': float, 'explain': [链...]}],
             'context_used': [初始情境 + 逐步加入的预测]}
        """
        # 路由: 情境含状态词 → 状态推演通道 (原理边/条件边驱动)
        if any(w in self._state_words for w in context):
            r = self._deduce_state_path(context, steps, top_k,
                                        use_abstract=use_abstract)
        else:
            r = self._deduce_assoc_path(context, steps, top_k)
            # 记忆旁路 (阶段 C, 2026-08-16): 影子检索相似情境 → 历史后续
            # 倾向。联想通道符号链推不出时, 记忆提供候选 (诚实标注来源);
            # 检索失败/无记忆 → None → 零破坏回退 (输出与基线逐键一致)。
            mem = self._memory_evidence(context)
            if mem is not None:
                r['memory_evidence'] = mem
                if not r['chain'] and mem['candidates']:
                    cand, conf = mem['candidates'][0]
                    r['chain'] = [{'step': 1, 'prediction': cand,
                                   'weight': round(conf, 3),
                                   'confidence': round(conf, 3),
                                   'cum_conf': round(conf, 3),
                                   'explain': [f"记忆: 相似情境 {mem['similar']} 个, 历史后续倾向"],
                                   'memory': True}]
                    r['path'] = ([context[0], cand] if context else [cand])
                    r['chain_conf'] = round(conf, 4)
                    r['cost'] = {'steps': 1, 'chain_conf': r['chain_conf']}
                    r['truncated'] = True
        # 检索激活 (2026-08-29, 测试效应生产版): 成功消费 → 轻度复习
        # (用进废退 — 被问/被推理的知识保值)。只 touch 成功链概念 +
        # 情境锚定概念, 不写边表 (统计纯净), 冻结概念不复活。
        # 扩散激活 (2026-08-29, 实验56, Collins & Loftus 语义启动):
        # 沿正 DMIT 因果边向邻居连带保温 (空间维), 与自身检索
        # (时间维) 正交 — 双轨保值。
        if (getattr(self, 'retrieve_touch_enabled', True)
                and r is not None and r.get('chain')):
            used = [p.get('prediction') for p in r['chain']]
            used += [w for w in context if w in getattr(self,
                                                        '_life_strength', {})]
            self.retrieve_touch(used)
            if getattr(self, 'diffuse_enabled', True):
                self.diffuse_activate(used)
        return r

    # ── 扩散激活 (2026-08-29, 实验56, Collins & Loftus 语义启动) ──
    # 语义网络激活传播生产版: 查询命中概念 → 激活沿正 DMIT 因果边
    # 向邻居扩散 (强度∝边权重, 随语义距离衰减 — 一阶邻居只扩散
    # 一跳, 多跳由多轮查询累积)。物理语义 = 空间维连带保温:
    # 被用过的知识 (及其语义邻居) 一起保值 — 簇级记忆 (实验55
    # 温度梯度的传导项: 原 Fourier 负结果 = 无传导机制的结构事实,
    # 扩散激活 = 主动补传导, 梯度从纯外部账单 → 内外+邻居合力)。
    # 三铁律兼容: 只碰 _life_strength, 不写边表, 冻结不复活;
    # 只沿 score>0 因果边 (负关联 = 抑制, 不传播激活)。
    def diffuse_activate(self, concepts: List[str],
                         gain: Optional[float] = None) -> int:
        """扩散激活: 邻居 n → a_n + g·w·(1−a_n), w = 归一化正 DMIT score.

        邻居 = 与任一 concepts 有正 score 因果边 (无向: 出边+入边)
        的概念 (语义关联双向, priming 对称)。g 默认 cs.diffuse_gain
        (默认 0.15, 弱于自身检索 0.3 — 连带保温弱于直接复习)。
        返回实际扩散数。零破坏: 无因果边/无活性场 → 0。
        """
        if not getattr(self, 'diffuse_enabled', True):
            return 0
        g = gain if gain is not None else getattr(self, 'diffuse_gain',
                                                  0.15)
        _ls = getattr(self, '_life_strength', None)
        if not _ls:
            return 0
        _frz = getattr(self, '_frozen', {}) if hasattr(self, '_frozen')\
            else {}
        _dmit = getattr(self, '_causal_edges_dmit', {}) or {}
        if not _dmit:
            return 0
        n = 0
        for c in concepts:
            if c is None or c not in _ls:
                continue
            for (s, t), meta in _dmit.items():
                sc = meta.get('score', 0)
                if sc <= 0 or not meta.get('auto', True):
                    continue
                nb = None
                if s == c:
                    nb = t
                elif t == c:
                    nb = s
                if nb is None or nb in _frz or nb not in _ls:
                    continue
                w = min(1.0, abs(sc) / 0.5)  # 0.5 封顶归一
                h = _ls[nb]
                _ls[nb] = min(1.0, h + g * w * (1.0 - h))
                n += 1
        return n

    # ── 检索激活 (2026-08-29, 测试效应生产版) ──
    # 用进废退: 被成功消费 (推理/问答得出结果) 的概念轻度恢复活性
    # (部分复习, 弱于观察回满 a=1.0)。物理语义 = 内部负熵源 (自
    # 我复习), 补实验55 定论的纯被动耗散 (温度梯度只由外部观察流
    # 维持) → 引入微弱自维持: 查询过的知识保值, 不用的照常遗忘。
    # 三铁律兼容: 只碰 _life_strength (生命周期场), 不写边表
    # (观察验证统计纯净), 冻结概念不复活 (复活仍由观察驱动)。
    def retrieve_touch(self, concepts: List[str], gain: Optional[float]
                       = None) -> int:
        """检索激活: 概念 a → a + g·(1−a) (部分恢复, 观察回满的弱化版).

        g 默认 cs.retrieve_gain (默认 0.3, 深度遗忘恢复 30% 差距)。
        gain 收敛性质: 重复检索 n 次后 1−a → (1−g)^n (指数逼近 1.0),
        与衰减指数对偶 — 检索频率 vs 遗忘速率的拉锯 = 稳态活性
        决定方程 (实验55 场景2 的检索版)。返回实际 touch 数。
        """
        if not getattr(self, 'retrieve_touch_enabled', True):
            return 0
        g = gain if gain is not None else getattr(self, 'retrieve_gain',
                                                  0.3)
        _ls = getattr(self, '_life_strength', None)
        if not _ls:
            return 0
        _frz = getattr(self, '_frozen', {}) if hasattr(self, '_frozen')\
            else {}
        n = 0
        for c in concepts:
            if c is None or c in _frz or c not in _ls:
                continue
            h = _ls[c]
            _ls[c] = min(1.0, h + g * (1.0 - h))
            n += 1
        return n

    # ── 主动复习调度 (2026-08-29, 实验59 序列位置效应反哺) ──
    # 系统原只有被动重点 (观察流频率映射 + 消费驱动检索) → 实验59
    # 定论: 首因 = 主动重点 × 方向性 (偏向性复述才产生 U 形, 均匀
    # 复述只是平线); 生产缺"主动复习调度" (何时复习) — 有限复习
    # 模型只调制"复习多少" (幅度, 观察驱动), 本调度器决定"何时
    # 复习" (周期扫描濒危概念 → 冻结前自动复习)。
    # 语义: 零信息损失保障层 — 冻结 = 资源约束下的最后手段, 调度器
    # 尽量推迟 (自组织间隔复习: 复述范围 = 主动重点范围 实验59 H4)。
    # 三铁律兼容: 只碰 _life_strength (经 retrieve_touch), 不写边表,
    # 冻结不复活。默认关 (rehearse_enabled=False) → 零操作零影响。
    def rehearse_scan(self) -> int:
        """主动复习调度: 扫描活跃概念, 剩余寿命 ≤ rehearse_window 的
        最濒危 rehearse_budget 个 → retrieve_touch (冻结前复习)。

        剩余寿命 ttl = ln(θ/a)/ln(d) (当前活性 a 衰减到 θ 的步数)。
        复习窗口 = 临界前最优化时点 (活性低但未冻 → 信息损失风险
        最小; 间隔效应: 复习越晚增益越大, 但不能晚于冻结)。
        返回实际复习概念数。默认关 → 0。
        """
        if not getattr(self, 'rehearse_enabled', False):
            return 0
        _ls = getattr(self, '_life_strength', None)
        if not _ls:
            return 0
        import math as _m
        _frz = getattr(self, '_frozen', {})
        _hl = max(1, getattr(self, 'life_half_life', 425))
        ln_d = _m.log(0.5) / _hl  # ln(d), d=0.5^(1/hl)
        theta = max(1e-6, getattr(self, 'life_theta', 0.05))
        win = max(1, getattr(self, 'rehearse_window', 500))
        budget = max(1, getattr(self, 'rehearse_budget', 3))
        cands = []
        for c, a in _ls.items():
            if c in _frz or not (0.0 < a < 1.0):
                continue
            ttl = _m.log(theta / a) / ln_d
            if ttl <= win:
                cands.append((ttl, c))
        if not cands:
            return 0
        cands.sort()  # 最濒危 (ttl 最小) 优先
        n = 0
        for _ttl, c in cands[:budget]:
            self.retrieve_touch([c])
            n += 1
        return n

    # ── 推理记忆 (2026-08-29, 推理→记忆反补: 推理结果沉淀) ──
    # 推理本身纯查询 (三铁律: 执行不决策不写状态) → 沉淀发生在
    # 推理成功后: record_inference 记录 (情境, 结果) → 同情境再推理
    # query_inference 命中复用 → hits≥2 且高置信 → 固化为概念边
    # (推理内化: 从每次现推到直接知道). 零破坏: 记录/查询叠加,
    # 不碰 deduce/infer 返回值.

    def record_inference(self, context: List[str], result: str,
                         confidence: float, step: Optional[int] = None,
                         solidify: bool = True) -> bool:
        """记录一次推理成功 (情境→结果, 置信度).

        纯增量记忆: 键 = (情境元组, 结果), 值累计 hits/conf/last.
        固化: hits ≥2 且 conf ≥0.6 → 写概念边 (情境首概念→结果,
        强度=conf) — 推理内化 = 概念边 (下次直接 infer 命中).
        零破坏: 无结果/无情境 → False (静默拒绝); 固化失败不阻塞
        记录 (try/except).
        """
        try:
            if not result or not context:
                return False
            key = (tuple(context), result)
            mem = self._inference_mem.get(key)
            if mem is None:
                mem = {'hits': 0, 'conf': 0.0, 'last': 0}
            mem['hits'] += 1
            mem['conf'] = (mem['conf'] * (mem['hits'] - 1) + confidence) \
                / mem['hits']
            mem['last'] = step if step is not None \
                else getattr(self, '_inference_mem_step', 0)
            self._inference_mem[key] = mem
            self._inference_mem_step += 1
            # 固化: 多次命中 + 高置信 → 概念边 (推理内化)
            if solidify and mem['hits'] >= 2 and mem['conf'] >= 0.6:
                self._solidify_inference(context, result, mem['conf'])
            return True
        except Exception:
            return False

    def _solidify_inference(self, context: List[str], result: str,
                            conf: float) -> bool:
        """推理固化: (情境首概念→结果) 写概念边 (推理内化).

        只写已有的概念 (边两端必须已存在于概念空间 — 零概念空间
        写入纪律); 强度 = 置信度 × 0.8 (推理边略低于观察边);
        幂等 (已存在边只加强度, 不覆盖).
        """
        try:
            src = context[0]
            if src not in self.types or result not in self.types:
                return False
            key = (src, result)
            old = self._causal_edges.get(key)
            if old is None:
                self._causal_edges[key] = {
                    'strength': round(conf * 0.8, 3),
                    'inferred': True, 'hits': 1}
            else:
                old['strength'] = round(
                    max(old.get('strength', 0.0), conf * 0.8), 3)
                old['inferred'] = True
                old['hits'] = old.get('hits', 0) + 1
            return True
        except Exception:
            return False

    def query_inference(self, context: List[str],
                        top_k: int = 3) -> List[tuple]:
        """检索推理记忆: 同情境命中 → 复用 (推理缓存).

        返回 [(结果, {hits, conf, last}), ...] 按 conf×hits 排序.
        零破坏: 无命中 → [] (回退现推).
        """
        try:
            ctx = tuple(context)
            cands = []
            for (c, r), mem in self._inference_mem.items():
                if c == ctx:
                    cands.append((r, mem))
            cands.sort(key=lambda x: -x[1]['conf'] * x[1]['hits'])
            return cands[:top_k]
        except Exception:
            return []

    def inference_mem_stats(self) -> dict:
        """推理记忆统计 (审计/探针可读, 纯查询)."""
        return {'n_mem': len(self._inference_mem),
                'n_step': self._inference_mem_step,
                'solidified': sum(1 for m in self._inference_mem.values()
                                  if m['hits'] >= 2 and m['conf'] >= 0.6)}

    # ── 推理失败反馈记忆 (③反补, 2026-08-29: 缺口→定向探索) ──
    # 深推失败 (plan_state 无解/低置信) = 知识缺口: 从当前状态到
    # 目标的知识不足. record_gap 标记 (对象, 目标) → 探索时
    # query_gap 命中 → 定向探索 (优先选有已知预测结果的动作, 用
    # 想象指导探索补缺口). 零破坏: 默认空 dict, 纯增量, 不碰
    # deduce/infer/plan_state 返回值.

    def record_gap(self, obj: str, goal: str,
                   step: Optional[int] = None) -> bool:
        """标记知识缺口 (深推失败: 对象→目标推不出路).

        零破坏: 无目标 → False (静默拒绝); 幂等累计 fails.
        """
        try:
            if not goal or not obj:
                return False
            key = (obj, goal)
            g = self._gap_mem.get(key)
            if g is None:
                g = {'fails': 0, 'last': 0}
            g['fails'] += 1
            g['last'] = step if step is not None \
                else getattr(self, '_inference_mem_step', 0)
            # 缺口复活 (2026-08-29, 主动认知环): 新失败 = 旧解决
            # 结论不再成立 → 重新待办 (审计保留 fails 累计)。
            g.pop('resolved', None)
            self._gap_mem[key] = g
            return True
        except Exception:
            return False

    def query_gap(self, obj: str) -> List[tuple]:
        """检索对象的知识缺口 → [(goal, fails), ...] 按 fails 降序.

        已解决缺口 (resolved 标注, 主动认知环 2026-08-29) 过滤:
        推理成功 = 缺口不再是待办 (定向探索/巡检不再指向它),
        审计保留 (fails 累计不删)。零破坏: 无缺口 → []。
        """
        try:
            cands = [(g, m['fails']) for (o, g), m in self._gap_mem.items()
                     if o == obj and not m.get('resolved')]
            cands.sort(key=lambda x: -x[1])
            return cands
        except Exception:
            return []

    def gap_stats(self) -> dict:
        """缺口统计 (审计/探针可读, 纯查询)."""
        return {'n_gap': len(self._gap_mem),
                'n_fails': sum(m['fails']
                               for m in self._gap_mem.values())}

    def _memory_evidence(self, context: List[str]):
        """记忆旁路 (阶段 C, 2026-08-16): 影子检索相似情境 → 历史后续倾向

        记忆参与推理 = 符号链推不出时, 相似情境的历史时间序列提供
        候选 (相似情境下, 历史上接下来发生了什么)。时间维度:
        后续倾向来自事件流时间序 (先发生→后发生), 非词频乱序。

        铁律: 记忆只做候选采证 (感知层带宽), 判定在仲裁层; 来源
        诚实标注 (memory 标记); 检索失败/无记忆 → None (零破坏回退)。
        """
        try:
            mem = self.memory()
        except Exception:
            return None
        if mem is None or not mem.episodic:
            return None
        # 1. 相似情境检索: context 词 → 影子联合命中 (对象/动作双索引)
        hits = {}
        for w in context:
            if not w:
                continue
            for r in mem.retrieve(obj=w, limit=30):
                hits[r['id']] = hits.get(r['id'], 0) + 1
            for r in mem.retrieve(act=w, limit=30):
                hits[r['id']] = hits.get(r['id'], 0) + 1
        if not hits:
            return None
        # 2. 相似事件按时间序; 一遍扫描找每个相似事件后最近的同主体
        #    后续 (谁在相似情境下, 接下来发生了什么 = 时间维度证据)。
        #    实现 O(n log n): 不逐相似事件全表扫描 (大世界会平方爆炸)。
        sim_ids = set(hits)
        follow = Counter()
        last = {}          # subj -> 最近事件 id
        for r in sorted(mem.episodic, key=lambda r: r['t']):
            s = r.get('subj')
            prev = last.get(s)
            if prev is not None and prev in sim_ids:
                k = r.get('obj') or r.get('act')
                if k:
                    follow[k] += 1
            last[s] = r['id']
        if not follow:
            return None
        sim = [r for r in mem.episodic if r['id'] in sim_ids]
        total = float(sum(follow.values()))
        cands = [(c, round(n / total, 3))
                 for c, n in follow.most_common(3)]
        return {'similar': len(sim),
                'candidates': cands,
                'evidence': [{'t': e['t'], 'subj': e.get('subj'),
                              'act': e.get('act'), 'obj': e.get('obj')}
                             for e in sim[-3:]]}


    def _deduce_assoc_path(self, context: List[str], steps: int,
                           top_k: int) -> dict:
        """联想通道: 循环单步 infer (DMIT 方向边, 语义联想)

        原 deduce 实现 (无状态词情境): 扣球→飞→网→到。
        用于排球等无状态维度世界; 每步附 explain (联想链)。
        """
        ctx = list(context)
        chain = []
        seen = set()
        # 链置信传播 (阶段 B, 2026-08-16): 联想通道每步 conf 乘积 —
        # 语义跳跃链的信息传递也随时间指数衰减 (与状态通道同构)。
        prod_c = 1.0
        for step in range(1, steps + 1):
            r = self.infer(ctx, top_k=top_k)
            if not r['predictions']:
                break
            pred, w = r['predictions'][0]
            ex = self.explain(pred, ctx)
            conf = r['confidence']
            prod_c *= conf
            chain.append({'step': step, 'prediction': pred,
                          'weight': round(w, 3),
                          'confidence': round(conf, 3),
                          'cum_conf': round(prod_c, 3),
                          'explain': ex['chains']})
            if pred in seen or pred in ctx:
                break  # 防循环: 已推演过或已在情境
            seen.add(pred)
            ctx.append(pred)
        chain_conf = round(prod_c, 4) if chain else 0.0
        return {'chain': chain, 'context_used': ctx,
                'path': ([context[0]] + [s['prediction'] for s in chain]
                         if chain else list(context)),
                'chain_conf': chain_conf,
                'cost': {'steps': len(chain), 'chain_conf': chain_conf},
                'truncated': len(chain) < steps}


    def _deduce_state_path(self, context: List[str], steps: int,
                           top_k: int, use_abstract: bool = False) -> dict:
        """状态推演通道: 情境中对象+当前状态 → 沿状态转移表逐步推演

        过程计算 (时间维度不可约): 每步 = 当前状态 + 情境动作
        → 查 state_chain 转移表 → 下一状态; 结果依赖中间步骤,
        不能一步从起点跳到终点 (查表对照研究层已证失败)。

        对象 = 情境中非状态词且 state_chain 有转移表的词;
        当前状态 = 情境中第一个状态词;
        每步: 当前状态 + 情境动作 (取置信最高转移) → 下一状态。
        无转移可推 → 停止 (诚实不确定, 不瞎猜)。

        输出格式与联想通道一致 (chain 每步附 explain), 兼容
        既有消费端。
        """
        ctx = list(context)
        # 找对象: 情境中非状态词且在 state_chain 有转移表的词
        # (2026-08-11 修复: 动作词 "加热/扣球" 从未在宾语位出现,
        # state_chain 对其返回未过滤全表 → 被误认为对象, 情境动作
        # 集错位 → 起步探测失败 → 错误回退联想。对象身份 = 事件
        # 结构中出现在宾语位的词, 优先找真对象, 兜底再找任意
        # 有转移表的词。)
        obj = None
        chain = None
        for w in ctx:
            if w in self._state_words or w == "我":
                continue
            if not any(o == w for (p, a, o) in self.events):
                continue  # 从未作宾语 = 动作/属性词, 不是对象
            ch = self.state_chain(w)
            if ch['trans']:
                obj, chain = w, ch
                break
            # 抽象规则回退 (2026-08-18 推理基础能力): 对象有身份
            # (作过宾语) 但自身零转移经验 → 抽象规则可当链 (假设
            # 起步: 新对象没见过加热, 但见过其他对象加热 → 假设
            # 它也可加热 — 领域无关规则)。链仍为空, 由每步回退
            # 提供转移; 找对象条件放宽为 自身链 或 抽象表非空。
            if use_abstract and self.abstract_rules():
                obj, chain = w, ch
                break
        if obj is None:
            # 兜底: 无宾语位词有转移表 → 退回任意有转移表的词
            for w in ctx:
                if w in self._state_words or w == "我":
                    continue
                ch = self.state_chain(w)
                if ch['trans']:
                    obj, chain = w, ch
                    break
                if use_abstract and self.abstract_rules():
                    obj, chain = w, ch
                    break
        if obj is None:
            # 有状态词但找不到有转移表的对象 → 回退联想 (诚实)
            return self._deduce_assoc_path(context, steps, top_k)
        trans, conf = chain['trans'], chain['conf']
        # 抽象规则回退 (2026-08-18): use_abstract 时对象自身链无路
        # → 类别规则 (对象所属类别) → 跨对象共享转移 (领域无关规则)
        # 补路径; 来源标注 abstract (assumed=True), 不写回对象链
        # (假设≠事实)。
        _ar = self.abstract_rules() if use_abstract else {}
        # 当前状态: 情境中第一个状态词
        cur = next((w for w in ctx if w in self._state_words), None)
        if cur is None:
            return {'chain': [], 'context_used': ctx}
        # 情境动作: 非状态词、非对象、非"我"
        acts = [w for w in ctx
                if w not in self._state_words and w != obj and w != "我"]
        # 起步探测: 当前状态+情境动作必须有实际转移才走状态通道;
        # 否则回退联想 (排球世界位置词 "网前/界内" 也被"在"事件灌入
        # 状态词集, 但无推演路径 — 名实不符的伪状态, 不阻塞联想演绎)
        # use_abstract 时抽象规则也算实际转移 (新对象假设起步)
        if not any((cur, a) in trans or ('__any__', a) in trans
                   or (use_abstract and self._abstract_rule_for(obj, cur, a))
                   for a in acts):
            return self._deduce_assoc_path(context, steps, top_k)
        out, seen = [], set()
        start = cur
        # 链置信传播 (阶段 B, 2026-08-16): 每步转移置信乘积累积 —
        # 时间维度不可约的量化 (信息沿链指数衰减, 对齐 R6 实证);
        # 每步 cum_conf = 走到该步的累积置信 (单调不增)。
        prod_c = 1.0
        for step in range(1, steps + 1):
            nxt, c_best, act_used = None, 0.0, None
            assumed = False
            for a in acts:
                r = trans.get((cur, a))
                if r is not None:
                    c = conf.get((cur, a), CONF_COND_DEFAULT)
                    if c > c_best:
                        nxt, c_best, act_used = r, c, a
            if nxt is None and use_abstract:
                # 抽象规则回退: 对象自身链无路 → 类别规则 (对象所属
                # 类别共享, 更精确) → 全局抽象规则 (领域无关, 假设
                # 推演)。来源标注 abstract: explain type 改 '抽象推演'
                # (假设≠事实)。
                for a in acts:
                    m = self._abstract_rule_for(obj, cur, a)
                    if m is not None:
                        c = self._abstract_confidence(
                            m.get('strength', 1.0), m.get('kind', 'cond'))
                        if c > c_best:
                            nxt, c_best, act_used = m['result'], c, a
                            assumed = True
            if nxt is None:
                break  # 当前状态+情境动作无转移 → 停止 (诚实)
            prod_c *= c_best
            out.append({'step': step, 'prediction': nxt,
                        'weight': round(c_best, 3),
                        'confidence': round(c_best, 3),
                        'cum_conf': round(prod_c, 3),
                        'assumed': assumed,
                        'explain': [{'source': cur,
                                     'type': '抽象推演' if assumed
                                              else '状态推演',
                                     'edge': f"{cur}+{act_used}→{nxt}",
                                     'weight': round(c_best, 3),
                                     'confidence': round(c_best, 3)}]})
            if nxt in seen or nxt in ctx:
                break  # 防循环: 已推演过或已在情境
            seen.add(nxt)
            ctx.append(nxt)
            cur = nxt
        chain_conf = round(prod_c, 4) if out else 0.0
        return {'chain': out, 'context_used': ctx,
                'path': [start] + [s['prediction'] for s in out],
                'chain_conf': chain_conf,
                'cost': {'steps': len(out), 'chain_conf': chain_conf},
                'truncated': len(out) < steps}


    def analogize(self, obj: str, src_obj: str,
                  min_shared: int = 1) -> dict:
        """结构映射类比: 源域→目标域结构补全 (Gentner 1983)

        科学假说 (Gentner 结构映射理论): 类比 = 源域→目标域的
        结构对齐, 关系结构 (因果转移) 的映射优先于表面特征;
        结构对齐后, 目标域缺失的关系可从源域推断补全.

        步骤:
          1. 结构对齐: obj 与 src_obj 共享的转移边
             (同 (状态,动作)→结果)
          2. 结构差异: src_obj 有、obj 没有的转移边
          3. 推断补全: 差异边起点状态已在 obj 中出现 (状态对齐)
             → 推断 obj 也可能有该转移 (analogy 证据, 保守)

        保守原则 (三铁律/零破坏):
          - 类比推断是**假设**不是事实: 不写回 _state_cond_edges,
            state_chain/plan_state/process_infer 完全不受影响
            (事实查询仍诚实 known=False)
          - 只补全共享结构延伸: 差异边起点必须状态对齐
          - 不推断反向 (只沿因果方向补全)

        Args:
            obj: 目标域对象 (待补全)
            src_obj: 源域对象 (结构完整的域)
            min_shared: 触发类比所需最少共享边 (默认 1)

        Returns:
            {'shared': [(状态,动作,结果)...],
             'inferred': [(状态,动作,结果)...],
             'source': 'analogy', 'known': bool}
        """
        o_trans = self.state_chain(obj)['trans']
        s_trans = self.state_chain(src_obj)['trans']
        shared = [(c, a, b) for (c, a), b in o_trans.items()
                  if s_trans.get((c, a)) == b]
        if len(shared) < min_shared:
            return {'shared': shared, 'inferred': [],
                    'source': 'analogy', 'known': False}
        # 目标域出现的所有状态 (起点 + 结果)
        o_states = {c for (c, a) in o_trans}
        o_states |= {b for (c, a), b in o_trans.items()}
        # 源域有、目标域没有的转移边
        inferred = [(c, a, b) for (c, a), b in s_trans.items()
                    if (c, a) not in o_trans and c in o_states]
        return {'shared': shared, 'inferred': inferred,
                'source': 'analogy', 'known': bool(inferred)}


    def infer_feedback(self, observed_members, infer_result,
                       hit_reward: float = 0.3,
                       miss_boost: float = 0.1,
                       miss_dopamine: float = 4.0) -> dict:
        """推断反馈闭环: 命中 → 内啡肽(搞懂了), 落空 → 多巴胺+好奇心

        后续 observe 的事件成员若命中之前 infer 的预测 → 内啡肽
        满足 (搞懂了, 原理验证); 落空 → 双通道内分泌:
          - 探索欲推高 (好奇, 原理还不完整, 继续采样)
          - 多巴胺注资 (预期违背 = 新颖 = 学习时刻: 未预测到的
            成员按 RPE 调制注资, 能量累积超阈值 → 迸发 → 调用方
            学习这个意外 — MES 失败路径=知识: 预测失败的时刻
            正是学习的时刻)
        这就是"修好奇心"的机制形态: 推断对错直接调制内分泌,
        驱动系统继续学习 (用户战略: 修内啡肽/多巴胺=修好奇心)。

        三铁律: 反馈是内分泌观测 (感知), 不代行决策; 决策仍由
        决策层做。多巴胺注资只操作能量池 (动机信号), 不创建
        概念不写状态 — 概念创建由感知层自然完成。

        Returns:
            {'hit': bool, 'hit_concept': str|None,
             'endorphin_gain': float, 'explore_gain': float,
             'dopamine_gain': float, 'n_dopamine_bursts': int}
        """
        if not infer_result or not infer_result.get('predictions'):
            return {'hit': False, 'hit_concept': None,
                    'endorphin_gain': 0.0, 'explore_gain': 0.0,
                    'dopamine_gain': 0.0, 'n_dopamine_bursts': 0}
        preds = [w for w, _ in infer_result['predictions']]
        hit_concept = next((m for m in observed_members if m in preds),
                           None)
        if hit_concept:
            # 2026-08-25 修复: 命中奖励走同一内啡肽代谢通道 (先衰减再
            # 累积)。旧实现直加无衰减 → satisfaction 无上限累积 →
            # death_scan/cooldown_scan 豁免永久成立 (搞懂的永不判死)
            # → 概念只进不出 → 长跑概念数线性增长 → 步成本 O(N) 平方
            # 级变慢 (融合 20000 步 1507 概念 8.25h 实锤)。修复后语义:
            # 持续命中 → 浓度保持 (豁免); 停止命中 ~1000 步代谢归零
            # → 过气概念可回收 (概念生命周期闭环)。
            self.reward_satisfaction(hit_concept, amount=hit_reward)
            self._n_infer_hits += 1
            return {'hit': True, 'hit_concept': hit_concept,
                    'endorphin_gain': hit_reward, 'explore_gain': 0.0,
                    'dopamine_gain': 0.0, 'n_dopamine_bursts': 0}
        # 落空 → 双通道内分泌: 探索欲 (好奇继续学) + 多巴胺
        # (预期违背注资, RPE 调制: 越少见越意外 → 越多奖励)
        self.explore_drive = min(1.0, self.explore_drive + miss_boost)
        self._n_infer_misses += 1
        dopamine_gain = 0.0
        n_bursts = 0
        # 未预测到的成员 = 意外 = 新颖 → 多巴胺注资
        # (RPE 语义与原 reward_rpe 一致 (已删 2026-08-26): 1 − P(成员), 高频预期内
        #  成员不奖励 = 噪声拦截; 罕见意外 = 满额奖励)
        from collections import Counter
        freq = Counter()
        for ev in self._principle_log[-self._principle_batch_size * 2:]:
            freq.update(ev)
        total = max(sum(freq.values()), 1)
        for m in observed_members:
            if not m or m in preds:
                continue
            p = freq.get(m, 0) / total
            rpe = max(0.0, 1.0 - p)
            if rpe <= 0.05:
                continue  # 高频预期内成员不奖励 (噪声拦截)
            gain = miss_dopamine * rpe
            self._burst_energy[m] += gain
            dopamine_gain += gain
            if self._burst_energy[m] >= self.burst_threshold:
                self._burst_energy[m] *= self.burst_fatigue
                self.log_burst(m, self._burst_energy[m],
                               self.burst_threshold, fired_nbrs=0)
                n_bursts += 1
                # ★ 265 裁决A (2026-09-23): 迸发→创建消费半环 (08-26 删除件的消费侧重建,
                #   RPE 判定版; 与探针唯一差异: 单部件词不 compose, 防自环 part-of 边)
                if getattr(self, 'burst_create_enabled', True):
                    _parts = [c for c in str(m).split('·') if c and c != str(m)]
                    if _parts:
                        try:
                            self.compose(m, _parts, 1.0)
                        except Exception:
                            pass
        self._n_dopamine_bursts += n_bursts
        return {'hit': False, 'hit_concept': None,
                'endorphin_gain': 0.0, 'explore_gain': miss_boost,
                'dopamine_gain': round(dopamine_gain, 4),
                'n_dopamine_bursts': n_bursts}


    def principle_stats(self) -> dict:
        """元认知可读: 原理表状态 (纯查询)"""
        auto_edges = {k: v for k, v in self._causal_edges_dmit.items()
                      if v.get('auto')}
        return {'auto_edges': len(auto_edges),
                'cond_edges': len(self._causal_edges_cond),
                'total_dmit_edges': len(self._causal_edges_dmit),
                'granger_edges': len(self._causal_edges),
                'infer_hits': self._n_infer_hits,
                'infer_misses': self._n_infer_misses,
                'explore_drive': self.explore_drive,
                'dopamine_bursts': self._n_dopamine_bursts,
                'principle_events': len(self._principle_log)}
