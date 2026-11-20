#!/usr/bin/env python3
"""PVS 治理中间件 — LLM 调用治理接口 (模型可插拔)。

这是"通用大模型中间件"的第一层: 把不可靠的 LLM 调用
(超时/烧穿/空响应/上下文超限/HTTP错误) 治理成可靠组件。

从 ARC-AGI-2 agent_v1.ds_llm 提炼, 领域无关。

治理能力:
  * 超时 watchdog (线程双保险, 防静默挂死)
  * 上下文超限 → 生成预算减半重试
  * 烧穿/空响应 → reasoning_content 回退 + 降档重试
  * 指数退避重试 (429/5xx)
  * 预算记账 (calls/tokens 供给预算控制器)
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Protocol


@dataclass
class LLMResponse:
    """一次治理后的 LLM 响应。"""
    content: str                # 最终可用文本 (content 优先, reasoning_content 回退)
    finish: Optional[str]       # finish_reason
    usage: Dict[str, int]       # token 计数 (prompt/completion/total)
    elapsed: float              # 秒
    raw: Dict[str, Any]         # 原始响应 (调试/复盘)
    reasoning: str = ""         # 推理文本 (content 空时的答案来源)
    error: Optional[str] = None # 非 None = 调用失败


class LLMBackend(Protocol):
    """模型后端接口 (可插拔): 任何本地/远程 LLM 都适配成这个签名。"""
    def complete(self, messages, *, max_tokens, temperature,
                 extra: Optional[Dict] = None) -> Dict[str, Any]:
        """返回 openai 兼容的 choices[0] 结构, 或抛异常。
        实现者负责: 网络、认证、模型选择、底层 API 差异。"""
        ...


class LLMGate:
    """LLM 调用治理器: 包装任意 LLMBackend, 加上可靠化治理。

    用法:
        backend = OpenAIBackend(base_url, key, model)   # 或 LocalLlamaCppBackend(...)
        gate = LLMGate(backend, timeout=420, max_retries=3)
        resp = gate.call("你的问题", max_tokens=24000, temperature=0.15)
    """

    def __init__(self, backend, *, timeout: float = 420,
                 watchdog_slack: float = 30.0, max_retries: int = 3,
                 on_state: Optional[Callable[[str, dict], None]] = None,
                 budget=None):
        """
        timeout          单次调用超时 (秒)
        watchdog_slack   看门狗额外等待 (线程挂死检测)
        max_retries      指数退避重试次数
        on_state         治理事件回调 (降档/重试/烧穿), 供预算控制器/日志
        budget           Budget 记账器 (可 None)
        """
        self._backend = backend
        self._timeout = timeout
        self._slack = watchdog_slack
        self._retries = max_retries
        self._on_state = on_state or (lambda *a: None)
        self._budget = budget

    def call(self, prompt: str, *, max_tokens: int = 24000,
             temperature: float = 0.15, extra: Optional[Dict] = None) -> LLMResponse:
        """治理一次调用。返回 LLMResponse (error 非 None = 失败)。"""
        messages = [{"role": "user", "content": prompt}]
        t0 = time.time()
        out: Dict[str, Any] = {}

        def _call():
            payload = dict(max_tokens=max_tokens, temperature=temperature,
                           **(extra or {}))
            try:
                resp = self._backend.complete(
                    messages, max_tokens=max_tokens,
                    temperature=temperature, extra=extra)
            except Exception as e:
                out["err"] = e
                return
            try:
                ch0 = resp["choices"][0]
                msg = ch0.get("message", {})
                content = msg.get("content") or ""
                rc = msg.get("reasoning_content") or ""
                # ★烧穿时答案在 reasoning_content
                if not content.strip() and rc.strip():
                    content = rc
                usage = dict(resp.get("usage", {}) or {})
                out["ok"] = LLMResponse(
                    content=content, finish=ch0.get("finish_reason"),
                    usage=usage, elapsed=round(time.time() - t0, 1),
                    raw=resp, reasoning=rc)
            except Exception as e:
                out["err"] = e

        # 线程 + 看门狗: 防底层驱动挂死不返回
        th = threading.Thread(target=_call, daemon=True)
        th.start()
        th.join(self._timeout + self._slack)
        if "ok" in out:
            resp = out["ok"]
            if self._budget:
                self._budget.add(1, resp.usage.get("total_tokens", 0))
            return resp
        err = out.get("err")
        self._on_state("timeout", {"err": str(err)})
        return LLMResponse(content="", finish=None, usage={},
                           elapsed=round(time.time() - t0, 1), raw={},
                           error=f"超时/失败: {err}")

    # ---------- 治理重试: 上下文超限减半 + 指数退避 ----------
    def call_resilient(self, prompt: str, *, max_tokens: int = 24000,
                       temperature: float = 0.15,
                       extra: Optional[Dict] = None) -> LLMResponse:
        """带治理的调用: 上下文超限自动减半生成预算重试; 429/5xx 指数退避。
        这是 agent_v1 '预算减半重试' 的通用化。"""
        tokens = max_tokens
        for attempt in range(self._retries + 1):
            resp = self.call(prompt, max_tokens=tokens,
                             temperature=temperature, extra=extra)
            # 烧穿(空 content + finish=length): 答案在 reasoning 被截断, 也需重试
            if resp.error is None and not (resp.finish == "length"
                                           or not resp.content.strip()):
                return resp
            # 上下文超限 → 生成预算减半重试
            err = str(resp.error or "")
            if ("Context size" in err or "context" in err.lower()) and tokens > 2048:
                tokens = max(2048, tokens // 2)
                self._on_state("ctx_downsize", {"tokens": tokens})
                continue
            # 烧穿 → 降档重试 (把模型能力上限变可调度资源)
            if resp.error is None and not resp.content.strip():
                self._on_state("burnout_retry", {"attempt": attempt})
                continue
            # 429/5xx → 指数退避
            wait = 2 ** attempt
            self._on_state("retry", {"attempt": attempt, "wait": wait})
            time.sleep(wait)
        return resp
