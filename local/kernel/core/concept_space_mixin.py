#!/usr/bin/env python3
"""
core/concept_space.py — ConceptSpace space 子模块 (mixin)

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


class ConceptSpaceSpaceMixin:
    def causal(self, src: Optional[str] = None,
               tgt: Optional[str] = None,
               top_k: int = 10) -> List[Tuple[str, str, float]]:
        """查询因果边 (有向): 谁 影响 谁

        src 给定 → 该源的全部出边 (按 f 降序)
        tgt 给定 → 指向该目标的入边
        都 None → 全部因果边按 f 降序

        granger 边 (f_stat) 与 dmit 边 (score) 合并返回:
        granger 优先 (同一对存在 granger 边则只返回它),
        dmit 边作为补充 (score 绝对值降序)。
        """
        out = []
        seen = set()
        for (s, t), meta in self._causal_edges.items():
            if meta.get('strength', 1.0) < self._cond_edge_dead:
                continue  # K4: granger 边证据过期 (活性死亡) — 消费端过滤
            if src is not None and s != src:
                continue
            if tgt is not None and t != tgt:
                continue
            out.append((s, t, meta['f_stat']))
            seen.add((s, t))
        for (s, t), meta in self._causal_edges_dmit.items():
            if (s, t) in seen:
                continue  # granger 优先
            if meta.get('score', 0) <= 0:
                continue  # 反向记录 (score<0) 不当作正向因果边
            if src is not None and s != src:
                continue
            if tgt is not None and t != tgt:
                continue
            out.append((s, t, meta['score']))
        out.sort(key=lambda x: -abs(x[2]))
        return out[:top_k]
    EDGE_KINDS = ('granger', 'dmit', 'cond', 'state_cond', 'state_det')

    # (归档 2026-08-16: all_edges → _archive_legacy/dead_interfaces_20260816.py)

    # ── 概念先到: 从观察涌现类型 ─────────────────────────

    def _explore_scale(self, *members) -> float:
        """候选① 延伸: 执行层消费 — 事件成员的注意增益 (explore 建议)

        元认知 explore 建议 (高档独立新类, _novelty_attention 增益>1)
        是决策依据候选; 执行层 (observe) 消费它: 事件含 explore 概念时
        coupling 力度 × 增益 (注意资源倾斜, 让新类更快融入相位场)。
        三铁律: 执行不决策 — 增益由器官/元认知已算好, 这里只执行;
        非暴力: 只调相位动力学, 不写 types/语义网络。
        无 explore 成员 → 返回 1.0 (零破坏)。
        """
        if not self._novelty_attention:
            return 1.0
        gains = [self._novelty_attention[m] for m in members
                 if m in self._novelty_attention]
        return max(gains) if gains else 1.0


    def _focus_scale(self, *members) -> float:
        """意识阶段D 消费端 (2026-08-13): 全局焦点 → 注意资源倾斜

        GWT 意识核心功能: 焦点 = 处理资源分配 — '当下' (相位场同步∧
        新鲜区成员, 时空结构涌现) 参与的事件耦合力度增强, 焦点概念
        更快巩固。只读读数零写 (phase._focus_members 轻量 O(n), 高频
        可调); 默认关 (focus_gain_scale=0) / 无焦点 → 1.0 (零破坏)。
        三铁律: 执行不决策 — 焦点是读数 (阶段D), 倾斜是执行层资源
        分配, 不写语义不产判定。与 _explore_scale (元认知建议) /
        explore_drive (内分泌注意) 并列 — 三个信号源不同 (读数/
        判定/激素), 消费端同为耦合力度, 相乘叠加。
        """
        if getattr(self, 'focus_gain_scale', 0.0) <= 0:
            return 1.0
        _f = getattr(self, '_focus_members', None)
        if _f is None:
            return 1.0
        _focus, _members, _, _ = _f()
        if _focus is None:
            return 1.0
        if any(m in _members for m in members):
            return 1.0 + self.focus_gain_scale
        return 1.0


    def remember(self, time: str, person: str, action: str,
                 obj: Optional[str] = None, place: Optional[str] = None):
        """记录情景事件: 何时/谁/做什么/对什么/在哪 (时间轴日志)

        ⚠️ 归位标注 (2026-08-16 记忆盘点): V2 旧设计 (符号字符串字段,
        非向量侧)。生产主链零消费 — 记忆主线 = observe 六路写入
        (events 计数/event_stream 真源/emergence/MES/RPE/边表)。
        保留原因: verify_global_focus G9/G9b (阶段 D 意识焦点锚定
        记忆检索) 验证路径依赖 — 实验/验证专用, 归档候选。

        认知依据: Tulving 情景记忆 = 海马体, 与语义记忆分开编码;
        标准巩固模型 (Squire): 海马体反复编码 → 前颞叶语义化
        """
        self.episodes.append({
            "time": time, "person": person, "action": action,
            "obj": obj, "place": place,
        })
        self.types[person].add(PERSON)
        self.types[action].add(ACTION)
        if obj:
            self.types[obj].add(OBJECT)
        if place:
            self.types[place].add("地点")
        return self


    def recall(self, person: Optional[str] = None,
               action: Optional[str] = None,
               time: Optional[str] = None,
               place: Optional[str] = None,
               top_k: int = 10,
               focus_anchor: bool = False) -> List[dict]:
        """回溯: 按条件过滤情景事件 (海马体重放)

        ⚠️ 归位标注 (2026-08-16 记忆盘点): 同 remember — V2 旧设计,
        生产零消费, 实验/验证专用 (verify_global_focus 阶段 D 验证路径), 归档候选。

        focus_anchor (2026-08-13 阶段D 消费端): 无过滤条件时以全局
        焦点为检索锚 — 先想焦点相关的事 (意识焦点引导记忆检索,
        情境相关回忆优先; GWT: 广播内容也组织记忆提取)。
        焦点概念匹配事件任一角色位 (person/action/obj/place);
        锚定不足 → 回退最近事件 (时间维度: 焦点不在就最新)。
        默认 False: 历史行为一字不动 (零破坏)。
        """
        out: List[dict] = []
        if focus_anchor and not any((person, action, time, place)):
            gf = getattr(self, 'global_focus', None)
            gf = gf() if callable(gf) else gf
            anchor = gf.get('focus') if isinstance(gf, dict) else None
            if anchor:
                for ep in self.episodes:
                    if anchor in (ep['person'], ep['action'],
                                  ep['obj'], ep['place']):
                        out.append(ep)
                        if len(out) >= top_k:
                            return out
            for ep in reversed(self.episodes):
                if ep not in out:
                    out.append(ep)
                    if len(out) >= top_k:
                        break
            return out
        for ep in self.episodes:
            if person and ep["person"] != person:
                continue
            if action and ep["action"] != action:
                continue
            if time and ep["time"] != time:
                continue
            if place and ep["place"] != place:
                continue
            out.append(ep)
            if len(out) >= top_k:
                break
        return out


    def consolidate(self, threshold: int = 3,
                    rhythm: bool = False):
        """固化: 重复情景 (>=threshold 次同人同动作) → 语义记忆

        ⚠️ 已归档 (2026-08-16, 用户拍板 O3 选 A): 复制式固化
        (重复情景→语义) 违例定稿铁律⑤ (巩固=时间展开非复制);
        输入源 episodes 生产零写入 (V2 旧设计实验专用) → 恒空转。
        通道移除: 睡眠主力 = phase_reconsolidate (全部共现重放
        →相位再同步, 时间展开)。保留本方法为 sleep 接口占位
        (三铁律不破坏), 恒返回 0。

        (原实现) 语义化粒度: 人+动作 ("国见会扣球"), 不看具体对象
        rhythm (纯加法): 学习-巩固节律 (spike_hyst_v2 抗垄断) —
        垄断时抑制最高频概念固化 — 随通道一并归档。
        """
        return 0


    def sleep_pressure(self) -> float:
        """蓝图 M3 睡眠压力读数 (只读信号, 零副作用)

        连续浓度 [0,1]: observe 累积 (未沉淀的编码负担), sleep() 释放。
        行为从信号涌现: 压力高 = 该整合了 (睡眠节律触发), 不代行决策
        (三铁律: 执行不决策 — 何时睡由调用方/节律定, 信号只表达)。
        """
        return round(self._sleep_pressure, 4)


    def sleep(self, rounds: int = 5, threshold: int = 3,
              cooldown: Optional[bool] = None) -> dict:
        """蓝图 M3 睡眠/离线整合节律: 白天积累 → 夜间沉淀

        时间维度不可约: 整合必须发生在积累之后, 不是同步。
        consolidate (情景→语义) + phase_reconsolidate (全部共现重放
        →相位再同步) = 一次夜间沉淀; 完成后睡眠压力释放 (负反馈)。

        M4 中期抑制接线 (2026-08-16): 睡眠=长会话生命周期节点,
        沉淀同时扫冷概念 (cooldown_scan) — 长期未激活且能量低 →
        抑制态 (给活跃概念腾资源); 活跃概念豁免 (用进即活跃)。
        cooldown=None → 跟随 cooldown_observe_enabled (同一能量池
        语义); 默认关 → 跳过, 逐位不变。

        三铁律: sleep 只做整合 (机制层), 不代行获取/判定;
        无事件 → 空整合 (压力不释放, 没睡够/没可沉淀)。
        """
        n_cons = self.consolidate(threshold=threshold)
        n_replay = self.phase_reconsolidate(top_n=None, rounds=rounds)
        # M4 中期抑制 (2026-08-16 接线): 睡眠=长会话生命周期节点 → 扫冷概念
        # cooldown=None → 跟随 cooldown_observe_enabled (同一能量池语义);
        # 默认关 (cooldown_observe_enabled=False) → 跳过, 逐位不变
        n_cooldown = 0
        n_restored = 0
        if cooldown is None:
            cooldown = self.cooldown_observe_enabled
        if cooldown:
            n_cooldown = self.cooldown_scan()
            # ④ 状态复用闭环修复 (2026-08-22, 用户拍板): restore_phase
            # 零调用者 = 被冷却概念永久停在抑制态 (anti_phase_until
            # 永不过期清理, for_steps=10 后无人恢复 — 实测 2000 步
            # 抑制 7 概念 0 恢复实锤)。此处补过期恢复: 睡眠节点扫
            # anti_phase_until, 已过期 (> 当前步) 概念 restore_phase
            # (恢复原相位 + 清标志) → 生命周期闭环: 冷却→抑制→恢复。
            # 与 cooldown_scan 同受 cooldown 开关门控 (默认 True),
            # 纯增量无新开关。语义: 冷却的抑制是“短时避让”不是死亡。
            _expired = [c for c, until in self._anti_phase_until.items()
                        if until <= getattr(self, '_n_phase_steps', 0)]
            for c in _expired:
                self.restore_phase(c)
                n_restored += 1
        # A1 概念死亡扫描 (2026-08-19, 默认关=零破坏): 睡眠=长会话生命
        # 周期节点 → 死亡层 (冻结可重激活, 与冷却同读数两档尺度)
        n_death = 0
        if self.concept_death_enabled:
            # λ 内容层 (2026-08-25): λ/基准 比例 → T_life 缩放;
            # 无 λ 读数/基准 → 1.0 (零影响, 逐位等价)
            _lscale = None
            _dl = getattr(self, 'death_lambda', None)
            _dlr = getattr(self, 'death_lambda_ref', None)
            if _dl is not None and _dlr not in (None, 0.0):
                _lscale = _dl / _dlr
            n_death = self.death_scan(
                death_horizon_steps=getattr(self, 'life_horizon', None)
                or 2000,  # D6 时间维 (2026-08-27): --life-horizon 独立控 T_life, 默认 2000 魔数逐位不变
                theory_calibrated=getattr(self, 'death_theta', None) is not None,
                theta=getattr(self, 'death_theta', None) or 0.05,
                lambda_scale=_lscale)
        # T3: 累计产出计数 (纯记录, 元认知可读)
        self._consolidated_total += n_cons
        self._replayed_total += n_replay
        self._cooldown_total += n_cooldown
        self._death_total += n_death
        if self.events or self.episodes:
            self._sleep_cycles += 1
            self._sleep_pressure = 0.0  # 负反馈: 沉淀完成 → 压力释放
        return {'consolidated': n_cons, 'replayed': n_replay,
                'cooldown': n_cooldown, 'restored': n_restored,
                'death': n_death, 'cycle': self._sleep_cycles}
    def goal(self) -> Optional[dict]:
        """蓝图 M2 内生日标读数 (只读信号, 零副作用)

        目标 = 探索欲锁定 (attention_target) 的时间累积形态:
        持续多轮未达成 → 强度上升 (想要多久 = 多强的方向);
        达成 (内啡肽盖章) → 解除。返回:
          {target, strength, hold, coherence, solved} 或 None (无方向)。
        三铁律: 目标只表达方向, 不代行行为 (执行不决策)。
        """
        if self._attention_target is None or self._goal_strength <= 0:
            return None
        return {
            'target': self._attention_target,
            'strength': round(self._goal_strength, 3),
            'hold': self._goal_hold,
            'coherence': round(self.coherence_of(self._attention_target), 3),
            'solved': len(self._goal_history),
        }


    # (归档 2026-08-16: goal_history → _archive_legacy/dead_interfaces_20260816.py)


    # @deprecated — 接口预留 (ee9b601 设计): 情景记忆时间轴只读查询, 问答/决策未消费
    def timeline(self) -> List[str]:
        """时间轴概览 (按记录顺序)"""
        return [f"{ep['time']}: {ep['person']}{ep['action']}"
                f"{ep['obj'] or ''}@{ep['place'] or '?'}"
                for ep in self.episodes]

    # ── 概念空间推理 (第十九课): 借同类/联想链/组合 ───────

# 2026-08-17 决策(用户拍板): 不接 — 目标=表达层(说人话)非问答。
    #   价值实证: 冷门规则+借同类查询 (deduce 死角, 实验已证); 但规模下
    #   泛化不稳 (相位门控切断异相路径 + hub 概念串扰), 接需先解 gate/hub。
    #   与 deduce 互补不重复 (时序 vs 主体查询); 预留: 表达层内容源需要时再评估。
    def borrow(self, subj: str, qtype: str = "动作",
               top_k: int = 3) -> Tuple[Optional[List[str]], str]:
        """借同类概念: 找同类型 + 联想最强 的有知识邻居

        认知依据: 判别性泛化 — 见过"国见扣球", 问"小林做什么"
        → 借同为人物/攻手且联想最强的邻居 (国见) 的事件知识
        """
        my_type = self.type_of(subj)
        if not my_type:
            return None, "陌生概念"
        candidates = []
        for other, types in self.types.items():
            if other == subj or my_type not in types:
                continue
            strength = 0.0
            _subj_m = self._id_main(subj)
            for (f, rel, t), s in self.edges.items():
                if (f == subj or f == _subj_m) and (t == other):
                    strength += s
                elif (f == other) and (t == subj or t == _subj_m):
                    strength += s
            has_knowledge = any(e[0] == other for e in self.events)
            if has_knowledge:
                candidates.append((strength, other))
        if not candidates:
            return None, "无同类知识邻居"
        candidates.sort(key=lambda x: -x[0])
        best = candidates[0][1]
        if qtype == "动作":
            acts = sorted({e[1] for e in self.events
                           if e[0] == best})[:top_k]
        else:
            acts = sorted({e[2] for e in self.events
                           if e[0] == best and e[2]})[:top_k]
        return acts, f"借同类概念{best}({self.type_of(best)})"


# 2026-08-17 决策(用户拍板): 不接 — 目标=表达层(说人话)非问答。
    #   价值实证: 冷门规则+借同类查询 (deduce 死角, 实验已证); 但规模下
    #   泛化不稳 (相位门控切断异相路径 + hub 概念串扰), 接需先解 gate/hub。
    #   与 deduce 互补不重复 (时序 vs 主体查询); 预留: 表达层内容源需要时再评估。
    def infer_chain(self, subj: str, top_k: int = 3
                    ) -> Tuple[Optional[List[str]], str]:
        """联想链推理: 借不了同类 → 激活扩散找动作"""
        assoc = self.associate(subj, hops=2, top_k=10)
        acts = [c for c, s, r in assoc if "动作" in self.type_of(c)]
        if not acts:
            return None, "联想无动作"
        return acts[:top_k], "联想链"


# 2026-08-17 决策(用户拍板): 不接 — 目标=表达层(说人话)非问答。
    #   价值实证: 冷门规则+借同类查询 (deduce 死角, 实验已证); 但规模下
    #   泛化不稳 (相位门控切断异相路径 + hub 概念串扰), 接需先解 gate/hub。
    #   与 deduce 互补不重复 (时序 vs 主体查询); 预留: 表达层内容源需要时再评估。
    def infer_compound(self, word: str, top_k: int = 3
                       ) -> Tuple[Optional[List[str]], str]:
        """组合推理: 新词 → 借部件字义 → 推断"""
        wholes = set()
        for ch in word:
            for w in self.wholes_of.get(ch, set()):
                wholes.add(w)
        if not wholes:
            return None, "部件无整词"
        ranked = sorted(wholes, key=lambda w: -self.entrenchment(w))
        return ranked[:top_k], "借部件字义"

    # ── 机制化: 运行模式统一 (第二十三课) ────────────────

# 2026-08-17 决策(用户拍板): 不接 — 目标=表达层(说人话)非问答。
    #   价值实证: 冷门规则+借同类查询 (deduce 死角, 实验已证); 但规模下
    #   泛化不稳 (相位门控切断异相路径 + hub 概念串扰), 接需先解 gate/hub。
    #   与 deduce 互补不重复 (时序 vs 主体查询); 预留: 表达层内容源需要时再评估。
    def propagate(self, subj: str, qtype: str = "动作",
                  depth: int = 3, threshold: float = 0.0,
                  top_k: int = 3,
                  gate: Optional[float] = 0.8,
                  time_sliced: bool = False,
                  causal_boost: Optional[float] = None,
                  category_jump: bool = False,
                  dynamic_routing: bool = False,
                  routing_k: float = 0.5,
                  phase_source: Optional[str] = None) -> Tuple[Optional[List[str]], str]:
        """一种激活传播机制, 两种运行模式 (System 1/2 是同一网络的
        两种运行状态, 参数差异非两条路径)

        自动 (反射): 候选激活强度 > threshold → 直接输出
        受控 (思考): 激活不足 → 抑制 → 借同类/联想链/组合;
                     结果回写 (Hebbian) → 下次自动

        gate: 相位门控 (spike_couple 系列, 纯加法):
          - None  = 无门控, 行为与历史一致 (显式关闭, 对抗场景降级保护)
          - 0-1   = 传播时只沿相位相干边扩散 (CTC 语义):
                    绝对相位差相干度 < 1.0-gate 的边不参与传播
                    gate=0.8 → 放行 coh≥0.2 (同步概念优先)
          - 无相位信息的概念对 = 放行 (无增益, 退回默认)

        causal_boost (2026-08-09 推理攻坚, 默认 None=历史行为):
          因果边顺流增益 — 沿 granger 检出的因果方向 (src→tgt) 传播时
          激活 ×(1+boost); 逆流 (tgt→src) 不增益。
          同时消费 DMIT 边 (_causal_edges_dmit): 稀疏流方向性
          (证明流操作链) 同样顺流增益 — 两种测量单位一个消费端。
          推理涌现: 因果链 S→A→B→C 沿时间箭头自然加速,
          反向 (结果→原因) 保持基线。boost=None 逐位不变。

        认知依据: Kahneman 双过程理论 — 非两个模块;
        前额叶执行网络 = 操作者 (第十九课)
        """
        # ── 自动模式: 激活扩散找候选, 强度够直接输出 ──
        cands = self._spread(subj, qtype, depth=depth, gate=gate,
                             time_sliced=time_sliced,
                             causal_boost=causal_boost,
                             category_jump=category_jump,
                             dynamic_routing=dynamic_routing,
                             routing_k=routing_k,
                             phase_source=phase_source,
                             top_k=top_k)
        if cands and cands[0][1] > threshold:
            return [c for c, _ in cands[:top_k]], "自动(激活足够)"
        # ── 受控模式: 抑制 → 借同类 → 联想链 → 组合 ──
        acts, how = self.borrow(subj, qtype, top_k)
        if acts:
            return acts, f"受控(借同类:{how})"
        acts, how2 = self.infer_chain(subj, top_k)
        if acts:
            return acts, f"受控(联想链:{how2})"
        if len(subj) >= 2:
            acts, how3 = self.infer_compound(subj, top_k)
            if acts:
                return acts, f"受控(组合:{how3})"
        return None, "无路径"

    SEMANTIC_RELS = {"执行", "执行者", "对象", "被", "同类", "喜欢", "讨厌",
                     "讨厌者"}
    # 结构边 (字形/命名) 不参与语义扩散: 组成/属于 = 字形结构,
    # 命名/所指 = 词↔概念标签 — 扩散过去是字面联想不是语义联想
    STRUCTURAL_RELS = {"组成", "属于", "命名", "所指"}


# 2026-08-17 决策(用户拍板): 不接 — 目标=表达层(说人话)非问答。
    #   价值实证: 冷门规则+借同类查询 (deduce 死角, 实验已证); 但规模下
    #   泛化不稳 (相位门控切断异相路径 + hub 概念串扰), 接需先解 gate/hub。
    #   与 deduce 互补不重复 (时序 vs 主体查询); 预留: 表达层内容源需要时再评估。
    def _spread(self, subj: str, qtype: str,
                depth: int = 3,
                gate: Optional[float] = 0.8,
                time_sliced: bool = False,
                causal_boost: Optional[float] = None,
                category_jump: bool = False,
                top_k: int = 5,
                dynamic_routing: bool = False,
                routing_k: float = 0.5,
                phase_source: Optional[str] = None) -> List[Tuple[str, float]]:
        """激活扩散: 从 subj 沿语义边传播, 只收集 qtype 类型候选

        机制化修复 (第二十三课回归): 只沿语义关系边
        (执行/对象/同类) 扩散 — 组成/属于是字形结构边,
        扩散过去是"字面联想"不是语义联想 (小林→小→小林真由 是
        字形不是知识)。联想 associate() 保留结构边 (带关系标签),
        但候选生成 (_spread) 必须语义门控。

        gate (纯加法, 默认 0.8=同步者优先; None=显式关闭历史行为):
        相位门控传播
        — 绝对相位差相干度 < 1.0-gate 的边不参与扩散 (CTC 语义)。

        causal_boost (2026-08-09, 默认 None=历史行为): 因果边顺流增益
        — 同时消费 granger 边 (_causal_edges) 与 dmit 边
        (_causal_edges_dmit): 沿有向因果方向传播 ×(1+boost),
        逆流不增益 (时间箭头单向)
        — 沿 granger 因果方向 (src→tgt) 传播时 ×(1+boost);
        逆流不增益 (时间箭头单向)。推理涌现: 因果链顺流加速。

        ④ 状态复用 (纯加法): 反相抑制集 (set_anti_phase 置入) 的
        概念不作为候选 — 刚学概念避开重复回答。默认空集无影响。

        time_sliced (MES M5 落地, 默认 False=历史行为): 分时复用
        — 按节律时钟把概念分片, 同一时间窗口只扩散当前节律槽
        相位相近的概念域 (带宽窗口); 大图传播不再全量扫 edges,
        每步只扫 1/rhythm_period 的边 (研究: 真实图 29 步节律)。
        仅当 rhythm_period>0 且开启时生效, 否则逐位不变。
        """
        _cboost = 1.0 + (causal_boost or 0.0)
        _dr = dynamic_routing and routing_k > 0.0
        _cat_members = getattr(self, '_category_members', None)
        _cat_jump = category_jump and bool(_cat_members)
        act: Dict[str, float] = defaultdict(float)
        act[subj] = 1.0
        frontier = {subj}
        # MES M5 分时复用: 当前节律槽相位窗口 (默认全开=历史行为)
        _slice_on = time_sliced and self.rhythm_period > 0
        if _slice_on:
            self._rhythm_step += 1
            _slot = (self._rhythm_step % self.rhythm_period) / self.rhythm_period
            _win = 1.0 / self.rhythm_period  # 窗口宽度 = 一个节律槽
        for hop in range(1, depth + 1):
            nf = set()
            for node in frontier:
                _node_m = self._id_main(node)
                for (f, rel, t), w in self.edges.items():
                    if rel in self.STRUCTURAL_RELS:
                        continue  # 字形/命名结构不参与语义扩散
                    _coh = 1.0
                    if gate is not None or _dr:
                        # 相位相干度 (同相=1, 反相=0) — gate 硬门 + 软调制共用
                        # phase_source (M4 消费端接线, 2026-08-18, 默认 None):
                        # 'substep' → 亚步连续演化相位 (mes.phase, 经
                        # concept_idx 映射) — 路由读连续时间相位而非事件步
                        # 相位; None → 现状 (concept_space._phases 事件步相位)
                        _coh = self._phase_coh_routing(f, t, w, phase_source)
                        if gate is not None and _coh < 1.0 - gate:
                            continue  # 相位门控: 不同步的边不传播 (CTC)
                    _drg = 1.0
                    if _dr:
                        # 自注意力路由 (T4 CTC 推论, 2026-08-18, 默认关):
                        # 传播权重 = 相位差函数 — 同相 (coh→1) 增强 ×(1+k),
                        # 正交 (coh=0.5) 中性, 反相 (coh→0) 抑制 ×(1-k)。
                        # 连续软调制 (非 0/1 硬门), 与 gate 叠加;
                        # k≤1 → 调制因子恒 ≥0 (无负权重翻转语义)。
                        _drg = 1.0 + routing_k * (2.0 * _coh - 1.0)
                    if _slice_on:
                        # 分时窗口: 只扩散相位落在当前节律槽内的概念
                        _ph_f = self._phase_get(f)
                        if _ph_f is None:
                            continue  # 无相位概念不参与分片传播
                        _ph_t = self._phase_get(t)
                        if _ph_t is None:
                            continue
                        _cyc = (_ph_f / (2 * np.pi) - _slot) % 1.0
                        if _cyc > _win:
                            continue  # 不在当前时间窗口 → 等待下一节律槽
                    if (f == node or f == _node_m) and t != subj:
                        if t in self._anti_phase_until:
                            continue  # ④ 抑制态: 反相概念不参与回答
                        _g = 1.0
                        if causal_boost is not None:
                            if (f, t) in self._causal_edges:
                                if self._causal_edges[(f, t)].get('strength', 1.0) \
                                        >= self._cond_edge_dead:
                                    _g = _cboost  # granger 边顺流 (K4: 活性过滤)
                            elif (f, t) in self._causal_edges_dmit:
                                # DMIT 边: 仅 score>0 (真方向) 才增益,
                                # 负 score = 反向记录, 不误当正向
                                if self._causal_edges_dmit[(f, t)]['score'] > 0 \
                                        and self._causal_edges_dmit[(f, t)].get(
                                            'strength', 1.0) >= self._cond_edge_dead:
                                    _g = _cboost
                        act[t] += w * (0.7 ** (hop - 1)) * _g * _drg
                        nf.add(t)
                    elif t == node and f != subj:
                        if f in self._anti_phase_until:
                            continue  # ④ 抑制态: 反相概念不参与回答
                        _g = 1.0
                        if causal_boost is not None:
                            if (t, f) in self._causal_edges:
                                if self._causal_edges[(t, f)].get('strength', 1.0) \
                                        >= self._cond_edge_dead:
                                    _g = _cboost  # K4: 活性过滤
                            elif (t, f) in self._causal_edges_dmit:
                                if self._causal_edges_dmit[(t, f)]['score'] > 0 \
                                        and self._causal_edges_dmit[(t, f)].get(
                                            'strength', 1.0) >= self._cond_edge_dead:
                                    _g = _cboost
                        act[f] += w * (0.7 ** (hop - 1)) * _g * _drg
                        nf.add(f)
                # 类别跳转 (缺口 3, C 层, 默认关零破坏): 对象 → 类别
                # 概念 (上行) / 类别概念 → 其他成员 (下行) — 类别区域
                # 是传播中间节点, 同类动作模式对象互激活。0.5 衰减
                # 系数与 hop 衰减同量级 (防振荡, 单跳结构无回路)。
                if _cat_jump:
                    for _cn, _mem in _cat_members.items():
                        if node in _mem and _cn != subj:
                            if _cn in self._anti_phase_until:
                                continue
                            act[_cn] += 0.5 * (0.7 ** (hop - 1))
                            nf.add(_cn)
                        elif node == _cn:
                            for _m in _mem:
                                if _m == subj or _m in self._anti_phase_until:
                                    continue
                                act[_m] += 0.5 * (0.7 ** (hop - 1))
                                nf.add(_m)
            frontier = nf
        want_action = (qtype == "动作")
        out = []
        for c, a in sorted(act.items(), key=lambda x: -x[1]):
            if c == subj or a <= 0:
                continue
            if want_action and "动作" not in self.types.get(c, set()):
                continue
            out.append((c, round(a, 2)))
            if len(out) >= top_k:
                break
        return out


# 2026-08-17 决策(用户拍板): 不接 — 目标=表达层(说人话)非问答。
    #   价值实证: 冷门规则+借同类查询 (deduce 死角, 实验已证); 但规模下
    #   泛化不稳 (相位门控切断异相路径 + hub 概念串扰), 接需先解 gate/hub。
    #   与 deduce 互补不重复 (时序 vs 主体查询); 预留: 表达层内容源需要时再评估。
    def write_back(self, subj: str, ans: List[str],
                   burst_weight: bool = False):
        """受控推理结果 → Hebbian 回写 → 下次自动模式秒答

        (第十九课闭环: 思考→固化→反射; 第二十三课: 回写=strengthen)

        burst_weight (纯加法, 默认 False=历史行为): 迸发热点加权
        (spike_couple 系列落地, 显著性涌现):
          - False: 每个答案 observe 一次 (历史行为一字不动)
          - True : 迸发过的动作 (burst_stats 有能量记录) 回写
                   加权 — 记忆系统自动知道谁是主角, 无需人工
                   importance (方向二: 迸发热点=语义热点)
        """
        for a in ans:
            if "动作" in self.types.get(a, set()):
                if burst_weight and self._burst_energy_log.get(a, 0) > 0:
                    self.observe(subj, a, None, count=3)  # 迸发热点加权
                else:
                    self.observe(subj, a, None, count=1)

    # ── 联想: 激活扩散 (含 part-of 边, 第十六课) ────────

# 2026-08-17 决策(用户拍板): 不接 — 目标=表达层(说人话)非问答。
    #   价值实证: 冷门规则+借同类查询 (deduce 死角, 实验已证); 但规模下
    #   泛化不稳 (相位门控切断异相路径 + hub 概念串扰), 接需先解 gate/hub。
    #   与 deduce 互补不重复 (时序 vs 主体查询); 预留: 表达层内容源需要时再评估。
    def associate(self, concept: str, hops: int = 2,
                  top_k: int = 5) -> List[Tuple[str, float, str]]:
        """从概念出发联想: 激活扩散 1跳/2跳 → (相关概念, 强度, 关系)

        1跳: 直接关系 (扣球 → 国见[执行者], 球[对象])
        2跳: 间接关系 (国见 → 扣球 → 球)
        衰减系数 0.7 (越远的跳数越弱)
        """
        act: Dict[str, float] = defaultdict(float)
        act[concept] = 1.0
        path: Dict[str, Tuple[str, str, int]] = {}

        frontier = {concept}
        for hop in range(1, hops + 1):
            next_frontier = set()
            for node in frontier:
                _node_m = self._id_main(node)
                for (f, rel, t), w in self.edges.items():
                    if (f == node or f == _node_m) and t != concept:
                        gain = w * (0.7 ** (hop - 1))
                        if t not in path:
                            path[t] = (node, rel, hop)
                        act[t] += gain
                        next_frontier.add(t)
                    elif t == node and f != concept:
                        # 反向边 (执行者边: 动作→人物)
                        gain = w * (0.7 ** (hop - 1))
                        if f not in path:
                            path[f] = (node, rel + "(反)", hop)
                        act[f] += gain
                        next_frontier.add(f)
            frontier = next_frontier

        out = []
        for c, a in sorted(act.items(), key=lambda x: -x[1]):
            if c == concept or a <= 0:
                continue
            rel = path.get(c, ("", "", 0))[1]
            out.append((c, round(a, 2), rel))
            if len(out) >= top_k:
                break
        return out

    # ── 查询: 事件记忆反查 (语义记忆的知识检索) ──────────

    # ⚠️ 预留接口 (2026-08-17 标注): 语言层消费端 (08-13 语言后置) — 问答/空间推理;
    def who(self, action: str, top_k: int = 5,
            gate: Optional[float] = None) -> List[Tuple[str, int]]:
        """谁做过这个动作

        gate (纯加法, 默认 None=历史行为): 按相位相干重排结果
        — 同步者优先 (CTC 语义, spike_couple 系列落地)。
        """
        out = defaultdict(int)
        for (p, a, o), c in self.events.items():
            if a == action:
                out[p] += c
        if gate is not None:
            anchor = self._phase_anchor()
            def _key(item):
                c, n = item
                if c not in self._phases:
                    return (0.0, -n)  # 无相位 → 排后 (无增益)
                d = abs((self._phase_get(c) - anchor + np.pi) % (2*np.pi) - np.pi)
                return (1.0 - d / np.pi, -n)
            items = sorted(out.items(), key=_key, reverse=True)[:top_k]
            return items
        return sorted(out.items(), key=lambda x: -x[1])[:top_k]


# 2026-08-17 决策(用户拍板): 不接 — 目标=表达层(说人话)非问答。
    #   价值实证: 冷门规则+借同类查询 (deduce 死角, 实验已证); 但规模下
    #   泛化不稳 (相位门控切断异相路径 + hub 概念串扰), 接需先解 gate/hub。
    #   与 deduce 互补不重复 (时序 vs 主体查询); 预留: 表达层内容源需要时再评估。
    def does(self, person: str, top_k: int = 5,
             gate: Optional[float] = None) -> List[Tuple[str, int]]:
        """这个人做过什么

        gate (纯加法, 默认 None=历史行为): 按相位相干重排结果
        — 同步动作优先 (CTC 语义, spike_couple 系列落地)。
        """
        out = defaultdict(int)
        for (p, a, o), c in self.events.items():
            if p == person:
                out[a] += c
        if gate is not None:
            anchor = self._phase_anchor()
            def _key(item):
                c, n = item
                if c not in self._phases:
                    return (0.0, -n)  # 无相位 → 排后 (无增益)
                d = abs((self._phase_get(c) - anchor + np.pi) % (2*np.pi) - np.pi)
                return (1.0 - d / np.pi, -n)
            items = sorted(out.items(), key=_key, reverse=True)[:top_k]
            return items
        return sorted(out.items(), key=lambda x: -x[1])[:top_k]


    # ⚠️ 预留接口 (2026-08-17 标注): 语言层消费端 (08-13 语言后置) — 问答/空间推理;
    def what(self, action: str, top_k: int = 5) -> List[Tuple[str, int]]:
        """这个动作的对象 (对什么做)"""
        out = defaultdict(int)
        for (p, a, o), c in self.events.items():
            if a == action and o:
                out[o] += c
        return sorted(out.items(), key=lambda x: -x[1])[:top_k]


    # ⚠️ 预留接口 (2026-08-17 标注): 语言层消费端 (08-13 语言后置) — 问答/空间推理;
    def who_likes(self, target: str, emotion: str = "喜欢",
                  top_k: int = 5) -> List[Tuple[str, int]]:
        """谁喜欢某对象"""
        out = defaultdict(int)
        for (p, a, o), c in self.events.items():
            if a == emotion and o == target:
                out[p] += c
        return sorted(out.items(), key=lambda x: -x[1])[:top_k]
    def spatial_reason(self, source: str, rel_types=None,
                       top_k: int = 3,
                       gate: Optional[float] = None
                       ) -> Optional[List[Tuple[str, float]]]:
        """概念版空间推理 (方向 D 落地, 概念空间替代 MLP 方向桶)

        从概念空间直接推理下一概念: 记忆检索 → 泛化扩散 → 联想链。
        与 semantic_memory.spatial_reason (MLP 方向桶) 签名对齐
        (source, rel_types), 内部完全走概念空间知识。

        路径组合 (D0 研究实证: 未见对泛化 0.700 vs MLP 0.000):
          ① does       — 事件记忆检索 (人物→做过什么, 频率排序)
          ② propagate  — 激活扩散/借同类 (泛化: 未见对也能推)
          ③ infer_chain— 2 跳联想链 (多跳涌现)

        Returns
        -------
        list or None : [(候选概念名, 分数), ...] 按分数降序
          None = 概念空间无该概念知识 (调用方应回退)
        """
        if source not in self.types:
            return None
        # ① 记忆检索: 事件反查 (does 语义: 这个人做过什么)
        mem = self.does(source, top_k=top_k, gate=gate)
        if mem:
            return [(a, float(c)) for a, c in mem[:top_k]]
        # ② 泛化: 激活扩散 (借同类/联想链), 未见对也能推
        cands, _how = self.propagate(source, "动作", top_k=top_k, gate=gate)
        if cands:
            # 分数 = 排名递减 (扩散候选无频次, 用序当置信度)
            return [(c, 1.0 - i * 0.1) for i, c in enumerate(cands[:top_k])]
        # ③ 联想链: 2 跳涌现 (A~B~C)
        chain, _how2 = self.infer_chain(source, top_k=top_k)
        if chain:
            return [(c, 1.0 - i * 0.1) for i, c in enumerate(chain[:top_k])]
        return None


    def type_of(self, concept: str) -> str:
        return ",".join(sorted(self.types.get(concept, {"?"})))

    def category_of(self, concept: str):
        """类别索引 (2026-08-18 推理基础能力二期): 对象 → 所属类别

        type_of 消费端: 类别 = 共享动作模式的对象聚簇 (M5 emergence
        涌现物, 零预置), 类别名 = 对象名拼接 (涌现的索引, 非设计)。
        返回首个含 concept 的类别名, 无则 None。

        用法 (消费端): 对象属于类别 C → C 的类别规则可用 (加热让
        冷变温 只对材料类成员生效, 食物类 加热→熟 互不污染)。
        """
        em = getattr(self, 'emergence', None)
        cats = getattr(em, 'categories', None) if em else None
        if not cats:
            return None
        for name, members in cats.items():
            if concept in members:
                return name
        return None


    # (归档 2026-08-16: has_concept → _archive_legacy/dead_interfaces_20260816.py)
    def ownership(self, semantics: bool = False):
        """第八刀+ (2026-08-12): 个体化读出 — 归属从分布涌现

        从事件方向性 (谁在什么时间点作用于什么) 涌现, 非词面。
        机制层零阈值: 返回作用占比分布 + 排他性 (1-归一化熵)。

        semantics=False: {对象: {"shares": {主体: 占比}, "exclusivity": float}}
        semantics=True:  命名层语义 (独占/共享/公共/强归属), 供仲裁消费
        """
        if getattr(self, '_rhythm', None) is not None:
            return self._rhythm.ownership(semantics=semantics)
        return {}

    def stats(self) -> dict:
        n_p = sum(1 for t in self.types.values() if PERSON in t)
        n_a = sum(1 for t in self.types.values() if ACTION in t)
        n_o = sum(1 for t in self.types.values() if OBJECT in t)
        n_e = sum(1 for t in self.types.values() if EMOTION in t)
        s = {
            "概念": len(self.types),
            "人物": n_p, "动作": n_a, "物体": n_o, "情感": n_e,
            "事件": len(self.events), "关系边": len(self.edges),
            "因果边": len(self._causal_edges),
            "DMIT因果边": len(self._causal_edges_dmit),
        }
        # 第六刀 (2026-08-12): vNext 节律层读数 — 时间维度进判定
        # (相位相干/能量涨落/混沌边缘参数; 依赖缺失时为零, 零破坏)
        if getattr(self, '_rhythm', None) is not None:
            r = self._rhythm.readings()
            s["节律"] = r
            # 第九刀+ (2026-08-12): 归属谱 — 个体化进判定链消费
            # (作用分布+排他性+语义命名, 仲裁消费端读这里)
            s["归属谱"] = self._rhythm.ownership(semantics=True)
        return s


    def to_dict(self) -> dict:
        # events 键含 Optional 第三元: None 用 "\x00" 占位, 与空串 "" 区分
        # (修复: 旧版 `o or ''` 把 None→'', 保存/加载往返后 obj=None 丢失)
        return {
            "types": {k: list(v) for k, v in self.types.items()},
            "events": {f"{p}\t{a}\t" + (o if o is not None else '\x00'): c
                       for (p, a, o), c in self.events.items()},
            "edges": {f"{f}\t{r}\t{t}": w
                      for (f, r, t), w in self.edges.items()},
            "part_of": {k: list(v) for k, v in self.part_of.items()},
            "wholes_of": {k: list(v) for k, v in self.wholes_of.items()},
            "entrench": dict(self.entrench),
            "sense_of": {k: list(v) for k, v in self.sense_of.items()},
            "word_bind": {k: dict(v) for k, v in self.word_bind.items()},
            "word_to_concept": {k: dict(v)
                                 for k, v in self.word_to_concept.items()},
            "episodes": self.episodes,
            "_phases": {k: v for k, v in self._phases.items()},
            "_causal_edges": {f"{s}\t{t}": meta
                               for (s, t), meta in self._causal_edges.items()},
            "_causal_edges_dmit": {f"{s}\t{t}": meta
                                   for (s, t), meta in self._causal_edges_dmit.items()},
            "_inference_mem": {
                "\x01".join(c) + "\t" + r: {**m, 'conf': round(m['conf'], 4)}
                for (c, r), m in self._inference_mem.items()},
            "_gap_mem": {
                f"{o}\t{g}": dict(m)
                for (o, g), m in self._gap_mem.items()},
            # 多级概念金字塔 (2026-09-03): 未装配 → _pyramid_to_dict
            # 返空 {}; 装配后存活力 (树由事件流重扫可重建)
            "_pyramid": self._pyramid_to_dict(),
            # 符号层对立结构 (2026-09-04 B 路线): 未装配 → 返空 {};
            # 装配后边/轨迹统计全息 (edges 由 sync 可重建, occ/de 为
            # 增量统计真源 — 存档保留免重建偏差)
            "_opposition": self._opposition_to_dict(),
        }


    def from_dict(self, d: dict):
        self.types = defaultdict(set, {k: set(v) for k, v in d["types"].items()})
        # \x00 占位还原为 None (与 to_dict 对应); 空串 "" 保持为 ""
        events = {}
        for k, c in d["events"].items():
            p, a, o = k.split("\t")
            events[(p, a, None if o == "\x00" else o)] = c
        self.events = defaultdict(int, events)
        self.edges = defaultdict(
            float, {tuple(k.split("\t")): w for k, w in d["edges"].items()})
        if "part_of" in d:
            self.part_of = defaultdict(list, d["part_of"])
            self.wholes_of = defaultdict(set,
                {k: set(v) for k, v in d["wholes_of"].items()})
            self.entrench = defaultdict(float, d["entrench"])
            self.sense_of = defaultdict(set,
                {k: set(v) for k, v in d["sense_of"].items()})
            self.word_bind = {k: dict(v) for k, v in d.get("word_bind", {}).items()}
            # 对称索引: 优先读存档; 旧存档无此字段时从 word_bind 重建
            self.word_to_concept = {}
            for concept, wmap in self.word_bind.items():
                for w, s in wmap.items():
                    self.word_to_concept.setdefault(w, {})[concept] = s
            self.episodes = list(d.get("episodes", []))
        if "_phases" in d:
            self._phases = dict(d["_phases"])
        if "_causal_edges" in d:
            self._causal_edges = {
                tuple(k.split("\t")): dict(v)
                for k, v in d["_causal_edges"].items()}
        if "_causal_edges_dmit" in d:
            self._causal_edges_dmit = {
                tuple(k.split("\t")): dict(v)
                for k, v in d["_causal_edges_dmit"].items()}
        if "_inference_mem" in d:
            self._inference_mem = {}
            for k, m in d["_inference_mem"].items():
                _c, _r = k.rsplit("\t", 1)
                self._inference_mem[(tuple(_c.split("\x01")), _r)] = m
        if "_gap_mem" in d:
            self._gap_mem = {}
            for k, m in d["_gap_mem"].items():
                _o, _g = k.rsplit("\t", 1)
                self._gap_mem[(_o, _g)] = m
        if "_pyramid" in d:
            self._pyramid_from_dict(d["_pyramid"])
        if "_opposition" in d:
            self._opposition_from_dict(d.get("_opposition"))
        return self
