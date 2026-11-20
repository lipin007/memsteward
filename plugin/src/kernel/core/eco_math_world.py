"""EcoMathWorld v2 — 随机离散事件生态世界 (2026-08-20)

宇宙底层逻辑是数学: 生态 = 微分方程组, 物理 = 数学, 调参 = 方程系数。
本世界**无引擎、纯数学演化** — 状态是连续变量 (草量 P / 温度 T) +
**整数个体** (兔 R / 狼 G), 演化是**随机离散事件模拟** (Gillespie 风格):

- 期望值 = 资源限制 Lotka-Volterra 方程组 (数学理论: 平衡点可解析)
- 个体事件 (繁殖/死亡/捕食) 是真实概率过程 → 振荡 + 混沌自然涌现
  (连续 ODE 稳定螺旋收敛不振荡 — v1 实锤; 真实生态振荡来自离散性)

与 Godot 生态世界 (引擎隐式求解) 的本质差异:
- Godot: 调参 = 跑实验摸动力学; 行为环是旁观者 (干预破坏生态 → 规划 0)
- 本世界: 参数 = 生态学系数 (出生率/死亡率/捕食率/承载力), 有理论;
  行为环动作 = **控制输入直接改状态** (喂食/猎杀/保护/放牧) —
  **动作因果强 → 行为环规划可学**

复杂度:
1. 三物种食物链 (草→兔→狼) + 资源限制 (承载力争斗)
2. 昼夜周期驱动 (草生长光驱动 + 温度节律, F3)
3. 随机个体事件 (出生/死亡/捕食 — 生/死事件真实语义, F4 混沌)
4. 最小种群保护 rescue (灭绝→恢复 — F4 僵化破局舞台)
5. 可扩展: 空间元胞/季节多周期/更多物种 (设计即支持)

事件流与 Godot 同构 (在/变/共现/生/死 → cs.observe), 概念空间学习
(DMIT 边: 草↔兔↔狼 生态关联) 纯数学世界更干净 (无 id 污染/物理噪声)。
"""

from typing import List, Optional, Tuple
import math
import random


# ── 说话者词表 (2026-08-22, 语言理解端: "会说话的世界") ──────
# 环境预置: 世界侧说话者把事件三元组 (对象, 谓词, 状态) 翻译成
# 标准英文词 (语言哲学约束: 符号须符合标准英文语境), 逐词喂
# learn_pair → 系统把外部符号锚到内部概念 (符号接地)。
# 三分类: [环境预置] (说话者词汇表 = 世界物理的一部分)。
SPEAKER_LEXICON = {
    # 对象
    '草': 'grass', '兔': 'rabbit', '狼': 'wolf', '太阳': 'sun',
    '我': 'I', '生态': 'ecosystem',
    # 谓词 (事件类型)
    '在': 'be', '变': 'become', '共现': 'co-occur', '生': 'born',
    '死': 'die', '捕食': 'hunt', '进食': 'eat',  # 进食 (fusion 2026-08-22)
    '吃草': 'grass',  # 进食事件宾语 (fusion; 非概念, 仅翻译表条目)
    '观望': 'watch', '喂食': 'feed',
    '猎杀': 'cull', '保护': 'protect', '放牧': 'graze',
    # 状态桶
    '枯': 'withered', '低': 'low', '中': 'medium', '高': 'high',
    '丰': 'abundant', '灭绝': 'extinct', '濒危': 'endangered',
    '少': 'scarce', '多': 'plentiful', '新生': 'newborn', '死亡': 'dead',
    '白天': 'day', '黑夜': 'night', '温': 'warm', '热': 'hot',
    '冷': 'cold',
}


