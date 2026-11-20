# -*- coding: utf-8 -*-
"""CallDecay —— 决策型智能体的记忆层（LLM 调用衰减中间件）。

三行接入：
    from calldecay import CallDecay
    cd = CallDecay()
    d = cd.decide(obj="兔", goal="丰", current="兔", actions=["喂食", "放牧"])

许可：本包编排层 Apache-2.0；core/ 内核 AI Research Source License v1.2
（非商用免费、商用需事先书面同意）。详见包内 LICENSE 与仓库 PATENTS.md。
"""

__version__ = "0.1.0"


def __getattr__(name):
    # 惰性导入：允许调用方先把 LLM_ARM_HOST 等环境变量设好再取 CallDecay
    if name == "CallDecay":
        from .adapter import CallDecay
        return CallDecay
    if name == "Metrics":
        from .metrics import Metrics
        return Metrics
    raise AttributeError(f"module 'calldecay' has no attribute {name!r}")
