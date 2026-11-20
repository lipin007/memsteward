# -*- coding: utf-8 -*-
"""端到端管道胶水（M2）：observe → 摘要入账 → ask → 召回 → 热冷帧 → main 上游。

记忆即上下文方案的执行面（一个中间件＋一张路由表＋N 上游）：
  observe(text)  对话流进摘要引擎（闩锁/两段式/入账，M1/M1.5 机制全复用）
  ask(question)  决策时：签名召回冷段＋热态原样 → 热冷分段帧 → main 上游 → 答案

守则：main 挂了帧仍在（fail-soft，记忆不断链）；答案失败照登 error 字段；
热段原样保真 O(1)（热冷混淆守则）。判据：tests/test_pipeline.py T9a-d。
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Dict, List, Optional

from .landing import LandingStore
from .summarize import SUMMARIZE_MAX_CHARS, Summarizer, render_frame

MAIN_MAX_TOKENS = int(os.environ.get("MAIN_MAX_TOKENS", "512"))


class Pipeline:
    """一条链管到底：叙事进、决策出。两个上游（summarize=/main=）都是路由表条目。"""

    def __init__(self, landing: LandingStore, session: str = "s",
                 summarize_url: Optional[str] = None,
                 main_url: Optional[str] = None,
                 max_chars: int = SUMMARIZE_MAX_CHARS,
                 enhance_fn=None, gate=None):
        self.landing = landing
        self.session = session
        self.gate = gate                     # 23号保险丝（缺省无门＝全放）
        self.main_url = (main_url or os.environ.get("MAIN_URL", "") or "").rstrip("/")
        self.s = Summarizer(landing, session=session,
                            summarize_url=summarize_url,
                            max_chars=max_chars, enhance_fn=enhance_fn)

    def observe(self, text: str, turn_id=None, kind: str = "narrative",
                accumulate: bool = False) -> dict:
        """喂一轮对话（缺省逐轮编译入账；accumulate=True 攒轮后批量定稿）。"""
        return self.s.feed(text, turn_id=turn_id, kind=kind,
                           accumulate=accumulate)

    def record_outcome(self, effective: bool) -> dict:
        """注入有效性回填（23号保险丝）：由判读/反馈层回填，不自报。"""
        return self.gate.record(effective) if self.gate is not None else {}

    def ask(self, question: str, hot_state: str = "",
            k: int = 8, budget: int = 2000) -> dict:
        """决策一步：召回冷段＋热态 → 帧 → main 上游。main 挂不丢帧（fail-soft）。
        23号保险丝：gate 拒入时帧退纯热段（注入隔离，非删除）。"""
        allow = self.gate.admit() if self.gate is not None else True
        hits = self.landing.recall(str(question), k=k) if allow else []
        cold: List[str] = []
        for h in hits:
            e = h.get("entry") or {}
            cold.append(str(e.get("body") or e.get("act") or ""))
        frame = render_frame(str(hot_state or question), cold, budget=budget)
        out = self._call_main(frame)
        return {"frame": frame, "cold_hits": len(hits),
                "answer": out.get("text"), "error": out.get("error"),
                "usage": out.get("usage")}

    def _call_main(self, frame: str) -> Dict:
        if not self.main_url:
            return {"text": None, "error": "no main upstream"}
        payload = json.dumps({
            "model": os.environ.get("MAIN_MODEL", ""),
            "messages": [{"role": "user", "content": frame}],
            "temperature": 0.0, "max_tokens": MAIN_MAX_TOKENS,
        }).encode("utf-8")
        req = urllib.request.Request(
            self.main_url + "/v1/chat/completions", data=payload,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                resp = json.load(r)
            msg = ((resp.get("choices") or [{}])[0].get("message") or {})
            return {"text": (msg.get("content") or "").strip() or None,
                    "error": None, "usage": resp.get("usage")}
        except Exception as e:
            # fail-soft：main 挂了帧仍在，失败照登（决策可回退 explore/人工）
            return {"text": None, "error": f"{type(e).__name__}: {e}"}
