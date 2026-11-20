#!/usr/bin/env python3
"""PVS 治理中间件 — 模型后端适配器 (可插拔)。

模型可插拔 = 任意 LLM 后端都适配成 LLMBackend 接口:
  * OpenAICompatBackend  — 任何 OpenAI 兼容 API (DeepSeek/小米/OpenAI/本地vLLM...)
  * LlamaCppBackend     — 本地 llama.cpp 服务器 (推理预算本地可控)

用法:
    gate = LLMGate(OpenAICompatBackend("https://api.deepseek.com/v1", key, "deepseek-chat"))
    gate = LLMGate(LlamaCppBackend("http://localhost:8086", model="qwen"))
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Dict, Optional


class OpenAICompatBackend:
    """任何 OpenAI 兼容 /chat/completions 后端。"""

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base = base_url.rstrip("/")
        self.key = api_key
        self.model = model

    def complete(self, messages, *, max_tokens, temperature,
                 extra: Optional[Dict] = None) -> Dict[str, Any]:
        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            **(extra or {}),
        }).encode()
        req = urllib.request.Request(
            self.base + "/chat/completions", data=body,
            headers={"Authorization": "Bearer " + self.key,
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=100) as r:
            return json.load(r)


class LlamaCppBackend:
    """本地 llama.cpp 服务器 (无需 key, 模型由服务器加载)。"""

    def __init__(self, base_url: str, model: str = "qwen"):
        self.base = base_url.rstrip("/")
        self.model = model

    def complete(self, messages, *, max_tokens, temperature,
                 extra: Optional[Dict] = None) -> Dict[str, Any]:
        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            **(extra or {}),
        }).encode()
        req = urllib.request.Request(
            self.base + "/v1/chat/completions", data=body,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=1200) as r:
            return json.load(r)


def key_from_env(name: str = "LLM_API_KEY") -> Optional[str]:
    return os.environ.get(name) or None