def make_eco_world(rng=None, cs=None, wm=None, seed: int = 42,
                   dt: float = 0.1, day_len: int = 20,
                   noise: float = 0.02,
                   predator_cycle: int = 0,
                   predator_window: int = 5,
                   predator_base: float = 0.3,
                   hide_clock: bool = False,
                   **kwargs):
    """工厂: 返回世界流句柄 dict (与 math_world/godot 同构).

    world_step(obj, act) -> (dict, dict)             # 多对象状态 (生态全貌)
    world_tick() -> None                           # 环境推进 (昼夜/草)
    obj_of() -> '兔'                               # 焦点对象 (行为环单焦点决策器)
    state_of(obj) -> 桶串
    acts_of(obj) -> 动作集
    context_of() -> [('太阳', '白天/黑夜')]        # 节律调制源
    goal_of(obj) -> None                           # 自治世界: 目标由内在动机涌现 (M8)
    families() -> {}                               # 无题族 (非回合制)
    """
    if rng is None:
        rng = random.Random(seed)

    # ── 说话者 (语言理解端, 2026-08-22): 默认关零破坏 ──
    speaker = kwargs.get('speaker', False)  # --speaker: 事件旁白 → learn_pair
    lang = kwargs.get('lang', None)          # LangInterface (词↔概念绑定, 零写)

    # ── 状态: P 草量 (连续) + R/G 个体 (整数) ──
    st = {
        'P': 60.0,   # 草量 (0~K_P)
        'R': 20,     # 兔个体数
        'G': 6,      # 狼个体数
        't': 0.0,    # 时间步 (dt 连续时钟, 昼夜用)
        'step': 0,   # 行为步时钟 (2026-08-24 E3: 捕食周期用, world_tick 推进)
    }
    stats = {'events': 0, 'buckets': 0, 'acts': 0,
             'born': 0, 'dead': 0, 'hunted': 0,
             'R': 0, 'G': 0, 'P': 0.0}  # R/G/P 数值同步 (2026-08-29 A3
             # 剩余空间: 归一化信号源 — 捕食压力 = hunted/R, 需种群
             # 数值; world_step 末尾同步, 零行为影响)

    # ── 生态学参数 (期望值 = 资源限制 LV, 平衡点可解析) ──
    # R* = h_R*d2/(b2-d2), P* ≈ g*(1-P/K)/(a1*R), G* = (b1*P/(P+h_P)-d1)/a2
    PAR = {
        'g': 2.5,    # 草生长率 (光驱动)
        'K_P': 300.0,  # 草承载力
        'a1': 0.0005,  # 兔吃草率
        'b1': 0.30,  # 兔出生率 (期望/天, 依赖草半饱和)
        'h_P': 20.0,  # 兔半饱和 (草 20 时出生率半速)
        'd1': 0.05,  # 兔自然死亡率
        'a2': 0.025,  # 狼捕食率 (每兔每狼)
        'b2': 0.075,  # 狼出生率 (依赖兔半饱和)
        'h_R': 20.0,  # 狼半饱和 (兔 20 时出生率半速)
        'd2': 0.05,  # 狼死亡率
    }

    # ── 桶化 (观察接口; 对准平衡点 R*≈25 区域) ──
    def grass_bucket(p):
        if p < 15: return '枯'
        if p < 35: return '低'
        if p < 60: return '中'
        if p < 90: return '高'
        return '丰'

    def rabbit_bucket(r):
        if r < 3: return '灭绝'
        if r < 10: return '濒危'
        if r < 25: return '少'
        if r < 55: return '中'
        if r < 95: return '多'
        return '暴增'

    def wolf_bucket(g):
        if g < 2: return '灭绝'
        if g < 5: return '少'
        if g < 11: return '中'
        if g < 20: return '多'
        return '泛滥'

    def day_bucket(t):
        phase = math.sin(2.0 * math.pi * t / day_len)
        return '白天' if phase >= 0 else '黑夜'

    def state_of(obj):
        if obj == '草':
            return grass_bucket(st['P'])
        if obj == '兔':
            return rabbit_bucket(st['R'])
        if obj == '狼':
            return wolf_bucket(st['G'])
        if obj == '太阳':
            return day_bucket(st['t'])
        if obj == '生态':
            return (f"草{grass_bucket(st['P'])}/兔{rabbit_bucket(st['R'])}"
                    f"/狼{wolf_bucket(st['G'])}")
        return None

    _last = {}  # obj -> 上次观察桶

    def _sentence(cs_obj, t, val=''):
        """事件三元组 → 标准英文句子 (说话者旁白, 模板直译).

        只转述事件已知信息, 不编造: 捕食事件主语=被捕对象 → 被动式
        "The rabbit is hunted", 不说 "wolf hunts" (狼是捕食者是
        说话者代码外的知识 — 语言陷阱: 说话者不替系统思考)。
        标准英文语境铁律 (08-16): 状态桶词作表语 (plentiful 非
        many — "The rabbit is many" 非标准英文)。太阳状态特例:
        "It is day/night" ("The sun is day" 非标准)。"""
        o = SPEAKER_LEXICON.get(cs_obj)
        v = SPEAKER_LEXICON.get(val)
        if t == '在':
            if cs_obj == '太阳' and v:
                return f"It is {v}"
            return f"The {o} is {v}" if (o and v) else None
        if t == '变':
            return f"The {o} becomes {v}" if (o and v) else None
        if t == '生':
            return f"A {o} is born" if o else None
        if t == '死':
            return f"A {o} dies" if o else None
        if t == '捕食':
            return f"The {o} is hunted" if o else None
        if t == '共现':
            return f"{o} co-occurs with {v}" if (o and v) else None
        return None

    def _speak(cs_obj, t, val=''):
        """说话者旁白: 事件三元组 → 逐词 learn_pair 绑定 + 标准英文
        句子 → hear_sentence (反查理解, 词锚定 + 同刻 see+hear 符号
        接地). 零概念空间写入; 句子不驱动决策; 不做语法分析 (语言
        陷阱纪律 2026-08-22)."""
        for concept in (cs_obj, t, val):
            w = SPEAKER_LEXICON.get(concept)
            if w:
                lang.learn_pair(concept, w)
        s = _sentence(cs_obj, t, val)
        if s and lang is not None:
            lang.hear_sentence(s)

    def _emit(cs_obj, t, val=''):
        stats['events'] += 1
        if cs is not None:
            if t == '在':
                cs.observe(cs_obj, '在', val)
            elif t == '变':
                cs.observe(cs_obj, '变', val)
            elif t == '共现':
                cs.observe(cs_obj, '共现', val)
            elif t in ('生', '死'):
                cs.observe(cs_obj, t, '新生' if t == '生' else '死亡')
            elif t == '捕食':
                # 2026-08-20 M2: 捕食事件进概念空间 (主语=被捕对象,
                # 由调用处传入) — 原 _emit('共现','捕食') 的 t='捕食'
                # 不在调度分支 → 静默丢弃 (真实 bug)。
                cs.observe(cs_obj, '捕食', val)
        if speaker and lang is not None:
            _speak(cs_obj, t, val)

    def _bucket_sync(force=False, emit_every=False):
        """桶变化检测 → 在/变 事件.
        emit_every=True (2026-08-20): 每步强制发全部对象 '在' 事件 —
        相邻事件对 (草,在,低)→(兔,在,多) 天天有 → DMIT 生态关联
        (草↔兔↔狼) 涌现 (生产回归基线量级事件密度, 相位耦合可承受)。
        顺序=草→兔→狼→太阳 (原样): 条件提取 (_recent_state_word) 有
        同对象过滤 + 结果侧有前看窗口 (sweep 对齐) → 事件顺序与
        学习无关 — 排序迁就已移除 (2026-08-20 三修回滚)。"""
        _objs = (('草', grass_bucket), ('兔', rabbit_bucket),
                 ('狼', wolf_bucket))
        if not hide_clock:
            _objs = _objs + (('太阳', day_bucket),)  # hide_clock → 太阳不 emit (环境时钟隐藏)
        for obj, fn in _objs:
            v = fn(st['P'] if obj == '草' else st['R'] if obj == '兔'
                   else st['G'] if obj == '狼' else st['t'])
            if emit_every or force or _last.get(obj) != v:
                if (emit_every or force) and obj in _last and _last.get(obj) != v:
                    _emit(obj, '变', v)
                _emit(obj, '在', v)
                _last[obj] = v
                stats['buckets'] += 1

    def _advance():
        """推进 1 步: 草连续演化 + 兔/狼随机离散事件 (期望=LV).
        事件稀疏化 (2026-08-20): 相位耦合 O(n²) × 事件密度 — 生产回归基线
        每步 1-2 事件; 本世界逐只 emit 25+/步卡死 (concept_phase
        _step_phase_coupling 瓶颈)。改: 步末汇总, 每步 ≤4 事件。"""
        p, r, g = st['P'], st['R'], st['G']
        par = PAR
        light = 0.5 + 0.5 * math.sin(2.0 * math.pi * st['t'] / day_len)
        # 草: 光驱动生长 - 兔吃 (连续)
        dP = (par['g'] * (1.0 - p / par['K_P']) * (0.5 + 0.5 * light)
              - par['a1'] * r * p)
        st['P'] = max(0.0, p + dP * dt)
        st['t'] += dt
        # 兔: 繁殖 (依赖草) / 自然死亡 / 被捕 (随机离散, 汇总事件)
        p_birth = min(1.0, par['b1'] * p / (p + par['h_P']) * dt * 10.0)
        p_death = par['d1'] * dt * 10.0
        # 周期性捕食窗口 (2026-08-24 E3 跨世界复现, 默认 0 零影响):
        # predator_cycle > 0 → 狼捕食变成周期事件 — fusion 同款双通道:
        #   物理通道: 窗口内 p_hunt 全量, 窗口外 ×predator_base 低基线
        #              (生态平衡 + 干净周期信号);
        #   事件通道: 每窗口最多 emit 一次捕食事件 (窗口索引变更时
        #              重置 — 兼容 eco 双推进 world_step+world_tick
        #              同 step 值重复评估), 保证 _appear_ivals 干净
        #              周期 (interval ≈ cycle; 窗口内密集 emit 间隔
        #              =1 会拉低 interval mean — fusion 实测实锤)。
        _win = st['step'] // predator_cycle if predator_cycle > 0 else -1
        if _win >= 0 and st.get('_emit_win') != _win:
            st['_emit_win'] = _win
            st['_emit_fired'] = False
        _in_hunt_window = (predator_cycle > 0
                           and st['step'] % predator_cycle < predator_window)
        _p_hunt_full = min(1.0, par['a2'] * g * dt * 10.0)
        if predator_cycle > 0:
            p_hunt = _p_hunt_full if _in_hunt_window \
                else _p_hunt_full * predator_base
        else:
            p_hunt = _p_hunt_full
        n_born = n_dead = n_hunt = 0
        for _ in range(r):
            x = rng.random()
            if x < p_birth:
                st['R'] += 1; n_born += 1
            elif x < p_birth + p_death:
                st['R'] -= 1; n_dead += 1
            elif x < p_birth + p_death + p_hunt:
                st['R'] -= 1; n_hunt += 1
        # 狼: 繁殖 (依赖兔) / 死亡 (汇总事件)
        p_gb = min(1.0, par['b2'] * r / (r + par['h_R']) * dt * 10.0)
        p_gd = par['d2'] * dt * 10.0
        n_gb = n_gd = 0
        for _ in range(g):
            x = rng.random()
            if x < p_gb:
                st['G'] += 1; n_gb += 1
            elif x < p_gb + p_gd:
                st['G'] -= 1; n_gd += 1
        # 步末汇总事件 (每类 1 次, 语义保留密度降 10×+)
        # 生/死/捕食**恢复进概念空间** (2026-08-20 二修回滚 — 教科书
        # 真实性优先): 个体事件是生态世界的真实语义 (F4 混沌)。
        # 词性污染 (生/死→动作词) 由对象过滤挡真链; 打断 sweep 对齐
        # 由前看窗口 (跳过非变事件 + '我' 主语 break) 解决。固定词
        # (新生/死亡, Godot 同款) 防数字 id 污染状态词集。
        if n_born + n_gb > 0:
            stats['born'] += n_born + n_gb
            _emit('兔' if n_born > n_gb else '狼', '生')
        if n_dead + n_gd > 0:
            stats['dead'] += n_dead + n_gd
            _emit('兔' if n_dead > n_gd else '狼', '死')
        if n_hunt > 0:
            stats['hunted'] += n_hunt
            # 2026-08-20 M2 修复: 原 _emit('共现','捕食') 的 t='捕食'
            # 不在 _emit 调度分支 → 静默丢弃 (注释声称"捕食恢复进
            # 概念空间"但实现漏分支 — 真实 bug)。主语 = 被捕对象
            # (同生/死同构): 归因循环同对象对齐, 防全局事件污染
            # (窗口宽+频率高 → 全对象变事件都被归因捕食的假因果)。
            # 事件通道控制 (2026-08-24 E3, fusion 同款): 周期模式下
            # 窗口内只 emit 第一次捕食, 窗口外基线捕食不 emit —
            # _appear_ivals 干净周期 (interval ≈ cycle)。
            _do_emit = True
            if predator_cycle > 0:
                if _in_hunt_window:
                    if st.get('_emit_fired'):
                        _do_emit = False
                    else:
                        st['_emit_fired'] = True
                else:
                    _do_emit = False
            if _do_emit:
                _emit('兔', '捕食', '被捕')
        # 环境噪声 (混沌) — 草扰动
        if noise > 0:
            st['P'] *= 1.0 + rng.uniform(-noise, noise)

    def _rescue():
        """最小种群保护: 灭绝 → 补种 (F4 僵化破局舞台不塌)."""
        if st['R'] < 3:
            st['R'] += 3
            _emit('兔', '生')
        if st['G'] < 2:
            st['G'] += 1
            _emit('狼', '生')

    # ── 动作 (控制输入 — 行为环与世界因果交互) ──
    ACTS = ['喂食', '猎杀', '保护', '放牧', '观望']
    ACT_COOLDOWN = 25  # 控制输入冷却步数 (生态治理: 不能连发)

    def _apply_act(act):
        # 2026-08-20 动作幅度桶级化 (三修): 原幅度 (+3 兔/-2 狼/+20 草)
        # 被生态振荡淹没 (同动作后兔桶暴增/濒危/少都有 → p_ab≈1 建不出
        # 无条件边 → 状态链空 → 规划 0 实锤)。控制输入须桶级可见:
        # 保护 +30 一步濒危→中/少→中/中→多 (全跨界), 猎杀 -10 一步
        # 狼多→少|中, 喂食 +80 一步枯→高|丰/低→丰/中→丰。动作低频
        # (每 25 步) 不破坏生态振荡, 但效果立现 → 确定性动作边 →
        # 状态链可建。
        if act == '喂食':
            st['P'] = min(PAR['K_P'], st['P'] + 80.0)   # 草补给 → 兔繁殖升
        elif act == '猎杀':
            st['G'] = max(0, st['G'] - 10)              # 减狼 → 兔压力降
        elif act == '保护':
            st['R'] += 30                                # 兔避难 → 兔升 (桶级)
        elif act == '放牧':
            st['P'] *= 0.5                               # 割草 → 草降 (桶级)

    # ── 世界流接口 ──
    def obj_of() -> str:
        # 焦点对象 = 兔 (治理受益者)。行为环是单焦点决策器 (每步一个
        # obj) — 生产回归基线同构; 观察通道 (world_step 返回 dict) 保留生态全貌。
        return '兔'

    def acts_of(obj: str) -> List[str]:
        return ACTS

    def effect_obj_of(act: str) -> Optional[str]:
        """动作 → 效果对象 映射 (2026-09-18, 动作-对象绑定错位修复).

        世界真实语义: 每个动作作用于**不同对象** (_apply_act 逐条
        对应), 而 acts_of 对所有对象返回全集 ACTS ⇒ 概念空间建转移
        表时把 '放牧'(效果对象=草) 也挂到查询对象 '兔' 名下 ⇒
        查 '兔+放牧' 命中的是草/狼的状态边 (实测: 放牧 3 条记录
        全挂 草/狼, 兔 0 条) ⇒ 计划首跳必错 ⇒ advanced 恒 0。

        本映射 = 世界侧对'动作实际改变谁'的权威声明 (查询侧筛选用,
        **不限制** agent 能做什么 — acts_of 一字不动)。
        观望无效果对象 (纯观察) → None (消费端不筛 = 零破坏)。
        """
        return {'喂食': '草', '放牧': '草', '猎杀': '狼',
                '保护': '兔'}.get(act)

    def context_of() -> List[tuple]:
        # S3 消费端接线 (2026-08-20): 加狼状态进观察/决策通道 —
        # desire 信号 (狼状态→捕食压力→兔濒危) 需要当前狼状态读
        # 数; 同时动作效果条件于狼状态 (狼多时猎杀 vs 狼少时) 的
        # 真实因果结构进入学习 (条件边) — 内在变化可归因 (基因
        # vs 内在原则: 生产回归基线无狼零影响)。
        # hide_clock → 太阳不进 context (2026-08-24 E3, fusion 同款:
        # 环境时钟隐藏, 系统只能从事件流间隔学周期)。
        if hide_clock:
            return [('狼', wolf_bucket(st['G']))]
        return [('太阳', day_bucket(st['t'])),
                ('狼', wolf_bucket(st['G']))]

    def goal_of(obj: str) -> Optional[str]:
        # 自治世界: 无外部目标。治理目标由内在动机 (M8: 需求池/能力/
        # 概念张力) 从认知状态涌现 — 系统自己决定"要让兔种群繁荣"。
        return None

    def families() -> dict:
        return {}

    def _eco_state_dict() -> dict:
        """生态全貌状态 (教科书真实): 多对象 dict — 学习机制观察层
        拆解成多对象事件 (2026-08-20 五修: 复合串投影 (obj,变,复合串)
        污染状态链是学习机制缺陷, 已由 wm.observe_state dict 支持修复;
        教科书返回生态全貌, 不迁就单桶)。"""
        return {'草': grass_bucket(st['P']), '兔': rabbit_bucket(st['R']),
                '狼': wolf_bucket(st['G']), '太阳': day_bucket(st['t'])}

    def world_step(obj: str, act: str) -> Tuple[dict, dict]:
        stats['acts'] += 1
        old = _eco_state_dict()
        cooldown = st.get('cooldown', 0)
        if cooldown > 0:
            # 动作冷却 (2026-08-20 四修): 真实生态治理控制输入不能连发
            # (Godot 教训: 高频干预破坏生态)。冷却期动作被世界拒绝 →
            # 观察为观望, 生态正常演化。行为环 explore 时 expected=None
            # → 无违背虚增; known plan 时违背 = 学习"动作需要间隔"。
            st['cooldown'] = cooldown - 1
            if wm is not None:
                wm.observe_action('我', '观望', obj, ctx=context_of(), channel='obs')
            elif cs is not None:
                cs.observe('我', '观望', obj, channel='obs')
            _advance()
            _rescue()
            stats['R'] = st['R']
            stats['G'] = st['G']
            stats['P'] = st['P']
            _bucket_sync(emit_every=True)
            return _eco_state_dict(), old
        # 动作观察先喂 (与生产回归基线同序: 动作事件 → 变事件 相邻 → sweep
        # 对齐 (动作, 前驱状态, 结果) 三元)。原序 (先演化发变事件
        # 再喂动作) → 变事件在动作前 → 因果边永不涌现 (实锤)。
        if wm is not None:
            wm.observe_action('我', act, obj, ctx=context_of(), channel='obs')
        elif cs is not None:
            cs.observe('我', act, obj, channel='obs')
        if act in ACTS and act != '观望':
            st['cooldown'] = ACT_COOLDOWN  # 控制输入冷却 (25 步)
            _apply_act(act)
        _advance()
        _rescue()
        stats['R'] = st['R']   # 种群数值同步 (2026-08-29 A3 归一化
        stats['G'] = st['G']   # 信号源: 装配端闭包读 stats 算捕食压力)
        stats['P'] = st['P']
        _bucket_sync(emit_every=True)  # 每步强制 4 对象'在'事件 (生态关联学习)
        return _eco_state_dict(), old

    def world_tick() -> None:
        _advance()
        _rescue()
        stats['R'] = st['R']
        stats['G'] = st['G']
        stats['P'] = st['P']
        _bucket_sync(emit_every=True)
        st['step'] += 1  # 行为步时钟 (2026-08-24 E3: 捕食周期相位 — fusion 同款, world_tick 每行为步恰一次)

    _bucket_sync(force=True)

    def signals() -> dict:
        """世界声明的标量信号 (2026-09-19 元选择第 1 步: 信号 = 世界知识):
        governance = 捕食压力 (hunted / max(1,R)) — 治理动作效用源。
        此前该计算住在装配层 (gov_signal 的 eco 分支 lambda) ⇒ 现声明在世界上。"""
        def governance():
            try:
                return stats.get('hunted', 0) / max(1.0, stats.get('R', 1))
            except Exception:
                return 0.0
        return {'governance': governance}

    # ★ §222 世界契约 (只声明, 不写数据): 本世界**没有**有序坐标轴 (SPECS axis=None)
    return {
        'axis_declared': False,
        'world_step': world_step,
        'world_tick': world_tick,
        'obj_of': obj_of,
        'state_of': state_of,
        'acts_of': acts_of,
        'effect_obj_of': effect_obj_of,
        'context_of': context_of,
        'goal_of': goal_of,
        'families': families,
        'stats': stats,
        'PAR': PAR,
        'signals': signals(),   # 世界声明的标量信号 (2026-09-19; 求值后 = name→callable dict)
    }
