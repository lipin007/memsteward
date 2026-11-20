# -*- coding: utf-8 -*-
"""M7 记忆影子 — 事件流的派生投影视图 (V3 图纸施工件移植, 2026-08-12)

图纸: plan/modules/M7-记忆影子.md
记忆 = 事件流的影子 (派生视图), 不是独立写入点。事件流 (M1) 是唯一事实源。

M7 既定任务: 记忆影子形态 (事件级投影 + 巩固标记, 按内容索引)。
实验体 v2-fix 现状: memory_hub 是向量级三通道 (E10 修复, 感知侧);
概念层记忆散在 ConceptSpace (types/events/causal_edges 即语义)。本模块 =
概念层记忆影子: 从事件流投影, 按对象/动作复合索引, 零独立写入。

边界 (单真源铁律):
  - 影子零写入: 任何模块 (包括记忆自己) 不得向影子写入新事件
  - 巩固/遗忘只动投影 (consolidated 标记 / 投影缩小), 真源完整
  - 遗忘分层: 事件层=投影缩小 (窗口外不可检索, 真源保留);
    概念层=M2/M3 休眠可恢复 (语义稳定, 不因窗口滚动而丢)
  - M7 零统计: 语义查询走概念空间 (统计只在 M9 采集/M6 消费)
"""
from collections import defaultdict
from typing import Dict, List, Optional


