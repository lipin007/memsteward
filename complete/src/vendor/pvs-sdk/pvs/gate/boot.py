# -*- coding: utf-8 -*-
"""pvs.gate.boot —— 开机闸/冷启动包（整合施工方案_v1.md B2，治"新会话冷启动重复劳动"）。

新会话开机 = 一条命令拿到知情包：
  ① 门禁断言（run_preflight）——教训→行为检查，FAIL 即开工受阻
  ② 签名记忆切片（LandingStore.recall，注入依赖，不硬连 CallDecay）——只拉相关账，不背全史
  ③ 真相摘要 digest（调用方注入）——当前真相，不用扫全盘

用法：
    from pvs.gate.boot import boot, render
    pkg = boot(landing=store, signature="arc2 发射", digest=truth_text)
    print(render(pkg))   # 注入新会话上下文

铁律：治理层不硬依赖记忆层（landing 以参数注入）；一切失败如实报 FAIL，禁静默吞错。
"""
from __future__ import annotations

import time
from typing import Any, Optional

from .preflight import run_preflight


def boot(landing: Any = None, signature: str = "", digest: str = "",
         root: Optional[str] = None, ack=None, strict: bool = False,
         slice_k: int = 8) -> dict:
    """开机闸：门禁＋签名记忆切片＋真相摘要 → 冷启动包（dict）。"""
    errors = []
    try:
        rows, ok = run_preflight(root=root, ack=ack, strict=strict)
    except Exception as e:                      # 门禁自身炸 = 阻断，不静默
        rows, ok = [], False
        errors.append(f"preflight_crash: {e}")
    slice_: list = []
    if landing is not None and signature:
        try:
            slice_ = landing.recall(signature, k=slice_k)
        except Exception as e:
            errors.append(f"recall_crash: {e}")
    elif landing is not None and not signature:
        errors.append("landing 给了但 signature 为空——切片跳过（防全史注入）")
    n_fail = sum(1 for r in rows if r.get("status") == "FAIL")
    n_decl = sum(1 for r in rows if r.get("status") == "DECL")
    return {"ok": ok, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "preflight_rows": rows, "n_fail": n_fail, "n_decl": n_decl,
            "memory_slice": slice_, "digest": digest, "errors": errors}


def render(pkg: dict) -> str:
    """把开机包渲染成可注入文本（冷启动包本体；尺寸=冷启动 token 账）。"""
    L = []
    L.append("=== 开机包 (pvs.gate.boot) ===")
    L.append(f"门禁: {'放行' if pkg['ok'] else '受阻'} (FAIL {pkg['n_fail']}, DECL {pkg['n_decl']})")
    for r in pkg.get("preflight_rows", []):
        if r.get("status") != "OK":
            L.append(f"  [{r.get('status')}] {r.get('id')}: {r.get('detail', '')[:120]}")
    for e in pkg.get("errors", []):
        L.append(f"  [ERR] {e}")
    ms = pkg.get("memory_slice") or []
    L.append(f"记忆切片 ({len(ms)} 条):")
    for m in ms:
        en = m.get("entry", m) if isinstance(m, dict) else {"raw": str(m)}
        sig = (en.get("signature") or en.get("obj", "")) if isinstance(en, dict) else ""
        L.append(f"  - {str(sig)[:60]} (liveness {en.get('liveness', '?')})" if isinstance(en, dict) else f"  - {en}")
    d = pkg.get("digest") or ""
    L.append("真相摘要:")
    L.append(d if d else "  (未提供)")
    return "\n".join(L)
