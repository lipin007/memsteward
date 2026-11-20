# -*- coding: utf-8 -*-
"""M1 事件结构 — V3 图纸施工件移植 (2026-08-12 19:2x)

图纸: plan/modules/M1-事件结构.md (五轮质疑 + C1 修复 + K5 回流后)
战略: P3 时间维度显式不可约 — t 是事件的结构成分, 不是元数据。

与旧雏形 (图纸质疑前) 的本质差异:
  1. frozen=True          事件不可变 (事实性, 构造后修改抛异常)
  2. changes = (dim, new) 二元组 (观察通道产物, 旧值是状态表职责)
  3. 真源不删             窗口 = 查询/投影边界 (C1 修复: 遗忘在视图层, 不在事实层)
  4. after(t) / count()  时序查询 + 单调计数 (旧雏形缺失)
  5. 零依赖              不 import 任何其他 ns 模块 (唯一纯净地基)
"""
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class Event:
    """最小事件单元: 时间不可约, 不可变, 纯 id 不承载语义."""
    t: int                          # 时间戳 (全局单调, 结构成分)
    subj: str                       # 主体 (对象身份, 纯 id)
    act: str                        # 动作 (纯 id, 概念在 M2 涌现)
    obj: Optional[str] = None       # 客体 (可为 None: 无客体动作)
    changes: Tuple[Tuple[str, str], ...] = ()  # (dim, new_value) 元组
    cog: bool = False               # 认知自我事件标记 (2026-09-19 A): 由调用点【显式声明】
                                    # — 探索/失手/达成 等自我投影事件, 非世界动作。
                                    # 默认 False ⇒ 既有构造零破坏。

    def __repr__(self) -> str:
        chg = f" {self.changes}" if self.changes else ""
        tail = f"→{self.obj}" if self.obj else ""
        return f"Event(t={self.t}, {self.subj}→{self.act}{tail}{chg})"


class EventStream:
    """事件流: 时间维度的容器.

    真源语义 (C1 修复): _all 保留全部事件永不删, count() 单调;
    窗口只是查询/投影边界 (window_events/recent 的视角), 不是删除.
    """

    def __init__(self, window: int = 2000):
        self.window = window
        self._all: List[Event] = []   # 真源: 全量, 永不删
        self._t: int = 0              # 全局单调时间轴

    # -- 时间轴 --
    def tick(self) -> int:
        """分配下一个时间戳 (全局单调递增)."""
        self._t += 1
        return self._t

    # -- 写入 --
    def emit(self, subj: str, act: str, obj: Optional[str] = None,
             changes: Optional[List[Tuple[str, str]]] = None,
             cog: bool = False) -> Event:
        """事件进入 (源头): 打时间戳, 入真源. 无变化 = 空元组, 不产生污染."""
        ev = Event(t=self.tick(), subj=subj, act=act, obj=obj, cog=cog,
                   changes=tuple(changes or ()))
        self._all.append(ev)
        return ev

    def append(self, e: Event) -> None:
        """追加外部构造的事件 (t 须已分配)."""
        assert e.t > self._t or (e.t == self._t and self._all), \
            f"t 必须单调递增: got {e.t}, axis at {self._t}"
        if e.t > self._t:
            self._t = e.t
        self._all.append(e)

    # -- 查询 (投影视角, 不删真源) --
    def recent(self, k: int = 100) -> List[Event]:
        """最近 k 个 (时间窗口查询)."""
        return self._all[-k:]

    def after(self, t: int) -> List[Event]:
        """t 之后的所有 (严格边界, 不含 t 本身)."""
        return [e for e in self._all if e.t > t]

    def window_events(self) -> List[Event]:
        """滚动窗口内全部 (投影视角, 真源仍在)."""
        return self._all[-self.window:]

    def count(self) -> int:
        """总量 (单调, 真源完整性)."""
        return len(self._all)

    def __len__(self) -> int:
        return len(self._all)

    def __getitem__(self, i: int) -> Event:
        return self._all[i]