class MemoryShadow:
    """记忆影子: 事件流投影 (按对象/动作/时间复合索引)

    与 M1 事件流职责互补:
      - M1 按 t 查 (after/recent) — 唯一事实源
      - M7 按内容查 (对象/动作) — 派生索引 + 巩固标记
    """

    def __init__(self, stream, window: int = 2000):
        self.stream = stream            # 唯一事实源 (注入, 非复制)
        self.window = window            # 投影窗口 (事件层遗忘边界)
        self.episodic: List[dict] = []  # 情景投影 (事件级记忆, 可查视图)
        self.consolidated: set = set()  # 已巩固事件 id (时间展开标记)
        self._last_t: int = 0           # 已投影到的流时间戳 (增量对齐锚)
        # 复合索引: 内容 → 投影事件位置 (对象/动作)
        self._idx_obj: Dict[str, list] = defaultdict(list)
        self._idx_act: Dict[str, list] = defaultdict(list)

    # ── 投影 (只读流 → 写影子投影; 事件写入仍只经 M1) ─────────
    def refresh(self, t: Optional[int] = None) -> None:
        """从事件流投影窗口内全部事件 (增量: 只补新事件).

        对齐修复 (2026-08-16 盘点): 旧实现用 `recent(window)[n_old:]`
        增量 — 事件数超过窗口时 episodic 不回缩, n_old 与流位置错位 →
        长会话影子停止更新。现改为以 `_last_t` 为增量锚
        (stream.after(_last_t), 严格边界不含自身), 与 episodic 长度
        解耦 — 窗口滚动不再影响增量对齐。
        窗口自维护: 投影后若 episodic 超 window → 剪尾重建索引
        (遗忘在视图层, 真源保留; 与 C1 修复同哲学)。
        """
        if hasattr(self.stream, 'after') and self._last_t > 0:
            new_events = self.stream.after(self._last_t)
        elif hasattr(self.stream, 'recent'):
            # 无 after 流 (或首次): 窗口内全量, 与旧语义一致
            new_events = self.stream.recent(self.window)
            if self.episodic:
                # 保底: 只取未投影部分 (兼容非 after 流)
                n_old = len(self.episodic)
                new_events = new_events[n_old:]
        else:
            new_events = []
        for ev in new_events:
            rec = self._project(ev)
            if rec is not None:
                self.episodic.append(rec)
                self._idx_obj[rec.get('obj', '')].append(len(self.episodic) - 1)
                self._idx_act[rec.get('act', '')].append(len(self.episodic) - 1)
                if rec.get('t') is not None:
                    self._last_t = max(self._last_t, rec['t'])
        # 窗口自维护 (遗忘在视图层): 超窗剪尾 + 索引重建
        if len(self.episodic) > self.window:
            self.episodic = self.episodic[-self.window:]
            self._idx_obj = defaultdict(list)
            self._idx_act = defaultdict(list)
            for i, rec in enumerate(self.episodic):
                self._idx_obj[rec.get('obj', '')].append(i)
                self._idx_act[rec.get('act', '')].append(i)

    def _project(self, ev) -> Optional[dict]:
        """事件 → 投影记录 (事件级记忆形态)"""
        subj = getattr(ev, 'subj', None) or getattr(ev, 'person', None)
        act = getattr(ev, 'act', None) or getattr(ev, 'action', None)
        obj = getattr(ev, 'obj', None)
        t = getattr(ev, 't', None)
        if subj is None or act is None:
            return None
        return {'t': t, 'subj': subj, 'act': act, 'obj': obj or '',
                'cog': bool(getattr(ev, 'cog', False)),
                'id': getattr(ev, 'id', f'{t}:{subj}:{act}:{obj}')}

    # ── 巩固/遗忘 (时间展开, 只动投影) ─────────────────────────
    def consolidate(self, t: Optional[int] = None) -> None:
        """巩固标记: 投影内全部事件标记已巩固 (全部非 top-K).

        语义澄清 (2026-08-16 盘点): 此标记 = 时间展开标记 (睡眠/重放
        覆盖过的经历), 非固化写回 — 消费端待阶段 C (记忆参与推理)
        接线。当前仅 summary 计数可读 (元认知读数), 零副作用。
        """
        for rec in self.episodic:
            self.consolidated.add(rec['id'])

            # ⚠️ 预留接口 (2026-08-17 标注): 显式遗忘入口 (语义独有, 元认知可调);
            #    生产零消费; 勿删勿归档
    def forget(self, t: Optional[int] = None) -> None:
        """遗忘: 超过窗口的事件从投影移除 (影子缩小, 真源保留).

        窗口自维护已在 refresh 内建 (超窗剪尾); 本方法 = 显式主动
        遗忘入口 (研究/阶段 C 可调), 只动影子, 真源不动。
        """
        # 投影只保留窗口内 (recency 排序由事件流保证)
        keep = self.episodic[-self.window:]
        if len(keep) < len(self.episodic):
            dropped = self.episodic[:len(self.episodic) - len(keep)]
            # 重建索引 (只动影子, 真源不动)
            self.episodic = keep
            self._idx_obj = defaultdict(list)
            self._idx_act = defaultdict(list)
            for i, rec in enumerate(self.episodic):
                self._idx_obj[rec.get('obj', '')].append(i)
                self._idx_act[rec.get('act', '')].append(i)
            # 已巩固事件从投影移除 → 标记保留? 不: 投影移除即不可检索
            # (事件层遗忘 = 检索失败, 真源仍在 stream)

    # ── 查询 (按内容, 非按 t — 与 M1 职责互补) ─────────────────
    def retrieve(self, obj: Optional[str] = None,
                 act: Optional[str] = None,
                 subj: Optional[str] = None,
                 limit: int = 20) -> List[dict]:
        """按对象/动作/主体查询投影 (内容索引, 非时间序).

        联合检索修复 (2026-08-16 盘点): 旧实现 obj/act/subj 为 elif
        互斥 — 情境相似性 (阶段 C) 恰需对象+动作联合约束。现改为
        任意组合交集: 有索引的取索引位集合, 其余全量; 交集后按
        索引序取最近 limit 个 (时间倒序, 最近优先)。
        """
        cands = None
        if obj:
            cands = set(self._idx_obj.get(obj, []))
        if act:
            s = set(self._idx_act.get(act, []))
            cands = s if cands is None else (cands & s)
        if cands is None:
            cands = set(range(len(self.episodic)))
        if subj:
            cands = {i for i in cands
                     if self.episodic[i].get('subj') == subj}
        out = [self.episodic[i] for i in sorted(cands)]
        return out[-limit:][::-1]  # 最近优先

    def count_by_obj(self, obj: str) -> int:
        """对象出现次数 (投影视图)"""
        return len(self._idx_obj.get(obj, []))

    # (归档 2026-08-16: count_by_act → _archive_legacy/dead_interfaces_20260816.py)

    # ── 元认知 ────────────────────────────────────────────────
