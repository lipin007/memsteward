#!/usr/bin/env python3
"""
core/concept_principle.py — ConceptSpace principle 子模块 (mixin)

S3 拆分 (2026-08-11 施工, 用户拍板 P2①): ConceptSpace 单文件 3656 行
→ 5 子模块 mixin (ontology/phase/principle/state/space), 保持
`from core.concept_space import ConceptSpace` 重导出兼容。

零机制变更: 方法体一字未改, 仅按 C1 14 区块边界归位。
"""
from collections import defaultdict, Counter
from types import SimpleNamespace as _SN
from typing import List, Dict, Tuple, Optional
import numpy as np

# 概念类型 (自动涌现的类别)
PERSON, ACTION, OBJECT, EMOTION = "人物", "动作", "物体", "情感"

# 感知层统计阈值 (质询点 7 命名化, 默认值一字不改):
GRANGER_F_THRESHOLD = 3.84   # granger_test F 统计阈值 (≈p<0.05)
DET_RESULT_MIN_P = 0.9       # 确定性单结果边概率门槛 (p_det≥0.9 且唯一)
DET_DOMINANCE_TH = 0.7       # 2026-08-24 漂移适应: 窗口主导结果门槛
                              # (argmax 比例 ≥0.7 即建 det 边 — 漂移边界
                              # 混合窗口里旧结果残留 → len(bcnt)>1 伪多结
                              # 果, 原单结果约束让新边永不建, E4 漂移奖励
                              # ns 实锤; 主导门槛让边跟随近期主导结果重定向)
DMIT_MIN_SCORE = 0.05        # DMIT 方向边最小分数门槛 (E12 命名化, 不调值)

# 推理验证回灌 (阶段 A, 2026-08-16): 外推预测对验证阈值
# 证伪 1 次即禁 (宁缺毋滥: 错误推理比不给答案危害大, 行为会基于
# 它执行); 证实 2 次标已验证 (证据累积才升级, 与代谢死阈值同构,
# 非统计调参 — 这是仲裁层可靠性的最小证据量判定)。
VERDICT_REFUTE_LIMIT = 1      # 证伪阈值 → '不可靠' (禁外推)
VERDICT_CONFIRM_LIMIT = 2     # 证实阈值 → '已验证' (稳定可用)


