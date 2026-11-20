#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""召回注入保险丝（23号·顾问通道可靠性隔离恢复 移植，2026-11-07）。

记忆注入本质是顾问：23 号的滑窗有效率→隔离→每 K 次探测→连续 n 次好才恢复，
直接套到召回注入——注入连续无效（带歪/空转）就隔离该通道，帧退纯热段；
隔离期每 probe_every 次放行一次探测；连续 recover_n 次探测有效才恢复。
把「选错子集」从裸奔变成有保险丝。

判据 G1–G5 见 tests/test_gate.py（判据先行）。状态落盘（原子写），换进程续接。
有效信号由调用方回填（m3_judge 的有效命中/空转、或反馈层的答错）。
"""
import json
import os

DEFAULT_PATH = os.path.expanduser("~/.calldecacy/recall_gate.json")


class RecallGate:
    def __init__(self, path=None, window=20, lower=0.2,
                 probe_every=5, recover_n=3):
        self.path = path or DEFAULT_PATH
        self.window = max(1, int(window))
        self.lower = float(lower)
        self.probe_every = max(1, int(probe_every))
        self.recover_n = max(1, int(recover_n))
        self._load()

    def _load(self):
        try:
            d = json.load(open(self.path, encoding="utf-8"))
        except Exception:
            d = {}
        self.recent = [bool(x) for x in d.get("recent", [])][-self.window:]
        self.isolated = bool(d.get("isolated", False))
        self.since_probe = int(d.get("since_probe", 0))
        self.good_probes = int(d.get("good_probes", 0))

    def _save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = f"{self.path}.tmp.{os.getpid()}.{os.urandom(3).hex()}"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"recent": self.recent[-self.window:],
                       "isolated": self.isolated,
                       "since_probe": self.since_probe,
                       "good_probes": self.good_probes}, f)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, self.path)

    def admit(self) -> bool:
        """准入：健康全放；隔离期每 K 次放行一次探测，其余拒入（帧退纯热段）。"""
        if not self.isolated:
            return True
        self.since_probe += 1
        hit = self.since_probe >= self.probe_every
        if hit:
            self.since_probe = 0
        self._save()
        return hit

    def record(self, effective: bool) -> dict:
        """记一次注入结果（有效=True／带歪=False）。隔离期记录即探测结果。"""
        self.recent.append(bool(effective))
        self.recent = self.recent[-self.window:]
        out = {"isolated": self.isolated}
        if self.isolated:
            if effective:
                self.good_probes += 1
                if self.good_probes >= self.recover_n:    # G4 连续好探测恢复
                    self.isolated = False
                    self.good_probes = 0
                    self.since_probe = 0
                    out["recovered"] = True
            else:
                self.good_probes = 0
        elif len(self.recent) >= self.window:              # G2 滑窗低效隔离
            rate = sum(self.recent) / len(self.recent)
            if rate < self.lower:
                self.isolated = True
                self.good_probes = 0
                self.since_probe = 0
                out["isolated_now"] = True
        self._save()
        return out

    def status(self) -> dict:
        rate = (sum(self.recent) / len(self.recent)) if self.recent else None
        return {"isolated": self.isolated, "window_used": len(self.recent),
                "rate": rate, "good_probes": self.good_probes}
