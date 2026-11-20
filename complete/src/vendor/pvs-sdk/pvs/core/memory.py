#!/usr/bin/env python3
"""PVS 治理中间件 — 门控记忆层 (跨任务学习, 从 agent_v1 CallDecay 提炼)。

治理能力: 把"经验"变成可靠先验, 同时防负迁移。
  * 相关性门控: 召回先判"是否真与本题同类", 异质不召回 (防"看似相似实则陷阱")。
  * 失败负先验: 同结构曾失败 → 注入"别走哪条路", 防重踩。
  * CallDecay: 固化条目命中 → 直连查表 (零 token 交卷), 调用随学习衰减。
  * 只存抽象规则/技能, 绝不存某题答案/输入输出映射 (对齐 ARC 大赛"无法仅记住解决方案")。

领域无关: 记忆单元 = 任意可序列化规则 + 适用条件 digest + 活动度。
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import List, Optional, Tuple


class MemoryEntry:
    """一条记忆: 抽象规则 + 适用条件 + 活动度 + 成败标签。"""
    __slots__ = ("code", "digest", "tid", "stage", "cons", "success",
                 "activity", "ts", "used")

    def __init__(self, code: str, digest: str, tid: str = "", stage: str = "",
                 cons: float = 0.0, success: bool = True, activity: float = 1.0):
        self.code = code
        self.digest = digest          # 适用条件/结构签名 (相关性钥匙)
        self.tid = tid
        self.stage = stage
        self.cons = cons              # 一致性分数
        self.success = success        # True=成功规则, False=失败负先验
        self.activity = activity
        self.ts = time.time()
        self.used = 0


class GateMemory:
    """门控记忆层。"""

    def __init__(self, path: Optional[str] = None,
                 sim_fn=None, gate_threshold: float = 0.3,
                 decay_factor: float = 0.92, min_activity: float = 0.05):
        self._lock = threading.Lock()
        self.entries: List[MemoryEntry] = []
        self._path = path
        self._sim = sim_fn or self._token_sim
        self._gate = gate_threshold
        self._decay = decay_factor
        self._min_act = min_activity
        if path and os.path.exists(path):
            self.load(path)

    @staticmethod
    def _token_sim(a: str, b: str) -> float:
        """token 重叠相似度 (Jaccard)。领域无关: 抽取标识符/数字。"""
        sa = set(re.findall(r"[A-Za-z_]+|\d+", a or ""))
        sb = set(re.findall(r"[A-Za-z_]+|\d+", b or ""))
        if not sa or not sb:
            return 0.0
        return len(sa & sb) / len(sa | sb)

    # ---------- 写 ----------
    def deposit(self, code: str, digest: str, tid: str = "", stage: str = "",
                cons: float = 0.0, success: bool = True) -> MemoryEntry:
        with self._lock:
            e = MemoryEntry(code, digest, tid, stage, cons, success)
            self.entries.append(e)
            return e

    def deposit_fail(self, digest: str, tid: str = "", stage: str = "") -> MemoryEntry:
        return self.deposit("", digest, tid, stage, 0.0, success=False)

    # ---------- 读 (相关性门控) ----------
    def recall(self, query: str, k: int = 2) -> List[Tuple[float, MemoryEntry]]:
        """召回成功规则: 过门控阈值才进, 按 相似度×活动度 排序。"""
        with self._lock:
            scored = []
            for e in self.entries:
                if not e.success or e.activity < self._min_act:
                    continue
                s = self._sim(query, e.digest)
                if s >= self._gate:
                    scored.append((s * e.activity, s, e))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [(s, e) for _, s, e in scored[:k]]

    def recall_fails(self, query: str, k: int = 1) -> List[Tuple[float, MemoryEntry]]:
        """召回失败负先验。"""
        with self._lock:
            scored = []
            for e in self.entries:
                if e.success or e.activity < self._min_act:
                    continue
                s = self._sim(query, e.digest)
                if s >= self._gate:
                    scored.append((s * e.activity, s, e))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [(s, e) for _, s, e in scored[:k]]

    # ---------- 活动度维护 (CallDecay) ----------
    def boost_used(self, entries: List[MemoryEntry]) -> None:
        with self._lock:
            for e in entries:
                e.activity = min(1.0, e.activity * 1.2)
                e.used += 1

    def decay(self, factor: Optional[float] = None) -> None:
        f = factor or self._decay
        with self._lock:
            for e in self.entries:
                e.activity *= f

    # ---------- 持久化 ----------
    def persist(self, path: Optional[str] = None) -> str:
        p = path or self._path
        if not p:
            raise ValueError("no path")
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        data = [{"code": e.code, "digest": e.digest, "tid": e.tid, "stage": e.stage,
                 "cons": e.cons, "success": e.success, "activity": e.activity,
                 "used": e.used} for e in self.entries]
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        return p

    def load(self, path: str) -> None:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        with self._lock:
            self.entries = []
            for d in data:
                e = MemoryEntry(d.get("code", ""), d.get("digest", ""),
                                d.get("tid", ""), d.get("stage", ""),
                                d.get("cons", 0.0), d.get("success", True),
                                d.get("activity", 1.0))
                e.used = d.get("used", 0)
                self.entries.append(e)

    def __len__(self) -> int:
        return len(self.entries)