class ConceptSpacePrincipleMixin:
    def social_learn(self, c1: str, a: str, b: str,
                     speaker: Optional[str] = None,
                     speaker_s: Optional[float] = None) -> bool:
        """社会学习: 外部 (另一智能体) 因果知识经仲裁显式采纳.

        ③ 第三版 (2026-08-27): B hear A 的规则句 → 仲裁层解析出
        因果三元组 (c1,a,b) → 显式调用本方法写入 B 自己的因果知识.
        语言是传播通道 (不引入新机制): 知识落点 = 现有状态链边表
        (_state_cond_edges 单条件边表, 连续世界感知边同表同格式 —
        2026-08-27 V11 修复落点: 原 edges2 复合条件表只在 context
        已知时被 state_chain 消费, 连续世界无 context → 社会知识
        不可达) — 社会学习 = 感知学习的加速器 (B 不用自己碰巧
        执行 冷+远离 才学得到).

        门控 (候选由仲裁层显式消费, 非自动驱动):
          1. 概念门控: c1/a/b ∈ 自己的概念空间 — 共享指称 (同一
             世界涌现的概念才可锚定), 不创建概念 (未知词不建)
          2. 相反强边门控 (三表全貌, 2026-08-27 V11 修复): 已有
             (c1,a)→b' 且 b'≠b 且 strength ≥ 1.0 (自己实证的强
             因果优先于社会传闻) → 拒绝。感知边可能落在三个边表
             任一 (复合条件 _state_cond_edges2 / 单条件
             _state_cond_edges / 确定性无条件 _state_det_edges)
             — 原实现只查 edges2 → 感知边在单条件表时门控失效 →
             社会传闻覆盖自己实证 (实锤: A 感知 (冷,远离)→冷
             strength 1.0 在单条件表, B 表达 (冷,远离)→温 不被
             拒绝)。
          3. 社会冲突仲裁 (2026-08-27 V12): 已有相反 social 边
             (a,b',c1) 来自 speaker1 (信任 t1) vs 新 speaker2
             (信任 t2) — t2 > t1 → 覆盖 (高可信说话者胜);
             t2 ≤ t1 → 拒绝 (保留先到/高可信, 防震荡)。信任 =
             执行验证学来的 (非预置, 初始 0): B 验证社会边为真
             → +1.0, 证伪 → -1.0 (见 _state_cond_scan 证伪段)。
          4. 低初始置信: strength=0.5 (低于自己涌现边的 1.0) —
             待 B 自己验证: 后续真实执行 (c1,a)→b 触发现有回补
             机制 strength+1.0 (confirm), 无证据 → 衰减死亡
             (_cond_edge_dead=0.3, 残留不维持活性)
        返回 True (采纳) / False (拒绝).
        """
        _acm = __import__('os').environ.get('SOC_ACCEPT_MODE', '')   # ★ 接收策略 (默认 '' = 现状)
        if c1 not in self.types or a not in self.types \
                or b not in self.types:
            if _acm == 'verify':
                # ★ ② 语义 (2026-09-21): "先认识、再收假设" —— 认识这个词不等于信它,
                #   由**证伪**去决定对错 (edhe 无证据会衰减死亡 ✓)
                try:
                    for _t in (c1, a, b):
                        try:
                            self.types.add(_t)
                        except Exception:
                            pass
                    self._soc_new_concepts = getattr(self, '_soc_new_concepts', 0) + 1
                except Exception:
                    pass
            else:
                return False
        # ★ 2026-09-21: **接收策略** gated 变体 (SOC_ACCEPT_MODE; 默认 '' = 现状 ⇒ 零影响 ✓)
        #   ''       = 现状: 相反强边 (strength>=1.0) **硬拒** ✓
        #   'verify' = ② 验证驱动: **不硬拒** ⇒ 落为**低置信假设** (方法尾部写 0.5 ✓) 待自己执行证伪 ✓
        #   'trust'  = ① 信任权重: 仅当**说话者信任 >= 1.0** 时放行相反边 ✓ (初始信任 0 ⇒ 需先攒 ✓)
        _tr = float((getattr(self, '_speaker_trust', {}) or {}).get(speaker or '', 0.0))
        # ★ §287 (2026-09-26, gated 'scred' 模式): 可信度货币 = 说话人懂度 (归一化 s)
        #   仅当 SOC_ACCEPT_MODE='scred' 且调用方传 speaker_s 时生效; 默认路径逐位不变。
        #   _sn = s/(1+|s|) ∈ (−1,1) ⇒ 跨代理可比 (各自资金史不同 ⇒ 归一化后可比)
        if _acm == 'scred' and speaker_s is not None:
            _sv = float(speaker_s)
            _tr = _tr + (_sv / (1.0 + abs(_sv)))

        def _pass_gate() -> bool:
            if _acm == 'verify':
                return True
            if _acm in ('trust', 'scred') and _tr >= 1.0:
                return True
            return False

        for (aa, bb, cc), m in self._state_cond_edges2.items():
            c0 = cc[0] if isinstance(cc, tuple) else cc
            if aa == a and c0 == c1 and bb != b \
                    and m.get('strength', 0.0) >= 1.0:
                if not _pass_gate():
                    return False   # 相反强边 → 拒绝 (★ 策略可放行 ✓)
        for (aa, bb, c0), m in self._state_cond_edges.items():
            if aa == a and c0 == c1 and bb != b \
                    and m.get('strength', 0.0) >= 1.0:
                if not _pass_gate():
                    return False
        for (aa, bb), m in self._state_det_edges.items():
            if aa == a and bb != b \
                    and m.get('strength', 0.0) >= 1.0:
                if not _pass_gate():
                    return False
        # 相同键保护 (2026-08-27 V11): 自己实证的相同边不降级 —
        # 社会传闻与实证一致 → 无操作 (原实现直接覆盖 strength
        # 1.0→0.5 降级自己实证)
        # 落点表 = 单条件边表 _state_cond_edges (2026-08-27 V11
        # 修复): 社会边键 (a,b,c1) 与连续世界感知边同表同格式 —
        # 原落点 edges2 (复合条件表) 只在 context 已知时被
        # state_chain 消费, 连续世界无 context → 复合段永不执行
        # → 社会知识不可达 (V11b 实锤: 采纳 2 条但状态链无新边)。
        key = (a, b, c1)
        old = self._state_cond_edges.get(key)
        # 世界模型隔离 (2026-09-18): 他世界旧边在本世界视作不存在
        if old is not None and old.get('world') is not None \
                and old.get('world') != getattr(self, '_current_world', None):
            old = None
        if old is not None and not old.get('social') \
                and old.get('strength', 0.0) >= 1.0:
            return True
        # 门控③: 相反社会边冲突 — 按说话者信任仲裁 (信任从执行
        # 验证中学: 真 +1.0 / 证伪 -1.0, 初始 0)
        _st = getattr(self, '_speaker_trust', {})
        t_new = _tr if speaker else -1.0   # ★ §287: 有效信任 (scred 含懂度货币; 其余模式 = 原值逐位)
        for (aa, bb, cc), m in list(self._state_cond_edges.items()):
            if aa == a and cc == c1 and bb != b and m.get('social'):
                # 世界模型隔离 (2026-09-18): 仲裁只在本世界内进行
                if m.get('world') is not None \
                        and m.get('world') != getattr(self, '_current_world',
                                                     None):
                    continue
                t_old = _st.get(m.get('speaker'), 0.0) \
                    if m.get('speaker') else 0.0
                if t_new <= t_old:
                    return False   # 保留先到/高可信
                del self._state_cond_edges[(aa, bb, cc)]  # 高可信覆盖
                break
        self._state_cond_edges[key] = {
            'lift': 1.0, 'strength': 0.5, 'n_updates': 1,
            'p_acb': 1.0, 'p_ab': 1.0,
            'auto': True, 'social': True,
            'speaker': speaker,
            'world': getattr(self, '_current_world', None),
        }
        return True

    def learn_causal(self, series_map: Dict[str, List[float]],
                     lag: int = 2, threshold: float = GRANGER_F_THRESHOLD,
                     min_total: float = 3.0,
                     min_len: int = 12) -> dict:
        """感知级因果测量: 从概念时间序列提取有向因果边

        推理涌现 (R1 实验证实): 事件流时间顺序承载因果信息 —
        同一语料语言看到词, 推理看到因果链。本方法把测量结果
        写入概念空间 (纯感知统计, 不判定 — 三铁律: 感知不判定)。

        Args:
            series_map: {概念名: 时间序列} (每点=一个时间桶的计数增量)
            lag: Granger 滞后阶数
            threshold: F 统计阈值 (3.84 ≈ p<0.05)
            min_total: 概念总活动量下限 (防冷启动稀疏噪声)
            min_len: 序列最小长度 (granger 需 lag+10)

        Returns:
            {'learned': n, 'checked': n_pairs, 'edges': [(src,tgt,f,direction)]}
        """
        if not self.causal_learning_enabled:
            return {'learned': 0, 'checked': 0, 'edges': [],
                    'disabled': True}
        from .reasoning import granger_test  # 单一真源
        names = [k for k, v in series_map.items()
                 if len(v) >= max(min_len, lag + 10)
                 and sum(abs(x) for x in v) >= min_total]
        learned, checked, edges = 0, 0, []
        for i in range(len(names)):
            for j in range(len(names)):
                if i == j:
                    continue
                checked += 1
                g = granger_test(series_map[names[i]], series_map[names[j]],
                                 lag=lag)
                if g['is_causal'] and g['f_stat_xy'] > threshold:
                    f = g['f_stat_xy']
                    key = (names[i], names[j])
                    if key in self._causal_edges:
                        old = self._causal_edges[key]
                        self._causal_edges[key] = {
                            'f_stat': max(f, old['f_stat']),
                            'strength': old['strength'] + 1.0,
                            'n_updates': old['n_updates'] + 1,
                        }
                    else:
                        self._causal_edges[key] = {
                            'f_stat': f,
                            'strength': 1.0,
                            'n_updates': 1,
                        }
                    learned += 1
                    edges.append((names[i], names[j], f, g['direction']))
        return {'learned': learned, 'checked': checked,
                'edges': edges[:50]}


    # (归档 2026-08-16: learn_causal_dmit → _archive_legacy/dead_interfaces_20260816.py)

    # ══ 候选③ 原理消费端 (2026-08-10): 从已知推未知 ════════
    # 用户战略定调: 推理的源头是原理, 通过学习原理来推理 = 因果。
    # 链路: 经历(observe) → 原理涌现(自动建边) → 推断消费(infer)
    #       → 反馈闭环(命中=搞懂了→内啡肽, 落空=好奇→继续采样)
    # 三铁律: 建边=感知统计(不判定), infer=纯查询(不写状态),
    # 反馈=内分泌观测(不代行决策) — 决策仍由决策层自己做。
    # 不依赖特定语料: 任何事件流都能涌现方向结构 (从源头修机制)。


    def _principle_ingest(self, members, max_window: Optional[int] = None):
        """原理自动涌现: observe 事件 → 增量转移计数 → DMIT 精化

        每事件 O(1): 成员写日志 + 相邻事件转移计数 (A→B)。
        每 _principle_batch_size 事件: 从转移计数选 top 候选对,
        用最近窗口构建对齐序列跑 DMIT (延迟互信息方向性) 精化,
        方向边增量写入 _causal_edges_dmit。

        转移计数 = 廉价在线筛选 (谁跟着谁出现); DMIT = 严格
        方向判据 (防稀疏爆炸, R2 已验证)。两者互补: 候选少而准。
        原理表 = 纯统计涌现, 不写规则不判定; 任何事件流都能
        涌现方向结构 (不依赖特定语料)。

        三铁律: 感知不判定 — 建边是统计测量 (观测), 判定只在一处
        (Metacognition.adjudicate)。
        """
        if not self.causal_learning_enabled:
            return
        self._n_feed_calls = getattr(self, '_n_feed_calls', 0) + 1
        if max_window is None:
            max_window = self._principle_log_window
        members = [m for m in members if m]
        self._principle_log.append(members)
        self._principle_log = self._principle_log[-max_window:]
        # 增量转移计数: 上一事件成员 → 本事件成员 (相邻共现方向)
        if self._principle_prev:
            for a in self._principle_prev:
                for b in members:
                    if a != b:
                        self._principle_transitions[(a, b)] += 1
                        # 缺口1 在线: 状态结果增量 (O(1))
                        # b ∈ 状态词 (在线涌现集) → a→b 是动作→状态转移
                        # _action_state_results[a] 供在线分歧检测 (每事件
                        # 刷新, 不依赖批量条件边 — 研究 v1 教训)
                        # 第五刀: 词面 ∪ 结构状态词 (感知锚点无词面)
                        if (b in self._state_words_online
                                or b in getattr(self, '_struct_state_words', set())):
                            self._action_state_results.setdefault(
                                a, set()).add(b)
        # 在线 det 反证 (2026-08-24 漂移适应 A 通道加速): 变事件结果
        # ≠ 既有 det 边结果 → 立即 ×0.85 衰减 (不等 sweep 批量 ~65 步
        # 延迟 — 漂移后第一次拉错即降权, MAB 确定性世界 8 次反证
        # 0.85^8 < 0.3 死透 ≈24 步)。sweep det 独立衰减段已删 (在线
        # 替代, 防双倍衰减)。稳态世界 (生产回归基线/eco): 确定性动作结果恒定
        # → 无(少)反证 → 零(微)影响; 多结果动作 det 边不建 (唯一性
        # 破坏置 0) → 无对象。A 场景天然保护: 无变事件 (无效动作/无
        # 证据) 不进本段。回补平衡: sweep 建边段窗口内真转移 +1.0,
        # 稳态支持 > 反证 → 不误杀。
        # 🩸 零破坏铁律 (2026-08-24 二分实测): 本段是漂移在线信号 —
        # behavior_loop 冷却/drop 用它门控 (eco/生产回归基线稳态无反证 → 冷
        # 却/drop 不触发 → 逐位一致, 887/886/675 vs 908/436/199 实
        # 锤)。本段自身不衰减非漂移边: 稳态世界确定性动作结果恒定。
        if ('变' in members and self._principle_prev
                and self._state_det_edges):
            _res = next((w for w in members
                         if w in self._state_words_online
                         or w in getattr(self, '_struct_state_words',
                                         set())), None)
            if _res is not None:
                for _a in self._principle_prev:
                    for (da, db), _m in list(self._state_det_edges.items()):
                        # 🩸 轮换漂移免疫 (2026-08-24 批跑实测): 无条件
                        # 反证在轮换漂移 (每 100 拉杆最优臂轮换) 触发 →
                        # 落空期衰减旧边, 得分期重建 → 循环波动 → 退化
                        # (seed 888 rot −15 → −81 实锤)。门控: 反证只对
                        # 曾差集/收缩检测过的动作 (真漂移) 生效 — 轮换
                        # 结果周期性回好 → 窗口恒混合 → 检测不触发 →
                        # 反证零触发 → 均匀探索保持 (正确行为); 永久漂
                        # 移首批 sweep 标后反证生效 (延迟 ~1 批可接受)。
                        if (da == _a and db != _res
                                and _m.get('strength', 1.0) > 0.0
                                and (_a in getattr(self, '_drift_acts', set())
                                     or _a in getattr(
                                         self, '_drift_ever', set()))):
                            _m['strength'] = max(
                                0.0, _m.get('strength', 1.0)
                                * self._cond_edge_decay)
                            # 漂移在线信号 (2026-08-24): 该动作的 det
                            # 边被反证 = 环境规则变了 → 记录最近反证
                            # 步。消费端: behavior_loop 冷却/drop 门控
                            # (只对漂移动作生效 → eco/生产回归基线零破坏)。
                            # 🩸 先读后写坑 (2026-08-24 永久漂移实验实锤):
                            # self._online_drift[_a]=... 属性不存在时抛
                            # AttributeError (被 mab_world try/except 吞 →
                            # 静默空转, det 衰减了但信号没记录)。安全创建。
                            _od = getattr(self, '_online_drift', None)
                            if _od is None:
                                _od = {}
                                self._online_drift = _od
                            _od[_a] = self._n_feed_calls
        # _principle_prev 更新放反证段之后 (2026-08-24 永久漂移实验
        # 修复): 反证段读旧值 (上次动作事件 members) — 若先更新则读到
        # 本次结果事件 (变/状态词, 无动作) → da 永不匹配 → 反证空转
        # (perm drift 生产 online={} 实锤, det (拉1,得分) 4.0 恒定)。
        self._principle_prev = members
        self._principle_pending += 1
        if self._principle_pending >= self._principle_batch_size:
            self._principle_pending = 0
            self._principle_batch()


    def _slot_structures(self):
        """槽位结构涌现: 动作词集 + 状态词集 (零预置)

        从事件 (person, action, obj) 的三元槽位涌现:
          - 状态谓词 = 变/是/在 (对象状态表达, 语言接口层)
          - 状态词集 = 状态谓词的宾语 (对象经历的状态: 冷/温/热/沸)
          - 动作词集 = 非状态谓词 action 槽 (我执行的动作: 加热/推/拉)

        这是事件编码语法本身的结构, 不是预置规则 — 系统从自己
        看到的事件里知道"哪些词是对象的状态、哪些词是动作"。
        三铁律: 槽位统计=感知观测, 不写规则不判定。
        """
        state_preds = ('变', '是', '在')
        actions = set()
        states = set()
        for (p, a, o), cnt in self.events.items():
            if a not in state_preds:
                actions.add(a)
            elif o is not None:
                states.add(o)
        # K5 修复 (2026-08-12): 在线轨并入批量轨 — 状态词单真源
        # 双轨分裂: 在线轨 _state_words_online (每事件 O(1) 增量涌现,
        # 驱动分歧检测/RPE 闭环) vs 批量轨 _state_words (本函数全量重算,
        # 驱动状态链)。批量重算只从 events 计数重建, 会覆盖在线已见
        # 但尚未计入 events 的状态词 → 同一概念两套记忆, 结构不统一
        # (审计 K5 🟡 低)。修法: 批量轨 = 批量全量 ∪ 在线已见 (合并
        # 而非覆盖, 在线增量永不丢; 零行为变更, 仅消除分裂)。
        online_seen = getattr(self, '_state_words_online', set())
        states |= online_seen
        # T5/107 修复 (2026-08-14): 状态词集剔除一词多义词 — 对象词
        # 首现于动作宾语位 (角色=对象) 被第五刀误收进 _struct_state_words,
        # 随后变事件主语位暴露其非状态身份 (角色=对象+人物) → 若保留
        # 则假转移对 (加热,泪) 淹没真链 (107 世界 0 边)。状态词身份 =
        # 专用宾语位 (角色多样性 ≤1, 第五刀语义) — 这里是最终防线:
        # 无论 online/struct 如何残留, 输出时剔除多义词。真状态词
        # (冷/温/热/沸/强/弱) 恒为专用宾语位 → 不受影响。零破坏:
        # 原第五刀就是剔除多义词, 此过滤只是把时机从注册改为输出。
        roles = getattr(self, '_sense_roles', {})
        states = {w for w in states if len(roles.get(w, set())) <= 1}
        # 动作词 = 我执行的动作 (排除 变/是/在 已在上面)
        self._action_words = {a for a in actions if a != '我'}
        self._state_words = states


    def _state_cond_scan(self, a: str, b: str, log, cnt: int,  # 半成品: cnt 参数未用 (标注勿删)
                         recent: bool = True):
        """状态条件扫描: 动作→结果|状态 (认知结构本体化)

        与 _principle_cond_scan 同构 (lift = P(B|A,C)/P(B|A) 调制
        测量), 但两个关键差异 (研究层已验证):
          1. 不依赖 DMIT 前置 — 对全量 (动作→状态) 转移对直接扫,
             多结果因果 (加热→温/热/沸) 不再被门槛淘汰
          2. 候选条件只用状态词集 — 排除对象名/动作名/主语噪声,
             真条件共同特征: 条件都是状态词 (研究层 14 条全真)

        写入独立 _state_cond_edges (与 _causal_edges_cond 共存,
        新增不覆盖, 默认零破坏)。三铁律: 统计测量=感知, 不判定。

        T5 修复 (2026-08-14): 条件上下文回看从紧邻 1 步扩展为
        最近状态断言 — 真实感知流里方向事件 (火,升) 插在状态断言
        与状态转移之间, 紧邻回看被方向词占位 → 条件候选丢失 →
        中间链 (加热,温,冷)/(加热,热,温) 建不出, 状态链只有
        冷→沸 一跳。条件语义 = 转移发生前的对象状态 (最近断言),
        与中间插了多少方向/动作条目无关。
        """
        from collections import defaultdict
        n = len(log)
        if n < 20:
            return
        # 相反社会边证伪 (2026-08-27 V12): 本 scan(a,b) 的 recent 含
        # 真实 (a,c)→b — 全表 social 边 (a,b',c) 预测 b'≠b → 被证伪
        # → 说话者信用受损 (信任从执行验证中学)。挂在真实转移处理
        # 上 (数据驱动: 看到真结果才淘汰错误预测), 不依赖被预测
        # 结果/条件出现在候选循环里 (V12b 实锤: B 轨迹无靠近+冷
        # 组合 → 候选 c 循环不处理 → 检测挂循环内触发不到)。
        # refuted 标记防重复扣分。
        if isinstance(recent, set):
            for (_aa, _bb, _cc), _m in list(
                    self._state_cond_edges.items()):
                if _m.get('social') and not _m.get('refuted') \
                        and _aa == a:
                    _c0 = _cc[0] if isinstance(_cc, tuple) else _cc
                    for (_ra, _rc, _rb) in recent:
                        if _ra == a and _rc == _c0 and _rb != _bb:
                            _spk = _m.get('speaker')
                            if _spk:
                                _st = getattr(self, '_speaker_trust', {})
                                _st[_spk] = _st.get(_spk, 0.0) - 1.0
                            _m['refuted'] = True
                            break
        states = self._state_words
        # 2026-08-26 提速 (6G 反哺, cProfile 实测 fusion 60% 热点):
        # 原两遍全量遍历 — 第二遍 per-c 重复 _recent_state_word 回看
        # (最多 500 步) + 窗口前看, 与第一遍逐位置重复 → 每批多扫
        # n×回看 次。现第一遍顺带记录特征数组 (evs[i] = 对齐变事件 /
        # rsws[i] = 最近状态词), 第二遍 O(1) 回读。计数逐位一致
        # (同调用同参数, 仅消除重复计算)。
        evs = [None] * n
        rsws = [None] * n
        a_pos = []  # 2026-08-26 提速: a 命中位置索引 — 第二遍只遍历
        # 命中位置 (原全 n 重复判断 a not in cur → len(a_pos) 10-20× 小)
        # 无条件基线: P(B|A)
        n_a = 0
        n_ab = 0
        cand_counts = defaultdict(int)
        for i in range(n - 1):
            cur = log[i]
            if a not in cur:
                continue
            a_pos.append(i)
            n_a += 1
            # 转移只认变事件 (结果变化); 状态断言/动作条目不产生转移
            # (无效动作后 '是 旧状态' 断言若计入 → 假转移 → 基线虚高
            #  → lift 稀释 → 真条件边被挡)
            # 2026-08-20 同对象对齐: 多对象世界动作后紧邻变事件是
            # 其他对象 (eco: 草先发) → 前看窗口找含宾语 obj 的变
            # 事件 (与 sweep got 同构); 生产回归基线单对象紧邻即命中逐位不变。
            # 2026-08-22 宾语位修复: 取最后一个候选 = 动作宾语
            # (demo 第三人称主语 tom/heat/water 原取到主语 tom →
            # 变事件 water/变/hot 不含 tom → 转移丢失, 条件边 0
            # 实锤)。生产回归基线 (我,加热,火) 末位=火 / eco 同构不变。
            # 谓词位排除 (2026-08-22): 生产回归基线 observe_action 带 context,
            # 复合扫描把 (火,在,旺) 成员并入事件 → 事件形如
            # (我,加热,火,火,在,旺) → reversed 原会选中 '在' (谓词非
            # 状态词) → 宾语位取错 (生产回归基线 954/0/0 实锤); 排除谓词后
            # 旺(状态词)→在(谓词)→火 ✓。demo (tom,heat,water) 无谓词
            # reversed 取 water ✓ 不变。
            # ★ §184/§185 (gated · **默认关** ⇒ 关闸逐位不变): 非自我事件 (生态谓词
            # 生/死/共现, 主语 = 兔/狼) 的**主体位**必须进对象检测 —— 原实现只扫
            # `cur[1:]` (契约: 0 号位恒 '我'), 而非自我事件主语在 0 号位 ⇒ `_obj=None`
            # ⇒ 对象过滤**被静默关闭** ⇒ 前看窗口抓到**别的对象**的状态词当结果
            # (实锤 §184: 适配层写的坐标词 `题4·变·量63·命中` 被当成 `兔·生·新生`
            # 的结果 ⇒ KB 感知层 9 条「命中」违例)。开闸后 = "跨主体归因禁止"
            # (与既有"跨动作归因禁止"同族); 对 `我` 事件逐位不变 (0 号位被 `!= '我'` 滤掉)。
            _scope = cur if getattr(self, '_cond_subj_scope', False) else cur[1:]
            _obj = next((w for w in _scope
                         if w != '我' and w not in states
                         and w not in self._action_words
                         and w not in ('变', '是', '在')), None)
            _ev = None
            for _k in range(i + 1, min(n, i + 1 + self._cond_align_window)):
                _e = log[_k]
                if any(w in self._action_words for w in _e):
                    if '我' in _e:
                        break  # 跨动作归因禁止 (2026-08-20): 窗口内
                        # 再遇动作事件 (主语'我') 即停 — 生产回归基线密集动作
                        # 无效动作后窗口内的后续变是下一动作的效果。
                        # 生/死/捕食事件含动作词 (槽位: 非状态谓词)
                        # 但主语是对象非'我' → 不是动作 → 不中断前看
                        # (eco 恢复个体事件后验证)
                if '变' not in _e:
                    continue
                if _obj is not None and _obj not in _e:
                    continue
                _ev = _e
                break
            evs[i] = _ev
            if _ev is not None and b in _ev:
                n_ab += 1
            # 候选条件: 只取状态词 (身份结构过滤) — 从最近状态断言
            # 回看 (跳过方向/动作条目; 转移发生前的对象状态)
            cw = self._recent_state_word(log, i, states, {a})
            rsws[i] = cw
            if cw:
                cand_counts[cw] += 1
        if n_a < self._state_cond_min_support:
            return
        p_ab = n_ab / n_a
        # 状态链门槛: 绝对计数 (真转移事件) — 比例门槛对连续流
        # 场景是错的 (动作每回合一次, 跨桶几十回合一次 → 无条件
        # 基线天然低; 感知层穷举哲学: 低频真因果不被比例稀释挡)
        if n_ab < self._state_cond_min_support:
            return
        for c, c_cnt in cand_counts.items():
            if c_cnt < self._state_cond_min_support:
                continue
            n_ac = 0
            n_acb = 0
            for i in a_pos:  # 2026-08-26 提速: 索引列表遍历 (原全 n)
                cur = log[i]
                # 特征数组回读 (2026-08-26 提速): 原此处重复
                # _recent_state_word 回看 (O(500)) + 窗口前看 — 与
                # 第一遍同调用同参数, 结果逐位一致。
                if rsws[i] != c:
                    continue
                n_ac += 1
                _ev2 = evs[i]
                if _ev2 is not None and b in _ev2:
                    n_acb += 1
                # 结果分布记录 (2026-08-20 立项 D1): 条件满足的每次
                # 转移顺带累积 (c,a)→结果 全分布 (纯增量测量, 不改
                # 现有边/判定 — 消费端 (分布预期) 另接线)。结果 = 变
                # 事件第一个状态词 (eco (兔,变,多)→'多'; 生产回归基线
                # (泪,变,温)→'温')。_state_trans_dist 只存条件满足
                # 的转移 → 条件概率分布 (与 p_acb 同口径)。
                if _ev2 is not None:
                    _res = next((w for w in _ev2 if w in states), None)
                    if _res:
                        # 2026-08-20 立项 M1: 键升级 (obj, c, a) —
                        # obj = 变事件主语 (效果对象)。多对象世界
                        # 跨对象效果: 狼捕食 → 兔变 → obj='兔'。
                        # 单对象 (生产回归基线 (泪,变,温)) → obj='泪'。
                        # 撞名状态词 (兔'少' vs 狼'少') 靠对象维度
                        # 分流, 否则分布污染。
                        _eff = _ev2[0] if _ev2 else None
                        d = self._state_trans_dist.setdefault(
                            (_eff, c, a), {})
                        d[_res] = d.get(_res, 0) + 1
            if n_ac < self._state_cond_min_support:
                continue
            p_acb = n_acb / n_ac
            lift = p_acb / p_ab if p_ab > 0 else 0.0
            key = (a, b, c)
            old = self._state_cond_edges.get(key)
            # 证据时效回补 (2026-08-13 第六步): 回补/新建都要最近
            # 窗口内有 (a→b) 转移 — broken 后动作不再产生结果时,
            # 学习期残留撑起的 p_acb 不得维持边活性 (火世界: 加热
            # 失效但残留 26 次 (加热→温) → p_acb=0.96 → 边恒活
            # → plan 不诚实)。无最近证据 → 只衰减 → 死亡 (本体
            # 保留可恢复)。测量 (p_acb/lift 全窗口) 与活性 (recent)
            # 分离。
            # T5 第三轮 (2026-08-14): has_recent = sweep 传入的窗口内
            # 真转移标志 — 原用 recent_pairs (相邻共现) 被断言共现
            # 污染 ((我,加热,泪)→(泪,是,温) 产生 (加热,温) 相邻对)
            # → 规则突变后旧链被历史样本重建不衰减 (second_order 实证)。
            # 2026-08-16 粒度修复: (a,b) → (a,c,b) 三元 (见 sweep
            # 衰减段注释) — 窗口内必须真实发生 前驱c 经 a 得 b 的
            # 转移才维持/回补边 (a,b,c); 反转期新转移 (冷却+冷→温)
            # 不再错误回补旧边 (冷却,热,温)。cond_recent 存储序
            # = (动作, 前驱, 结果), 边键 = (a,b,c)=(动作,结果,条件)
            # → 此处查询序 = (a, c, b)。
            has_recent = (a, c, b) in recent if isinstance(recent, set) \
                else recent
            # 维持语义 (2026-08-13 阶段C 接线调试): 已建立边的
            # 回补只看条件证据持续性 (p_acb), lift 门槛只用于涌现
            # 新边。理由: 无条件基线 p_ab 随探索率漂移 (排球探索
            # 占 83% 时 p_ab 0.5→0.56 → lift 2.0→1.796 擦线 < 1.8)
            # → 真条件边被无条件噪声误杀 (strength 衰减到 0.1 <
            # 死亡阈值 → known=False)。语义: 发现用调制测量 (lift),
            # 维持用条件证据持续性 — 已证明的条件因果 (p_acb=1.0)
            # 不因无条件成功率偶然升高而失效 (用进废退)。规则突变
            # 后 p_acb 实时掉 → 旧边照常死亡 (阶段C 语义不破坏)。
            # 社会边预测证伪检测 (2026-08-27 V12): 社会边 (speaker
            # 标记) 窗口内有 (a,c) 执行但结果 ≠ b → 说话者信用受损
            # (经验证伪 — 信任从验证中学, 非预置)。每边只扣一次
            # (refuted 标记, 防重复扣分); 无最近证据且未执行过 =
            # 未验证 → 不动信任 (等 B 自己执行)。
            if old is not None and old.get('social') \
                    and not old.get('refuted') and not has_recent:
                if isinstance(recent, set):
                    _exec_other = any(
                        _aa == a and _cc == c and _rr != b
                        for (_aa, _cc, _rr) in recent)
                    if _exec_other:
                        _spk = old.get('speaker')
                        if _spk:
                            _st = getattr(self, '_speaker_trust', {})
                            _st[_spk] = _st.get(_spk, 0.0) - 1.0
                        old['refuted'] = True
            if has_recent and \
                    ((lift >= self._cond_min_lift and
                      n_acb >= self._state_cond_min_support) or
                     (old is not None and p_acb >= 0.8)):
                if old:
                    # 回补保留社会标记 (2026-08-27 V12 修复): 原覆盖
                    # 整个 dict → social/speaker 丢失 → 信任追踪断链
                    _keep = {k: old[k] for k in ('social', 'speaker')
                             if k in old}
                    self._state_cond_edges[key] = {
                        'lift': lift,
                        'strength': old['strength'] + 1.0,
                        'n_updates': old['n_updates'] + 1,
                        'p_acb': p_acb, 'p_ab': p_ab,
                        'auto': True,
                        'world': getattr(self, '_current_world', None),
                        **_keep,
                    }
                    # 验证为真 → 说话者信任 +1.0 (2026-08-27 V12:
                    # 信任从执行验证中学 — 社会边被 B 真实执行确认
                    # → 说话者信用升; 与证伪 -1.0 对称)
                    if old.get('social') and old.get('speaker'):
                        _spk = old['speaker']
                        _st = getattr(self, '_speaker_trust', {})
                        _st[_spk] = _st.get(_spk, 0.0) + 1.0
                else:
                    self._state_cond_edges[key] = {
                        'lift': lift, 'strength': 1.0,
                        'n_updates': 1,
                        'p_acb': p_acb, 'p_ab': p_ab,
                        'auto': True,
                        'world': getattr(self, '_current_world', None),
                    }


    def drift_active(self, a: str) -> bool:
        """漂移动作查询 (2026-08-24 漂移适应 A 通道 v2): sweep
        检测到该动作窗口出现全量没有的结果 (新结果涌现 = 环境规则
        变了)。eco/生产回归基线稳态世界恒 False → 零影响。"""
        return a in getattr(self, '_drift_acts', set())

    def trans_uncertainty(self, c: str, a: str,
                          obj: Optional[str] = None,
                          recent: bool = False) -> dict:
        """转移分布不确定性 (概率预期, 2026-08-30 第一层: 学习自主).

        从 result_dist 分布读 (结果, count) → 归一化熵 + 样本量 +
        置信度 — 系统表达「我不确定」的统计基础 (点估计 → 分布).

        - entropy ∈ [0, log2(k)]: 0=确定单点, 高=结果分散
        - entropy_norm ∈ [0,1]: 归一化 (1=均匀分布)
        - confidence = (1 − entropy_norm) × 样本折扣 n/(n+1):
          确定性 × 证据量 — 少样本「确定」≠ 真确定 (1 次成功
          置信度只有 0.5, 99 次成功 → 0.98)
        - mode: 众数结果 (最高概率结果)

        三铁律: 纯统计读数, 不判定 — 判定在消费端 (探索权重/
        预期判定/过程置信/信念推断). 确定性世界退化为单点分布
        (entropy_norm=0) — 零影响基线.
        """
        cnts = self.result_dist(c, a, obj=obj, recent=recent)
        n = int(sum(cnts.values()))
        if n == 0 or not cnts:
            return {'entropy': 0.0, 'entropy_norm': 0.0, 'n': 0,
                    'confidence': 0.0, 'mode': None, 'dist': {}}
        probs = np.array([v / n for v in cnts.values()], dtype=float)
        ent = float(-np.sum(probs * np.log2(probs)))
        ent_max = float(np.log2(len(probs)))
        ent_norm = ent / ent_max if ent_max > 0 else 0.0
        conf = (1.0 - ent_norm) * (n / (n + 1.0))
        mode = max(cnts.items(), key=lambda kv: kv[1])[0]
        return {'entropy': round(ent, 4),
                'entropy_norm': round(ent_norm, 4),
                'n': n, 'confidence': round(conf, 4),
                'mode': mode, 'dist': dict(cnts)}

    def result_dist(self, c: str, a: str,
                    obj: Optional[str] = None,
                    recent: bool = False) -> dict:
        """结果分布读数 (2026-08-20 立项 D1 + M1): (对象,条件,动作)
        → 结果计数。obj=None → 合并全部对象 (旧调用兼容: 单对象
        世界键 (唯一obj,c,a) 合并 = 原 (c,a) 语义, 逐位等价; 旧
        存档 2 元组键不兼容 — _state_trans_dist 不持久化, 无迁移
        负担)。

        分布预期消费端用: 随机世界同一 (c,a) 多结果 → 预期从单点
        升级为分布 (violated = 结果不在高概率集)。确定性世界分布
        单点 → 消费端退化为原判定 (逐位等价)。

        三铁律: 纯读数 (统计测量), 不判定 — 判定在消费端。
        """
        if obj is not None:
            # identity_learn 路由 (2026-08-30): 分裂对象 → 当前状态子节点
            if obj in getattr(self, '_identity_route', {}):
                obj = self._identity_route_lookup(
                    obj, getattr(self, '_last_obs', {}).get(obj))
            return dict(self._state_trans_dist.get((obj, c, a), {}))
        # 漂移窗口路径 (2026-08-24 漂移适应): 漂移动作用最近窗口真
        # 转移分布 — 全量累积被漂移前旧证据淹没 (漂移后拉错仍 ∈ 全
        # 量高概率集 → 容错吞违背 → 过程库永不降权锁死实锤)。窗口
        # 样本 <5 (低频动作) → 回退全量 (R23 低频保护)。零破坏: 非
        # 漂移动作 (eco/生产回归基线稳态) drift_active 恒 False → 原全量路
        # 径逐位一致 (2026-08-24 二分实测)。
        if recent and a in getattr(self, '_drift_acts', set()):
            _wr = getattr(self, '_nxt_recent_win', {})
            out = {}
            for (_a, _b), _cnt in _wr.items():
                if _a == a:
                    out[_b] = out.get(_b, 0) + _cnt
            if sum(out.values()) >= 5:
                return out
        out: dict = {}
        for (_o, _c, _a), _cnts in self._state_trans_dist.items():
            if _c == c and _a == a:
                for _r, _n in _cnts.items():
                    out[_r] = out.get(_r, 0) + _n
        return out

    def _recent_state_word(self, log, i, states, exclude=()):
        """从位置 i 往前回看最近的状态词 (T5 修复, 2026-08-14)

        语义 = 转移发生前的对象状态 (最近状态断言)。真实感知流里
        方向事件 (火,升) 插在断言与转移之间, 紧邻 1 步回看会被
        方向词占位 → 条件候选丢失。回看跳过非状态条目 (方向/
        动作), 最多 500 步 — 连续动作段 (冷却期 60+ 回合无感知
        事件, 断言在动作段之前) 也能跨过 (T5 连续流暴露: 8 步
        不够, 条件候选错位 → 状态链建不出)。

        同对象过滤 (T5 第二轮修复, 2026-08-14): 对象 = 动作条目
        里非我/非动作/非状态的词 (log[i]=(我,加热,泪) → 泪)。
        回看时跳过不含该对象的事件 — 107 多对象世界回看 500 步
        会撞上其他对象的状态词 (噪声对象 (物3,变,乙) 的'乙')
        → 条件跨对象错位 → 污染边 (加热,沸,乙) 淹真链。
        """
        actions = self._action_words
        cur = log[i]
        obj = next((w for w in cur
                    if w != '我' and w not in actions
                    and w not in states), None)
        for j in range(i - 1, max(-1, i - 500), -1):
            if obj is not None and obj not in log[j]:
                continue
            for w in log[j]:
                if w in states and w not in exclude:
                    return w
        return None

    def _ctx_pairs(self, cur):
        """从事件条目提取 (rel, val) 上下文对 (2026-08-16 重建)

        观察流里上下文以 (属性词, '在', 状态词) 平铺: (我,采样,球,
        向,在,正,率,在,快) → (('向','正'),('率','快'))。rel = 属性
        词 (非动作非状态), val = 状态词。多关联对象世界 (物理:
        向+率) 必须保留 rel 才能精确匹配 — 丢 rel 后 (左,正) 与
        (左,快) 都命中同 ctx_states → 后写覆盖先写系统性答错。
        """
        pairs = []
        i = 1
        while i < len(cur) - 1:
            if cur[i] == '在' and cur[i - 1] != '在' and cur[i + 1] != '在':
                rel = cur[i - 1]
                val = cur[i + 1]
                if rel not in self._action_words and \
                        rel not in self._state_words and \
                        val in self._state_words:
                    pairs.append((rel, val))
                    i += 2
                    continue
            i += 1
        return tuple(pairs)

    def _state_cond_scan2(self, a: str, b: str, log, cnt: int,  # 半成品: cnt 参数未用 (标注勿删)
                          recent: bool = True):
        """复合条件扫描 (世界模型): 关系 = 二阶条件调制

        与 _state_cond_scan 同构 (lift = P(B|A,C1,C2)/P(B|A)),
        但候选条件 = 跨事件状态对 (c1, c2):
          c1 = 前一事件自身状态断言 (泪,在,冷) — T5 修复: 回看
          最近状态断言 (方向事件占位同 scan)
          c2 = 本事件上下文关联对象状态 (动作事件成员 (火,在,旺))
        — 关系的最小涌现形态 (研究层实证: 单条件扫描原理上
        够不着复合条件 — (冷,旺)→温 的 '冷' 单独 p_acb=0.55
        被火灭无效稀释, '旺' 单独 lift=1.3 被泪状态稀释;
        复合 (冷,旺) p_acb=1.0 lift=20)。

        独立表 _state_cond_edges2 (零破坏); 三铁律: 统计测量=感知。
        """
        from collections import defaultdict
        n = len(log)
        if n < 20:
            return
        states = self._state_words
        # 无条件基线: P(B|A)
        n_a = 0
        n_ab = 0
        comp_counts = defaultdict(int)
        for i in range(n - 1):
            cur = log[i]
            nxt = log[i + 1]
            if a not in cur:
                continue
            n_a += 1
            if '变' in nxt and b in nxt:
                n_ab += 1
            # 复合候选: prev 状态 × cur 上下文 (rel,val) 对 (有序)
            c1 = self._recent_state_word(log, i, states, {a})
            pairs = self._ctx_pairs(cur)
            if c1 and pairs:
                comp_counts[(c1, pairs)] += 1
        if n_a < self._state_cond_min_support:
            return
        p_ab = n_ab / n_a
        if n_ab < self._state_cond_min_support:
            return
        for (c1, pairs), cc in comp_counts.items():
            if cc < self._state_cond_min_support:
                continue
            n_ac = 0
            n_acb = 0
            for i in range(n - 1):
                cur = log[i]
                nxt = log[i + 1]
                if a not in cur:
                    continue
                if self._recent_state_word(log, i, states, {a}) != c1 \
                        or self._ctx_pairs(cur) != pairs:
                    continue
                n_ac += 1
                if '变' in nxt and b in nxt:
                    n_acb += 1
            if n_ac < self._state_cond_min_support:
                continue
            p_acb = n_acb / n_ac
            lift = p_acb / p_ab if p_ab > 0 else 0.0
            key = (a, b, (c1, pairs))
            # 感知层无门槛证据快照 (2026-08-16 范式攻坚第二步):
            # 统计只做采证 — comp_counts/n_acb 本来就是本遍历算出的
            # 原始计数, 顺手保留 (零额外遍历), 仲裁层 (state_chain
            # 外推段) 现场读它做调制律验证。不设门槛: lift 裁剪是
            # 感知层内部的带宽压缩, 原始证据必须留底 (判别实验实证:
            # 跨界边 lift 1.6-1.8 卡 1.8 门槛被丢, 仲裁层无证可裁)。
            # 覆盖式写入 = 每次 batch 重建快照 (最近观测, 证据时效)。
            self._state_cond_raw[key] = {
                'n_ac': n_ac, 'n_acb': n_acb, 'p_acb': p_acb,
            }
            # 推理验证回灌 (阶段 A, 2026-08-16): 真实转移 (c1,a)→b
            # 被观察到 → 核对外推预测 (统计只做采证: 记录证实/证伪;
            # 判定在外推段查询时做 — 仲裁层)。掩码组合一旦出现在
            # 事件流 = 世界给出真答案 (规则突变/新观察); 预测命中 →
            # confirm, 未命中 → refute。证伪 1 次即禁, 证实 2 次已验证。
            # key 含 pairs (情境维度): 外推预测针对 (向正,率快),
            # (向正,率慢) 的真实转移不是它的证据 (粒度不匹配不核对)。
            verdicts = getattr(self, '_reasoning_verdicts', None)
            if verdicts and n_acb > 0:
                v = verdicts.get((c1, a, pairs))
                if v is not None:
                    if v.get('b') == b:
                        v['confirm'] += 1
                    else:
                        v['refute'] += 1
                    if v['refute'] >= VERDICT_REFUTE_LIMIT:
                        v['status'] = '不可靠'
                    elif v['confirm'] >= VERDICT_CONFIRM_LIMIT:
                        v['status'] = '已验证'
            old = self._state_cond_edges2.get(key)
            # 证据时效回补 (2026-08-13 第六步): 同 _state_cond_scan
            # — 回补/新建都要最近窗口内有 (a→b) 转移; 残留不维持
            # 活性 (突变后复合边衰减死亡 → 诚实)。
            # T5 第三轮 (2026-08-14): 窗口内真转移标志 (同 scan);
            # 2026-08-16: (a,c1,b) 三元粒度 — 复合边活性证据 = 窗口
            # 内 前驱c1 经 a 得 b 的真转移 (pairs 关联对象不做活性
            # 证据, 只参与 p_acb/lift 测量; 活性=转移存在性)。
            has_recent = (a, c1, b) in recent if isinstance(recent, set) \
                else recent
            # 维持语义 (同 scan): 已建立复合边的回补只看条件证据
            # 持续性 (p_acb), lift 门槛只用于涌现新边。
            if has_recent and \
                    ((lift >= self._cond_min_lift and
                      n_acb >= self._state_cond_min_support) or
                     (old is not None and p_acb >= 0.8)):
                if old:
                    # 回补保留社会标记 (2026-08-27 V12 同 scan 修复)
                    _keep = {k: old[k] for k in ('social', 'speaker')
                             if k in old}
                    self._state_cond_edges2[key] = {
                        'lift': lift,
                        'strength': old['strength'] + 1.0,
                        'n_updates': old['n_updates'] + 1,
                        'p_acb': p_acb, 'p_ab': p_ab,
                        'auto': True,
                        **_keep,
                    }
                else:
                    self._state_cond_edges2[key] = {
                        'lift': lift, 'strength': 1.0,
                        'n_updates': 1,
                        'p_acb': p_acb, 'p_ab': p_ab,
                        'auto': True,
                    }


    def _state_cond_sweep(self):
        """结构通道: 对全量 (动作→状态) 转移对做状态条件扫描

        候选 = 转移计数里 a∈动作词集 且 b∈状态词集 的对
        (不依赖 DMIT 通过, 解决缺口2)。这是感知层穷举通道
        (统计=超人类带宽) → 仲裁层判定 → 认知结构涌现。
        """
        if not self._state_cond_enabled:
            return
        from collections import defaultdict
        log = self._principle_log
        n = len(log)
        if n < 20:
            return
        self._slot_structures()
        actions = self._action_words
        states = self._state_words
        if not actions or not states:
            return
        # ── 证据时效 (2026-08-15 语义修正, 丰富世界 10 类×多对象暴露) ──
        # 旧实现: 全表 ×decay 无差别代谢 → "对象停在目标状态后继续
        # 无效动作" (无变事件) 被当成证据缺失 → 已学成边衰减死
        # (plan_state known 消失)。R21a 12 对象 5499 步饱和侥幸未暴露;
        # 丰富世界/整体生命体长期运行必然触发 (单对象 4000 步复现:
        # 学会 甲→动→乙 后停在乙, 无效动作 40 批, strength 1.0→2.7e-06
        # → goal 不在转移表)。
        # 新语义: 只衰减"被失败尝试"的边。失败尝试 = 窗口内动作 a
        # 被尝试但无变事件 (结果不变) 时的对象状态。区分两类无变:
        #   A 已达成: 尝试状态 = 边结果 b (对象已在 b, 动作无效是预期)
        #     → 不衰减 (知识保留, 本体沉淀)
        #   B 规则突变: 尝试状态 = 边前驱 c (本应转移却无变)
        #     → 失败 → 衰减 (突变诚实语义保持: 突变后动作持续失败
        #     → 边照常衰减死亡, verify_second_order 不破坏)
        # 泛化 (2026-08-15 二修, 反转场景暴露): 失败尝试只覆盖"无结果"
        # (加热失效), 不覆盖"规则反转" (动作仍成功但结果变了: 冷却在
        # 温→热, 旧边 (温,冷却)→冷 残留 → plan 卡死循环, verify_self_model
        # B3/B3b 2 fail)。证据通道驱动: 边活性 = 窗口内 (动作,前驱) 尝试
        # 的结果证据。边 (a,b,c) 衰减 iff 前驱 c 被 a 尝试过 且 窗口内
        # (a,c) 的结果集不含 b (无变 → 空集 → 全部衰减 = 原 B 场景;
        # 结果改变 → 旧 b 衰减新 b 保持 = 新增反转场景)。A 场景保护
        # 保留: 尝试状态 = 边结果 b ≠ 前驱 c → 前驱未被尝试 → 不衰减
        # (已达成知识保留)。
        # 条件三元边按前驱状态判; 二元边 (det/DMIT/granger) 跟随同
        # (a,b) 条件边 (二元边 = 条件边下沉, 活性随条件证据)。
        # 未失败边维持活性 (本体保留) — 已学知识不因无效动作而亡。
        recent_start = max(0, n - self._recent_window)
        attempted: Dict[str, set] = defaultdict(set)
        results: Dict[Tuple[str, str], set] = defaultdict(set)
        results_by_obj: Dict[Tuple[str, str, str], set] = defaultdict(set)  # 2026-08-22: 窗口内 (对象,a,前驱) 结果集 (对象级翻转检测)
        attempted_cnt_by_obj: Dict[Tuple[str, str, str], int] = defaultdict(int)  # 2026-08-22: 窗口内 (对象,a,前驱) 尝试次数
        cond_recent: set = set()  # 窗口内 (a, 前驱c, 结果b) 真转移
        # 2026-09-03 情境切片证据 (复合边反证粒度修复): 复合边 = 情境条件
        # 调制 (泪 (热,加热,火旺)→沸 vs (热,加热,火灭)→温), 反证必须同情境
        # 切片 — 火灭期 热+加热→温 是火灭边的正证, 不是火旺边的反证。新增
        # (a,前驱,情境pairs) 粒度窗口证据供复合边衰减段按自身条件切片判定
        # (边键同构原则同 2026-08-16 回补粒度修复; 单条件/二元边不消费,
        # 原逻辑逐位不变)。_ep 为空 (无情境事件) 不登记 → 无情境世界零开销。
        attempted_ctx: Dict[Tuple[str, str, tuple], int] = defaultdict(int)
        results_ctx: Dict[Tuple[str, str, tuple], set] = defaultdict(set)
        results_by_obj_ctx: Dict[Tuple[str, str, str, tuple], set] = defaultdict(set)
        attempted_cnt_by_obj_ctx: Dict[Tuple[str, str, str, tuple], int] = defaultdict(int)
        # 2026-08-16 回补粒度修复: 条件边回补键从 (a,b) 细化到
        # (a,c,b) — 原粗粒度 (a,b) 下, 反转期新转移 (冷却,温)
        # (来自 冷却+冷→温) 会错误回补旧边 (冷却,热,温) (同
        # (a,b)=(冷却,温) 但条件 c=热 不同) → 旧边衰减×0.85 + 
        # 回补+1.0 = 净增长永活 (稳定点 6.7) → 规则反转后旧链
        # 不衰减死 → 冲突保留强者选出旧边 → 系统按旧规则预测 →
        # 违背持续 (verify_second_order C2a/C2b)。活性证据必须
        # 精确到 (动作,前驱,结果) 三元, 与边键同构。
        for i in range(recent_start, n - 1):
            # 2026-08-20 结果侧同对象对齐: 变事件须与动作宾语同对象。
            # 多对象世界动作后紧邻变事件可能是其他对象 (eco: 放牧/
            # 喂食直接改草 → 草先变 → got=草词) → 条件边 (放牧,草词,
            # 兔词) → state_chain 对象过滤全滤 → 动作因果边 0 (实锤)。
            # 前看窗口: log[i+1] 起找含宾语 obj 的变事件; 生产回归基线单对象
            # log[i+1] 即命中 → got 逐位一致 (零破坏)。
            got = None
            # 宾语位 (2026-08-22): demo 第三人称主语 (tom,heat,water)
            # 原取主语 tom → 变事件 water/变/hot 不含 tom → got=None
            # → 条件边 0 (verify_text_lifelong 全败实锤); 生产回归基线
            # (我,加热,火) 末位=火 不变。
            obj = next((w for w in log[i][1:]
                        if w != '我' and w not in self._action_words
                        and w not in self._state_words
                        and w not in ('变', '是', '在')), None)
            for k in range(i + 1, min(n, i + 1 + self._cond_align_window)):
                ev = log[k]
                if any(w in self._action_words for w in ev):
                    if '我' in ev:
                        break  # 跨动作归因禁止 (同上: 主语'我'才
                        # 是动作; 生/死/捕食事件非动作不中断)
                if '变' not in ev:
                    continue
                if obj is not None and obj not in ev:
                    continue
                got = next((w for w in ev if w in states), None)
                break
            for a in log[i]:
                if a not in actions:
                    continue
                s = self._recent_state_word(log, i, states, {a})
                if s is not None:
                    attempted[a].add(s)
                    _ep = self._ctx_pairs(log[i])  # 2026-09-03: 本事件情境切片
                    if _ep:
                        attempted_ctx[(a, s, _ep)] += 1
                    if got is not None:
                        results[(a, s)].add(got)
                        cond_recent.add((a, s, got))
                        if _ep:
                            results_ctx[(a, s, _ep)].add(got)
                        if obj is not None:
                            # 2026-08-22 方案F: 全历史产出对象集
                            # (跨 sweep 累积 — 局部会在反转后滚出窗口
                            # → 反证主体缺失 → 边永不衰减, seed42 D 段
                            # 25.0 实锤)。只在真转移时注册 (有证据)。
                            self._cond_produced.setdefault((a, s, got), set()).add(obj)
                            results_by_obj[(obj, a, s)].add(got)
                            attempted_cnt_by_obj[(obj, a, s)] += 1
                            if _ep:
                                results_by_obj_ctx[(obj, a, s, _ep)].add(got)
                                attempted_cnt_by_obj_ctx[(obj, a, s, _ep)] += 1
        # 条件三元边: 前驱被尝试且结果不含边结果 → 衰减 (含世界模型复合边)
        # 2026-08-22 反证强度修复 (方案F终版): 衰减 ×decay^n, n = 窗口内
        # 曾被边 (a,c,b) 泛化过的对象 (produced 全历史) 的 (a,c) 尝试次数
        # 且该对象窗口内结果集不含 b (对象级翻转)。
        # 原实现每次 sweep 至多衰减一次 (×0.85) — 短促反转信号 (demo
        # seed7 D 段: 突变后 15 次 热+加热→温 全在一个窗口, 之后泪降到
        # 冷窗口滚出) 只衰减一次 → 旧边 (加热,沸,(热,旺)) 残留 3.39 →
        # plan 假阳性不诚实。第一版 ×n (全局尝试次数) 过度杀伤: 多对象
        # 混合世界其他对象 (蜡类 冷+加热→融) 的反证算进材料类边
        # (加热,温,冷) → 0.85^22 < 死阈值 (verify_category_index V4 回归
        # 实锤)。第二版 (produced 局部) 反转后 produced 滚出窗口 → 永不
        # 衰减 (seed42 25.0 实锤)。第三版 (produced 全历史 + 全局结果
        # 判定) 破坏 eco: 低频结果边在采样波动窗口 (b 恰好未出现) 被
        # 快速衰减死 (1089/645/456 vs 878/724/387 实锤)。终版: 反证 =
        # 曾被边泛化过的对象自身窗口内结果集不含 b (对象级规则翻转:
        # seed7-D 泪 热+加热 全产温 → n=15 快速衰减; eco 对象结果集仍
        # 含 b → 零衰减; category 蜡类反证不属材料类 produced 对象 →
        # 零衰减)。
        # 终版 (方案N): 反证 = 曾被边泛化过的对象自身窗口内结果集
        # 不含 b (对象级规则翻转)。衰减速率按边确定性分级: 高确定性
        # 边 (p_acb≥0.8, 真因果) 反转 → ×decay^n 快速诚实 (seed7-D:
        # 泪 热+加热 全产温 → n=15 死); 低确定性边 (感知类如观望,
        # 结果=状态快照天然多值) → ×decay 温和 (eco 观望边 0.85^n
        # 打破回补平衡 → 观望不可规划 → 1089/645/456 破坏实锤; 基线
        # 平衡 = 回补+1.0 / 衰减×0.85)。
        def _ctx_key_match(cond, ep):
            """复合边条件 ↔ 事件情境 pairs 匹配 (与 state_chain 查询侧同构):
            新格式 cond=((rel,val),...) → 事件 pairs 全含 (AND); 旧格式
            cond=str (rel 通配, 历史兼容) → 任一事件 val == cond; None → 全匹配。"""
            if cond is None:
                return True
            if isinstance(cond, str):
                return any(v == cond for _r, v in ep)
            return all((r, v) in ep for r, v in cond)

        def _decay_n(a, c, b, p_acb, cond):
            # 快速分支只给复合边 (见调用处注释): 高确定性 (p_acb≥0.8)
            # 多反证 (n≥2) → ×0.85^n (seed7-D: 泪 热+加热 15 次全产
            # 温 → 复合边死 → plan 诚实)。单反证 (n=1) 不放大 (不确定)。
            # n = 曾被边 (a,c,b) 泛化过对象在其**自身情境切片**内的反证
            # 次数 (2026-09-03: 原无情境维度 → 兄弟情境合法结果算入反证
            # → 火灭期大量 热+加热→温 误杀火旺边, 实锤见衰减段注释)。
            n_try = 0
            for o in self._cond_produced.get((a, c, b), ()):
                _keys = [k for k in attempted_cnt_by_obj_ctx
                         if k[0] == o and k[1] == a and k[2] == c
                         and _ctx_key_match(cond, k[3])]
                if not _keys:
                    continue
                _r: set = set()
                for _k in _keys:
                    _r |= results_by_obj_ctx[_k]
                if _r and b not in _r:
                    n_try += sum(attempted_cnt_by_obj_ctx[k]
                                 for k in _keys)
            if n_try > 1 and p_acb >= 0.8:
                return n_try
            return 1
        for (a, b, c), m in list(self._state_cond_edges.items()):
            # 三元边恒温和 (方案Q): 感知类伪因果边 (观望→中 等) 的
            # p_acb 高是环境先验 (生态状态分布) 非动作因果 — 快速
            # 衰减杀死它们 → eco/fusion 行为漂移 (1089/645/456 /
            # 1922/75/40 实锤)。三元边不进 state_chain (plan_state
            # 只读复合边 _state_cond_edges2, concept_state.py:42) →
            # 温和衰减不影响 seed7-D 规划诚实。
            if c in attempted.get(a, ()) and b not in results.get((a, c), ()):
                m['strength'] = m.get('strength', 1.0) * self._cond_edge_decay
        for (a, b, cc), m in list(self._state_cond_edges2.items()):
            # 复合边: 快速分支 — seed7-D 假阳性唯一来源 (plan_state
            # 只读本表)。观望类不进本表 (无条件 pairs) → 零影响。
            # 2026-09-03 反证粒度修复: 反证 = **自身情境切片**内 (c1,a)
            # 被尝试且该切片结果不含 b。原实现只按 (动作,前驱) 聚合窗口
            # 结果 → 兄弟情境合法结果被当规则反转 (verify_world_model_loop
            # seed42: 学习尾段火灭期 50×/批 热+加热→温, (热,加热,火旺)→沸
            # 被 ×0.85^50 连打到 strength≈0 → 情境查询热→沸断链 →
            # B1/B2 plan=[] 实锤; 火旺边自身证据 6/6 p_acb=1.0 从未被违背)。
            # 自身情境整窗未出现 → 无证据无衰减 (A 场景同构: 条件不适用
            # ≠ 规则反转 — 条件规则是"火旺时加热→沸"的真知识, 非过时承诺)。
            # 无条件反转 (seed7-D: 自身情境内也全产温) 照常快速衰减 → 诚实保持。
            c1 = cc[0] if isinstance(cc, tuple) else cc
            cond = cc[1] if isinstance(cc, tuple) and len(cc) > 1 else None
            _keys = [k for k in attempted_ctx
                     if k[0] == a and k[1] == c1
                     and _ctx_key_match(cond, k[2])]
            if not _keys:
                continue  # 自身情境切片无尝试 → 不衰减 (不适用≠反转)
            _r: set = set()
            for _k in _keys:
                _r |= results_ctx[_k]
            if b not in _r:
                n_try = _decay_n(a, c1, b, m.get('p_acb', 0.0), cond)
                if n_try > 0:
                    m['strength'] = m.get('strength', 1.0) * (self._cond_edge_decay ** n_try)
        for (a, b, c), m in list(self._causal_edges_cond.items()):
            # 三元因果边: 恒温和 (同 _state_cond_edges 理由)
            if c in attempted.get(a, ()) and b not in results.get((a, c), ()):
                m['strength'] = m.get('strength', 1.0) * self._cond_edge_decay
        # 二元边: 跟随同 (a,b) 条件边 — 任一前驱被尝试且结果不含 b → 衰减
        # (与 LTM consolidate 同构; 无对应条件边的事件对保守保持)
        cond_c_by_ab: Dict[Tuple[str, str], set] = defaultdict(set)
        for (a, b, c) in self._state_cond_edges:
            cond_c_by_ab[(a, b)].add(c)
        for (a, b, c) in self._causal_edges_cond:
            cond_c_by_ab[(a, b)].add(c)
        for (a, b), m in list(self._state_det_edges.items()):
            if any(c in attempted.get(a, ())
                   and b not in results.get((a, c), ())
                   for c in cond_c_by_ab.get((a, b), ())):
                m['strength'] = m.get('strength', 1.0) * self._cond_edge_decay
        for (a, b), m in list(self._causal_edges_dmit.items()):
            if any(c in attempted.get(a, ())
                   and b not in results.get((a, c), ())
                   for c in cond_c_by_ab.get((a, b), ())):
                m['strength'] = m.get('strength', 1.0) * self._cond_edge_decay
        for (a, b), m in list(self._causal_edges.items()):
            if any(c in attempted.get(a, ())
                   and b not in results.get((a, c), ())
                   for c in cond_c_by_ab.get((a, b), ())):
                m['strength'] = m.get('strength', 1.0) * self._cond_edge_decay
        # 动作→状态 转移对 (全量, 不走 top-N 截断)
        # T5 修复 (2026-08-14): 转移只认变事件 (结果变化) — 注释
        # 声明"状态断言/动作条目不产生转移"但实现漏过滤: (我,加热,
        # 火)→(火,在,冷) 的 (加热,冷) 被当转移 → 加热→冷 假确定性
        # 边 + 条件候选被断言噪声占据 → 状态链错乱 (T5 连续流事件
        # 化暴露: 断言事件密度高, 假转移支撑超过 _cond_min_support
        # → 污染边建库)。107/排球世界断言稀 (变化驱动) 侥幸未触发。
        from collections import defaultdict
        nxt = defaultdict(int)
        # T5 第三轮修复 (2026-08-14): 窗口内真转移标志 — has_recent
        # 原用 recent_pairs (相邻共现): 反转期 (我,加热,泪)→(泪,是,温)
        # 断言共现产生 (加热,温) 相邻对 → 旧边 (加热,温,冷) 被当
        # "最近有证据" → 新建分支 (n_acb≥1) 靠全量 log 历史样本
        # 永久重建旧链 → 规则突变后旧链不衰减死 → 决策永远给旧 plan
        # → 执行违背不消退 (verify_second_order 3 fail)。语义修正:
        # 边活性证据 = 窗口内真转移 (变事件), 不是任意相邻共现。
        recent_start = max(0, n - self._recent_window)
        # 2026-08-24 窗口化: set → 计数 dict (窗口内真转移次数,
        # 用于 det 边确定性/单结果判定的窗口分布 — 全量 nxt 被漂移
        # 前旧证据淹没, 漂移后新结果永不出 2000 事件窗口 → 新边不
        # 建/旧边不衰减死, E4 漂移奖励 ns 实锤同源)。
        nxt_recent: Dict[Tuple[str, str], int] = defaultdict(int)
        # 2026-08-20 对象对齐前看窗口: 多对象世界动作后紧邻事件
        # 是其他对象的在/变 (eco: bucket_sync 草先发, 兔变在第 4
        # 位) → (动作,兔词) 转移计数恒 0 → 保护边永不建 (实锤)。
        # 与 got 对齐同构: 前看窗口找第一个含宾语 obj 的变事件。
        # 生产回归基线单对象 log[i+1] 即命中 → 逐位一致 (零破坏)。
        for i in range(n - 1):
            # 宾语位 (2026-08-22): 同 231 行 — demo 主语误取修复
            _obj = next((w for w in log[i][1:]
                         if w != '我' and w not in actions
                         and w not in states
                         and w not in ('变', '是', '在')), None)
            _ev = None
            for k in range(i + 1, min(n, i + 1 + self._cond_align_window)):
                _e = log[k]
                if any(w in actions for w in _e):
                    if '我' in _e:
                        break  # 跨动作归因禁止 (同上: 主语'我'才
                        # 是动作; 生/死/捕食事件非动作不中断)
                if '变' not in _e:
                    continue
                if _obj is not None and _obj not in _e:
                    continue
                _ev = _e
                break
            if _ev is None:
                continue  # 窗口内无同对象变事件 → 无转移
            for a in log[i]:
                if a not in actions:
                    continue
                # 2026-09-18: 多对象行串味修复 — 取【与 _obj 绑定】的
                # 状态词 (对象名之后的状态), 而非该行全部状态词。
                # 旧形态 [我,观望,兔,太阳,在,黑夜,狼,在,灭绝] 会把
                # 太阳的 黑夜/白天 记成 兔动作 的结果 → ('黑夜',观望)
                # 假边 (eco seed42: 201 次) → 计划监控永不满足。
                # _bs is None (无对象绑定: 单对象世界/旧形态) ⇒ 保持
                # 原全覆盖 = 零破坏路径。
                _bs = None
                if _obj is not None and _obj in _ev:
                    _oi = _ev.index(_obj)
                    _bs = [w for w in _ev[_oi + 1:]
                           if w in states and w != a]
                for b in (_bs if _bs is not None else _ev):
                    if b in states and b != a:
                        nxt[(a, b)] += 1
                        if i >= recent_start:
                            nxt_recent[(a, b)] += 1
        # 演化链 (2026-08-20 立项 M1, 主体预期扩展 S1): 无动作状态
        # 转移统计 — 变事件 (obj,变,x) + 回看最近同对象 '在' 断言
        # → (obj, c, None) → {x}。语义 = "不动时世界怎么变" 基线:
        # ① 他人演化模型 (eco 狼无'我'动作, 状态链 0 边 — 系统对
        #   狼完全透明, 主体预期缺口实锤); ② 观望假因果的对照基线
        #   (动作真效果 = lift 于演化基线, 候选③ 的地基)。
        # 纯增量统计, 无消费端 (M2/M3 接线) — 生产回归基线零行为影响。
        # M2 扩展 (2026-08-20, 立项 S2 desire 归因): 变事件前回看
        # 窗口内 (共现,捕食) 事件 (狼行为代理 — 兔被猎信号) →
        # 归因捕食: 键 (obj, '狼/状态', '捕食') — 条件 = 捕食时间点
        # 最近狼状态 (desire 主体状态)。语义 = "狼状态 → 捕食 →
        # 对象变" 链的统计端。支持度门槛在消费端 (统计=感知, 不
        # 判定纪律)。生产回归基线/数学/几何无捕食事件 → 零影响。
        _hunt_words = ('共现', '捕食')
        for i in range(n - 1):
            _e = log[i]
            if len(_e) < 3 or '变' not in _e:
                continue
            _src = _e[0]
            if _src == '我' or _src in actions or _src in states:
                continue
            _res = next((w for w in _e[2:] if w in states), None)
            if _res is None:
                continue
            _c = None
            for j in range(i - 1, max(-1, i - 100), -1):
                _l = log[j]
                if _src not in _l or '在' not in _l:
                    continue
                _c = next((w for w in _l if w in states), None)
                if _c:
                    break
            if _c is None:
                continue
            _d = self._state_trans_dist.setdefault((_src, _c, None), {})
            _d[_res] = _d.get(_res, 0) + 1
            # identity_learn (2026-08-30): 状态签名 + 连通并查集 —
            # 对象身份自学习的数据源 (分裂检测的信号)
            if _src and _src != '我':
                _sig = self._id_sigs[_src]
                _sig[_c] = _sig.get(_c, 0) + 1
                _sig[_res] = _sig.get(_res, 0) + 1
                self._id_union(_src, _c, _res)
        # 捕食归因 (desire 代理, 立项 M2/S2): 独立循环 — 对每个
        # 捕食事件 (src,捕食,被捕) (主语=被捕对象): 捕食后紧邻同
        # 对象 (src,在/变,桶) 状态 → 键 (src, '狼/状态', '捕食') →
        # {捕食后状态}。语义 = "狼状态 → 捕食压力 → 对象去向" 链的
        # 统计端。条件 = 捕食时刻最近狼状态 (desire 主体)。
        # 归因视角说明: 捕食频率高 (eco 每步 ~1 次) → "变事件前找
        # 最近捕食" 会把全对象变都归因捕食 (假因果实锤, 已回滚);
        # 捕食事件视角 + 紧邻同对象状态 = 每捕食 1 归因, 分布可靠。
        # 支持度门槛在消费端 (统计=感知, 不判定纪律)。生产回归基线/数学/
        # 几何无捕食事件 → 零影响。
        for i in range(n - 1):
            _e = log[i]
            if len(_e) < 3 or _e[1] != '捕食':
                continue
            _src = _e[0]
            if _src == '我' or _src in actions or _src in states:
                continue
            _w_state = None
            for k in range(i - 1, max(-1, i - 100), -1):
                _lk = log[k]
                if '狼' not in _lk or '在' not in _lk:
                    continue
                # 2026-08-20 S3 修: context 加狼后动作事件含
                # [我,观望,兔,太阳,在,黑夜,狼,在,灭绝] — 取第一个
                # 状态词会拿到太阳状态 (黑夜)。取 '狼' 之后的第一个
                # 状态词 = 狼状态 (desire 条件正确)。
                _li = _lk.index('狼')
                _w_state = next(
                    (w for w in _lk[_li + 1:] if w in states), None)
                if _w_state:
                    break
            if _w_state is None:
                continue
            for j in range(i + 1, min(n, i + 8)):
                _l = log[j]
                if len(_l) >= 3 and _l[0] == _src \
                        and _l[1] in ('在', '变'):
                    _after = next((w for w in _l if w in states), None)
                    if _after:
                        _dk = self._state_trans_dist.setdefault(
                            (_src, f'狼/{_w_state}', '捕食'), {})
                        _dk[_after] = _dk.get(_after, 0) + 1
                    break
        # 最近证据窗口 (2026-08-13 第六步修正): 回补条件 = 最近 W
        # 事件内有该转移 — 稀疏真因果 (cascade 每 ~69 事件一次) 用
        # 本批增量段回补过稀 → 稳态破坏 (det 边 10 回补/150 衰减
        # → 学习期就死)。W 窗口: 学习期每批窗口内总有 → 回补持续
        # → 稳态 1/(1-0.85)≈6.7; 突变后动作不再产生结果 → 窗口滚出
        # (~W/每批事件 批) → 停止回补 → 衰减死亡 (broken 场景级联
        # 断 → 诚实)。本体保留可恢复 (与 LTM/M4 同构)。DMIT 段复用。
        recent_pairs = set()
        # 全量转移对 (不限动作→状态): DMIT 边含 (我,飞) 等主语/
        # 事件词对, 只认动作→状态会让它们衰减死 → deduce 链变
        # (verify_deduce 回归失败)。全量对语义: 最近窗口内任何
        # 相邻共现都是证据 — broken 后动作不再产生结果 → (动作,
        # 结果) 对仍不在窗口 (ctx 行有动作词但结果词不出现) →
        # cond/det/DMIT 三套边照常衰减死亡 (突变诚实保持)。
        for i in range(recent_start, n - 1):
            for a in log[i]:
                for b in log[i + 1]:
                    if b != a:
                        recent_pairs.add((a, b))
        self._principle_recent_pairs = recent_pairs
        # 确定性单结果: 动作→唯一状态 (p_ab 高且无多结果分歧)
        # 事件流设计差异 (研究层结论): 真实认知体只在可做时做动作
        # (推只在关时推) → 无条件 p_ab=1.0, lift=1.0 不涌现条件边,
        # 但转移本身是确定的链边。候选窗口错配 (R7d/e 同源):
        # (加柴,强) 转移排 57 名 top40 外 → DMIT 永不建边 → 结构
        # 通道必须自己采集确定性转移 (感知层穷举, 不依赖 DMIT)。
        per_a: Dict[str, Dict[str, int]] = defaultdict(dict)
        for (a, b), c in nxt.items():
            per_a[a][b] = c
        # 窗口内分布 (2026-08-24 漂移适应 A 通道): det 确定性/单结果
        # 判定用最近窗口 — 全量累积被漂移前旧证据淹没 (拉1→得分 旧
        # 记录让 len(bcnt)>1 → 新边 (拉1,落空) 永不建, E4 漂移奖励
        # ns 实锤)。窗口 = 最近 _recent_window 事件 (≈漂移 1-2 轮)
        # → 漂移完全进窗口后 拉1→落空 单结果 → 新边重建。窗口内无
        # 转移 (低频动作) → 全量兜底 (R23 低频保护保持)。
        per_a_win: Dict[str, Dict[str, int]] = defaultdict(dict)
        for (a, b), c in nxt_recent.items():
            per_a_win[a][b] = c
        # 窗口内真转移缓存 (result_dist 消费端 — 漂移后全量分布仍
        # 含旧结果 → 高概率集含旧结果 → 拉错不算违背 → 过程库永不
        # 降权锁死旧计划实锤)。低频动作窗口样本 <5 → result_dist
        # 回退全量 (R23 低频保护)。
        self._nxt_recent_win = dict(nxt_recent)
        # 漂移动作集 (2026-08-24 漂移适应 A 通道 v2): 窗口出现全量
        # 没有的结果 (新结果涌现 = 环境规则变了) → 该动作标漂移。
        # 消费端: ①result_dist(recent) 直接窗口 (不等混合收敛) ②
        # behavior_loop violated 判定禁用分布容错 (漂移=严格验证,
        # 拉错即降权 → 过程库 2 次失败回退 → 快速脱离旧计划)。
        # eco/生产回归基线稳态: 窗口结果集 ⊆ 全量 → 恒空 → 零影响。
        _full_res: Dict[str, set] = {}
        _full_res_cnt: Dict[str, Dict[str, int]] = {}
        # 🩸 全量基准用本批全量 nxt (所有转移), 不用 _state_trans_dist
        # (2026-08-24 二分实测: 后者只存条件满足转移 — eco 观望/喂
        # 食无前置条件 → 全量侧缺失 → set(窗口)-全量 恒非空 → 恒标
        # 漂移 → 单点判定误杀随机世界实锤 911/765/663)。nxt = 全量
        # log 窗口内所有 (动作→状态) 转移, 与窗口 per_a_win 同口径
        # 同粒度 → 稳态差集恒空。
        for (a, b), c in nxt.items():
            _full_res.setdefault(a, set()).add(b)
            _fc = _full_res_cnt.setdefault(a, {})
            _fc[b] = _fc.get(b, 0) + c
        # 漂移判定 v5 (2026-08-24 永久漂移受控实验修复): ①窗口出现
        # 历史没有的结果 (新结果涌现) ②窗口单结果且全量多结果 (结果
        # 数收缩 = 环境从随机变确定, 漂移后收敛) 且窗口主导 ≠ 全量
        # 主导 (真切换)。②的收缩条件把 eco/生产回归基线随机多结果世界排除
        # (短窗口恒多结果, 结果集不收缩) → 永不误判。
        # 🩸 v5 修复 (永久漂移实锤): 差集比较对象 = **跨批历史结果
        # 集** (_seen_results, 首次预热只记录) 非本批全量 — 全量 log
        # 环形 500 ⊇ 窗口 200 → set(窗口)-全量 恒空 → 检测器从未工
        # 作 → 豁免/反证/冷却全链路空转 (perm drift 生产 online={}
        # drift_acts=set() 实锤)。历史集: 漂移前 {得分} → 漂移后落空
        # ∉ 历史 → 首次触发; eco/生产回归基线稳态结果集稳定 → 窗口 ⊆ 历史
        # → 恒空零影响。
        self._drift_acts = set()
        _seen = getattr(self, '_seen_results', {})
        # _drift_ever: 曾差集触发过的动作 (2026-08-24 二分实测修复
        # 2/2): 收缩分支只对这些动作启用 — MAB 漂移首次新结果涌现
        # (落空∉历史) → 差集触发 → 标记; 之后漂移周期窗口单结果
        # ≠ 全量主导时收缩继续维护。eco 观望/喂食结果集长期稳定
        # (无新结果) → 永不差集触发 → 收缩永不启用 → 窗口单结果
        # (环境阶段稳定) 不误判 → 单点判定零误触 (911/765/663 →
        # 基线实测)。
        _pend = getattr(self, '_drift_pending', set())
        # 🔴 2026-09-11 根因修复: 确认门曾**结构性不可达**。
        # 2026-08-24 的 7cbe1c8 同时引入三件事, 其中②与③互斥:
        #   ①差集比较对象改跨批历史 _seen_results (真修复: 全量 log
        #     ⊇ 窗口使旧差集恒空 — 检测器从未工作)
        #   ②无条件吸收本批窗口 _seen[_a] = _hist | set(_wcnt)
        #   ③新增连续两批确认 _conf = _new_diff & _pend (真修复:
        #     防单批误标 → 永久标 → 退化, seed 888 rot −15→−81)
        # 互斥: 首批把新结果并入 _hist 的**同一刻**置 pending →
        # 次批 len(_hist)>1 且差集为空 → _conf 恒空 → 门永不可达。
        # 实测: 连续 12+ 漂移批 (2400+ 事件) 触发次数=1, 40 随机场景
        # 零确认, 多臂 MAB 连续 8 批零确认 → 08-24 历史归因"旧臂 84
        # 事件 < 检测窗口 200"(事件量不足)**浅一层** — 给足事件量也
        # 无效, 根因是门不可达。
        #
        # ⚠️ 曾试"延迟一批吸收"(_prev_win_store) 并已实测**引入回归**:
        # fusion "用石头" 是随机多结果动作 (中/低/饱满/一般+石…), 历史
        # 因延迟永久滞后于窗口 → 差集反复触发 → 第 4 批误确认 → 过程
        # 库误降权 → 工具使用率后段 163→35 (verify_tool_use V2 fail)。
        # 故**不改吸收路径** (保持即时吸收, 与原语义逐位一致), 改用
        # **候选值对判据**:
        #   本批窗口单结果且为新值 → 与上批候选 (同值, 且不在上批
        #   历史快照内) 比对 → 连续两批同一新值 = 真漂移 → 直接确认。
        #   真漂移   : 窗口连续两批 {落空} (同值) → ✅ 确认
        #   随机多结果: 窗口 中→低→饱满 变 → ❌ 不确认 (值不同)
        #   轮换      : 得分/落空 交替 → ❌ 不确认 (08-24 轮换免疫保持)
        #   稳态      : 窗口 ⊆ 历史 → 差集空 → ❌ 零影响
        _prev_cand = getattr(self, '_drift_cand', {})
        _new_cand = {}
        _new_diff = set()
        _direct_conf = set()   # 候选值对已直接确认 (窗口单结果连续两批同值)
        for _a, _wcnt in per_a_win.items():
            _fa = _full_res.get(_a, set())
            _hist = _seen.get(_a)
            if _hist is None:
                # 首次: 预热只记录不触发 — 用全量结果 (500 事件环形
                # log, 比窗口 200 完整) — eco 放牧随机多结果首次预热
                # 即含 {少,中,多} → 后续窗口 ⊆ 历史 → 永不误触发
                _seen[_a] = set(_fa) if _fa else set(_wcnt)
                continue
            # 🩸 v5 差集门控 (2026-08-24 eco 破坏二分实锤): 只对"历史
            # 单结果"动作检测 — 曾确定性动作 (MAB 漂移前拉1 恒得分)
            # 出现新结果 = 环境规则变; eco 放牧/观望历史多结果 (随机
            # 分布/阶段波动) → len(_hist)>1 → 永不检测 → 零误标 →
            # 豁免永不误开 → 稳态行为逐位一致。
            if len(_hist) == 1 and set(_wcnt) - _hist:
                # 曾确定性动作 + 出现新结果 = 规则可能改变 (原语义)
                _new_diff.add(_a)
            # 🩸 候选值对判据 (2026-09-11 修复核心): **独立于上方
            # len(_hist)==1 门** — 首批触发后历史已含新值, 次批
            # len(_hist)>1 会挡住原门 → 故此处独立判定。
            # 条件: 窗口单结果 + 该值不在"上批候选时的历史快照"内
            # (即相对漂移前是新值) + 与上批候选**同值** → 连续两批
            # 稳定出现同一新值 = 真漂移 (而非随机多结果抖动)。
            if len(_wcnt) == 1:
                _x = next(iter(_wcnt))
                _pc = _prev_cand.get(_a)
                if (_pc is not None and _pc[0] == _x
                        and _x not in _pc[1]):
                    _direct_conf.add(_a)  # ✅ 连续两批同一新值
                _new_cand[_a] = (_x, set(_hist))
            _seen[_a] = _hist | set(_wcnt)  # 历史累积 (结果集只增)
            if (len(_wcnt) == 1 and len(_fa) > 1
                    and _a in getattr(self, '_drift_ever', set())):
                _w_dom = next(iter(_wcnt))
                _f_dom = max(_full_res_cnt.get(_a, {}),
                             key=_full_res_cnt.get(_a, {}).get)
                if _w_dom != _f_dom:
                    self._drift_acts.add(_a)
        # 🩸 连续两批确认 (2026-08-24 轮换免疫批跑实锤): 单批差集
        # 误标 (轮换漂移窗口单结果期 ~1 批 → _drift_ever 永久标 →
        # 收缩持续触发 → 判定/冷却持续 → 退化, seed 888 rot −15 →
        # −81 实锤) → _drift_ever 永不标 → 收缩门控不满足 → 轮换零
        # 影响 (均匀探索 = 周期环境最优策略)。永久漂移落空持续多批
        # → 连续两批确认 → 标 → 收缩/豁免/判定/冷却全链路激活。
        # 🔴 2026-09-11 根因修复: 本门曾**结构性不可达** — 与上方
        # "无条件吸收本批窗口"互斥。现改为: ①窗口单结果路径由候选值
        # 对直接确认 (上方 _new_diff), ②多结果窗口路径仍走本门求交。
        # 实测: 连续漂移批第 2 批即 _drift_ever 非空; 随机多结果动作
        # (fusion 用石头) 与轮换漂移均不误标。
        # 验证纪律: 本机制**不能用"零破坏"证明** (不触发必然零破
        # 坏) — 必验**触发计数** (_drift_ever 非空)。
        # 多结果窗口路径: 仍需与上批 pending 求交 (原连续两批语义);
        # 窗口单结果路径: 候选值对已保证"连续两批同值" → 直接确认。
        _conf = (_new_diff & _pend) | _direct_conf
        if _conf:
            _de = getattr(self, '_drift_ever', set())
            _de |= _conf
            self._drift_ever = _de
            self._drift_acts |= _conf
            # [drift-confirm] 消费端钩子 (2026-08-24 候选1): 漂移确认
            # (连续两批) → 通知装配层 (过程库层批量降权). 默认 None
            # 零影响 — concept_principle 不碰过程库 (职责分离, 回调
            # 由 run_lifeform fusion 分支注册).
            # ⚠️ 适用域 (59330ef 定论): 检测器可见性 = 动作事件结果
            # 带状态符号 (MAB 得分/落空, 生态控制动作) — '我' 状态
            # 动作 (进食/开采) 结果恒对象名 → 失明; 且连续两批窗口
            # (400 事件) > MAB 基础适应 (~100-200) → 即时反馈世界
            # 零触发. 钩子是为反馈延迟/稀释场景 (旧链顽固) 预留.
            _cb = getattr(self, '_on_drift_confirm', None)
            if _cb:
                try:
                    _cb(set(_conf))
                except Exception:
                    pass  # 回调失败不影响检测主链路
        self._drift_pending = _new_diff
        self._seen_results = _seen
        self._drift_cand = _new_cand  # 候选值对缓冲 (2026-09-11 根因修复)
        def _det_drift(a):
            """漂移检测 (2026-08-24): 窗口内该动作转移是否有明确主导
            结果 (argmax ≥ DET_DOMINANCE_TH, 样本 ≥5) → 返回主导
            结果; 否则 None (多结果/低频 → 全量路径, 与旧逻辑逐位
            一致)。用于: det 边衰减 (主导 ≠ 边结果 b → 旧链被否定
            → 衰减)、建边 (主导结果建边)、唯一性破坏 (主导=伪多结
            果不置 0)。
            🩸 不比较全量 argmax: 漂移积累后全量 argmax 也翻转
            (拉2 落空 38 > 得分 13) → 窗口==全量 → 误判稳态 → 永
            不衰减 (step 300 (拉2,得分) 残留 1.0 实锤)。稳态世界
            (生产回归基线/eco): 确定性动作窗口主导 = 边结果 → 不衰减; 多
            结果动作窗口无主导 → None → 全量路径。"""
            _w = per_a_win.get(a)
            if not _w:
                return None
            _wt = sum(_w.values())
            if _wt < 5:
                return None
            _dom, _dc = max(_w.items(), key=lambda x: x[1])
            if _dc / _wt >= DET_DOMINANCE_TH:
                return _dom
            return None

        for a, bcnt in per_a.items():
            tot = sum(bcnt.values())
            # 真转移最小支持度 (2026-08-16 R23): 与条件边同构
            # (T5 修复: 低频真因果不被 6 挡) — 单向边 (敲打
            # 甲→乙) 真转移只发生 1 次, _cond_min_support=6 永
            # 远不建边 → 新对象链学不到 (婴儿式: 真转移 1 次
            # 即学, 一次性观察)。det 边建边门槛 = 状态链真转移
            # 门槛 (1), 非共现门槛 (6)。
            if tot < self._state_cond_min_support:
                continue
            best_b, best_c = max(bcnt.items(), key=lambda x: x[1])
            p_det = best_c / tot
            # 漂移窗口路径 (2026-08-24): 窗口主导结果明确翻转 →
            # 窗口分布判定 (主导 ≥0.7 即建边 — 漂移边界混合窗口旧
            # 结果残留 → len(bcnt)>1 伪多结果, 单结果约束让新边永
            # 不建实锤)。全量路径保持原语义 (单结果 + 0.9, 生产回归基线/
            # eco 逐位一致 — 稳态世界 _det_drift 返回 None)。
            _dr = _det_drift(a)
            if _dr is not None:
                bcnt = per_a_win[a]
                tot = sum(bcnt.values())
                best_b, best_c = max(bcnt.items(), key=lambda x: x[1])
                p_det = best_c / tot
                _det_ok = p_det >= DET_DOMINANCE_TH
            else:
                _det_ok = p_det >= DET_RESULT_MIN_P and len(bcnt) == 1
            if _det_ok:
                key = (a, best_b)
                old = self._state_det_edges.get(key)
                # 世界模型隔离 (2026-09-18): 他世界旧边在本世界视作不存在
                if old is not None and old.get('world') is not None \
                        and old.get('world') != getattr(
                            self, '_current_world', None):
                    old = None
                if old:
                    if key in nxt_recent:
                        # 本批新证据 (窗口内真转移) → 回补 (用进废退)
                        # 2026-08-17 修: 原用 recent_pairs (相邻共现)
                        # — B 段加柴时泪=沸 的断言共现 (加柴,沸) 被当
                        # 最近证据回补 → 置 0 失效的跨对象假边复活 →
                        # plan 假阳性 (seed7 D 段泪→沸 known=True)。
                        # 与 T5 条件边同构: 活性证据 = 窗口内真转移。
                        self._state_det_edges[key] = {
                            'p_ab': p_det,
                            'strength': old['strength'] + 1.0,
                            'n_updates': old['n_updates'] + 1,
                            'auto': True,
                            'world': getattr(self, '_current_world', None),
                        }
                    else:
                        # 无新证据 → 只刷新概率, 活性只衰减
                        # (证据时效: 残留不维持活性)
                        self._state_det_edges[key] = {
                            'p_ab': p_det, 'strength': old['strength'],
                            'n_updates': old['n_updates'], 'auto': True,
                            'world': getattr(self, '_current_world', None),
                        }
                else:
                    if key not in nxt_recent:
                        continue  # 无新证据不建边 (残留不复活)
                    self._state_det_edges[key] = {
                        'p_ab': p_det, 'strength': 1.0,
                        'n_updates': 1, 'auto': True,
                        'world': getattr(self, '_current_world', None),
                    }
        # 唯一性破坏衰减 (2026-08-17 修): 动作结果集 >1 → 确定性
        # 破坏 → 该动作无条件 det 边立即失效。无条件边 = “动作→唯一
        # 结果” (p_ab≥DET_RESULT_MIN_P 且无多结果分歧) — 多结果 =
        # 确定性死亡 (语义失效), 与条件边证据时效同构 (本体保留,
        # 活性死亡, 未来唯一性恢复→窗口真转移 recent_pairs 回补
        # +1.0 复活)。置 0 而非 ×decay: 慢衰减在低频动作 (加柴) 下
        # 批次不足死不掉 (见下实锤)。
        # 实锤 (demo seed7 D 段): 突变后加热结果 {温,热} 各半, 旧
        # det 边 (加热,沸) p_ab=1.0 strength=25.5 永不衰减 — 原衰
        # 减只认单条件边 (cond_c_by_ab 不含复合边 _state_cond_edges2,
        # 泪 热+加热→沸 是火旺复合边) → 复合边断裂后 det 边永生
        # → sweep 无条件边重建仍=沸 → plan 假阳性 (泪→沸 known=True
        # 不诚实)。二修: 结果集 >1 → 该动作全部 det 边置 0 失效。
        for a, bcnt in per_a.items():
            if len(bcnt) > 1:
                # 漂移豁免 (2026-08-24): 漂移动作全量含新旧结果 →
                # 伪多结果误杀新边 (拉1 {得分,落空} → (拉1,落空) 也
                # 置 0, step 400 det 全空实锤)。窗口收敛单结果 = 确
                # 定性恢复 → 不破坏。稳态世界 (生产回归基线/eco) 窗口与全量
                # 结果集一致 → 不豁免 → 原语义逐位一致。
                # 🩸 漂移门控 (2026-08-24 二分实测): 豁免只对漂移动
                # 作生效 — eco 放牧全量多结果但窗口偶发单结果 (环境
                # 阶段稳定) → 豁免误保留旧 det 边 (放牧,多) → 行为
                # 改变实锤 (908/436/199 → 736/754/449)。MAB 漂移后
                # 全量伪多结果 (新旧结果混合) → 豁免让新边 (拉1,落
                # 空) 不被误杀。二修: 轮换漂移窗口 200 > 漂移周期
                # 100 → 窗口恒混合 (得分期+落空期) → len(_wa)==1 永
                # 不成立 → 豁免永不生效 → det 边被破坏循环 (dbg
                # step 400 后 det 恒空实锤)。漂移动作 (曾差集触发 =
                # 环境规则真变过) 无条件豁免破坏 — 全量伪多结果本就
                # 是漂移造成, 非真随机, 不该破坏。
                if (a in self._drift_acts
                        or a in getattr(self, '_drift_ever', set())):
                    continue
                for (da, db), m in list(self._state_det_edges.items()):
                    if da == a:
                        m['strength'] = 0.0
        # 多结果转移: 状态条件扫描 (分歧=隐藏变量信号)
        # T5 修复: 门槛用 _state_cond_min_support (真转移事件,
        # 低频真因果不被 6 挡); recent=窗口内真转移 (nxt_recent)
        for (a, b), cnt in nxt.items():
            if cnt < self._state_cond_min_support:
                continue
            self._state_cond_scan(a, b, log, cnt, cond_recent)
        # 世界模型 (2026-08-13): 复合条件扫描 (关系 = 二阶条件调制)
        # 同 (a,b) 候选, 独立表 _state_cond_edges2, 零破坏
        if getattr(self, '_state_cond2_enabled', True):
            self._state_cond_raw = {}  # 感知层证据快照重建 (零破坏)
            for (a, b), cnt in nxt.items():
                if cnt < self._state_cond_min_support:
                    continue
                self._state_cond_scan2(a, b, log, cnt, cond_recent)
        # 类别活力代谢 (四期, 2026-08-18): 类别整体冷却 — 全表 ×0.9
        # (M4 冷概念冷却同构: 不活跃概念冷却; 类别是二阶结构比单边
        # 0.85 记得更久)。休眠 (<0.3) 保留表不删 (本体保留哲学,
        # 再观察注入恢复)。
        _vit = getattr(self, '_category_vitality', None)
        if _vit:
            for _cn in list(_vit):
                _vit[_cn] *= 0.9
        # 多级概念金字塔代谢 (2026-09-03): 每批冷却各层类别活性
        # (与 _category_vitality 同构); pyramid_sleep_on 装配方开
        self.pyramid_metabolize()


    # ══ 加载后派生统计重建 (2026-09-18): 语义层加载后为空根因修复 ══
    def rebuild_online_stats_from_stream(self, events=None) -> dict:
        """从事件流重建【在线中间统计】(加载后调用; 单真源铁律)

        背景 (2026-09-18 实测坐实): 语义层 (抽象规则/类别规则/金字塔)
        由惰性重扫产出, 而重扫的输入是**在线中间统计** — 词角色
        (_sense_roles)、槽位结构 (_action_words/_state_words)、原理
        日志窗口 (_principle_log) 与由其涌现的条件边/确定性边
        (_state_cond_edges/_state_det_edges)、结果分布
        (_state_trans_dist)。这些统计随 observe 逐步累积、**不序列化**
        (派生层, 与 memory_shadow 同族) — 但加载后无人重建 → 重扫
        跑在空输入上 → 产出 0 还清掉脏标记 → 语义层永久为空
        (探针实测: 加载后 abstract_rules=0/_state_det_edges=0 vs
        全新跑完 17/34)。

        修法 (与单真源原则同构: 派生层不序列化 → 从事件流重建):
          ① 词角色 (_sense_roles/sense_of/_struct_state_words/
             _state_words_online/_struct_state_preds) ← events 计数表
             (槽位角色统计; 规则与 observe 逐条同构)
          ② 原理日志窗口 (_principle_log/_principle_prev/
             _principle_transitions/_action_state_results)
             ← 事件流尾部 (_principle_log_window 个事件, 同长度窗口)
          ③ _state_cond_sweep() ← 由 ①② 涌现条件边/确定性边/结果
             分布/证据快照 (与在线批次同一函数、同一语义)

        只写**非持久化**派生表: 持久化层 (types/events/edges/因果边/
        DMIT 边/相位/情景/过程库) 一字不动 ⇒ 加载后"逐位一致"断言
        (verify_persistence P2/P4) 不受影响, 也不产生二次学习。

        诚实边界 (事件流不携带 ⇒ 重建不了):
          - context 成员 (复合条件源): 事件流只存 (主语,动作,宾语)
            → 关联对象状态成员缺失 (复合边通道偏弱)
          - 感知通道事件 (person=='感知' = principle=False 语义)
            按同一语义排除在原理日志之外
          - 空间统计 (spatial_cond/spatial_index/spatial_cooccur):
            事件流无坐标 ⇒ 不可重建, 保持空 (空间世界消费端读数
            缺失 — 需要时须另行落盘)
          - 身份分裂 (obj#k) 不重放: 分裂是学习动作, 不是派生统计
            (信号 _id_sigs 按窗口重建, 不触发分裂)

        Args:
            events: M1 EventStream (None → self.event_stream)

        Returns:
            dict: 重建摘要 (窗口事件数/三条统计表大小)
        """
        es = events if events is not None else getattr(
            self, 'event_stream', None)
        if es is None:
            return {'rebuilt': False, 'reason': 'no_event_stream'}

        # ① 词角色 (槽位角色统计 ← events 计数表; 与 observe 同规则:
        #    主语=人物 / 动作位=动作 / 宾语=对象; ≥2 角色 → 义项注册)
        roles: Dict[str, set] = defaultdict(set)
        for (p, a, o) in self.events:
            if p:
                roles[p].add('人物')
            if a:
                roles[a].add('动作')
            if o:
                roles[o].add('对象')
        self._sense_roles = roles
        _so: Dict[str, set] = defaultdict(set)
        for _w, _r in roles.items():
            if len(_r) >= 2:
                _so[_w] |= _r
        # 义项表是持久化字段 → 只做并集 (重建绝不丢存档已有义项)
        for _w, _s in _so.items():
            self.sense_of[_w] |= _s
        # 专用宾语位 (结构状态词) + 状态谓词反推 (observe 第五刀/
        # 第十三刀同构: 宾语 ∈ 结构状态词 的动作 = 结构状态谓词)
        _sw = {_w for _w, _r in roles.items()
               if len(_r) == 1 and '对象' in _r}
        self._struct_state_words = _sw
        _preds = {_a for (_p, _a, _o) in self.events if _o in _sw}
        self._struct_state_preds = _preds
        _online = {_o for (_p, _a, _o) in self.events
                   if _o and (_a in ('变', '是', '在') or _a in _preds)}
        self._state_words_online = _online | _sw
        # 对象→动作集 (身份锚增量, 与 observe 同构)
        _oa: Dict[str, set] = {}
        for (_p, _a, _o) in self.events:
            if _o and _a not in ('变', '是', '在'):
                _oa.setdefault(_o, set()).add(_a)
        self._obj_actions = _oa

        # ② 原理日志窗口 ← 事件流**全量按序重放** (窗口滚动由 ingest
        #    维护; 感知通道事件不进日志 — 与在线 principle=False 同语义)
        win = int(getattr(self, '_principle_log_window', 2000) or 2000)
        _all = list(getattr(es, '_all', None) or ())
        log: List[List[str]] = []
        for _e in _all:
            if _e.subj == '感知':
                continue
            _m = [_e.subj, _e.act]
            if _e.obj:
                _m.append(_e.obj)
            log.append(_m)

        # ③ 派生表面清零 → 重放 (重建 = 事件流的纯函数, 可重复调用)
        #    清零的全是非持久化派生表 (持久化层一字不动)
        self._principle_log = []
        self._principle_prev = []
        self._principle_pending = 0
        self._principle_transitions = defaultdict(int)
        self._action_state_results = {}
        self._principle_recent_pairs = set()
        self._state_cond_edges = {}
        self._state_cond_edges2 = {}
        self._state_det_edges = {}
        self._state_trans_dist = {}
        self._state_cond_raw = {}
        self._cond_produced = {}
        self._id_sigs = defaultdict(dict)
        self._id_split_stable = defaultdict(int)
        self._drift_acts = set()
        self._drift_ever = set()
        self._seen_results = {}
        self._drift_pending = set()
        self._drift_cand = {}
        self._online_drift = {}
        # 重放: 逐事件喂原理日志通道 + **按在线批次节奏**重扫中间统计
        # (每 _principle_batch_size 事件一次 = 与在线 _principle_batch
        #  同节奏)。为何必须按节奏而非末尾单次快照: 边的活性/漂移
        # 标记是**演化量** (用进废退/差集检测跨批累积) — 末窗口单次
        # 重扫实测丢演化 (det 边 0 vs 在线 34, 抽象规则 3 vs 17)。
        # 只重放中间统计通道 (ingest + sweep): 因果层 (dmit/granger)
        # 随存档恢复, 不重算 (重算 = 二次学习 + 写持久化层);
        # 身份分裂 (学习动作) 同样不重放。
        _bs = max(1, int(getattr(self, '_principle_batch_size', 200) or 200))
        _sleep = bool(getattr(self, 'pyramid_sleep_on', False))
        if _sleep:
            # 重建不做代谢 (代谢 = 学习节奏, 不是派生统计还原)
            self.pyramid_sleep_on = False
        try:
            self._principle_batch_size = 10 ** 9  # 重放期 ingest 不自行触发
            for _i, _m in enumerate(log):
                self._principle_ingest(_m, max_window=win)
                if (_i + 1) % _bs == 0:
                    self._state_cond_sweep()
        finally:
            self._principle_batch_size = _bs
            if _sleep:
                self.pyramid_sleep_on = True
        if len(self._principle_log) < min(len(log), win):
            # 因果学习关 (ingest 直接返回) → 日志窗口直接回填
            self._principle_log = [list(_m) for _m in log[-win:]]
            self._principle_prev = (list(log[-1]) if log else [])
        # 批次计数器与在线同相位 (在线: pending = 自上次触发以来事件数)
        self._principle_pending = len(log) % _bs
        # 语义层脏标记: 重扫必须重跑 (抽象/类别/金字塔从新统计涌现)
        self._abstract_dirty = True
        self._pyramid_dirty = True
        return {
            'rebuilt': True,
            'stream_events': len(_all),
            'replayed_events': len(log),
            'sweeps': len(log) // _bs,
            'cond_edges': len(self._state_cond_edges),
            'det_edges': len(self._state_det_edges),
            'trans_dist': len(self._state_trans_dist),
            'sense_roles': len(self._sense_roles),
        }


    def _abstract_emerge(self, min_objects: int = 2) -> dict:
        """抽象规则涌现: 跨对象共享转移 → 领域无关规则

        2026-08-18 推理基础能力 (用户拍板: 表达层不着急, 先弄推理):
        四短板 (没有抽象概念 / 多步组合推理弱 / 反事实假设推理弱 /
        跨领域高阶抽象弱) 收敛到一个机制缺失 — 类别/抽象概念没有
        成为可推理对象。本方法补存储侧: 扫描所有对象的 state_chain,
        同一 (状态,动作)→结果 转移出现在 ≥min_objects 个对象 →
        领域无关抽象规则 (泪/水/铁 共享 冷+加热→温 → 抽象规则
        "加热让冷变温", 不绑定任何具体对象)。

        与 DMIT/条件边同族 (统计涌现, 零预置): 抽象规则是对象级
        规则的最大公约数 (概念=空间区域同哲学, 只是高一阶 — 区域
        间结构相似 → 更高阶区域)。

        三铁律: 感知不判定 — 建表是统计测量 (观测), 消费端回退
        路径才产生假设推演 (来源标注 abstract, 不写回对象链)。

        零破坏: 表默认空; 只在本方法显式涌现; 消费端默认不走
        回退 (use_abstract=False)。

        Args:
            min_objects: 至少几个对象验证过才视为领域无关 (默认 2)

        Returns:
            {(状态,动作): {result, n_objects, objects, strength}}
        """
        from collections import defaultdict
        if not getattr(self, '_abstract_enabled', True):
            self._abstract_rules = {}
            self._abstract_dirty = False
            return {}
        # 候选对象: 事件结构里的对象 (身份维度) — 有转移表才算
        objs = set()
        for (p, a, o), _ in self.events.items():
            if a in ('是', '变', '在'):
                if o is not None:
                    objs.add(p)
            else:
                objs.add(o)
        shared = defaultdict(set)   # (状态,动作,结果) → 覆盖对象集
        shared_st = {}              # (状态,动作,结果) → 边强度 (验证证据量)
        shared_kind = {}            # (状态,动作,结果) → 边类型 det|cond
        for obj in objs:
            # 直接从原始边表扫 (2026-08-18 二期修正): state_chain 的
            # 全局 trans 单键覆盖会丢冲突信息 — (冷,加热) 被 材料→温 /
            # 蜡→融 竞争, 后写覆盖先写, 对象过滤在覆盖之后 → 蜡链
            # 整键丢失 → 全局只见 温, 冲突永不涌现 → 无法诚实跳过。
            # 原始边表 + 对象身份维度过滤: 冲突可见, 才谈得上
            # 诚实跳过 (假设≠事实, 不猜覆盖)。
            obj_actions = set()
            obj_states = set()
            # 抽象规则涌现同样用对象字面名过滤 (2026-08-18 二期):
            # 身份锚合并跨类别对象 → 过滤退化为全局 → 冲突键被
            # 误判为类别内冲突而跳过; 字面名保留对象独立性, 冲突
            # 检测才能看见真跨类别冲突 (材料 温 vs 蜡 融 → 诚实跳过)。
            _objs = {obj}
            for (p, a, o), _ in self.events.items():
                if o in _objs and a not in ('是', '变', '在'):
                    obj_actions.add(a)
                if p in _objs and a in ('是', '变', '在') and o is not None:
                    obj_states.add(o)
            if not obj_actions or not obj_states:
                continue
            for (a, b, c), m in self._state_cond_edges.items():
                if not m.get('auto'):
                    continue
                if m.get('strength', 1.0) < self._cond_edge_dead:
                    continue
                if a not in obj_actions or c not in obj_states \
                        or b not in obj_states:
                    continue
                shared[(c, a, b)].add(obj)
                shared_st[(c, a, b)] = m.get('strength', 1.0)
                shared_kind[(c, a, b)] = 'cond'
            for (a, b), m in self._state_det_edges.items():
                if not m.get('auto') or m.get('p_ab', 0) < 0.9:
                    continue
                if m.get('strength', 1.0) < self._cond_edge_dead:
                    continue
                if a not in obj_actions or b not in obj_states:
                    continue
                shared[('__any__', a, b)].add(obj)
                shared_st[('__any__', a, b)] = m.get('strength', 1.0)
                shared_kind[('__any__', a, b)] = 'det'
        rules = {}
        for (c, a, b), os_ in shared.items():
            if len(os_) >= min_objects:
                rules[(c, a)] = {'result': b, 'n_objects': len(os_),
                                 'objects': sorted(os_),
                                 'strength': shared_st.get((c, a, b), 1.0),
                                 'kind': shared_kind.get((c, a, b), 'cond')}
        # 冲突键不涌现 (2026-08-18 二期): 同 (状态,动作) 多结果
        # (材料类 冷+加热→温 vs 蜡类 冷+加热→融) → 抽象泛化不确定,
        # 诚实做法是跳过该键 (假设≠事实, 不猜覆盖), 由类别规则
        # 精确区分 (类别内同构无冲突)。
        conflict = {k for k in rules if sum(1 for (c, a, _), _ in
                    shared.items() if (c, a) == k) > 1}
        for k in conflict:
            del rules[k]
        self._abstract_rules = rules
        self._abstract_dirty = False
        return rules

    def abstract_rules(self, min_objects: int = 2) -> dict:
        """抽象规则读取 (惰性涌现): 脏标记 → 重扫, 否则用缓存

        纯查询零写 (三铁律: 感知不判定); 消费端 (process_infer /
        deduce / plan_state) 在 use_abstract=True 时回退到本表。
        跨世界迁移规则 (world_registry 注入 _migrated_rules) 查询
        时合并 — 本地涌现优先 (同键不被迁移覆盖), 迁移规则兜底;
        迁移规则存独立字段, 本地重扫 (本方法重建) 不覆盖迁移。
        """
        _mig = getattr(self, '_migrated_rules', None)
        if self._abstract_dirty or (not self._abstract_rules and not _mig):
            self._abstract_emerge(min_objects=min_objects)
        if not _mig:
            return self._abstract_rules
        merged = dict(self._abstract_rules)
        merged.update({k: {**v, 'migrated': True}
                       for k, v in _mig.items()
                       if k not in self._abstract_rules})
        return merged

    def _category_emerge(self, min_objects: int = 2) -> dict:
        """类别规则涌现: 类别内共享转移 → 类别级抽象规则

        2026-08-18 推理基础能力二期 (用户拍板按建议: 类别显式索引,
        type_of 消费端, 不跑全量): 一期抽象规则表 key=(状态,动作)
        单结果 — 两个不同类别对同一动作有不同结果时 (材料类 加热→温
        vs 食物类 加热→熟) 后写覆盖先写, 全局表丢信息。类别表分开
        存: 从 emergence.categories (M5 共享动作聚簇, 已接线) 的成员
        state_chain 共享转移涌现, 类别内同构 → 无冲突。

        与抽象规则同族 (统计涌现, 零预置): 类别 = 共享动作模式的
        对象聚簇 (涌现物), 类别规则 = 类别成员共享转移的最大公约数
        (高一阶区域)。type_of 消费端: 对象→所属类别→类别规则回退。

        三铁律同抽象规则: 建表是统计测量 (观测), 消费端回退才产生
        假设推演 (来源标注 abstract, 不写回对象链)。

        Args:
            min_objects: 类别内至少几个对象验证过才视为共享 (默认 2)

        Returns:
            {cat_name: {(状态,动作): {result, n_objects, objects, strength}}}
        """
        from collections import defaultdict
        cats = getattr(getattr(self, 'emergence', None), 'categories', None)
        if not cats:
            return {}
        out = {}
        vitality = getattr(self, '_category_vitality', {})
        for cat_name, members in cats.items():
            if len(members) < min_objects:
                continue
            # 类别活力休眠 (四期, 2026-08-18): 类别整体长期不活跃 →
            # 冷却休眠 → 该类别规则不涌现 (类别记忆也遗忘 — 单边有
            # 证据时效, 类别整体同样需要; 休眠保留表, 再观察恢复)。
            # 与死边语义同构: 规则不涌现 → 消费端诚实 None +
            # abstract_used=False (无抽象可用, 非使用失败)。
            if vitality.get(cat_name, 1.0) < 0.3:
                continue
            shared = defaultdict(set)  # (状态,动作,结果) → 覆盖对象集
            shared_st = {}             # (状态,动作,结果) → 边强度 (验证证据量)
            shared_kind = {}           # (状态,动作,结果) → 边类型 det|cond
            for obj in members:
                # 对象身份维度 (与 state_chain 过滤同逻辑, 但直接扫
                # 原始边表 — 全局 trans 单键覆盖会污染: (冷,加热) 键
                # 被 材料→温 / 蜡→融 竞争, 后写覆盖先写, 对象过滤
                # 发生在覆盖之后 → 蜡查 (冷,加热) 拿到材料的温)。
                # 类别规则必须保留对象维度, 从 _state_cond_edges /
                # _state_det_edges 原始键过滤, 不走全局 trans。
                obj_actions = set()
                obj_states = set()
                # 类别规则涌现用对象字面名过滤 (2026-08-18 二期):
                # 不用 identity_members — 身份锚会把跨类别共享维度
                # 的对象认成同一物理对象 (蜡/油/泪/水 都加热+冷 →
                # identity_members('蜡') = 全部), 过滤退化为全局 →
                # (冷,加热) 温/融 冲突涌现 → 被冲突过滤误删。
                # 类别成员本就是已聚簇的对象名, 字面名即可 (统计
                # 测量, 不判定身份)。
                _objs = {obj}
                for (p, a, o), _ in self.events.items():
                    if o in _objs and a not in ('是', '变', '在'):
                        obj_actions.add(a)
                    if p in _objs and a in ('是', '变', '在') and o is not None:
                        obj_states.add(o)
                if not obj_actions or not obj_states:
                    continue
                for (a, b, c), m in self._state_cond_edges.items():
                    if not m.get('auto'):
                        continue
                    if m.get('strength', 1.0) < self._cond_edge_dead:
                        continue  # 证据过期: 活性死亡过滤
                    if a not in obj_actions:
                        continue
                    if c not in obj_states or b not in obj_states:
                        continue
                    shared[(c, a, b)].add(obj)
                    shared_st[(c, a, b)] = m.get('strength', 1.0)
                    shared_kind[(c, a, b)] = 'cond'
                for (a, b), m in self._state_det_edges.items():
                    if not m.get('auto') or m.get('p_ab', 0) < 0.9:
                        continue
                    if m.get('strength', 1.0) < self._cond_edge_dead:
                        continue
                    if a not in obj_actions or b not in obj_states:
                        continue
                    shared[('__any__', a, b)].add(obj)
                    shared_st[('__any__', a, b)] = m.get('strength', 1.0)
                    shared_kind[('__any__', a, b)] = 'det'
            rules = {}
            for (c, a, b), os_ in shared.items():
                if len(os_) >= min_objects:
                    rules[(c, a)] = {'result': b, 'n_objects': len(os_),
                                     'objects': sorted(os_),
                                     'strength': shared_st.get((c, a, b), 1.0),
                                     'kind': shared_kind.get((c, a, b), 'cond')}
            # 类别内冲突键不涌现: 同 (状态,动作) 多结果 → 该类别
            # 聚簇含异质成员 (动作共享但状态语义不同, 如水_米 混合
            # 类别), 规则不可靠 → 跳过, 防止污染类别成员推演。
            conflict = {k for k in rules if sum(1 for (c, a, _), _ in
                        shared.items() if (c, a) == k) > 1}
            for k in conflict:
                del rules[k]
            # w_prior 一致性 (2026-08-29, 实验54): 类别内成员行为
            # 同构度 = 1 − 冲突键占比 (σ 逆代理) — 冲突多 = 成员异质
            # (同动作不同结果) = 类别先验可能误导 → 折扣重; 无冲突
            # = 同构 = 类别先验可信 → 折扣轻。纯监测字段零行为。
            try:
                _tot = len(shared)
                _cons = (1.0 - len(conflict) / _tot) if _tot else 1.0
            except Exception:
                _cons = 1.0
            _cc = getattr(self, '_category_consistency', None)
            if _cc is not None:
                _cc[cat_name] = max(0.0, min(1.0, _cons))
            if rules:
                out[cat_name] = rules
        return out

    def category_rules(self, min_objects: int = 2) -> dict:
        """类别规则读取 (惰性涌现, 与抽象规则共用脏标记)

        纯查询零写; 消费端 (process_infer / deduce / plan_state) 在
        use_abstract=True 时按 自身链 → 类别规则 → 全局抽象 顺序回退。
        """
        if self._abstract_dirty or not self._category_rules:
            self._category_rules = self._category_emerge(min_objects=min_objects)
        return self._category_rules

    def _abstract_rule_for(self, obj: str, cur: str, act: str):
        """消费端回退查表: 按 对象所属类别 → 全局抽象 顺序取规则

        类别规则只对类别成员生效 (材料类 加热→温 不能借给食物类 的
        米); 对象无类别或类别无此规则 → 全局抽象兜底泛化。

        Returns:
            {'result': ..., 'source': 'category', 'cat': cat_name,
             'n_objects': ..., 'strength': ...} | {'result': ...,
             'source': 'global', 'n_objects': ..., 'strength': ...}
            | None — 纯查询零写, 永不写回对象链 (假设≠事实)。
            strength = 支撑边强度 (观察回补 +1, 衰减 ×0.85, 稳态
            ≈6.7; det 无条件边永不衰减) = 验证证据量, 消费端用它
            调制置信折扣 (假设越可靠越敢用)。
        """
        # ① 对象所属类别的类别规则 (类别内共享转移, 更精确)
        cats = self.category_rules()
        my_cats = [cn for cn, members
                   in getattr(getattr(self, 'emergence', None),
                              'categories', {}).items()
                   if obj in members]
        for cat_name in my_cats:
            _rules = cats.get(cat_name, {})
            # 无条件边键兜底: det 边规则键 = ('__any__', act)
            # (与 process_infer 主链同语义) — 2026-08-18 三期修复
            m = _rules.get((cur, act)) or _rules.get(('__any__', act))
            if m is not None:
                # w_prior 一致性 (2026-08-29, 实验54): 类别回退带
                # 成员同构度 (σ 逆代理) → 折扣调制 (同构→轻, 异质→重)
                _cc = getattr(self, '_category_consistency', None)
                _cons = (_cc.get(cat_name, 1.0)
                         if _cc else 1.0)
                return {'result': m['result'], 'source': 'category',
                        'cat': cat_name, 'n_objects': m['n_objects'],
                        'strength': m.get('strength', 1.0),
                        'kind': m.get('kind', 'cond'),
                        'consistency': _cons}
        # ② 全局抽象规则 (兜底泛化; 含跨世界迁移规则 — world_registry
        # 注入 _migrated_rules, 查询合并, 本地涌现优先迁移兜底)
        _g = self.abstract_rules()
        g = _g.get((cur, act)) or _g.get(('__any__', act))
        if g is not None:
            return {'result': g['result'],
                    'source': 'migrated' if g.get('migrated')
                    else 'global',
                    'n_objects': g['n_objects'],
                    'strength': g.get('strength', 1.0),
                    'kind': g.get('kind', 'cond'),
                    'source_world': g.get('source_world')}
        return None

    def _abstract_confidence(self, strength: float,
                             kind: str = 'cond',
                             consistency: Optional[float] = None) -> float:
        """抽象假设可靠性 → 置信折扣 (2026-08-18 三期, 用户"先把刚才
        加的推理能力进行更新"): 假设非事实, 但假设分可靠与不可靠 —
        kind + 验证证据量 (strength) 决定敢不敢用。det 无条件边
        (p_ab≥0.9 且唯一结果 = 确定性知识) 恒最高置信 0.7; cond
        条件边 (受隐藏变量调制): 濒死/刚涌现 (<1.0) 重折扣 0.3,
        常规 (1.0-3.0, 测试世界稳态 ≈2.0) 0.5 (一期固定值), 充分
        验证 (≥3.0) 轻折扣 0.65。
        预测被现实反复验证 → 折扣轻 → 假设接近事实; 证伪/长期未见
        → 边衰减 → 折扣重 → 假设被弃用 — 验证回馈闭环 (RPE 预期
        违背在抽象层)。

        w_prior 自适应 (2026-08-29, 实验54): consistency 非 None
        (类别回退专用) → 折扣 × (0.5 + 0.5×consistency) — 类别内
        成员同构 (σ 小) → 类别先验可信 w→1 (折扣不变); 异质 (σ 大)
        → 保守 w→0.5 (折扣减半防误导)。实验54 H2/H3: σ_ind 大时
        类别先验误导 → 自适应退让 = 适用域边界自动规避。
        """
        if kind == 'det':
            base = 0.7
        elif strength >= 3.0:
            base = 0.65
        elif strength >= 1.0:
            base = 0.5
        else:
            base = 0.3
        if consistency is not None:
            base *= (0.5 + 0.5 * max(0.0, min(1.0, consistency)))
        return base

    def _principle_batch(self, force: bool = False):
        """DMIT 精化: 转移计数 top 候选对 → 对齐序列 → 方向边

        感知层自适应带宽 (2026-08-11, 评估硬伤2 修复): 候选窗口
        K 不固定 — 复杂世界结构词 ("我"→变 13805 次) 霸占 top40,
        真实因果对 (加柴→强 2099 次) 排 41-49 被挤出 (seed 2026
        加柴→强 不涌现, 靠研究层手工 top100 规避)。批内循环:
        精化 top K → 检查窗口边缘比 (ranked[K-1]/ranked[0], 纯
        分布信号) → 边缘无断崖则带宽加倍并精化新区间 → 循环至
        断崖/上限。感知不判定: 扩窗只扩展带宽, 因果判定仍由
        DMIT + 仲裁层; 玩具世界候选少 → 扩到全量即停, 断崖世界
        → 不扩。
        """
        from .reasoning import dmit_test  # 单一真源
        import heapq
        if len(self._principle_log) < 12:
            return
        # ── 幂等门 (2026-09-03 检验 T3 反哺实锤, 手动/自动语义对齐) ──
        # 无新观察事件时重复 batch 只对同一窗口重复回补 (recent_pairs
        # 命中 → strength+1 膨胀 = "无观察也在学"; T3 指纹门抓到研究层
        # 重复手动 batch 的隐藏路径)。自动路径靠每 batch_size 事件触发
        # 天然防同窗重跑; 手动路径无此保护。统一标记 = feed 序号
        # (_n_feed_calls 单调; _principle_log 环形裁剪后 len 不变会骗
        # 人)。force=True = 显式强制重算 (逃生口, 语义同旧行为)。
        if not force:
            _last = getattr(self, '_last_batch_n_feed', 0)
            _now = getattr(self, '_n_feed_calls', 0)
            if _last == _now:
                return
        # 槽位结构通道 (认知结构本体化): 不依赖 DMIT 的多结果因果
        self._state_cond_sweep()
        while True:
            K = self._principle_top_candidates
            # 候选 = 转移计数 top (方向性原始证据, 增量廉价)
            # 万级批次改造 (2026-08-18): heapq.nlargest 替代全量
            # sorted — 语义零变更 (都取 top K, 计数相同), 复杂度
            # O(T log K) vs O(T log T)。10000 对象档 transitions
            # ~23 万条目, 全量排序每批 2 次是超线性主犯 (3000 档
            # 排序 31% 热点, 10000 档 T×3.3 后膨胀)。
            cands = heapq.nlargest(K, self._principle_transitions.items(),
                                   key=lambda x: x[1])
            if not cands:
                return
            # 对齐序列: 最近窗口内每概念 0/1 (同一时间轴)
            # 万级改造: 原实现对每个候选词单独遍历 log (O(词数×n)
            # 成员检查, 10000 档 320 词×2000 事件×5000 批 = 32 亿次)
            # → 单次遍历 log 批量置位 (O(n×成员数), 100× 提速),
            # 结果逐位等价 (每个 (w,i) 置 1 条件相同)。
            log = self._principle_log
            n = len(log)
            wanted = set()
            for (a, b), _ in cands:
                wanted.add(a)
                wanted.add(b)
            series = {w: np.zeros(n, dtype=float) for w in wanted}
            for i, members in enumerate(log):
                for w in members:
                    if w in wanted:
                        series[w][i] = 1.0
            for (a, b), cnt in cands:
                if cnt < self._principle_min_total:
                    continue
                sa, sb = series.get(a), series.get(b)
                if sa is None or sb is None:
                    continue
                g = dmit_test(sa, sb, k=1, bins=4,
                              min_score=self._principle_min_score)
                if g['is_causal']:
                    s = g['score']
                    key = (a, b)
                    old = self._causal_edges_dmit.get(key)
                    recent_pairs = getattr(self, '_principle_recent_pairs',
                                          None)
                    if old:
                        if recent_pairs and key in recent_pairs:
                            # 最近窗口内有证据 → 回补 (用进废退)
                            strength = old['strength'] + 1.0
                            n_updates = old['n_updates'] + 1
                        else:
                            # 无最近证据 → 活性只衰减 (证据时效:
                            # 残留不维持活性, 突变后边应死亡)
                            strength = old['strength']
                            n_updates = old['n_updates']
                        self._causal_edges_dmit[key] = {
                            'score': max(abs(s), abs(old['score']))
                                     * (1 if s > 0 else -1),
                            'strength': strength,
                            'n_updates': n_updates,
                            'auto': True,
                            'p_ab': old.get('p_ab', 0.0),
                        }
                    else:
                        # 新建不拦截 (与基线一致): DMIT test 已过滤
                        # 方向性, broken 后无 (a→b) 共现 → test 不过
                        # → 不会建突变边; recent_pairs 拦截只用于
                        # 已存在边的回补 (证据时效: 残留不维持活性)。
                        self._causal_edges_dmit[key] = {
                            'score': float(s), 'strength': 1.0,
                            'n_updates': 1, 'auto': True,
                            'p_ab': 0.0,  # 由 _principle_cond_scan 回写
                        }
                # ── 条件化精化 (缺陷1): 对通过 DMIT 的边扫描条件 C ──
                # 无条件边在条件交替时被稀释 (扣球→飞/弹 都弱);
                # 条件调制测量 lift = P(B|A,C)/P(B|A) 涌现 "A→B 只在
                # C 下成立"。C = 事件流里与 A 相邻出现、显著提升 B 的
                # 概念 (状态/情境)。纯统计测量, 不写规则 (三铁律)。
                self._principle_cond_scan(a, b, log, n)
            # ── 自适应带宽 (批内循环) ──
            # 边缘比 = 窗口边缘计数 / 榜首计数: 无断崖 (后面还有
            # 同量级候选, 含被结构词挤出的真实因果对) → 带宽加倍;
            # 断崖 → 信息边界, 停止。纯分布信号, 零语义预设。
            # 万级改造: 只需边缘处 (第 K 名) 与榜首, 不必全量排序
            # — 取 K+1 名即可 (nlargest 含第 K 名计数; 若有并列
            # 取 K+1 名保证第 K 名计数不因并列截断失真)。
            if len(self._principle_transitions) <= K:
                break  # 候选耗尽 → 已全量感知
            ranked_k = heapq.nlargest(
                K + 1, self._principle_transitions.items(),
                key=lambda x: x[1])
            top1 = ranked_k[0][1]
            edge = ranked_k[K - 1][1]
            if top1 <= 0 or edge / top1 < self._principle_window_ratio_min:
                break  # 边缘计数骤降 → 真实边界
            if K >= self._principle_max_candidates:
                break
            self._principle_top_candidates = min(
                K * 2, self._principle_max_candidates)
        # ── 时间衰减 (2026-08-29 实验63 反哺, 实验41 习惯化缺口补全) ──
        # 无最近证据 (recent_pairs 窗口滚出) → score 慢衰减 (×edge_decay)。
        # 与反证衰减 (strength ×_cond_edge_decay, 985 行) 正交:
        # 前者 = 时间流逝 (环境突变后动作不再尝试 → 旧因果永不降权
        # 缺口实锤: 更新路径 1794 行注释声称 "活性只衰减 (证据时效:
        # 残留不维持活性, 突变后边应死亡)" 但实现只回补不衰减);
        # 后者 = 主动反证 (attempted 无结果)。
        # 零信息损失: 不删除边, 降权可逆 (回补路径 max(abs(s), abs(old))
        # 回升) — 实验52 可逆经济 + 实验04 遗忘曲线时间维同构。
        # 默认 1.0 = 零影响 (生产回归基线/math 不装配); fusion/eco 装配 0.95
        # + --no-edge-decay 回退。周期 = 每批 (200 事件)。
        decay = getattr(self, 'edge_decay', 1.0)
        if decay < 1.0:
            recent = getattr(self, '_principle_recent_pairs', None)
            if recent is not None:
                for (_a, _b), _m in self._causal_edges_dmit.items():
                    if (_a, _b) in recent:
                        continue
                    _s = _m.get('score', 0.0)
                    if _s != 0.0:
                        _m['score'] = abs(_s) * decay * (1 if _s > 0 else -1)
                # granger 边同款 (实验63 扩展): f_stat 只增不减
                # (max 累积) + 无证据保持 — 与 dmit score 同构缺口;
                # 时间衰减 → 联想排序 (causal_edges 合并) 新鲜因果优先;
                # strength 不动 (反证衰减已有 + 消费端活性死亡过滤)。
                for (_a, _b), _m in self._causal_edges.items():
                    if (_a, _b) in recent:
                        continue
                    _f = _m.get('f_stat', 0.0)
                    if _f > 0.0:
                        _m['f_stat'] = _f * decay
        # 幂等门收尾: 记录本批已消费的 feed 序号 (函数体成功执行完才
        # 落记 — 中途异常不消耗, 下次调用可重试)。
        self._last_batch_n_feed = getattr(self, '_n_feed_calls', 0)


    def _principle_cond_scan(self, a: str, b: str, log, cnt: int):
        """条件化精化: 对通过 DMIT 的边 (a→b) 扫描窗口找条件 C

        条件调制测量: lift = P(B|A,C) / P(B|A)
        - 窗口内统计: A 事件后下一事件含 B 的比例 (无条件基线)
        - 对每个候选 C (与 A 相邻出现的概念): A 与 C 同现时
          下一事件含 B 的比例
        - lift >= _cond_min_lift 且支持度 >= _cond_min_support
          → 条件边 (a, b, c) 写入 _causal_edges_cond

        语义: "A→B 只在 C 下成立" — 世界规则是状态依赖的,
        条件 = 状态/情境概念。纯统计测量 (感知), 不写规则不
        判定 (三铁律)。
        """
        from collections import defaultdict
        n = len(log)
        if n < 20:
            return
        # 窗口化 (2026-08-31 分层记忆第一刀 — 概念容量扩大的成本
        # 根因): 原全量扫 log (可 8000 事件 × 3919 次调用 = 1.96s
        # 热点, 概念多时 log 被高基数候选占满 → 平方级趋势)。
        # 与 _state_cond_sweep 同构 (recent_window=200): 条件调制
        # 测量 (lift = P(B|A,C)/P(B|A)) 只取最近窗口 — 语义 =
        # 近期规律 (环境漂移适应: 旧历史条件不该影响当前调制,
        # 与 sweep 证据时效同哲学)。零写只读; 支持度门槛不变
        # (窗口内 n_a 判定 — 低频边窗口内证据不足 → 不建条件边
        # = 诚实: 条件边需要近期证据支撑, 残留不维持活性)。
        recent_start = max(0, n - self._recent_window)
        # 无条件基线: P(B|A) — A 事件后下一事件含 B
        n_a = 0
        n_ab = 0
        # 候选条件: 与 A 相邻的上下文 (A 事件本身 ∪ 前一事件) 里
        # 出现的概念 — 条件=状态/情境, 先于动作存在 (状态→动作→
        # 结果), 排除 A, B 自身
        cand_counts = defaultdict(int)
        a_pos = []  # 2026-08-26 提速: a 命中位置索引 — 第二遍只遍历
        # 命中位置 (原全 n 重复判断 → len(a_pos) 10-20× 小, 同
        # _state_cond_scan 提速 B)
        for i in range(recent_start, n - 1):
            cur = log[i]
            nxt = log[i + 1]
            if a not in cur:
                continue
            a_pos.append(i)
            n_a += 1
            if b in nxt:
                n_ab += 1
            for w in cur:
                if w != a and w != b:
                    cand_counts[w] += 1
            if i > recent_start:
                for w in log[i - 1]:
                    if w != a and w != b:
                        cand_counts[w] += 1
        if n_a < self._state_cond_min_support:
            return
        p_ab = n_ab / n_a
        # 置信回写 (缺陷5): 无条件边结果概率 → 置信 = 验证×确定性
        e = self._causal_edges_dmit.get((a, b))
        if e is not None:
            e['p_ab'] = p_ab
        if p_ab < 0.1:
            return  # 无条件边太弱, 无调制意义
        # 对候选条件 C: P(B|A,C) — C 在 A 事件本身或前一事件
        # (状态先于动作), 下一事件含 B
        for c, c_cnt in cand_counts.items():
            if c_cnt < self._cond_min_support:
                continue
            n_ac = 0
            n_acb = 0
            for i in a_pos:  # 2026-08-26 提速: 索引列表遍历 (原全 n)
                cur = log[i]
                nxt = log[i + 1]
                has_c = (c in cur) or (i > 0 and c in log[i - 1])
                if not has_c:
                    continue
                n_ac += 1
                if b in nxt:
                    n_acb += 1
            if n_ac < self._cond_min_support:
                continue
            p_acb = n_acb / n_ac
            lift = p_acb / p_ab if p_ab > 0 else 0.0
            # 条件边必须确定性高: 该条件下结果几乎必然 (p_acb 高)
            # 且显著高于无条件 (lift 高) — 排除 "lift 高但两可" 伪条件
            # 证据时效回补 (2026-08-13 第六步): 同构 — 回补/新建
            # 都要最近窗口内有 (a→b) 转移; 残留不维持活性。
            recent_pairs = getattr(self, '_principle_recent_pairs', None)
            has_recent = recent_pairs is not None and (a, b) in recent_pairs
            if has_recent and lift >= self._cond_min_lift and p_acb >= 0.8:
                key = (a, b, c)
                old = self._causal_edges_cond.get(key)
                if old:
                    self._causal_edges_cond[key] = {
                        'lift': lift,
                        'strength': old['strength'] + 1.0,
                        'n_updates': old['n_updates'] + 1,
                        'p_acb': p_acb, 'p_ab': p_ab,
                        'auto': True,
                    }
                else:
                    self._causal_edges_cond[key] = {
                        'lift': lift, 'strength': 1.0,
                        'n_updates': 1,
                        'p_acb': p_acb, 'p_ab': p_ab,
                        'auto': True,
                    }

    # ══ 认知结构本体化 (2026-08-10 22:54): 状态链 + 过程推演 ══
    # 三层研究统一落地 (身份→状态维度→过程推演, 零预置贯穿):
    #   state_chain: 从状态条件边 (动作→结果|状态) 涌现状态转移链
    #   process_infer: 当前状态 + 动作序列 → 沿链逐步传播 (过程计算)
    # 对照查表 (无条件 infer) 研究层已证完全失败 → 认知≠查表;
    # 时间维度不可约 (过程推演必须沿链逐步走, 不能一步查表)。
    # 三铁律: 链构建=统计涌现 (感知), 推演=纯查询 (执行不决策)。

    # ══ T2 关系时序记忆 (2026-08-14, 用户拍板方案 a): 驻留统计通道 ══
    # 核心命题: 认知 = 概念空间中的过程计算, 时间维度不可约。
    # 缺口: 变化驱动感知下状态不变不重复断言 → 事件流无驻留时间
    # 信息 (火旺 1 回合还是 50 回合无法区分) → drift 只能事后看见。
    # 机制: EnvLoop 心跳断言 (heartbeat_interval>0) 周期性重断言
    # (obj,在,状态) → 驻留间隔进事件流; 本通道扫描 '在' 断言串
    # (确认) 统计驻留分布, 串尾状态切换 (自然灭的 (在,灭) 或动作
    # 灭的 (变,灭)) = 转移 → 自转移边 (X→Y, dwell 分布) 从统计
    # 涌现 — 时间延迟=条件维度 (呼应 MES 相位, 时间进状态空间)。
    # 三铁律: 纯统计测量 (感知层穷举采集信号), 不写语义不判定;
    # 消费端 (仲裁/规划) 自行读 dwell 分布。无心跳 → '在' 串长
    # 全 1 → 无自转移边涌现 (零破坏, 默认路径一字不动)。
        # identity_learn (2026-08-30): 对象身份分裂检测 (批次末尾 —
        # _state_trans_dist 本轮已更新完, 信号完整)
        if self._id_sigs:
            self._maybe_split_identity()
    def _dwell_scan(self, obj: str, min_dwell: int = 2,
                    min_count: int = 2) -> Dict[Tuple[str, str], dict]:
        """驻留统计: 扫描事件流 '在' 断言串 → 自转移边 (X→Y)

        模式: 同一对象同一状态的连续 '在' 断言 = 驻留段 (含变化
        驱动首次断言 + 心跳重断言); 段尾状态切换 = 转移; 段长 =
        驻留回合数 (断言计数)。只认 '在' 串 (确认) — 变事件
        (转移) 是串尾信号不是驻留 (确认 vs 转移区分, 加固点1)。
        涌现阈值: 驻留 ≥2 断言 (≥1 次心跳) + 转移 ≥2 次 (防偶然)
        → 短暂状态 (亮 1 回合) 不涌现, 驻留状态 (旺 50 回合) 涌现。
        """
        seq = []
        for r in self._principle_log:
            if (r and len(r) >= 3 and r[0] == obj
                    and r[1] in ('在', '变')):
                seq.append((r[1], r[2]))
        trans: Dict[Tuple[str, str], list] = {}
        cur = None
        dwell = 0
        for kind, s in seq:
            if kind == '在':
                if s == cur:
                    dwell += 1          # 同状态连续断言: 驻留延长
                else:
                    if cur is not None and dwell >= 1:
                        m = trans.setdefault((cur, s), [0, []])
                        m[0] += 1
                        m[1].append(dwell)  # 串尾切换 = 转移
                    cur = s
                    dwell = 1
            else:  # '变' (动作结果转移)
                if cur is not None and dwell >= 1:
                    m = trans.setdefault((cur, s), [0, []])
                    m[0] += 1
                    m[1].append(dwell)
                cur = s
                dwell = 0
        edges: Dict[Tuple[str, str], dict] = {}
        for (x, y), (cnt, dwells) in trans.items():
            dm = sum(dwells) / len(dwells)
            if dm >= min_dwell and cnt >= min_count:
                # 延迟=条件维度: 驻留分布 (统计结构, 非数值字段)
                edges[(x, y)] = {'count': cnt, 'dwell_mean': dm,
                                 'dwell_max': max(dwells)}
        return edges

    # (归档 2026-08-16: self_transitions → _archive_legacy/dead_interfaces_20260816.py)

    # (归档 2026-08-16: dwell_predict → _archive_legacy/dead_interfaces_20260816.py)
