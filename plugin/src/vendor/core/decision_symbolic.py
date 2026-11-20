"""符号决策统一函数: decide_symbolic + learn_from_result (概念层)

黄金骨架 (2026-08-14): 内核统一函数活集之一 — 从 tasks/decision.py
抄活不抄死: 只提取纯符号路径 (plan_state/process_infer 查询 + observe
回灌), 向量侧 (torch/预测引擎) 不进内核。

机制 (行为闭环, 概念层符号级直接驱动行为):
  1. plan_state (过程计算): 目标 → 最少步动作序列
     (冷→沸 = [加热,加热,加热], 中间态 温/热 显式)
  2. known → 取第一步执行; 记录预期结果 (process_infer 首步结果)
     供 learn_from_result 回灌对比
  3. 无规划 → 探索 (返回 None, 上层随机/向量级兜底)

三铁律: 纯查询 (plan_state/process_infer 零写); 决策只选动作不执行;
执行后由 learn_from_result 观察回灌 (感知层写)。

context: 关联对象状态对 (世界模型, 2026-08-13) — 透传; None 零破坏。
"""
from typing import Optional, Sequence, Tuple


class SymbolicDecision:
    """符号决策引擎: 概念层直连, 零向量翻译, 单一真源"""

    def __init__(self, concept_space=None):
        self.concept_space = concept_space
        self._prev_symbolic = None  # (obj, act, expected_result, cur)

    def decide_symbolic(self, obj: str, goal: str,
                        current: Optional[str] = None,
                        explore_rate: float = 0.1,  # 半成品: 探索实际由 novelty_scan 驱动, 本参数未用 (标注勿删)
                        context: Optional[Sequence[Tuple[str, str]]] = None,
                        expect_conf: Optional[object] = None,
                        expect_gate: float = 0.3,
                        keep_all: bool = False
                        ) -> dict:
        """符号级决策: 概念层 plan_state 规划 → 选第一步动作

        expect_conf/expect_gate (M5b 元预期调制, 2026-08-20):
        expect_conf = 回调 (obj, act, state) → 预期可靠性置信度
        (元预期读数, 见 EmergenceEngine.expectation_confidence);
        路径每步 (状态, 动作) 查置信度 < gate → 计划降级为探索
        (is_explore=True) — 低置信预期边不值得执行, 倾向探索新
        路径 (统计前置: 系统自己判断"这条路不可靠")。
        expect_conf=None → 零破坏 (原逻辑一字不动)。

        Returns:
            {'act': str, 'expected': str|None, 'known': bool,
             'plan': [..], 'is_explore': bool, 'reason': str}
        """
        if self.concept_space is None:
            return {'act': None, 'expected': None, 'known': False,
                    'plan': [], 'is_explore': True,
                    'reason': 'no concept_space'}
        plan = self.concept_space.plan_state(obj, goal, current=current,
                                             context=context,
                                             keep_all=keep_all)
        # 联合状态回退 (多目标世界, 2026-08-13): 单目标无解且
        # 有关联对象时 → 联合空间 BFS (火灭时泪=冷 → 加柴→旺
        # 是子目标, 从过程涌现) — context=None 时 plan_multi
        # 内部退回 plan_state, 零破坏
        if not plan.get('known') and context:
            plan = self.concept_space.plan_multi(obj, goal,
                                                 current=current,
                                                 context=context,
                                                 keep_all=keep_all)
        # 已达成目标 (plan=[] 但 known=True): 无动作需要 — '我已在
        # 目标' 不是 '我不知道怎么做' (2026-08-13 阶段C 接线): 否则
        # current==goal 恒 known=False → 恒探索 → 二阶 pf 读数被
        # 已达成态污染 (排球稳态 pf≈0.5 → confused 边缘误触发)
        if plan.get('known') and not plan.get('plan'):
            return {'act': None, 'expected': None, 'known': True,
                    'plan': [], 'is_explore': False,
                    'reason': 'goal_reached'}
        if not (plan.get('known') and plan.get('plan')):
            # 记忆候选 (阶段 C, 2026-08-16): 规划无解 + 影子有相似
            # 情境历史动作倾向 → 诚实标注的探索候选 (试错由 RPE
            # 修正, 候选来自真实历史后续, 有统计依据; 记忆只做候选
            # 采证, 判定在仲裁层)。无记忆 → 原样返回 (零破坏)。
            # ★ LLM 臂介入 (路线 3, 2026-09-24): 离散无解时问外部 LLM
            # LLM 候选与记忆候选同级 — 都是探索级, 不设预期。
            # gated: LLM_ARM=1 启用; 默认关已验证逐位不变。
            from core.llm_arm import suggest as llm_suggest
            llm_sugg = llm_suggest(
                obj=obj, goal=goal, current=current,
                world_name=getattr(getattr(self, 'concept_space', None),
                                   '_world_name', ''),
                actions=list(getattr(getattr(self, 'concept_space', None),
                                      '_obj_actions', {}).get(obj, []))
                if hasattr(getattr(self, 'concept_space', None),
                           '_obj_actions') else None,
            )
            if llm_sugg and llm_sugg.get('act'):
                return {'act': llm_sugg['act'],
                        'expected': None, 'known': False,
                        'plan': [], 'is_explore': True,
                        'reason': f"LLM 候选: {llm_sugg.get('reasoning', '')}",
                        'llm_conf': llm_sugg.get('confidence', 0.0)}
            mem = plan.get('memory_evidence')
            if mem and mem.get('actions'):
                act, conf = mem['actions'][0]
                # 探索路径不设预期 (RPE 注释: 无预期不接线) —
                # 记忆候选 = 试错探索, 结果由 RPE/事件流自然修正
                return {'act': act, 'expected': None, 'known': False,
                        'plan': [], 'is_explore': True,
                        'reason': f"记忆候选: 相似情境 {mem['similar']} 个, "
                                  f"历史倾向 '{act}'"}
            # 统计候选 (第三消费端, 2026-10-03): result_dist 可靠性
            # 接进选择 — 规划/记忆都无解但 (obj,current,act) 历史分布
            # 里有动作多数能到 goal → 按 P(goal|current,act) 选最优。
            # 依据: focus_decision_layer_probe_20261003 实测 — 可靠性
            # 此前只用于分布判定/不确定性 (第一/二消费端), 从不用于
            # 选择 ⇒ E3/E4/E5 全 FAIL; 根因 = 消费缺口非表示缺口。
            # 门槛 n>=3 且 p_goal>0.5; 无达标动作 → 维持原探索回退
            # (零破坏: 只替换原本的纯随机兜底)。设预期=goal (RPE
            # 接线)。注: 分布为全历史累积 (_state_trans_dist 只增不
            # 删), 漂移世界下可能偏旧 — 仅作兜底候选, 低置信不推。
            if current and self.concept_space is not None:
                best = None
                for (_o, _c, _a) in getattr(
                        self.concept_space, '_state_trans_dist', {}):
                    if _o != obj or _c != current:
                        continue
                    d = self.concept_space.result_dist(current, _a,
                                                       obj=obj) or {}
                    n = sum(d.values())
                    p_goal = (d.get(goal, 0) / n) if n else 0.0
                    if n >= 3 and p_goal > 0.5 and (best is None
                                                   or p_goal > best[1]):
                        best = (_a, p_goal, n, d)
                if best:
                    _act, _p, _n, _d = best
                    self._prev_symbolic = (obj, _act, goal, current)
                    return {'act': _act, 'expected': goal, 'known': False,
                            'plan': [], 'is_explore': False,
                            'reason': f'统计候选: P({goal}|{current},{_act})='
                                      f'{_p:.2f} (n={_n})',
                            'source': 'result_dist', 'dist': _d}
            return {'act': None, 'expected': None, 'known': False,
                    'plan': [], 'is_explore': True,
                    'reason': plan.get('reason', 'unplanned')}
        seq = plan['plan']
        act = seq[0]
        # 预期结果: process_infer 首步实际转移 (冷─加热→温)
        exp = self.concept_space.process_infer(obj, seq, state=current,
                                               context=context,
                                               keep_all=keep_all)
        path = exp.get('path', [])
        expected = path[0][2] if path else None
        # M5b 元预期调制 (2026-08-20): 路径每步预期置信度 < gate →
        # 计划降级探索 — 系统自己判断"这条路不可靠, 不走了"
        # (统计前置)。默认信任: 置信度 None (样本不足) → 不降级
        # (截断器, 防冷启动瘫痪)。纯读数零写。
        if expect_conf is not None:
            for (s, a, _nxt) in path:
                c = expect_conf(obj, a, s)
                if c is not None and c < expect_gate:
                    return {'act': None, 'expected': None,
                            'known': False, 'plan': [],
                            'is_explore': True,
                            'reason': f"元预期: {s}─{a} 置信 {c:.2f} < {expect_gate}, 降级探索"}
        # 结果分布 (2026-08-20 立项 D1): (current, act) → 全结果计数
        # 分布预期消费端用: 随机世界多结果 → 预期升级为分布判定
        # (violated = 结果不在高概率集); 确定性世界单点 → 消费端
        # 退化原判定 (逐位等价)。三铁律: 纯读数, 判定在消费端。
        dist = {}
        if current and act:
            dist = self.concept_space.result_dist(current, act, obj=obj) or {}
        self._prev_symbolic = (obj, act, expected, current)
        return {'act': act, 'expected': expected, 'known': True,
                'source': 'state_chain',
                'plan': seq, 'is_explore': False, 'reason': '状态链规划',
                'dist': dist,
                # 透传 (2026-08-30, 计划意图): path = 状态序列
                # (冷→温→热→沸, 执行监控推进依据), conf = 计划置信
                # — 只读附加, 既有消费端零变化。
                'path': exp.get('path', []),
                'conf': plan.get('conf', 0.0)}

    def learn_from_result(self, is_novel: bool = False,  # 半成品: 新颖性判定归相位场/仲裁层, 本参数未用 (标注勿删)
                          actual: Optional[str] = None,
                          obj: Optional[str] = None,
                          act: Optional[str] = None,
                          cur: Optional[str] = None,
                          observe: bool = True) -> dict:
        """从行动结果中学习: 概念层回灌 (观察实际结果事件)

        actual/obj/act/cur 提供时: 观察实际结果事件 (感知层写),
        预期违背 (actual != expected) 自然进入事件流, 由周期性巩固
        代谢 (证据时效) 学会新规则。三铁律: 只 observe 写事件,
        不直接改概念层判定。

        observe=False: 调用方 (EnvLoop) 已完整编码事件流 — 再观察
        (我,act,obj) 双轨会把对象名灌进状态词集 (级联世界 per_a
        多结果 → 确定性边死), 且 observe('变') 无 new==prev 拦截。
        默认 True 零破坏。

        纪律: observe('是'/'我') 无条件 (状态与动作始终真实发生),
        只有 observe('变') 受 actual 保护 (动作不可用时无结果,
        避免 '变 None' 污染事件流)。无条件'是'断言 = 无效动作证据
        (状态未变也真实发生) → 事件流持续滚动 → log 窗口按时间
        流逝 → 旧证据被挤出 → 证据时效代谢 (规则突变后旧链死亡)。
        """
        if observe and (self.concept_space is not None and obj is not None
                        and act is not None):
            if cur is None and self._prev_symbolic:
                cur = self._prev_symbolic[3]
            if cur is not None:
                # 环境状态断言 (env): 对象实际状态 → 环境事件节律
                self.concept_space.observe(obj, '是', cur, channel='env')
            # 行为者执行动作 = 观察/行为事件 (obs): 不进节律
            # (行为者每步执行 ≠ 环境出现, 污染则 interval→1 →
            #  调度/监控基准失真 — 装配层实锤)
            self.concept_space.observe('我', act, obj, channel='obs')
            if actual is not None:
                # 环境状态变化 (env): 实际结果 → 环境事件节律
                self.concept_space.observe(obj, '变', actual,
                                           channel='env')
        # R16 接线 (2026-08-15): 决策环预期违背 → 内分泌闭环
        # 复用 infer_feedback: 预期 = _prev_symbolic 记录的 expected
        # (process_infer 首步转移), 实际 = actual. actual==expected →
        # 命中→内啡肽 (搞懂了); actual!=expected → 落空→多巴胺 RPE
        # 调制+探索欲 (好奇继续学). 三铁律: 只操作能量池 (动机信号),
        # 不创建概念不写状态. 零破坏: 无预期 (探索/is_novel 路径
        # _prev_symbolic=None) 或无实际 (无效动作) 不接线.
        prev = self._prev_symbolic
        pred_err = 0.0
        if (prev is not None and actual is not None
                and self.concept_space is not None):
            expected = prev[2]
            if expected is not None:
                self.concept_space.infer_feedback(
                    [actual], {'predictions': [(expected, 1.0)]})
                # A19 死信道修复 (2026-11-05): prediction_error 真算
                # (预期≠实际=1.0)；原恒 0 会被下游误当核验信号
                pred_err = 0.0 if actual == expected else 1.0
        self._prev_symbolic = None
        # reward: 本层无奖励信道，占位恒 0——勿当奖励/核验信号用
        # （A19 体检: 内部核验不可辨识）；任务奖励走独立反馈口
        # feedback()，且核验源须与触发源不同源
        return {'evaluation': {'reward': 0.0, 'prediction_error': pred_err},
                'concept_feedback': True}

    def get_stats(self) -> dict:
        return {'symbolic': True}
