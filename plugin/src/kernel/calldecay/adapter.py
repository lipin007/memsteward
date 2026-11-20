# -*- coding: utf-8 -*-
"""CallDecay SDK —— 决策记忆中间件的库接法（三行接入）。

    from calldecay import CallDecay
    cd = CallDecay()
    d = cd.decide(obj="兔", goal="丰", current="兔", actions=["喂食", "放牧"])
    cd.learn(obj="兔", act=d["act"], actual="丰", cur="兔")

机制本体在 core/（AI Research Source License v1.2）；本文件只是编排层：
known（查表直连，0 上游调用）→ llm（窄接口咨询）→ explore（回退）。
"""

from ._kernel import bootstrap

bootstrap()  # 使 core 可导入；不改内核一行

import core.llm_arm as llm_arm                        # noqa: E402
from core.concept_space import ConceptSpace           # noqa: E402
from core.decision_symbolic import SymbolicDecision   # noqa: E402

from .metrics import Metrics
from .landing import LandingStore, MIN_LIVENESS, _good_direct   # noqa: E402

import random                                         # noqa: E402


class CallDecay:
    """决策记忆中间件实例：一个实例 = 一份本地状态表（概念空间）。"""

    def __init__(self, gate_open=True, principle_batch_size=3, landing_path=None):
        self.metrics = Metrics()
        self.cs = ConceptSpace()
        # 边精化批间隔（core 统计参数）：默认 3 = 决策回路节奏；
        # 约 7 次一致确认后确定性边涌现 → 查表命中（固化阈值语义）
        self.cs._principle_batch_size = principle_batch_size
        self.sd = SymbolicDecision(concept_space=self.cs)
        # A2 落点件（整合施工方案_v1 A段）：硬落盘账本——learn 即落盘；
        # 启动时 replay 回灌状态表（进程重启后记忆可回放、可寻址）。
        self.landing = LandingStore(landing_path)
        self._replay_failed = 0
        # 有界回放（2026-11-05 清债）：init 成本随账本膨胀（真实账本 2479 条回放
        # 挂死 concept_principle 扫描）——只回放「暖条目＋最近 N 条」；冷条目/旧条目
        # 留账本（recall_good/landing.recall 可取，同构复现即回前排），表＝暖缓存、
        # 账本＝全量真值。上限 CALLDECAY_REPLAY_LIMIT（默认 500）。
        import os as _os
        _limit = int(_os.environ.get("CALLDECAY_REPLAY_LIMIT", "500"))
        _all = len(self.landing.entries)
        _done = 0
        for _e in self.landing.replay(min_liveness=MIN_LIVENESS, limit=_limit):
            try:
                self.sd.learn_from_result(obj=_e.get("obj"), act=_e.get("act"),
                                          actual=_e.get("actual"), cur=_e.get("cur"))
                _done += 1
            except Exception:
                self._replay_failed += 1  # 单条回放失败不阻启动（账本仍完整）
        self._replay_done = _done
        self._replay_skipped = _all - _done - self._replay_failed
        if gate_open:
            llm_arm.gate_should_call = lambda: True

    def decide(self, obj, goal, current=None, actions=None, context=None):
        """决策一步：命中查表直连（0 上游调用），未命中走窄接口咨询，仍无则探索回退。"""
        self.metrics.bump("decisions")
        res = self.sd.decide_symbolic(obj=obj, goal=goal,
                                      current=current, context=context)
        if res.get("known") or res.get("plan"):
            self.metrics.bump("table_hits")
            out = dict(res)
            out["source"] = "table"
            return out
        sug = llm_arm.suggest(obj=obj, goal=goal, current=current,
                              actions=actions, context=context)
        if sug:
            self.metrics.bump("llm_consults")
            return {"act": sug.get("act"), "expected": None, "known": False,
                    "plan": [], "is_explore": False,
                    "confidence": sug.get("confidence"),
                    "reason": "llm:" + str(sug.get("reasoning", ""))[:200],
                    "source": "llm"}
        # A14 good 答案模式回落：LLM 未命中且沉淀过 → 零 token 直答
        # （2026-11-05 G/S 系列 A/B 验证：G1 100%vs42.4%，S1 稀疏20=100%）。
        # 灰度只报不直答（缺省只读，2026-11-15 拍板）：命中照报（recall_good 计
        # good_shadow_hits 观测计数）但不直答，落 explore；MEMGATE_GOOD_DIRECT=1
        # 开直答（观察一周后）。
        ga = self.landing.recall_good(current) if current is not None else None
        if ga and (not actions or ga in actions) and _good_direct():
            self.metrics.bump("gmem_hits")
            return {"act": ga, "expected": None, "known": False,
                    "plan": [], "is_explore": False,
                    "reason": "good_pattern", "source": "gmem"}
        self.metrics.bump("explore_fallbacks")
        act = random.choice(actions) if actions else None
        return {"act": act, "expected": None, "known": False, "plan": [],
                "is_explore": True, "reason": "explore_fallback",
                "source": "explore"}

    def learn(self, obj=None, act=None, actual=None, cur=None, ok=None):
        """把行动结果写回状态表（蒸馏回灌）——学会的不再问。
        【A2 落点】同时强制落盘（learn→save），进程死记忆不死。
        【A14】ok=True/False 时同步 good 答案模式沉淀/撤销（生产反馈＝任务
        奖励/结果确认；A/B 验证：稀疏 20% 反馈即拿满质量，噪声 10%→79.9%）。"""
        self.metrics.bump("learns")
        res = self.sd.learn_from_result(obj=obj, act=act,
                                        actual=actual, cur=cur)
        self.landing.deposit(obj=obj, act=act, actual=actual, cur=cur)
        if ok is not None and cur is not None and act is not None:
            self.landing.feedback(cur, act, ok=bool(ok))
        return res

    def feedback(self, cur, act, ok=True):
        """独立反馈口（不带学习语义时用）：good 模式沉淀/撤销。"""
        self.metrics.bump("feedbacks")
        return self.landing.feedback(cur, act, ok=ok)

    def recall(self, obj=None, act=None, k=8):
        """签名门控召回（跨重启可查，落点层）。"""
        return self.landing.recall(f"{obj}|{act}", k=k)

    def stats(self):
        return {"core": self.sd.get_stats(), "metrics": self.metrics.summary(),
                "landing_entries": len(self.landing.entries),
                "good_patterns": len(self.landing.good_patterns),
                "landing_bytes": self.landing.stats().get("bytes", 0),
                "replayed": self._replay_done,
                "replay_skipped": self._replay_skipped,
                "replay_failed": self._replay_failed}
