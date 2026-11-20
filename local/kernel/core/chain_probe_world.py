# -*- coding: utf-8 -*-
"""core/chain_probe_world.py — **杠杆世界** (2026-09-21)

用途: 造一块"**单条规则有杠杆 (>1)**"的基底 —— 用于判定"挑内容"(§131: 旧基底里单条规则效应 <= ±1 ⇒ 不可辨别 ✗)

设计: 加一个**全局模式** `mode ∈ {0,1}`（每 `mode_period` tick 翻转一次, 且**写进状态词** ⇒ 可学 ✓）
      正确动作 = `ACTS[(k + mode) % M]` ⇒ **模式一翻, 所有上下文的答案整体挪一位** ✓
      ⇒ 关于"模式"的那一条知识 = **K 倍杠杆** (一次修好 K 个上下文) ✓✓
接口: 同 combo_probe_world (+ `truth_now()` 取当前模式下的真值表 · `mode()` 取当前模式)
"""
import random
from typing import List, Tuple


def make_chain_world(rng=None, cs=None, wm=None, seed: int = 42,
                     K: int = 16, M: int = 8, my_lo: int = 0, my_hi: int = -1,
                     mode_period: int = 200, persist=(8, 24),
                     couple: bool = False, **kwargs):
    """★ couple (2026-09-21, I-1 仪器修复, **默认 False ⇒ 逐位不变**):
    与 `combo_probe_world.couple` 同一修法 (同一种**观测伪造**: world_tick 每步无条件写
    '命中'+'落空' 两变体进因果日志, 而真结果从不进因果通道 ⇒ 链键/结果被钉死 ⇒
    精确率恒 = 1/M, §149 实dump 已坐实)。couple=True: ① 真结果在 world_step 内进因果通道
    ② 两变体词表观测降为 principle=False ③ tick 补写真实状态词。"""
    if rng is None:
        rng = random.Random(seed)
    ACTS: List[str] = ['A%d' % (i + 1) for i in range(max(2, int(M)))]
    CTX: List[str] = ['场%d' % i for i in range(max(2, int(K)))]
    st = {'tick': 0, 'k': 0, 'left': int(persist[0]), 'mode': 0, 'last_hit': 0, 'state': ''}
    stats = {'acts': 0, 'hits': 0, 'events': 0}

    def _correct(k: int) -> str:
        # ★ 杠杆点 (修正 2026-09-21): 把上下文**分组** (2 组) ⇒ **同组共用一个正确动作**
        #   ⇒ 一条'组×模式'的规则一次修好 K/2 个 (上下文,动作) 对 ⇒ 杠杆 = K/2 ✓✓
        _g = int(k) // max(1, len(CTX) // 2)
        return ACTS[(_g + int(st['mode'])) % len(ACTS)]

    def _sw() -> str:
        _g = st['k'] // max(1, len(CTX) // 2)
        return '模式%d·组%d·%s' % (st['mode'], _g, '命中' if st['last_hit'] else '落空')

    def _sd() -> dict:
        return {'表盘': st['state']}

    st['k'] = rng.randrange(len(CTX))
    st['state'] = _sw()

    def world_step(obj: str, act: str) -> Tuple[dict, dict]:
        if obj != '表盘' or act not in ACTS:
            return _sd(), _sd()
        prev = _sd()
        st['tick'] += 1
        stats['acts'] += 1
        if wm is not None:
            wm.observe_action('表盘', act, obj, ctx=None, channel='obs')
        elif cs is not None:
            cs.observe('表盘', act, obj, channel='obs')
        hit = 1 if act == _correct(st['k']) else 0
        stats['hits'] += hit
        st['last_hit'] = hit
        st['state'] = _sw()
        if couple and cs is not None:
            # ★ I-1 (gated): 真结果进因果通道 (动作事件之后, 同上下文同序 ✓)
            try:
                cs.observe('表盘', '变', st['state'])
            except Exception:
                pass
        return _sd(), prev

    def world_tick():
        st['tick'] += 1
        if mode_period and st['tick'] % int(mode_period) == 0:
            st['mode'] = 1 - st['mode']          # ★ 模式翻转 ⇒ 所有答案挪位 (杠杆 K)
        st['left'] -= 1
        if st['left'] <= 0:
            st['k'] = rng.randrange(len(CTX))
            st['left'] = rng.randint(int(persist[0]), int(persist[1]))
        st['state'] = _sw()
        if cs is not None:
            try:
                _g = st['k'] // max(1, len(CTX) // 2)
                _pair = ('模式%d·组%d·命中' % (st['mode'], _g),
                         '模式%d·组%d·落空' % (st['mode'], _g))
                if couple:
                    # ★ I-1 (gated): 词表 hack 只登记概念 (principle=False), 不进因果日志
                    for _w in _pair:
                        cs.observe('表盘', '变', _w, principle=False)
                    cs.observe('表盘', '变', st['state'])
                else:
                    for _w in _pair:
                        cs.observe('表盘', '变', _w)
                stats['events'] += 1
            except Exception:
                pass
        return []

    def obj_of():
        return '表盘'

    _hi = len(CTX) if (my_hi is None or my_hi < 0) else min(int(my_hi), len(CTX))
    _lo = max(0, int(my_lo))

    def acts_of(o):
        if o != '表盘':
            return []
        if not (_lo <= st['k'] < _hi):
            return ['等待']
        return list(ACTS)

    def state_of(o):
        return st['state'] if o == '表盘' else None

    def context_of():
        return []

    def goal_of(o):
        return None

    def families():
        return {}

    def truth_now():
        return {i: _correct(i) for i in range(len(CTX))}

    def mode():
        return int(st['mode'])

    # ★ §220 世界契约 (只声明, 不写数据): 本世界**声明其有序坐标轴** = '量' (复合序 j=模式*2+组 经适配层落档)
    # ★ §221 世界契约: 条件(命中/落空) **是**本世界状态的一维 —— 逐事件审计 bv=0 (无伪造)
    return {'axis_declared': '量', 'cond_is_state': True,
            'world_step': world_step, 'obj_of': obj_of, 'state_of': state_of,
            'acts_of': acts_of, 'context_of': context_of, 'goal_of': goal_of,
            'world_tick': world_tick, 'families': families, 'stats': stats,
            'truth_now': truth_now, 'mode': mode, 'K': len(CTX), 'M': len(ACTS)}
