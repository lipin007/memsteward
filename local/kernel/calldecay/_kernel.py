# -*- coding: utf-8 -*-
"""定位 core 内核并加入模块搜索路径（不改内核源码、不复制内核源码）。

查找顺序：
1. 环境变量 CALLDECAY_CORE（指向包含 core/ 的目录）
2. calldecay/_kernel/（将来 wheel 捆绑位）
3. 仓库布局：CallDecay/sdk/calldecay → 上两级 = CallDecay/（内含 core/）
"""

import os
import sys
from pathlib import Path


def bootstrap():
    os.environ.setdefault("LLM_ARM", "1")          # 开模型咨询臂（可 env 覆盖）
    os.environ.setdefault("LLM_ARM_CHAT", "1")     # 上游默认走 OpenAI 兼容端点
    here = Path(os.path.abspath(__file__)).parent  # L09 2026-11-20: abspath 形态
    candidates = []
    env = os.environ.get("CALLDECAY_CORE")
    if env:
        candidates.append(Path(env))
    candidates.append(here / "_kernel")
    candidates.append(here.parent.parent)
    for c in candidates:
        if (c / "core" / "llm_arm.py").exists():
            s = str(c)
            if s not in sys.path:
                sys.path.insert(0, s)
            return c / "core"
    raise ImportError(
        "未找到 core/ 内核。设置环境变量 CALLDECAY_CORE 指向包含 core/ 的目录。")
