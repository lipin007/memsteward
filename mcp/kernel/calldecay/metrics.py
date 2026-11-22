# -*- coding: utf-8 -*-
"""指标计数器 —— 只记实测数，不造节省估算。"""

import threading
import time


class Metrics:
    """线程安全的计数器。

    口径纪律：只记两类数——①直接计数（调用/命中/回灌）②上游返回的
    usage 计数（prompt/completion tokens）。不推算反事实节省；
    唯一的派生量 avoided_upstream_calls = table_hits
    （每次查表命中 = 一次未发生的上游调用，计数级可核）。
    """

    _KEYS = (
        "decisions", "table_hits", "llm_consults", "explore_fallbacks",
        "learns", "upstream_calls", "upstream_prompt_tokens",
        "upstream_completion_tokens", "request_chars_sent",
    )

    def __init__(self):
        self._lock = threading.Lock()
        self._c = {k: 0 for k in self._KEYS}
        self.started = time.time()

    def bump(self, key, n=1):
        with self._lock:
            self._c[key] = self._c.get(key, 0) + n

    def summary(self):
        with self._lock:
            d = dict(self._c)
        d["avoided_upstream_calls"] = d["table_hits"]
        d["uptime_seconds"] = round(time.time() - self.started, 1)
        return d
