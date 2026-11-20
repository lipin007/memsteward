"""
MechanismLearner — MotAgent 的机制级知识学习器

设计原则（loop.py 六步闭环的 ③⑥ 步）：
  ③ Hold：形成假设（"踩格 X 会让格 Y 变"）
  ⑥ Verify：收集证据确认/推翻

核心差异 vs 硬编码规则：
  - 知识来源 = agent 自己观察（不是我写）
  - 知识结构 = 带置信度+证据（不是裸命令）
  - 知识更新 = 新证据可推翻旧结论（不是永恒定律）
  - 知识存储 = MemSteward 三入层（不是源码常量）

接入方式：旁路，不改 MotAgent 决策逻辑。
  mech.observe(cur, action, before_frame, after_frame)  ← 每步调
  mech.get_hypotheses()  → 可查询当前机制知识
  mech.save_to_memsteward()  → 持久化
"""

import json
import time
import urllib.request


class Hypothesis:
    """一条机制假设。"""

    def __init__(self, cause, effect, kind="mechanism"):
        self.cause = cause        # str: "step:10,20" / "near:5,5"
        self.effect = effect      # str: "change:15,25" / "energy:+5"
        self.kind = kind          # mechanism / spatial / causal
        self.evidence = []        # [(timestamp, supports:bool, detail)]
        self.status = "untested"  # untested / testing / confirmed / refuted
        self.created = time.time()
        self.updated = self.created

    def add_evidence(self, supports, detail=""):
        self.evidence.append({"ts": time.time(), "supports": supports, "detail": detail})
        n_sup = sum(1 for e in self.evidence if e["supports"])
        n_ref = sum(1 for e in self.evidence if not e["supports"])
        total = len(self.evidence)
        if total >= 3:
            if n_sup >= total * 0.7:
                self.status = "confirmed"
            elif n_ref >= total * 0.7:
                self.status = "refuted"
            else:
                self.status = "testing"
        elif total >= 1:
            self.status = "testing"
        self.updated = time.time()

    @property
    def confidence(self):
        if not self.evidence:
            return 0.0
        n_sup = sum(1 for e in self.evidence if e["supports"])
        return round(n_sup / len(self.evidence), 2)

    def to_dict(self):
        return {
            "cause": self.cause, "effect": self.effect, "kind": self.kind,
            "status": self.status, "confidence": self.confidence,
            "n_evidence": len(self.evidence),
            "created": self.created, "updated": self.updated,
        }


class MechanismLearner:
    """机制级知识学习器。旁路运行，不改 MotAgent 决策。"""

    def __init__(self, memgate_url="http://127.0.0.1:8877"):
        self._url = memgate_url.rstrip("/")
        self.hypotheses = {}   # key=(cause,effect) → Hypothesis
        self._pending = {}     # action→state snapshot, 等待观察结果
        self._stats = {"observed": 0, "new_hypotheses": 0, "confirmed": 0, "refuted": 0}

    def observe(self, pos, action, world_before, world_after):
        """
        核心方法：观察一次动作→效果，更新假设。

        pos: 当前位置 (x, y)
        action: 动作编号
        world_before: dict, 动作前世界状态 {"changers": [...], "targets": [...], "energy": N}
        world_after: dict, 动作后世界状态
        """
        self._stats["observed"] += 1

        # 1. 检测变化
        changes = self._detect_changes(world_before, world_after)
        if not changes:
            return

        # 2. 形成/更新假设："在 pos 做 action 导致 changes"
        cause = f"act:{action}@{pos[0]},{pos[1]}"
        for change in changes:
            effect = f"change:{change}"
            key = (cause, effect)

            if key not in self.hypotheses:
                h = Hypothesis(cause, effect)
                self.hypotheses[key] = h
                self._stats["new_hypotheses"] += 1
            else:
                h = self.hypotheses[key]

            # 3. 添加证据
            h.add_evidence(supports=True, detail=f"step@{pos}")
            if h.status == "confirmed":
                self._stats["confirmed"] += 1
            elif h.status == "refuted":
                self._stats["refuted"] += 1

    def check_no_effect(self, pos, action, world_before, world_after):
        """如果动作导致了预期的变化但没发生，记为反证。"""
        # 对已有的相关假设添加反证
        cause = f"act:{action}@{pos[0]},{pos[1]}"
        for (c, e), h in self.hypotheses.items():
            if c == cause and h.status in ("testing", "confirmed"):
                changes = self._detect_changes(world_before, world_after)
                expected = e.replace("change:", "")
                if expected not in changes:
                    h.add_evidence(supports=False, detail=f"no_change@{pos}")

    def _detect_changes(self, before, after):
        """检测世界变化。返回变化描述列表。"""
        changes = []
        b_chg = set(tuple(c) for c in before.get("changers", []))
        a_chg = set(tuple(c) for c in after.get("changers", []))
        for new in a_chg - b_chg:
            changes.append(f"new_changer:{new}")
        for gone in b_chg - a_chg:
            changes.append(f"lost_changer:{gone}")

        b_tgt = set(tuple(t) for t in before.get("targets", []))
        a_tgt = set(tuple(t) for t in after.get("targets", []))
        for new in a_tgt - b_tgt:
            changes.append(f"new_target:{new}")
        for gone in b_tgt - a_tgt:
            changes.append(f"lost_target:{gone}")

        b_e = before.get("energy", 0)
        a_e = after.get("energy", 0)
        if a_e != b_e:
            changes.append(f"energy:{a_e - b_e:+d}")

        return changes

    def get_hypotheses(self, status=None, kind=None):
        """查询假设。可按状态/类型过滤。"""
        result = []
        for h in self.hypotheses.values():
            if status and h.status != status:
                continue
            if kind and h.kind != kind:
                continue
            result.append(h)
        return sorted(result, key=lambda h: -h.confidence)

    def get_mechanism_summary(self):
        """机制知识摘要。给 MotAgent 决策时参考。"""
        confirmed = self.get_hypotheses(status="confirmed")
        testing = self.get_hypotheses(status="testing")
        return {
            "confirmed": [h.to_dict() for h in confirmed],
            "testing": [h.to_dict() for h in testing],
            "total": len(self.hypotheses),
            "stats": dict(self._stats),
        }

    def save_to_memsteward(self):
        """持久化到 MemSteward。"""
        for h in self.hypotheses.values():
            if h.status in ("confirmed", "refuted"):
                try:
                    payload = {
                        "source": "mechanism_learner",
                        "obj": h.cause,
                        "act": f"hypothesis:{h.effect}",
                        "actual": f"status={h.status} conf={h.confidence} n={len(h.evidence)}",
                        "kind": h.kind,
                    }
                    req = urllib.request.Request(
                        f"{self._url}/decision",
                        json.dumps(payload).encode(),
                        {"Content-Type": "application/json"},
                    )
                    urllib.request.urlopen(req, timeout=3)
                except Exception:
                    pass

    def get_stats(self):
        return dict(self._stats)
