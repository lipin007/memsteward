#!/usr/bin/env python3
"""
core/concept_ontology.py — ConceptSpace ontology 子模块 (mixin)

S3 拆分 (2026-08-11 施工, 用户拍板 P2①): ConceptSpace 单文件 3656 行
→ 5 子模块 mixin (ontology/phase/principle/state/space), 保持
`from core.concept_space import ConceptSpace` 重导出兼容。

零机制变更: 方法体一字未改, 仅按 C1 14 区块边界归位。
"""
from collections import defaultdict, Counter
from types import SimpleNamespace as _SN
from typing import List, Dict, Tuple, Optional, Sequence
import os
import numpy as np

# 第六刀 (2026-08-12): MES vNext 节律层 — 概念空间的时间维度载体
# (能量/相位/生灭/混沌边缘; 严格映射: 概念注册=实体, 关分裂)
try:
    from core.rhythm_vnext import RhythmVNext
    _HAS_RHYTHM = True
except Exception:
    RhythmVNext = None  # type: ignore
    _HAS_RHYTHM = False

# M1 移植 (2026-08-12 19:2x, V3 图纸施工件): Event 五元组 + EventStream
# 时间维度显式不可约 — t 是事件的结构成分。真源不删, 窗口=查询投影边界。
try:
    from core.events import Event, EventStream
    _HAS_EVENT_STREAM = True
except Exception:
    Event = None  # type: ignore
    EventStream = None  # type: ignore
    _HAS_EVENT_STREAM = False

# M5 移植 (2026-08-12, V3 图纸施工件): EmergenceEngine 涌现唯一家
# 角色/类别/状态维度 三路默认涌现收口 (零行为变更, 元认知可读)
try:
    from core.emergence import EmergenceEngine
    _HAS_EMERGENCE = True
except Exception:
    EmergenceEngine = None  # type: ignore
    _HAS_EMERGENCE = False

# M4 移植 (2026-08-12, V3 图纸施工件): ProcessCore 五段编排
# ⚠️ 2026-08-16 全面检查归档: 模块文件从未存在 (图纸件), 入口 process()
# 已归档 → 本 import 块与 process_core 初始化一并移除 (见
# _archive_legacy/dead_interfaces_20260816.py)

# M9 移植 (2026-08-12, V3 图纸施工件): PerceptionStats 统计采集器
# 感知层超人类带宽: 只采集信号 → SignalBundle (给 M6), 永不判定
try:
    from core.perception_stats import PerceptionStats, SignalBundle
    _HAS_PERCEPTION_STATS = True
except Exception:
    PerceptionStats = None  # type: ignore
    SignalBundle = None  # type: ignore
    _HAS_PERCEPTION_STATS = False

# M7 移植 (2026-08-12, V3 图纸施工件): MemoryShadow 记忆影子
# 事件流派生投影视图 (按内容索引), 零独立写入, 单真源
try:
    from core.memory_shadow import MemoryShadow
    _HAS_MEMORY_SHADOW = True
except Exception:
    MemoryShadow = None  # type: ignore
    _HAS_MEMORY_SHADOW = False

# M2 移植 (2026-08-12, V3 图纸施工件): ConceptStore 四类原生结构视图
# 概念 = 空间区域 (骨架+活法一体), 结构字段归 M2, 相位字段归 M3
try:
    from core.ontology_core import ConceptStore, ObjectC, ActionC, CauseEdge, Dim
    _HAS_ONTOLOGY_CORE = True
except Exception:
    ConceptStore = None  # type: ignore
    _HAS_ONTOLOGY_CORE = False

# M3 移植 (2026-08-12, V3 图纸施工件): PhaseField 概念时间属性读出层
# 动力学 = vNext 连续时间 (用户拍板), 语义相干 = 能量同步
# 时间属性单点持有: 相位/能量/相干/成熟度全部经此视图, M2 无副本
try:
    from core.phase_field import PhaseField
    _HAS_PHASE_FIELD = True
except Exception:
    PhaseField = None  # type: ignore
    _HAS_PHASE_FIELD = False

# M10 移植 (2026-08-12, V3 图纸施工件): 语言末端薄壳 (表达层)
# 概念先行, 语言=表达层/索引层; 概念空间永不 import 本层 (单向依赖)
try:
    from core.language_layer import LanguageLayer, BindingIndex
    _HAS_LANGUAGE_LAYER = True
except Exception:
    LanguageLayer = None  # type: ignore
    _HAS_LANGUAGE_LAYER = False

# 概念类型 (自动涌现的类别)
PERSON, ACTION, OBJECT, EMOTION = "人物", "动作", "物体", "情感"


class ConceptSpaceOntologyMixin:
    # 第六刀 (2026-08-12): vNext 节律层总开关 (类属性, 默认开)
    rhythm_enabled: bool = True

    def __init__(self, rhythm_env_rate: float = 0.0,
                 rhythm_env_mode: str = "per_entity",
                 rhythm_birth_cost: float = 0.3,
                 rhythm_birth_cost_alpha: float = 0.4,
                 rhythm_death_threshold: float = 0.0,
                 rhythm_dormant_after: int = 0,
                 rhythm_substep=None,
                 drive_inject_enabled: bool = False,
                 drive_scale: float = 0.5):
        # 端到端注入通道消费端 (2026-08-16): 新颖性→动力层 drive 调制。
        # 默认 drive_inject_enabled=False = 零破坏 (observe 仍传 drive=0);
        # 开启后: 事件 p/a/o 命中上轮 scan 高档新颖概念 (_novelty_attention)
        # → observe_event(drive=增益调制量) — 概念层判定驱动动力层响应。
        # drive_scale: 增益→能量映射缩放 (增益范围 [1.0, 2.6];
        # 生产级调制量级远小于研究级 EXTRA=20, 不打破混沌)。
        # T4 开放系统 (2026-08-14): 节律层开放系统参数透传。
        # 默认全零破坏 (env_rate=0 封闭系统 = 历史行为一字不动);
        # 显式开 pool 模式 → 资源池注入 + 出生成本随规模 (Heaps)。
        # 2026-08-11 决策环接线: 轻量 cfg (供 DecisionEngine 读取,
        # 与 DualSpaceV2.cfg 同风格; 概念层自身不用向量)
        self.cfg = _SN(d_model=32, n_neurons=128)
        # 对象身份自学习 (2026-08-30 万能基因第一棒 identity_learn):
        # 同名对象跨世界异语义 (数学 e1 vs 几何 e1) 由系统自己发现
        # 分裂 — 不再依赖设计者手动前缀。原理: 对象身份 = 状态转移
        # 图的连通性。同对象的状态链连通 (兔在生态/fusion 同情境);
        # 异对象撞名 → 两套不相交状态链 = 两个连通分量 → 自动分裂
        # (obj#k 子节点, 历史经验按状态归属迁移, observe/查询按
        # 当前状态路由)。单世界 (唯一对象/单链) 永不触发。
        self._id_sigs: Dict[str, Dict[str, int]] = defaultdict(dict)  # obj -> {状态: 观察计数}
        self._id_par: Dict[str, str] = {}      # 状态并查集父指针 (obj 前缀键)
        self._id_split_stable: Dict[str, int] = defaultdict(int)  # obj -> 连续检测到多分量批次
        self._id_split_done: set = set()  # 已分裂对象 (一次性分裂: 子节点吸收后续观察 = 题位经验共享)
        self._identity_route: Dict[str, Dict[str, set]] = {}  # obj -> {子节点: 状态签名集}
        # cs 级最近 '在' 状态 (2026-08-30 identity_learn 配套): 世界
        # 文件的 _last_obs 是局部变量 (fusion/geom 各自), cs 侧无 —
        # 身份路由需要「对象当前在什么状态」判簇, 故 cs 自维护。
        self._last_obs: Dict[str, str] = {}
        # 概念类型: name → set(类型)
        self.types: Dict[str, set] = defaultdict(set)
        # 事件: (人物, 动作, 物体|None) → 次数
        self.events: Dict[Tuple[str, str, Optional[str]], int] = defaultdict(int)
        # M1 移植 (2026-08-12): EventStream — 事件流真源 (t 结构成分)
        # 与 self.events 计数共存: 计数=聚合视图, 流=时序真源 (零行为变更)
        self.event_stream = EventStream(window=2000) if EventStream else None
        # M5 移植 (2026-08-12): EmergenceEngine — 涌现唯一家
        # 增量统计随 observe 喂入, emerge() 默认路径产出 (零行为变更)
        self.emergence = EmergenceEngine(self) if EmergenceEngine else None
        # M4 移植 (2026-08-12): ProcessCore — 五段编排
        # ⚠️ 2026-08-16 归档: 模块从未存在 + 入口已删 (dead_interfaces_20260816.py)
        # M9 移植 (2026-08-12): PerceptionStats — 统计采集器 (只读不判定)
        self.perception_stats = PerceptionStats() if PerceptionStats else None
        # M7 移植 (2026-08-12): MemoryShadow — 记忆影子 (惰性构建)
        self.memory_shadow = None
        # M2 移植 (2026-08-12): ConceptStore — 四类原生结构视图 (惰性)
        self.ontology_store = None
        # M3 移植 (2026-08-12): PhaseField — 概念时间属性读出层 (惰性)
        self.phase_field = None
        # M10 移植 (2026-08-12): LanguageLayer — 语言末端表达层 (惰性)
        self.language_layer = None
        # 关系边 (联想通道): (from, rel, to) → 强度
        self.edges: Dict[Tuple[str, str, str], float] = defaultdict(float)
        # 边 Landauer 预算 (2026-08-26): edge_theta 低权重清零 /
        # edge_max 总边数上限 (删最弱) — 无界边增长 → 二次方慢
        # (概念层 θ/T_life 同构物理预算制扩展)。默认 0 = 关零破坏。
        self.edge_theta: float = 0.0
        self.edge_max: int = 0
        self._edge_evicted: int = 0
        # 空间索引 (2026-08-21 事件空间化): cell → 对象集
        # (最近一次在该空间位置出现的对象 — 空间局部性数据源;
        #  observe(spatial=...) 维护, 默认无 spatial 零破坏)
        self.spatial_index: Dict[str, set] = defaultdict(set)
        # 空间共现统计: (对象A, 对象B) 同 cell 共现次数
        # (空间因果关联涌现的原始计数 — 近处对象相互影响可学)
        self.spatial_cooccur: Dict[Tuple[str, str], int] = defaultdict(int)
        # 空间条件统计 (2026-08-21 受益验证→消费端): (action, A, B) 同
        # cell 共现次数 — 按动作分桶的空间共现, 使"捕食 ⇒ 狼兔同格"
        # 与"进食 ⇒ 兔草同格"可区分 (空间因果条件学习的消费端数据源)。
        # 纯新增, 默认无 spatial 零开销。
        self.spatial_cond: Dict[Tuple[str, str, str], int] = defaultdict(int)
        # 空间区域统计 (2026-08-21 区域化): cell → {语义状态: n} — 每个
        # 空间位置的交互/生死事件计数, 邻近 cell 聚合 = 空间区域概念
        # ("某区域捕食多"可学)。纯新增, 默认无 spatial 零开销。
        self.spatial_cell_cond: Dict[str, dict] = defaultdict(lambda: defaultdict(int))
        # 空间 cell 时间窗过期 (2026-08-21 环境突变实验修复): cell → 最后
        # 事件序数。群落迁走 → cell 停止事件 → sync 时过期移除 → 危险区
        # 消退 (自适应生命周期遗忘端 — 等比衰减无效, 占比不变, 实锤)。
        self.spatial_cell_last: Dict[str, int] = {}
        self._spatial_ev_n: int = 0  # 空间事件序数 (时间窗参考系)
        # 空间区域聚簇缓存 (2026-08-26 提速 A — 6G 条件短路): 行为环每步
        # 两次 spatial_region_of → 每次全量重算聚簇 (sorted cells + 曼哈顿
        # 邻近合并 + pred_ratio) — 安全区查询也重算。缓存后查询路径 O(1),
        # 写入 (spatial_cell_cond/spatial_cell_last) 时失效。纯提速零 rng
        # 零行为影响 (聚簇结果逐位一致)。
        self._spatial_regions_cache = None
        # 整词概念化 (第十六课): 词→部件 part-of + 固化强度 + 义项
        self.part_of: Dict[str, List[str]] = defaultdict(list)   # 词 → 部件
        self.wholes_of: Dict[str, set] = defaultdict(set)        # 部件 → 词
        self.entrench: Dict[str, float] = defaultdict(float)     # 固化强度
        self.sense_of: Dict[str, set] = defaultdict(set)         # 词 → 义项
        # K3 修复 (2026-08-12): 一词多义自动涌现 — 已见角色计数
        # (词 → 已见事件槽位角色集: 人物/动作/对象; ≥2 = 多义证据)
        self._sense_roles: Dict[str, set] = defaultdict(set)
        # 命名反射 (第十七课): 概念 → {词: 强度} (词的符号出口)
        self.word_bind: Dict[str, Dict[str, float]] = {}         # 概念→词
        # 2026-08-09 对称索引 (双词绑定合一): 词 → {概念: 强度}
        # (hear 反查 O(1), 与旧 BindingChannel.concept_words 同构;
        #  与 word_bind 互逆同步, 不另存真源)
        self.word_to_concept: Dict[str, Dict[str, float]] = {}   # 词→概念
        # 情景记忆 (第十八课): 时间轴日志 (海马体)
        self.episodes: List[dict] = []
        # 因果边 (2026-08-09, 推理攻坚): 有向统计因果知识
        # (src, tgt) → {f_stat, strength, n_updates}
        # 感知不判定: granger 是统计测量 (观测), 不是判定;
        # 因果知识供 adjudicate/传播消费, 三铁律保持
        self._causal_edges: Dict[Tuple[str, str], dict] = {}
        # DMIT 因果边 (2026-08-09 R2): 延迟互信息方向性 (抗稀疏爆炸)
        # 独立存储不污染 granger 边; 查询合并 (granger 优先, dmit 补充)
        self._causal_edges_dmit: Dict[Tuple[str, str], dict] = {}
        # 条件化原理边: (动作, 结果, 条件) → {score, strength, auto}
        # 缺陷1修复 (08-10 13:28 用户批准): 无条件边在条件交替时
        # 被稀释成"两可" (扣球→飞/弹 都弱) — 条件调制测量
        # lift=P(B|A,C)/P(B|A) 涌现"A→B 只在 C 下成立"的结构。
        self._causal_edges_cond: Dict[Tuple[str, str, str], dict] = {}
        self._cond_min_lift: float = 1.8      # 条件调制阈值
        self._cond_min_support: int = 6       # 条件边最小支持度
        # 状态链专用支持度 (T5 真实感知流, 2026-08-14):
        # _state_cond_scan 的转移对来自 (变) 事件 = 感知层测量的
        # 真实状态变化 (非统计共现) — 每类转移即使 1 次也是真实
        # 观测 (连续流里跨桶是稀有事件: 850 次加热仅 1-3 次跨桶)。
        # support=6 会把真转移全挡 (低频真因果恰是感知层超人类
        # 带宽的价值点); 假转移已由 '变' 事件过滤 + 证据时效衰减
        # 双重拦截。建边≠判定 (三铁律: 统计测量在感知层)。
        self._state_cond_min_support: int = 1
        # 最近证据窗口 (2026-08-14 T5 参数化): 原 hardcode 200。
        # T5 连续流里学习期不同段的转移 (二次加热 500-900 / 二次
        # 冷却 900-1200) 距离 log 尾都超 200 事件 → 全部在建边
        # 时刻已在窗口外 → 永不回补 → 状态链建不出。600 事件
        # ≈ 400 回合, 覆盖完整学习期 (验证在交替期前 n_ep=1200)。
        # 语义不变 (无新证据→照常衰减死), 只放宽“多久前的证据
        # 算最近”。零破坏: 默认值仍 200, T5 侧显式设 600。
        self._recent_window: int = 200
        self._var_bind_min_jac: float = 0.25  # 变量绑定最小部件重合度
        # 候选③ 原理消费端 (2026-08-10): 原理自动涌现 + 推断消费
        # 全局事件日志 (环形窗口) + 增量转移计数 + DMIT 精化候选
        self._principle_log: List[List[str]] = []
        # 原理日志滚动窗口 (2026-08-16 配置化): 决定 _state_cond_raw 快照
        # 可见证据范围 (证据时效语义: 最近证据)。默认 2000 事件 ≈ 400
        # ticks; 需要全训练证据的实验 (判别实验外推题: 组件已学必须
        # 在快照可见) 可调大。默认零变化。
        self._principle_log_window: int = 2000
        self._principle_pending: int = 0
        self._last_batch_n_feed: int = 0  # 幂等门: 上次 _principle_batch 消费的 feed 序号 (2026-09-03)
        self._principle_batch_size: int = 200  # 每 200 事件精化一批
        self._principle_min_total: float = 4.0   # 活动量门槛 (防冷启动噪声)
        self._principle_min_score: float = 0.02  # DMIT 方向性阈值
        # 增量转移计数 (A→B 相邻事件共现, O(1)/事件): 候选筛选器
        self._principle_transitions: Dict[Tuple[str, str], int] = defaultdict(int)
        self._principle_prev: List[str] = []   # 上一事件成员
        self._principle_top_candidates: int = 40  # 每批 DMIT 精化对数 (自适应起点)
        self._principle_window_ratio_min: float = 0.02  # 自适应扩窗边缘比阈值
        self._principle_max_candidates: int = 160  # 自适应带宽上限
        # ── 认知结构本体化 (2026-08-10 22:54): 槽位结构通道 ──
        # 三层研究 (身份恒存→状态维度→过程推演) 统一落地:
        #   缺口2: DMIT 前置门槛淘汰多结果因果 (加热→温/热/沸 各1/3
        #      DMIT 弱 → cond 永不触发) — 分歧=隐藏状态变量信号
        #   缺口3: cond 候选条件无过滤 (前一事件所有词) → 跨对象噪声
        # 解法: 从事件槽位结构涌现 动作词集/状态词集 (零预置),
        #   对全量 (动作→状态) 转移对直接做状态词条件扫描
        #   (不依赖 DMIT 通过), 独立边集 _state_cond_edges 与现有
        #   _causal_edges_cond 共存 (新增不覆盖, 默认零破坏)
        self._state_cond_enabled: bool = True    # 槽位结构通道开关
        # ★ §184/§185 (gated · **默认 False** ⇒ 关闸逐位不变): 前看对齐的对象检测
        # 是否把**事件主语** (0 号位, 非 '我' 时) 纳入 —— 关 = 原实现 `cur[1:]`。
        # 开 = "跨主体归因禁止" (非自我事件不得把**别的主体**的状态词当结果)。
        self._cond_subj_scope: bool = False
        self._state_cond_edges: Dict[Tuple[str, str, str], dict] = {}
        # 结果分布表 (2026-08-20 立项 D1): (条件,动作) → 全结果计数
        # (条件概率分布, 与 p_acb 同口径) — 分布预期消费端读数
        # 2026-08-20 立项 M1 (主体预期扩展): 键升级 (obj, c, a) —
        # obj=效果对象 (变事件主语), c=条件状态, a=动作
        # (None=无动作演化链)。多对象世界 (eco: 兔'少' vs 狼'少'
        # 撞名) 必须对象维度分流, 否则分布污染。
        self._state_trans_dist: Dict[Tuple[Optional[str], str, Optional[str]], dict] = {}
        # 世界模型 (2026-08-13): 复合条件边 (关系 = 二阶条件调制)
        # key = (动作, 结果, (自身状态, 关联对象状态)) — 对象间关系
        # 的最小涌现形态 (研究层实证: 单条件扫描够不着复合条件,
        # (冷,旺)→温 的 '冷' 单独 p_acb=0.55<'0.8 被火灭稀释)。
        # 独立表: 零破坏既有消费端 (三键解包不动)。
        self._state_cond_edges2: Dict[Tuple[str, str, Tuple[str, str]], dict] = {}
        self._state_cond2_enabled: bool = True
        # 说话者信任表 (2026-08-27 V12): 多说话者规则冲突仲裁 —
        # 信任非预置 (每个说话者初始 0, 从 B 的执行验证中学):
        # 社会边被验证为真 → +1.0, 被证伪 → -1.0。仲裁时高可信
        # 说话者优先 (传闻可补充不可覆盖自己实证 — 门控② 保持;
        # 多说话者之间按信任高低择优)。
        self._speaker_trust: Dict[str, float] = {}
        # 2026-08-22 方案F: 全历史 (a,前驱,结果) 产出对象集 — 跨 sweep
        # 累积 (sweep 局部会滚出窗口: D 段反转后 A/B/C 段沸证据消失 →
        # produced 空 → 反证主体缺失 → 永不衰减)。衰减只认"曾被边泛化
        # 过的对象"的窗口反证 (类别规则语义: 材料类规则不被蜡类反证)。
        self._cond_produced: Dict[Tuple[str, str, str], set] = {}
        # 感知层无门槛证据快照 (2026-08-16 范式攻坚第二步): scan2 遍历
        # 时顺手保留的原始计数 (无 lift 门槛), 每次 batch 重建覆盖 =
        # 最近一次扫描时点的全量 log 证据, 天然证据时效 (快照非累积
        # 表 → 零新衰减参数)。仲裁层 (state_chain 外推段) 现场读它做
        # 调制律验证 — 统计只做采证, 判定在仲裁层。
        self._state_cond_raw: dict = {}
        # 推理验证回灌 (2026-08-16 阶段 A): 外推预测对的验证记忆 —
        # 推理产物 (外推答案) 被真实转移证实/证伪后, 推理判定更新
        # (证伪→禁外推, 证实→已验证)。key = (c1, a) 目标组:
        #   {'b': 预测答案, 'refute': 证伪计数, 'confirm': 证实计数,
        #    'status': 待验证|已验证|不可靠}
        # 记录在感知层 scan2 (采证), 判定在外推段查询时 (仲裁层)。
        self._reasoning_verdicts: dict = {}
        self._state_det_edges: Dict[Tuple[str, str], dict] = {}
        # 当前世界名 (2026-09-18 世界模型隔离): 转移表按世界打标签。
        # trio 多世界段轮转下三张转移表共用 → 学到的边混不同世界的
        # 转移 → 计划预测必错 (实测 6000 步 seed42: 单世界 advanced 5 /
        # completed 6, trio 0/0)。运行时信号, 不持久化; None = 单世界
        # ⇒ 写入标签也 None ⇒ 读取过滤全通过 = 零破坏。
        self._current_world: Optional[str] = None
        self._state_words: set = set()           # 状态词集 (身份结构)
        self._action_words: set = set()          # 动作词集 (槽位结构)
        # 抽象规则表 (2026-08-18, 推理基础能力): 跨对象共享转移 →
        # 领域无关规则 (抽象概念 = 对象级规则的最大公约数)。
        # key=(状态,动作) → {result, n_objects, objects, strength}。
        # 从多个对象的 state_chain 共享转移涌现 (≥2 对象验证),
        # 消费端回退路径 (对象自身链无路 → 抽象规则), 来源标注
        # abstract, 不写回对象链 (假设≠事实)。默认空表零破坏。
        self._abstract_rules: Dict[Tuple[str, str], dict] = {}
        # 抽象规则涌现脏标记: 事件流变化 → 下次读取时重扫 (惰性)
        self._abstract_dirty: bool = True
        # 类别规则表 (2026-08-18, 推理基础能力二期): 类别内共享转移 →
        # 类别级抽象规则。cat_name → {(状态,动作): {result, n_objects,
        # objects, strength}}。从 emergence.categories (M5 共享动作聚簇)
        # 的成员 state_chain 共享转移涌现 — 类别内同构 (共享动作模式),
        # 无跨类结果冲突 (全局抽象表 key=(状态,动作) 单结果, 材料类
        # 加热→温 vs 食物类 加热→熟 会覆盖丢信息, 类别表分开存)。
        # 消费端回退顺序: 自身链 → 对象所属类别规则 → 全局抽象规则。
        # 默认空表零破坏; 与抽象规则共用 _abstract_dirty 脏标记。
        self._category_rules: Dict[str, Dict[Tuple[str, str], dict]] = {}
        # 类别本体化 (缺口 3, A 层, 2026-08-18): 类别 → 成员集合表
        # (概念空间内类别概念的结构位置; 与 categories dict 并存, 纯新增)
        self._category_members: Dict[str, set] = {}
        # 类别活力 (能量实体轻量版, 四期, 2026-08-18): 类别整体活性
        # — 成员观察注入, sweep 代谢衰减, <死阈值休眠 (类别记忆也遗忘:
        # 类别级整体冷却, 二阶结构比单边记得更久)。轻量字段不注册
        # rhythm 实体 → 读数零变化, 不需要 monitor 重锚。
        self._category_vitality: Dict[str, float] = {}
        # 证据时效 (2026-08-11, 行为闭环发现): 条件边活性用进废退
        # — 与 LTM consolidate(decay)/M4 冷却同构, 本体保留可恢复:
        #   每批衰减 (log 滚动窗口不再支持 → 活性下降), 低于死亡阈值
        #   不出现在状态链上 (但边保留, 再次被支持 +1 恢复活性)。
        #   代谢率 0.85 > LTM 0.95: 条件边是"最近证据"通道 (感知层
        #   信号), 且死亡不删除本体 (可恢复), 激进代谢零风险。
        self._cond_edge_decay: float = 0.85   # 每批活性衰减 (代谢率)
        self._cond_edge_dead: float = 0.3     # 活性死亡阈值 (证据过期)
        # 2026-08-20 条件边结果对齐窗口: 动作后几步内找同对象变事件
        # (多对象世界动作后紧邻变事件可能属其他对象 — eco 放牧/喂食
        # 先改草)。生产回归基线单对象 log[i+1] 即命中 → 零破坏。
        self._cond_align_window: int = 20
        # 证据时效回补游标 (2026-08-13 第六步): 回补只吃本批新增 log
        # 段 — 突变后动作不再产生结果时, 旧 log 窗口残留不得维持边
        # 活性 (broken 场景: (灯变亮,开) 靠残留回补 → strength 恒满
        # → 级联继续规划 → 突变不诚实)。无新证据 → 只衰减 → 死亡
        # (本体保留可恢复, 与 LTM/M4 同构)。
        self._principle_log_scanned: int = 0
        # None = 本批未算 (sweep 早退/禁用) → 消费端退回旧行为;
        # 空集 = 算了但无转移对 (不可能, log≥20) → 保守不建。
        self._principle_recent_pairs: set = None
        self._n_infer_hits: int = 0              # 推断命中次数 (元认知可读)
        self._n_infer_misses: int = 0            # 推断落空次数
        self._n_dopamine_bursts: int = 0         # 多巴胺迸发次数 (落空注资)
        # 因果学习开关 (默认开; 关闭时 learn_causal 零写)
        self.causal_learning_enabled: bool = True
        # 机制化 (第二十二课): 一条 Hebbian 学习机制的调用计数
        self._n_strengthen = 0
        # 相位场 (阶段 G): MES 极性共振 — 概念间的振荡同步基质
        self._phases: Dict[str, float] = {}
        # 2026-08-07 相位同步学习: 0.04 → 0.15 (sin(Δφ) 单固定点配套)
        self._phase_coupling: float = 0.15
        self._phase_noise: float = 0.001
        self._n_phase_steps: int = 0
        # 2026-08-19 跨通道锚定 (用户拍板): 感知通道概念向世界簇中心弱耦合
        # 动机: 感知-世界同步成为动力学量 (簇间相位差从初相残留变可调耦合)。
        # 设计: 感知概念 (名称含 _SENSOR_FRAGMENTS, F2 预置命名) 每次参与
        # 相位耦合后向世界簇中心 sin 吸引 (cross_anchor_scale 弱), 感知簇
        # 整体向世界簇漂移; 簇内耦合 (0.15) 远强于锚定 (0.05) → 内聚保持。
        # 世界概念零改动 (只拉感知侧)。行为零影响: chaos_guard 读数侧
        # 过滤感知概念 → 锁相检测不变; 数学世界无感知概念 → 自动不触发。
        self._cross_channel_anchor: bool = True
        self._cross_anchor_scale: float = 0.05
        # 通道同步 → 感知学习增益 (2026-08-19, 默认开): 感知-世界同步 =
        # 感知忠实反映世界 (时间对齐) → 感知事件关联学习增强; 失同步 →
        # 零增强。无感知概念 (数学世界) 自动 1.0 零影响。
        self._sync_learning_enabled: bool = True
        self._sync_learning_gain: float = 0.5
        # 通道同步 → 感知能量增益 (2026-08-20, 默认开): 同步时感知事件
        # 活跃证据注入增强 — 感知忠实反映世界时感知信息实时更活跃
        # (快通道, 处理层); 与学习增益 (慢通道, 记忆层) 同源不同参数。
        self._sync_energy_enabled: bool = True
        self._sync_energy_gain: float = 0.5
        # 2026-08-08 过程耦合 (开默认, 用户批准 16:43): 事件锚振荡器
        # 研究 (research_process_couple v2, 3/3 全绿): 每个事件 (subj,act,obj)
        # 有独立相位锚 (成员均值), 三成员向锚耦合而非彼此直接锁相。
        # 低频事件 (如"李寻欢望" w=0) 有自己的锚, 不被高频共现 (道 x492)
        # 主导 — 相位耦合升级为过程耦合 (时间维度进相位学习)。
        # 根因 (质询分析): 成对 _step_phase_coupling 强度=共现次数 (统计量),
        # 把"过程"压扁成"共现" — M1/M6 低频真实关联误伤的同源问题。
        # 开默认评估 (compare_process_couple_on_off, 5-trial 均值, 4/4 绿):
        #   低频真实被拦率 15.0%→8.0% | 高频相干 0.840→0.853 不降 |
        #   全 GT 被拦率 15.6%→11.1% | 低频掩码续写 Top-1 0.188→0.275
        self.process_couple_enabled: bool = True
        # 2026-08-07 相位置信度门控 (gate_normal_talk 发现):
        # 弱共现边耦合步数不足 → 相位停在随机初相 = 噪声。
        # 边权重 < 阈值 → 相位不可靠 → 相干度返回 1.0 (放行, 退回频率序)
        self.phase_conf_threshold: float = 4.0
        # MES M5 落地 (分时复用, 默认关=零破坏): 网络级节律时钟
        # 研究 (H3.5/verify_m5_network_rhythm): 快兴奋+慢抑制涌现
        # 29 步周期, alpha 缩放律 — 真实 1248 边图上主峰 0.063 vs 0.017
        # rhythm_period=0 → 时钟关 (历史行为); >0 → _spread 按节律槽
        # 分片扩散 (同一时间窗口只扩散相位相近的概念域 → 大图带宽窗口)
        self.rhythm_period: int = 0
        self._rhythm_step: int = 0
        # 2026-08-08 三档新颖响应 (阶段4 研究落地, 直接开发):
        # 结构错配 (相位成熟 + 无过程匹配) = 新颖候选 → 三档响应:
        #   低档 (可容纳) → 并入最近类 + 相位向类质心耦合
        #   中档 (独立但弱) → 建新锚 + 待观察登记
        #   高档 (独立稳定) → 建新类 + 注意加权 (不立即写语义网络)
        # 三铁律: 感知不判定 — 三档是响应动作, 判定由 Metacognition 消费
        self.novelty_scan_enabled: bool = True
        self.novelty_scan: Dict[str, dict] = {}   # 最近一次扫描结果 (可读)
        self._novelty_attention: Dict[str, float] = {}   # 高档注意增益
        self._novelty_pending: Dict[str, dict] = {}      # 中档待观察锚
        self._pending_resolved: List[tuple] = []         # 等待解决史 (元认知可读)
        self._novelty_labels: Dict[str, dict] = {}       # 低档自贴推测标签
        self._label_corrections: List[tuple] = []        # 纠正史 (元认知可读)
        # ④ 状态复用: 反相集生命周期 (抑制态自动过期)
        self._anti_phase_until: Dict[str, int] = {}   # 概念 → 过期步数
        self._frozen: Dict[str, int] = {}             # A1 概念死亡: 概念 → 冻结步 (冻结标记/审计, 默认关)
        # 抽象上移标记 (2026-08-29, 实验54 压缩逃生舱): 概念 → 已上移
        # (统计并入类别)。冻结时置位, 复活保留 — 统计已在类别规则里,
        # 不重复上移。消费端关 (use_abstract=False) → 纯沉淀零行为。
        self._abstracted: Dict[str, bool] = {}
        # 类别一致性 (2026-08-29, 实验54 w_prior 自适应): 类别 →
        # 成员行为同构度 0-1 (σ 逆代理)。_category_emerge 时计算 =
        # 1 − 冲突键占比 (同 (状态,动作) 多结果 = 成员异质 = σ 大)。
        # 消费: _abstract_confidence 类别回退折扣调制 (一致性高 →
        # 类别先验可信 w→1 折扣轻; 低 → 保守 w→0.5 防误导)。
        self._category_consistency: Dict[str, float] = {}
        self._anti_phase_from: Dict[str, float] = {}  # 概念 → 原相位 (恢复用)
        # 多级概念金字塔状态 (2026-09-03): 独立表不混
        # emergence.categories; 未装配 (pyramid_enabled=False) 时空表
        self._init_pyramid()
        # 符号层对立结构 (2026-09-04 B 路线落地): 独立表不混; 未装配
        # (opposition_enabled=False) 时空表 + observe 钩子零维护 (零破坏);
        # 消费端已接线 (2026-09-04): 行为环 _phase_opp_mod/_opposite_of +
        # 元认知 opposite_to 优先读符号边 (回退相位读数) — 门控开即全链生效
        self._init_opposition()
        # 方向三落地观测: 语义层活动后不应期 (H3.2 抗垄断, 纯观测)
        self._activation_log: List[Tuple[int, str]] = []   # (step, concept)
        self._n_activations: Dict[str, int] = defaultdict(int)
        self._n_total_activations: int = 0
        # 方向二落地观测: 迸发事件层 (纯追加观测, 不改变任何公式)
        self._burst_events: List[dict] = []
        self._burst_energy_log: Dict[str, float] = defaultdict(float)
        # 方向二落地 M2: 迸发能量纯观测累积 (accumulate_burst_observe,
        # 已接线) — 能量池/log_burst/观测版保留; 创建门控版
        # accumulate_burst + burst_gate_enabled 已删 (2026-08-26 实测
        # 定论: 频率≠重要性, 前置挡无效, 消费端 concept_death 为正确
        # 解法; 归档 _archive_legacy/rpe_burst_gate_archived_20260826.py)
        self._burst_energy: Dict[str, float] = defaultdict(float)   # 概念累积能量
        self.burst_threshold: float = 12.0                          # 迸发阈值 (对齐语言侧高频门槛)
        self.burst_fatigue: float = 0.3                             # 迸发后能量衰减 (MES 疲劳)
        # MES M4 (2026-08-21 默认开, 用户哲学: 默认关=死代码): 观察事件
        # 喂能量 (冷概念冷却的数据源) — 纯观测, 不参与创建/判定;
        # 生产回归基线/trio 实证零行为差异 (内啡肽豁免全盖 → 零触发), 开关保持
        # CLI 兼容 (--cooldown 传 True 无碍)。
        self.cooldown_observe_enabled: bool = True
        # A1 概念死亡 (2026-08-19, 默认关=零破坏, 立项书方案②): 死亡扫描
        # 挂 sleep (长会话生命周期节点), 与 cooldown_observe_enabled 同模式;
        # 冻结=types 移除可重激活 (生灭闭环), 本体全保留。
        self.concept_death_enabled: bool = False
        self.death_theta: Optional[float] = None  # E 理论校准 (2026-08-25): None=工程魔数 2000; 给值= T_life=lnθ/lnd 动态 horizon (Miller 锚定)
        self.death_lambda: Optional[float] = None  # λ 内容层 (2026-08-25): 当前创新率读数 (BehaviorLoop 更新, 纯只读消费)
        self.death_lambda_ref: Optional[float] = None  # λ 基准 (会话滑动平均, 自适应无设计者常数)
        # 概念淘汰完整版 (2026-08-25, 强度衰减语义): 连续活性场替代硬阈值
        # 生产默认开 (2026-08-26 用户拍板: 机制默认开哲学 — 已实证 fusion
        # 5000 步行为逐位一致 + 概念 3.2× 压缩 + 生产回归基线行为逐位一致);
        # --no-concept-life-full / 显式 False 回退旧行为
        self.concept_life_full: bool = True
        self.life_half_life: int = 425  # Miller 锚定: 半衰期 425 步 ≈ 5011 事件 ≈ 3.5 天
        self.life_theta: float = 0.05  # 理论淘汰阈值 (E 校准: θ=0.05 ↔ 工程魔数 2000 步同点)
        # 检索激活 (2026-08-29, 测试效应生产版, 默认开): 被成功消费
        # (推理/问答 deduce 出链) 的概念轻度恢复活性 = 内部负熵源
        # (用进废退), 补实验55 纯被动耗散定论 → 微弱自维持; 只碰
        # _life_strength 不写边表, 冻结不复活 (复活仍由观察驱动);
        # --no-retrieve-touch 回退零破坏 (deduce 逐键一致)
        self.retrieve_touch_enabled: bool = True
        self.retrieve_gain: float = 0.3  # 部分恢复强度 (观察回满的弱化版)
        self.diffuse_enabled: bool = True  # 扩散激活 (2026-08-29 实验56, Collins & Loftus)
        self.diffuse_gain: float = 0.15  # 邻居连带保温 (弱于自身检索 0.3)
        self._life_strength: Dict[str, float] = {}  # 概念活性场 (1.0 满, 无观察指数衰减)
        self._review_strength: Dict[str, float] = {}  # 巩固强度场 (有限复习模型, 2026-08-27)
        self._concept_birth: Dict[str, int] = {}  # 概念出生步 (T* v2 成熟度过滤, 2026-08-26)
        # ★ 出生事件计数器 (2026-09-13 判别实验 #7 修复): 纯仪器, 不改任何行为.
        # _concept_birth 的 len() = '曾见过的唯一概念数' (setdefault 永不更新),
        # 被输入词表封顶 ⇒ 不能当作出生数; 本计数器记真实出生事件 (首现+重激活).
        self._birth_events: int = 0
        self._revive_count: Dict[str, int] = {}  # 概念重激活次数 (轮回史, ②信息价值豁免, 2026-08-26)
        # θ 双标准 (2026-08-26, 概念=信息, 生产默认 2): 活性 < θ
        # 但轮回史 ≥ 阈值 → 豁免冻结 (低活性驻留)。信息价值代理 =
        # 重激活历史: 反复被系统需要 (多次轮回) = 可复用规律/工具
        # (石头/开采), 与过时实例 (题N 解一次即忘, 轮回 0-1) 区分。
        # 默认开 (2026-08-26 用户拍板): 防御性保护伞默认生效 —
        # 10000 步实证触发 4 豁免 + 行为涟漪非回归。
        self.info_revive_exempt: int = 2  # 0=关; N≥2 (≥2 次轮回豁免)
        # 擦除编码淘汰 (2026-08-26, 6G 信道编码反哺): 概念=信息,
        # 淘汰=擦除信道 → 优先删冗余度高的 (有替身, 损失最小) +
        # 信息独有豁免 (R < redundancy_exempt, 删了无法重建)。
        # 默认关零影响 (生产回归基线/直构逐位); fusion 实验体默认开。
        self.erase_code_evict: bool = False
        self.redundancy_exempt: float = 0.15
        self._unique_evict_exempt: int = 0  # 独有豁免计数 (审计)
        # T* 温度调节器 (2026-08-25, 负反馈自稳): 新概念初始活性受 T* 调制
        self.temp_write_gate: bool = False  # 默认关零破坏
        self.temp_write_strength: float = 0.5  # T* 满时新概念初始活性降到 1−0.5=0.5
        # T* 第三层信号模式 (2026-08-26, 6G 缓存替换反哺, 修自激):
        # 'dead_frac' 默认 (1−平均活性, 自激缺陷待修) / 'redundancy'
        # (R̄ 平均概念冗余度, 观测-控制完全解耦无自激) / 'growth_rate'
        # (dN/dt 归一化)。fusion 实验体可切换 A/B。
        # 2026-08-29 装配修复: 2e09038 声称转默认 growth_rate 但只改了
        # run_lifeform 死函数 (_fe_gain_fusion 内, 从未执行) → 本构造
        # 默认一直是 dead_frac (声明≠实现沉默失败, 同 08-27 装配覆盖
        # bug 模式)。修正: 构造默认 = growth_rate (2e09038 意图),
        # env TEMP_SIGNAL_MODE 可切回 (读真实生产路径)。
        self.temp_signal_mode: str = os.environ.get(
            'TEMP_SIGNAL_MODE', 'growth_rate')
        # T* v2 成熟窗口 (2026-08-26, 自参考环修复): 调节器输入/报告读数
        # 只算出生 ≥ 窗口步的成熟概念 — 新概念初始活性调制 (1−k·T*) 的
        # 足迹不再污染读数 (温度计与恒温器分离, 观测-控制解耦)。
        # 默认 100 步 = 半衰期 425 步的 ~24%, 活跃概念在窗口内多次
        # observe 回满 1.0, 冻结概念 (age 大) 正常计入死权重。
        self.temp_mature_window: int = 100
        # A1 概念死亡 (2026-08-19, 默认关=零破坏, 立项书方案②): 死亡扫描
        # 挂 sleep (长会话生命周期节点), 与 cooldown_observe_enabled 同模式;
        # 冻结=types 移除可重激活 (生灭闭环), 本体全保留。
        # 手术③ (范式转折): 多巴胺奖励环 — 新颖事件 → 奖励注资 (能量累积)
        # D 迸发能量 = 多巴胺累积的天然实现 (brain_organ_mapping.md §3.6):
        # reward_novelty 与迸发能量共用 _burst_energy 池 (同一能量系统),
        # 门控独立: 重复出现驱动 (1.0/次) + 新颖奖励驱动 (4.0/次, 新颖=
        # 强多巴胺→探索动机)。默认关闭 = 逐位不变。
        self.dopamine_reward_enabled: bool = False
        # ★ 265 裁决A 落地 (2026-09-23): 迸发→创建【消费半环】(2026-08-26 被删件的 RPE 判定版重建;
        #   依据: §263 探针实测 行为 0/18 零风险 + 结构 +3~+6 概念; 判定 = RPE 违背度(非频率,
        #   避开 08-22「频率≠重要性」) + 自发触发(避开 08-26 外在论) + 能量阈值挡一次性垃圾
        #   + concept_death 后置 = 08-22 归档件自认的组合。默认开 (09-22 拍板: 新机制默认开)。)
        self.burst_create_enabled: bool = True
        # 内分泌层 (endocrine_drive_layer.md, 2026-08-09): 内啡肽(满足/整合)信号
        # 与多巴胺(追求)互补: 相位成熟/重对齐/巩固 → 满足感累积 → 价值标尺
        # (巩固深度 + 冷却豁免)。浓度随时间衰减 (激素代谢: 分泌→代谢→回落)。
        # 2026-08-09 22:24 用户裁决: 直接开默认 (开发优先, 依据已立: 研究实验
        # A/B 对照 + verify 11/11)。三铁律: 信号累积是观测, 豁免是权重调制不代行判定。
        self.endorphin_reward_enabled: bool = True
        # 内分泌层第二版 (2026-08-09): 主动采样 — 注意选择权 (多巴胺侧)
        # 探索欲浓度 explore_drive [0,1] + 注意目标 _attention_target:
        # ① 高档新颖事件 → 探索欲推高 (多巴胺) ② 探索欲最高新类 = 目标
        # (主动选择) ③ 事件含目标 → 深度耦合 (增益 ×(1+explore_drive))
        # ④ 目标搞懂 (satisfaction≥阈值) → 探索欲回落 + 释放目标 (内啡肽
        # 负反馈) — 锁定→满足→释放→转移 的自然涨落节律。
        # 三铁律: 目标锁定是执行层注意选择, 不写语义; 释放由满足信号驱动。
        self.explore_drive_enabled: bool = True
        self.explore_drive: float = 0.0          # 探索欲浓度 [0,1]
        self._explore_drive_decay: float = 0.98  # 每观察衰减 (激素代谢)
        self._attention_target: Optional[str] = None  # 注意目标
        self._attention_hold: int = 0            # 目标持续观察轮次
        self._attention_solved: List[str] = []   # 已解决目标 (探索史)
        # 端到端注入通道消费端 (2026-08-16): 新颖性→动力层 drive 调制
        # (与 focus_gain_scale 同构: 默认关=零破坏, 开启才介入)
        self.drive_inject_enabled: bool = drive_inject_enabled
        self.drive_scale: float = drive_scale    # 增益→能量映射缩放
        # 意识阶段D 消费端 (2026-08-13): 全局焦点注意增益
        # 焦点成员 (相位场同步∧新鲜区) 参与事件 → 耦合力度 ×(1+scale)。
        # 默认 0.0 = 零破坏 (焦点不干预); >0 开启注意资源倾斜
        # (GWT 意识核心功能: 焦点 = 处理资源分配)。
        self.focus_gain_scale: float = 0.0
        # 缺口1 情境不确定候选集 (认知结构本体化第2层后半):
        # {obj: 分歧强度} — 对象关联动作存在多结果转移 (同动作→2+状态)
        # = 系统自己知道"这里有隐藏变量" (情境不确定原始信号)。
        # 与 _novelty_attention (结构新颖) 并列的注意来源:
        # 新颖=新东西想搞懂 (释放=相位成熟); 情境不确定=老对象有隐藏
        # 状态想搞清 (释放=分歧消失, 见 observe ③)。
        # 结构检测→内分泌→锁定→sampling_request 全自然链路 (研究
        # research_gap1_wiring v2 3 seed 验证: 148/133/134 次请求
        # target=分歧对象, 消融对照 0)。
        self._context_uncertain: Dict[str, float] = {}
        self._obj_actions: Dict[str, set] = {}   # 对象→动作集 (增量涌现, 身份锚)
        # 对象身份统一 (2026-08-16): 同一物理对象多候选名 (感知通道
        # 不同帧给不同名) → 动作集完全一致 + 相位近 → 并入同一身份锚.
        # 研究实锤 (research_object_identity): 杯/水杯 act_sim=1.00 链重叠
        # 1.00 相位 0.001-0.005 rad; 不同对象动作集不同 → 误并无风险.
        # 零破坏: 纯增量新字段, 不改变任何既有路径 (observe 尾部只读
        # 既有 _obj_actions 做合并, 不动事件/相位/链).
        self._identity_anchors: Dict[str, str] = {}   # 词 → 身份锚词
        self._identity_members: Dict[str, set] = {}   # 锚词 → 成员词集
        self._identity_enabled: bool = True
        # 缺口1 在线增量结构 (O(1)/事件):
        # _state_words_online = 状态谓词宾语 (在线涌现, 不等批量槽位结构)
        # _action_state_results[a] = 动作→已见状态结果集 (转移过滤后的状态结果)
        self._state_words_online: set = set()
        self._action_state_results: Dict[str, set] = {}
        # 第五刀 (2026-08-12): 状态词/状态谓词身份的结构涌现集 —
        # 不依赖词面 ('变'/'是'/'在'), 从事件角色专用性涌现:
        #   专用宾语位 (角色仅'对象') = 候选状态词 → _struct_state_words
        #   结构谓词 → _struct_state_preds 由状态词反推 (宾语是状态词
        #   的动作 = 状态转移发出者), 不是'专用动作位' (第十三刀修复:
        #   词面世界所有动作都是专用动作位, 正推会污染状态词集)
        # 感知锚点命名 (感知对象N) 无词面, 词面检测失效; 结构信号
        # 保留感知通道的状态识别 (状态维度铁律: 状态进入观察通道)。
        self._struct_state_preds: set = set()
        # 第六刀 (2026-08-12): vNext 节律层挂载 — 概念空间的时间维度
        # (默认开, 依赖缺失自动降级 None = 零破坏; 结构侧不变)
        self._rhythm: Optional[RhythmVNext] = None
        if _HAS_RHYTHM and self.rhythm_enabled:
            try:
                self._rhythm = RhythmVNext(
                    seed=42, env_rate=rhythm_env_rate,
                    env_mode=rhythm_env_mode,
                    birth_cost=rhythm_birth_cost,
                    birth_cost_alpha=rhythm_birth_cost_alpha,
                    death_threshold=rhythm_death_threshold,
                    dormant_after=rhythm_dormant_after,
                    substep=rhythm_substep)
            except Exception:
                self._rhythm = None
        self._struct_state_words: set = set()
        # 缺口1 收尾 (2026-08-11): RPE 自动闭环 — infer 记录预测快照,
        # observe 尾部检测到状态结果事件时自动喂 infer_feedback
        # (命中→内啡肽“搞懂了”; 落空→探索欲+多巴胺“预期违背=学习时刻”)
        # 默认开; 触发条件严格 (事件对象∈上次推断上下文 + 状态谓词动作)
        # → 排球等无状态谓词世界零破坏; 设 False 可关闭 (显式降级)
        self._auto_feedback: bool = True
        self._last_infer: Optional[dict] = None   # 上次推断快照 (一次性消费)
        self._satisfaction: Dict[str, float] = defaultdict(float)   # 内啡肽池
        self._satisfaction_decay: float = 0.99        # 每步浓度衰减 (激素代谢)
        self.satisfaction_threshold: float = 1.0      # 盖章阈值 (冷却豁免用)
        # 蓝图 M3 睡眠节律 (内分泌层第五版): 睡眠压力信号
        # 白天积累(编码) → 夜间沉淀(巩固+重放), 时间维度不可约:
        # 整合必须发生在积累之后, 不是同步。
        # 睡眠压力 = 先天信号 (未沉淀的编码负担), observe 累积,
        # sleep() 整合后释放 (负反馈) — 行为从信号涌现, 不代行决策。
        self.sleep_pressure_enabled: bool = True
        self._sleep_pressure: float = 0.0          # 睡眠压力浓度 [0,1]
        self._sleep_pressure_per_event: float = 0.02  # 每事件累积量
        self._sleep_pressure_decay: float = 0.999  # 每观察轻微代谢 (慢)
        self._sleep_cycles: int = 0                # 睡过几晚 (元认知可读)
        # T3 多尺度巩固分层 (2026-08-14): 睡眠级累计产出计数
        # (元认知可读, consolidation_tiers 视图用; 纯记录零副作用)
        self._consolidated_total: int = 0         # 累计固化 (情景→语义)
        # 推理记忆 (2026-08-29, 推理→记忆反补): 推理结果沉淀表.
        # 纯增量: 键 = (情境元组, 结果概念), 值 = {'hits': 命中次数,
        # 'conf': 平均置信, 'last': 最后步}. 推理成功(高置信) →
        # record_inference 记录; 同情境再推理 → query_inference 命中
        # 直接复用 (缓存); hits ≥2 且高置信 → 固化为概念边 (推理
        # 内化 = 从每次现推到直接知道). 零破坏: 默认空 dict, 不碰
        # deduce/infer 返回值 (查询叠加).
        self._inference_mem: Dict[Tuple[Tuple[str, ...], str], dict] = {}
        self._inference_mem_step: int = 0        # 推理记忆计数步
        # ②记忆检索驱动推理 (2026-08-29): infer 入口缓存命中开关
        # (同情境记忆直接复用) + 活性场注意力 (候选按活性加权).
        # 默认关零破坏 (env 门控在 run_lifeform 设置, core 零依赖).
        self._infer_mem_cache: bool = False
        self._infer_attn: bool = False
        # ③推理失败反馈记忆 (2026-08-29): 深推失败 = 知识缺口 →
        # record_gap 标记 (对象,目标) → 探索时 query_gap 命中 →
        # 定向探索 (用想象指导探索补缺口). 默认空 dict 零破坏.
        self._gap_mem: Dict[Tuple[str, str], dict] = {}
        self._replayed_total: int = 0             # 累计重放 (相位再同步)
        self._cooldown_total: int = 0             # 累计冷却 (M4 中期抑制)
        self._death_total: int = 0                # A1 累计概念死亡 (冻结, 生灭闭环)
        self._life_total: int = 0                 # 完整版累计活性淘汰 (2026-08-25)
        # 蓝图 M2 内生日标 (wanting 的终点形态): 目标=信号累积涌现
        # 探索欲锁定的目标 (attention_target) 持续多轮未解决 →
        # 目标强度累积 (想要多久 = 多强的方向); 达成 (内啡肽盖章)
        # → 解除 (负反馈) + 达成史。目标不是被设计的功能, 是
        # 现有信号的时间累积形态 — 系统自己涌现"想达成什么"。
        self._goal_hold: int = 0                  # 目标持续轮次
        self._goal_strength: float = 0.0          # 目标强度 [0,1]
        self._goal_strength_per_hold: float = 0.1 # 每轮累积量
        self._goal_history: List[str] = []        # 达成史 (元认知可读)
        # 主语-动作频率统计 (2026-08-07, observe 增量维护 O(1)): 原供
        # reward_rpe 在线预期分布 (已删 2026-08-26, 终态裁决不开 — RPE
        # 思想由 infer_feedback 承载); 保留写侧作频率统计诊断 (仅统计
        # 零消费, 归档见 _archive_legacy/rpe_burst_gate_archived_20260826.py)
        self._subj_act_counts: Dict[str, Dict[str, int]] = defaultdict(
            lambda: defaultdict(int))
        self._subj_total: Dict[str, int] = defaultdict(int)

    def set_current_world(self, name: Optional[str]) -> None:
        """设置当前世界名 (2026-09-18 转移表世界隔离)。

        转移表写入时给 value 打 'world' 标签, state_chain 读取时
        过滤掉他世界标签的边。外部 (run_lifeform 段切换) 只在多世界
        (trio) 分支调用 ⇒ 单世界保持 None ⇒ 全通过零破坏。
        """
        self._current_world = name

    # ══ 方向三落地: 语义层活动观测 (H3.2 不应期抗垄断, 纯观测) ═══

    def log_activation(self, concept: str, step: Optional[int] = None):
        """记录概念激活事件 (观测用)

        研究结论 (mes_hysteresis_forgetting_research.md H3.2):
          语义层缺活动后不应期 → 高频概念垄断激活
          (幂律输入下最高频份额 17.8%, 低频概念被饿死)
        此观测记录激活流, 供高频垄断度统计; 不改变任何行为。
        """
        self._activation_log.append((step if step is not None else
                                     self._n_total_activations, concept))
        self._n_activations[concept] += 1
        self._n_total_activations += 1


    # (归档 2026-08-16: refractory_stats → _archive_legacy/dead_interfaces_20260816.py)

    # ══ 方向二落地: 迸发事件层观测 (纯追加) ═══════════

    def log_burst(self, concept: str, energy: float, threshold: float,
                  fired_nbrs: int, step: Optional[int] = None):
        """记录概念迸发事件 (观测用)

        研究结论 (mes_threshold_burst_research.md):
          迸发 = 语义选择性传播器 (语义纯度 0.422 > Strengthen 0.402)
        此观测记录迸发事件流 (谁/能量/阈值/点燃邻居数),
        供迸发统计; 不改变任何行为。
        """
        self._burst_events.append({
            "step": step if step is not None else len(self._burst_events),
            "concept": concept,
            "energy": round(float(energy), 2),
            "threshold": round(float(threshold), 2),
            "fired_nbrs": fired_nbrs,
        })
        self._burst_energy_log[concept] = float(energy)
        # 迸发事件同样计入激活观测 (统一事件流)
        self.log_activation(concept, step)


    def burst_stats(self, top_k: int = 5) -> dict:
        """观测: 迸发事件统计 (纯追加)"""
        if not self._burst_events:
            return {"n_bursts": 0}
        top = sorted(self._burst_energy_log.items(),
                     key=lambda x: -x[1])[:top_k]
        return {
            "n_bursts": len(self._burst_events),
            "n_burst_concepts": len(self._burst_energy_log),
            "top_energy": [(c, round(e, 1)) for c, e in top],
            "avg_fired_nbrs": round(float(np.mean([b["fired_nbrs"] for b in self._burst_events])), 2),
        }

    # ══ 方向二落地 M2: 迸发能量纯观测累积 (MES 接入, 创建门控版已删) ══

    def accumulate_burst_observe(self, concept: str, energy: float = 1.0,
                                 step: Optional[int] = None) -> bool:
        """迸发能量纯观测累积 (MES M2 接入, 不参与创建门控)

        只累积能量 + 超阈值时记录迸发事件 (log_burst, 供 write_back
        迸发加权查询)。三铁律 (感知不判定): 能量累积是感知观测, 概念
        创建与否不由迸发能量判定 (创建门控版已删 2026-08-26, 频率≠
        重要性实测定论; 归档 _archive_legacy/rpe_burst_gate_archived_20260826.py)

        返回 True = 本次累积触发迸发 (纯观测事实, 无副作用决策)。
        """
        e = self._burst_energy[concept] + float(energy)
        self._burst_energy[concept] = e
        thr = self.burst_threshold
        if e >= thr:
            # 超阈值 → 迸发事件记录 (能量喷出 + 疲劳, 防连续迸发)
            self._burst_energy[concept] = e * self.burst_fatigue
            self.log_burst(concept, e, thr, fired_nbrs=0, step=step)
            return True
        return False


    # (reward_rpe 已删 2026-08-26: 终态裁决不开 — 手动触发版=设计者
    # 定义对错 (外在论反噬), RPE 思想由 infer_feedback 落空链路承载
    # (同 RPE=1−P); 归档 _archive_legacy/rpe_burst_gate_archived_20260826.py)

    # (归档 2026-08-16: burst_energy_of → _archive_legacy/dead_interfaces_20260816.py)

    # ══ 内分泌层: 内啡肽 (满足/整合) 信号 (2026-08-09) ════════

    def reward_satisfaction(self, concept: str, amount: float = 1.0,
                            step: Optional[int] = None) -> float:  # 半成品: step 参数未用 (标注勿删)
        """内啡肽注资: 搞懂了(相位成熟/重对齐/巩固) → 满足感累积

        endocrine_drive_layer.md: 多巴胺=追求(wanting, 已有手术③),
        内啡肽=满足(liking, 本次补)。满足感=价值标尺: 高满足概念
        巩固更深 + 冷却豁免 (值得记住的留下, 没搞懂的遗忘)。

        浓度先衰减再累积 (激素代谢: 分泌→代谢→回落);
        endorphin_reward_enabled=False 时零副作用 (默认逐位不变)。
        三铁律: 信号累积是观测; 冷却豁免是权重调制, 不代行判定。
        """
        if not self.endorphin_reward_enabled:
            return 0.0
        e = (self._satisfaction.get(concept, 0.0) * self._satisfaction_decay
             + float(amount))
        self._satisfaction[concept] = e
        return e


    def satisfaction_of(self, concept: str) -> float:
        """当前满足感浓度 (观测用, 元认知可读)"""
        return self._satisfaction.get(concept, 0.0)


    def coherence_of(self, concept: str) -> float:
        """概念与相位场主簇的相干度 [0,1] (观测: 相位成熟度)

        与 phase_noise_gate 内联计算同构 (提取为独立观测, 供内啡肽
        输入源用); phase_noise_gate 逻辑不动 (已验证, 零破坏)。
        """
        if concept not in self._phases or len(self._phases) < 3:
            return 0.0
        anchor = self._local_anchor(concept)
        d = abs((self._phase_get(concept) - anchor + np.pi) % (2 * np.pi)
                - np.pi)
        return max(0.0, 1.0 - d / np.pi)


    def _refresh_context_uncertain(self, obj: str):
        """缺口1 在线分歧检测 (感知查询, 不判定): 刷新对象的情境不确定强度

        从增量结构查该对象关联动作 → 已见状态结果种数 (每事件 O(1)
        维护, 见 _principle_ingest):
          1 种 = 确定 (门: 推→开, 无隐藏变量) → 强度 0 (不打扰)
          2+ 种 = 分歧 (水: 加热→温/热/沸 依状态) → 强度 = 种数-1
        = 系统自己知道"这里有隐藏变量" (情境不确定原始信号)。

        不依赖批量条件边 (_state_cond_edges 每 _principle_batch_size
        =200 事件才涌现) — 在线回路事件不足 200 时增量结构即可用
        (研究 v1 教训: 等批量边 → 分歧检测永不触发)。

        三铁律: 纯感知查询 (读已有增量计数 + 身份锚), 零状态判定;
        是否采样/锁定由内分泌层决定 (observe ③ / sampling_request)。
        """
        if not obj:
            return
        actions = self._obj_actions.get(obj)
        if not actions:
            return
        strength = 0.0
        for a in actions:
            results = self._action_state_results.get(a)
            if not results:
                continue
            n = len(results)
            if n >= 2:
                strength = max(strength, n - 1)
        if strength > 0:
            self._context_uncertain[obj] = strength
        else:
            self._context_uncertain.pop(obj, None)


    def sampling_request(self, threshold: float = 0.3) -> Optional[dict]:
        """输出通道第一形态: 主动采样请求 (探索欲 → 行为接线)

        系统"想知道 X"时发出请求 (内分泌层第二版 d874704 的对外形态):
        注意目标锁定 + 探索欲浓度超阈值 → 返回 {'target': X, 'drive': ..};
        调用方 (世界/语言/agent) 可响应请求, 优先喂目标相关事件 —
        从"被动等证据上门"到"主动索要证据" (好奇→获取行为)。

        行为从信号涌现: 本方法只表达"想要什么", 不代行获取行为
        (三铁律: 执行不决策); 探索欲低/无目标 → None (安静, 不打扰)。
        纯观测接口, 零状态变更, 默认开无副作用。
        """
        if not self.explore_drive_enabled:
            return None
        if self._attention_target is None:
            return None
        if self.explore_drive < threshold:
            return None
        return {
            'target': self._attention_target,
            'drive': round(self.explore_drive, 3),
            'coherence': round(self.coherence_of(self._attention_target), 3),
            'solved': len(self._attention_solved),
        }


    # (归档 2026-08-16: act_request → _archive_legacy/dead_interfaces_20260816.py)


# 2026-08-17 决策 → 2026-08-21 终态裁决 → 2026-08-26 已删: 手动触发版
    # 不开 (外在论反噬), 函数本体已删 (归档 _archive_legacy/
    # rpe_burst_gate_archived_20260826.py)。不开理由 (终态, 非等条件):
    # ①EnvLoop 环境 RPE 已是真源 (规则突变
    # 40 次真实违背) ②概念层奖励 = 设计者定义对错 (哲学反噬, 外在论)
    # ③**RPE 思想已由自发链路承载**: infer_feedback 落空链路 (默认开)
    # 用同一 RPE=1−P 公式注资 miss_dopamine×RPE — 系统自己的推断预期
    # 违背才触发, 不是设计者定义。原 reward_rpe 是设计者触发的手动版
    # 多余副本。08-17 注释 "等系统自发形成稳定预期再评估" 是虚条件 (系统
    # 无预期稳定性检测机制) — 自发链路 (infer_feedback) 本就默认开着,
    # 不存在"预期稳定后开手动版"的路径。标注: 设计裁决不开已删除。
    def reward_novelty(self, concept: str, amount: float = 4.0,
                       step: Optional[int] = None) -> bool:
        """手术③ 多巴胺奖励注资: 新颖事件 → 能量累积 → 超阈值 → 迸发

        与迸发能量共用 _burst_energy 池 (同一能量系统),
        门控独立:
          重复出现驱动 (1.0/次) — 频率即能量
          reward     = 新颖奖励驱动 (4.0/次) — 新颖=强多巴胺→探索动机
        (brain_organ_mapping.md §3.6: D 的迸发能量累积 = 多巴胺累积
         的天然实现, 重定位为"新颖性 → 多巴胺奖励 → 强化固化 + 探索
         创建"即完整闭环)。

        闭环: 新颖(未固化) → 奖励注资 → 能量超阈值 → 迸发 → 概念
        创建 (compose) → 固化 → 不再新颖 → 调用方短路不再奖励。

        dopamine_reward_enabled=False 时永不触发 (默认逐位不变)。
        返回 True = 本次奖励触发迸发 (调用方应创建该概念);
        返回 False = 未达阈值 (奖励已累积, 待下次)。
        """
        if not self.dopamine_reward_enabled:
            return False
        e = self._burst_energy[concept] + float(amount)
        self._burst_energy[concept] = e
        thr = self.burst_threshold
        if e >= thr:
            # MES: 超阈值 → 迸发事件 + 能量喷出 + 疲劳
            self._burst_energy[concept] = e * self.burst_fatigue
            self.log_burst(concept, e, thr, fired_nbrs=0, step=step)
            return True
        return False

    # ══ 机制化核心: 一条 Hebbian 学习机制 (第二十二课) ═════

    def strengthen(self, a: str, b: str, rel: str, delta: float = 1.0,
                   reverse: Optional[str] = None):
        """Hebbian 学习: a 与 b 共激活 → 关系边强度 +Δ

        认知依据: fire together, wire together (Hebb 1949) + LTP
        机制化 (mechanization_design.md 统一②):
          事件学习/整词固化/视觉经验/命名绑定 全是它的实例 —
          大脑只有这一条学习规则, 其余全是对它的组织方式。
        """
        self.edges[(a, rel, b)] += delta
        if reverse:
            self.edges[(b, reverse, a)] += delta
        # 机制化 (阶段 B): 符号边挂家族签名 (数值语义不变)
        from .hebbian import get_family
        get_family().boost(
            "symbol_edge", a=a, b=b, rel=rel, delta=delta,
            source="concept_space" + (f"/{reverse}" if reverse else ""),
        )
        self._n_strengthen += 1
        return self

    def edge_scan(self) -> int:
        """边 Landauer 预算扫描 (2026-08-26): 低权重边清零 (< edge_theta)
        + 超上限删最弱 (edge_max)。返回淘汰数。默认 0 = 恒不触发。
        语义: 弱边 = 信息冗余 (联想无区分度); 物理预算制统一记忆层
        (概念层 θ/T_life 同构扩展)。调用方: BehaviorLoop 周期扫。
        """
        if self.edge_theta <= 0 and self.edge_max <= 0:
            return 0
        dead = []
        for k, w in self.edges.items():
            if self.edge_theta > 0 and w < self.edge_theta:
                dead.append(k)
        for k in dead:
            del self.edges[k]
        n = len(dead)
        if self.edge_max > 0 and len(self.edges) > self.edge_max:
            ordered = sorted(self.edges.items(), key=lambda kv: kv[1])
            over = len(ordered) - self.edge_max
            for k, _ in ordered[:over]:
                del self.edges[k]
            n += over
        self._edge_evicted += n
        return n

    # ══ 信息冗余度 (2026-08-26, 擦除编码反哺 — 6G 信道编码 → 内部淘汰) ══
    # 理论 (跨学科反补: 擦除编码/喷泉码): 信息分散在冗余分布中,
    # 局部丢失可重建。内部映射: 概念 c 的信息冗余度 R(c) = 其边邻域
    # 与其他概念的最大 Jaccard 相似度 — 存在"替身"概念承载几乎相同
    # 关联模式 → c 的信息被冗余覆盖 → 删除损失最小。R=0: 信息独有
    # (无替身, 删了无法重建)。纯只读, 零 rng 零行为影响。
    def _id_main(self, c: str) -> str:
        # identity_learn 查询级合并 (2026-08-30): 子节点 'e1#1' 的
        # 主节点 = 'e1'。分裂后主节点不再收新观察 (路由到子节点),
        # 主节点边 = 分裂前历史关联 — 子节点查询时只读叠加历史关联
        # (继承先验), 不写存储 (避免复制迁移的子节点间边污染)。
        if '#' in c:
            return c.split('#')[0]
        return c

    def _concept_neighbors(self, c: str, _nb: dict = None) -> set:
        # 注 (2026-08-30 实测裁决): 不做 identity 合并 — 子节点 R=0
        # 豁免 = 正确保护 (行为经验在 _state_trans_dist 不在边, 主节点
        # 空壳不是真替身; 合并 → R 虚高 → 擦除误删行为经验)。豁免
        # 342 = 擦除通道保护分裂产物, 非膨胀 (概念 380 < 前缀 402)。
        # 批量索引路径 (2026-08-31 分层记忆第二刀): 调用方 (如
        # _decay_life erase_code 分支) 传预构建邻居索引 → O(1) 查
        # 询 — 原每概念 O(m) 遍历边表 = O(n·m) 平方级 (概念 1081
        # × 边 9798 实测 16% 热点)。索引与原遍历逐位等价 (同一边
        # 集) → 结果不变, 只提速。不传 → 原路径零变化。
        if _nb is not None:
            return _nb.get(c, set())
        nb = set()
        for (a, r, b), w in self.edges.items():
            if w <= 0:
                continue
            if a == c:
                nb.add(b)
            elif b == c:
                nb.add(a)
        return nb

    def _concept_redundancy(self, c: str, _nb: dict = None) -> float:
        """概念信息冗余度 R(c) (2026-08-26): max Jaccard(N(c), N(c')).
        R=0 = 信息独有 (无替身); R≈1 = 完全冗余 (替身承载相同关联)。
        计算成本 O(n·m) (n 概念数 × m 边数), 概念库有界 (K* 容量)
        → 周期扫可接受。"""
        nb = self._concept_neighbors(c, _nb)
        if not nb:
            return 0.0
        best = 0.0
        _frozen = getattr(self, '_frozen', {}) or {}
        # 概念集合 = types ∪ 边端点 (直构 strengthen 不填 types,
        # 边端点才是真实概念面; types 补充类别/无边概念)
        _concepts = set(getattr(self, 'types', {}) or {})
        for (a, _r, b) in self.edges:
            _concepts.add(a)
            _concepts.add(b)
        for c2 in _concepts:
            if c2 == c or c2 in _frozen:
                continue
            nb2 = self._concept_neighbors(c2, _nb)
            if not nb2:
                continue
            inter = len(nb & nb2)
            uni = len(nb | nb2)
            if uni:
                j = inter / uni
                if j > best:
                    best = j
        return best

    def concept_redundancy_stats(self) -> dict:
        """概念库冗余度统计 (2026-08-26): R̄ (平均冗余度) + 独有占比 +
        最冗余概念 — T* 调节器第三层信号输入 + 擦除编码淘汰审计。
        概念面 = types ∪ 边端点 (同 _concept_redundancy)。纯只读。"""
        _frozen = getattr(self, '_frozen', {}) or {}
        cs_all = set(getattr(self, 'types', {}) or {})
        for (a, _r, b) in self.edges:
            cs_all.add(a)
            cs_all.add(b)
        if not cs_all:
            return {'mean': 0.0, 'unique_frac': 1.0, 'top': []}
        rs = []
        for c in cs_all:
            if c in _frozen:
                continue
            rs.append((c, self._concept_redundancy(c)))
        if not rs:
            return {'mean': 0.0, 'unique_frac': 1.0, 'top': []}
        vals = [r for _, r in rs]
        top = sorted(rs, key=lambda kv: kv[1], reverse=True)[:3]
        return {'mean': sum(vals) / len(vals),
                'unique_frac': sum(1 for v in vals if v <= 0.0)
                / len(vals),
                'top': [(c, round(r, 3)) for c, r in top]}
    # identity_learn (2026-08-30 万能基因第一棒): 同名对象跨世界异语义
    # 由系统自己发现分裂, 不再依赖设计者手动前缀。原理: 对象身份 =
    # 状态转移图连通性。同对象状态链连通 (兔 生态/fusion 同情境);
    # 异对象撞名 -> 两套不相交状态链 = 两个连通分量 -> 自动分裂
    # (obj#k 子节点, 历史经验按状态归属迁移, observe/查询按当前
    # 状态路由)。单世界 (单链/稀疏) 永不触发。
    def _id_find(self, x: str) -> str:
        _par = self._id_par
        _root = x
        while _par.get(_root, _root) != _root:
            _root = _par[_root]
        while _par.get(x, x) != x:
            _nxt = _par[x]
            _par[x] = _root
            x = _nxt
        return _root

    def _id_union(self, obj: str, a: str, b: str) -> None:
        # 状态并查集 union (同对象状态转移边 -> 连通)
        _key = lambda s: (obj, s)
        _ra, _rb = self._id_find(_key(a)), self._id_find(_key(b))
        if _ra != _rb:
            self._id_par[_rb] = _ra

    def _id_components(self, obj: str):
        # obj 的状态连通分量 (每分量状态数 >= 2 才有效: 孤立状态不算
        # 身份信号 — 稀疏观察/一次性状态不能证明多身份)
        _sigs = self._id_sigs.get(obj, {})
        if not _sigs:
            return []
        _comps = {}
        for _st in _sigs:
            _root = self._id_find((obj, _st))
            _comps.setdefault(_root, set()).add(_st)
        return [c for c in _comps.values() if len(c) >= 2]

    def _identity_reset(self) -> None:
        # 切段通知 (2026-08-30): 清最近状态路由缓存 — 避免上一段的
        # 状态把本段首帧查询路由到旧簇 (切段瞬间路由错位)。
        self._last_obs.clear()

    def _identity_route_lookup(self, name, state):
        # 分裂对象路由: name -> 当前状态所属子节点。state 为 None 或
        # 不属于任何分量 -> 保守返回 name 自身 (主节点数据已迁移走
        # 为空 -> 决策冷启动探索, 不误入他簇)。
        if not name:
            return name
        _route = self._identity_route.get(name)
        if not _route:
            return name
        if state is not None:
            for _sub, _sigs in _route.items():
                if state in _sigs:
                    return _sub
        _last = self._last_obs.get(name)
        if _last is not None:
            for _sub, _sigs in _route.items():
                if _last in _sigs:
                    return _sub
        return name

    def _maybe_split_identity(self) -> None:
        # 分裂检测 (原理批次末尾调用): 同名对象状态图 >=2 有效分量且
        # 连续 2 批次稳定分离 -> 分裂为 obj#k 子节点 + 历史数据按
        # 状态归属迁移 + 路由表登记。之后 observe/查询自动路由。
        # 单世界 (单链/稀疏) 永不触发; 兔/我 跨段状态连通 -> 不触发
        # (正迁移保留)。
        for _obj in list(self._id_sigs.keys()):
            if _obj in self._id_split_done or '#' in _obj:
                continue  # 子节点不再分裂 (题位经验共享, 一次性分裂)
            _comps = self._id_components(_obj)
            if len(_comps) >= 2:
                self._id_split_stable[_obj] += 1
            else:
                self._id_split_stable[_obj] = 0
            if self._id_split_stable[_obj] < 1:
                continue
            # 分裂执行
            _comps = sorted(_comps, key=lambda c: sorted(c)[0])
            _route = {}
            for _k, _c in enumerate(_comps, 1):
                _sub = "%s#%d" % (_obj, _k)
                _route[_sub] = set(_c)
                if _obj in self.types:
                    self.types[_sub].update(self.types[_obj])
            self._identity_route[_obj] = _route
            # 注 (2026-08-30 实测): edges 不迁移 — 复制=子节点间边
            # 污染 (低能 46% 负优化, A/B 实测), 不复制=信息孤岛 (豁免
            # 膨胀 342, 12%)。v1 裁决: 不迁移, 孤岛成本 = 自主身份
            # 学习的真实过渡代价 (论文素材: 分裂的关联边成本)。
            # 历史数据迁移: _state_trans_dist 按 c/res 归属
            for (_o, _c, _a), _cnts in list(self._state_trans_dist.items()):
                if _o != _obj:
                    continue
                _sub = self._identity_route_lookup(_obj, _c)
                if _sub != _obj:
                    for _r, _n in _cnts.items():
                        _d = self._state_trans_dist.setdefault((_sub, _c, _a), {})
                        _d[_r] = _d.get(_r, 0) + _n
                    del self._state_trans_dist[(_o, _c, _a)]
            # _causal_edges 值按状态归属
            _ce = getattr(self, '_causal_edges', {})
            for (_o, _a), _cnts in list(_ce.items()):
                if _o != _obj:
                    continue
                _new = {}
                for _st, _n in _cnts.items():
                    _sub = self._identity_route_lookup(_obj, _st)
                    _d = _new.setdefault(_sub, {})
                    _d[_st] = _d.get(_st, 0) + _n
                for _sub, _st_cnts in _new.items():
                    if _sub == _obj:
                        continue
                    _d = _ce.setdefault((_sub, _a), {})
                    for _st, _n in _st_cnts.items():
                        _d[_st] = _d.get(_st, 0) + _n
                del _ce[(_o, _a)]
            # 分裂后重置增量统计 (子节点重新积累) + 一次性标记
            del self._id_sigs[_obj]
            self._id_split_stable[_obj] = 0
            self._id_split_done.add(_obj)

    def observe(self, person: str, action: str, obj: Optional[str] = None,
                count: int = 1, principle: bool = True,
                context: Optional[Sequence[Tuple[str, str]]] = None,
                channel: str = "env", spatial: Optional[str] = None,
                spatial_objs: Optional[Sequence[str]] = None,
                cog: bool = False):
        """观察一个事件: 谁 做什么 (对什么)

        Args:
            principle: 是否参与世界因果原理统计 (默认 True 零破坏)。
              False = 认知事件通道 (意识阶段A): 自我事件 (我,失手) 等
              仍是概念空间事件 (事件流/类型/相位/注意力全参与), 但
              不进原理日志/转移计数 — 认知动作不是世界因果, 若进
              会稀释世界转移对的证据时效回补 (log 窗口被占满 →
              正向规则边活性死亡 → 规划失败, 08-13 实证)。
            context: 观察上下文 (世界模型, 2026-08-13): (关联对象,
              状态) 对列表 — 同帧观察的关联对象状态 (看到泪的同时
              看到火旺)。展开为 (关联对象,在,状态) 成员并入事件
              成员进原理统计 (复合条件扫描的关系数据源), 不改变
              主事件结构 (不进 events/相位/事件流)。默认 None 零破坏。
              注意: context 值会进状态词集 (复合扫描数据源), 只传
              语义状态词, 不传高基数标识 (如 cell 坐标 — 网格一大
              状态词集爆炸, 08-21 真实数据实锤 38/45 污染率)。
            channel: 节律通道 (2026-08-17 机制级升级, 默认 "env"
              零破坏): "env" = 环境事件 (对象在环境中出现/状态变化),
              更新概念级节律 _appear_ivals; "obs" = 观察/行为事件
              (行为者每步执行动作), 能量/共现/recency 全保留但
              不更新节律 — 观察不是环境出现, 污染环境节律则
              调度/监控基准失真 (装配层实锤: '我' 每步被观察 →
              interval≈1 → cv 尺度失真 → 异常通道无区分度)。
            spatial: 事件空间坐标 (2026-08-21 事件空间化): 事件发生
              位置的 cell 标识 (如 "2,3")。默认 None 零破坏 (无空间
              维度事件行为一字不动); 有值时维护空间索引 spatial_index
              (cell → 对象集) + 空间共现统计 spatial_cooccur (同 cell
              对象对共现计数) — 空间局部性学习的数据源 (近处对象相互
              影响可学)。cell 只进空间索引, 不注册概念/状态词
              (高基数标识污染, 08-21 真实数据实锤)。
            spatial_objs: 同 cell 空间对象列表 (2026-08-21 事件空间化
              配对修复): 共现事件携带的完整对象集 (如 [狼,兔]) —
              spatial_cooccur 对 person/obj/spatial_objs 去重全配对,
              使 (狼,兔) 同格共现被真正捕获 (旧实现单独 observe 只
              配对到动作状态 → 捕食本体对象对丢失, 08-21 真实数据
              B2 实锤 0 次)。默认 None 零破坏。

        ⚠️ 入口纪律 (2026-08-22 用户追问定稿, knowledge/concept_space_entry_boundary.md):
        本方法是概念空间的**唯一写入汇流点** (向量侧 PerceptionAdapter
        与世界侧各 world 文件都是事件源, 出口全汇入此处)。连续向量/原始
        数值**禁止直灌** — 必须分桶符号化 (有限基数、语义稳定) 或经感知层
        识别→匿名→涌现。原因 (代码事实): types 直写无条件、无上限、无
        基数控制、无清理 (concept_death 默认关) — 喂 42.7 这种原始数值,
        每次不同值 = 每个新概念 → 基数爆炸。防线现状: ①人物一致性只挡
        person 位 (噪声实验实证 4935 次高频 + 1000 一次性全拒) ②action/
        obj 位无条件创建 — 噪声词 8 个进 types 实证, 接真实场景时若需
        前置挡基数, 正确挂点 = 本方法 types[action]/types[obj].add 之前
        (创建门控 accumulate_burst 已删 2026-08-26, 频率≠重要性实测定论;
        消费端 concept_death 为当前防线)。
        """
        # 身份路由 (2026-08-30 identity_learn): 分裂对象名 → 当前
        # 状态对应的子节点。'在'/'变' 事件 person=对象名, obj=状态
        # 词 (直接判簇); 行为事件 (我 对 obj 动作) obj 位无状态 →
        # 用最近 '在' 状态判簇。零影响: 未分裂对象原样返回。
        _idr_state = obj if (action in ('在', '变') and obj) else self._last_obs.get(person)
        person = self._identity_route_lookup(person, _idr_state)
        if obj is not None:
            obj = self._identity_route_lookup(obj, self._last_obs.get(obj))
        p_types = self.types.get(person, set())
        a_types = self.types.get(action, set())
        # λ 创新率统计 (2026-08-25 立项, 纯只读零行为影响): 组合级
        # 新事件统计 — 全历史 seen 集合 (与 types/edges 同量级增长,
        # 概念空间本就无界) + 滑动窗口 is_new 标记 → innovation_rate()
        # 返回最近窗口新组合比例 (创新率 λ)。唯一写入汇流点此处统计
        # 全覆盖 (含 context 展开前的原始事件, 事件级组合口径)。
        if getattr(self, '_triple_seen', None) is None:
            self._triple_seen = set()
            from collections import deque
            self._triple_win = deque(maxlen=2000)
        _triple = (person, action, obj)
        _is_new = _triple not in self._triple_seen
        if _is_new:
            self._triple_seen.add(_triple)
        self._triple_win.append(1 if _is_new else 0)
        # A1 重激活挂点 (2026-08-19, 默认关零破坏): 冻结概念再次被观察 →
        # 解除冻结 (types 由下方类型涌现逻辑自然恢复, 本体从未删除)
        # 2026-08-25 完整版: concept_life_full 冻结同 _frozen 结构 → 同挂点
        if self.concept_death_enabled or getattr(self, 'concept_life_full', False):
            self._maybe_revive(person)
            self._maybe_revive(action)
            if obj:
                self._maybe_revive(obj)
        # 完整版活性重置 (2026-08-25, 默认关零破坏): 观察 → 活性回满
        if self.concept_life_full:
            # T* 温度调节器 (2026-08-25): 新概念初始活性 = 1 − k·T* —
            # T* 高 (过热, 概念死得多) → 新概念脆弱 (快速验证价值),
            # 少堆积 → T* 降 = 负反馈自稳。已有概念 (活性场有记录)
            # 仍回满 1.0 (巩固优先)。零 rng 零行为影响 (只动活性场,
            # 不碰决策/类型涌现)。
            if self.temp_write_gate:
                # T* v2 输入 (2026-08-26, 自参考环修复): 调节器只读成熟
                # 概念面 (出生 ≥ temp_mature_window 步) — 新概念初始
                # 活性调制足迹不进读数 → 观测-控制解耦, 负反馈净降可达。
                _ts = self._temp_signal(
                    mature_window=self.temp_mature_window)
                _init = max(0.0, 1.0 - self.temp_write_strength * _ts)
                _rh2 = getattr(self, '_rhythm', None)
                _now2 = (getattr(_rh2, '_step_count', 0)
                         if _rh2 is not None else 0)
                for _c in (person, action, obj):
                    if _c is None:
                        continue
                    if _c in self._life_strength:
                        # 已有: 巩固
                        # 有限复习模型 (2026-08-27, 默认关零影响):
                        # 复习回满幅度 = f(遗忘深度) — 遗忘深 (活性低)
                        # → 恢复少; 遗忘浅 → 恢复接近满。同时累加巩固
                        # 强度 m → 该概念后续衰减变慢 (Bjork 双效应)。
                        # 离线验证 (finite_review.py): 恢复连续 spacing
                        # curve (最优间隔 ~0.2×T_life, 与人类一致)。
                        if getattr(self, 'finite_review', False):
                            _h = self._life_strength[_c]
                            _depth = 1.0 - _h
                            _gain = getattr(self, 'fr_gain', 1.0)
                            _p = getattr(self, 'fr_power', 1.0)
                            _str = getattr(self, 'fr_strengthen', 0.5)
                            self._life_strength[_c] = min(
                                1.0, _h + _gain * _depth * (_h ** _p))
                            _m = self._review_strength.get(_c, 0.0)
                            self._review_strength[_c] = min(
                                1.0, _m + _str * _depth)
                        else:
                            self._life_strength[_c] = 1.0  # 已有: 巩固
                    else:
                        # 新概念: 受 T* 调制 + 记出生步 (成熟度过滤用)
                        self._life_strength[_c] = _init
                        self._review_strength.setdefault(_c, 0.0)
                        self._concept_birth.setdefault(_c, _now2)
                        self._birth_events += 1
            else:
                _rh3 = getattr(self, '_rhythm', None)
                _now3 = (getattr(_rh3, '_step_count', 0)
                         if _rh3 is not None else 0)
                for _c in (person, action, obj):
                    if _c is None:
                        continue
                    self._life_strength[_c] = 1.0
                    self._concept_birth.setdefault(_c, _now3)
                    self._birth_events += 1
        # 类型涌现: 事件结构本身定义类型
        # 2026-08-13 人物一致性约束 (修复类型涌现污染):
        #   主语位无条件标人物 → 位置词/场景词/动词残片坐主语位
        #   即被标人物 (网前/直线/轻松/刚好 全被污染)。
        #   人物 = 能动者: 需要 动作多样性 ≥ 2 (执行过 ≥2 种动作)
        #   或 位置统计确认的主语 (emergent_subjects 预标集, 干净)。
        #   单动作词 (网前 只被"拦"过) 证据不足, 不标人物 —
        #   保持涌现: 类型从动作分布结构涌现, 非主语位无条件。
        _person_evidence = person in getattr(self, "emergent_subjects", set())
        # 2026-08-13 去机械化: 能动者证据 = 位置统计信号
        # (emergent_subjects: 句首高频+紧邻动词+占比, 感知层超人类带宽,
        # 语言无关)。移除"动作多样性>=2" — 排球实证 '球/手/头' 执行
        # 多种动作 (飞/落/滚) 被误贴人物 (B2 确认=0 的根源之一):
        # 动作多样性是物体也具备的属性, 不是能动者证据。
        # 人物类型 = 事件结构真源 (observe 主语位), 只由位置统计
        # 信号冷启动引导 — 标签不反作用于事件结构。
        if (ACTION not in p_types and PERSON not in a_types
                and _person_evidence):
            self.types[person].add(PERSON)
        if PERSON not in a_types:
            # 类型涌现: 动作位无条件创建 (动作词 = 事件结构语义, 低基数)
            # ⚠️ 2026-08-22 入口纪律: 此处无门控 — 新动作词直接建概念。
            # 噪声实验实证: 高频噪声动作 (抖动/波动 等 8 词) 进 types,
            # 但固定小集合不爆炸; 一次性噪声 token 走 person 位被
            # 人物一致性拒。若将来接真传感器需挡一次性垃圾词, 门控
            # 正确挂点在此 add 之前 (创建门控 accumulate_burst 已删
            # 2026-08-26, 频率≠重要性定论; 消费端 concept_death 兜底)。
            self.types[action].add(ACTION)
        if obj:
            # 类型涌现: 物体位无条件创建 (物体词 = 事件结构语义)
            # ⚠️ 2026-08-22 入口纪律: 同上无门控。世界侧喂值必须分桶
            # 符号化 (fusion 草/兔/狼 各 5-6 档实证), 禁止原始数值直灌
            # (42.7 → 每值新概念 → 基数爆炸)。感知层路线 = 识别→匿名→
            # 涌现 (区域注册), 不 bypass 符号化。
            self.types[obj].add(OBJECT)
        # 事件记忆 (真实观察)
        self.events[(person, action, obj)] += count
        # 抽象规则脏标记 (2026-08-18): 事件流变化 → 下次读取重扫
        # (抽象规则 = 对象级规则的最大公约数, 新事件可能改变共享集)
        self._abstract_dirty = True
        # M1 移植 (2026-08-12): 事件流真源 emit (t 结构成分, 零行为变更)
        # count>1 时逐次 emit (每事件一个时间戳, 时间维度不可约)
        if self.event_stream is not None:
            for _ in range(count):
                self.event_stream.emit(person, action, obj, cog=cog)
        # M5 移植 (2026-08-12): 涌现引擎增量统计 (角色/维度源, 零行为变更)
        if self.emergence is not None:
            self.emergence.observe(person, action, obj)
        # 第六刀 (2026-08-12): vNext 节律层注入 — 事件 = 概念活跃证据
        # (能量注入 + 共现边增强; 严格映射: 概念注册=实体)
        # 端到端注入通道消费端 (2026-08-16): 事件含上轮 scan 高档新颖
        # 概念 → drive 调制 (增益→能量映射, 概念层判定驱动动力层响应)。
        # 默认 drive_inject_enabled=False → drive=0.0 逐位不变 (零破坏);
        # 上轮判定本轮消费 (时间维度: 与 _explore_scale 同构)。
        if self._rhythm is not None:
            _drive = 0.0
            if self.drive_inject_enabled and self._novelty_attention:
                _g = self._explore_scale(person, action, obj)
                if _g > 1.0:
                    # 增益→drive: 高档新类出现在事件里 → 动力层响应
                    # (生产级量级: 增益增量 × drive_scale, 不打破混沌)
                    _drive = ( _g - 1.0 ) * self.drive_scale
            # 通道同步→能量增益 (2026-08-20 默认开): 感知事件活跃证据
            # 注入 × sync_energy_scale — 同步时感知信息实时更活跃 (处理层)
            if person == '感知':
                _sync_e = self.sync_energy_scale()
            else:
                _sync_e = 1.0
            self._rhythm.observe_event(person, action, obj, drive=_drive,
                                       channel=channel, energy_scale=_sync_e)
        # RPE 总线: 增量计数 (在线预期分布, O(1) 更新)
        self._subj_act_counts[person][action] += count
        self._subj_total[person] += count
        # 关系边 (联想通道) — 机制化: 全部经 strengthen (第二十二课)
        # 通道同步 → 感知学习增益 (2026-08-19 默认开): 感知事件
        # (person=='感知', F2 感知总线统一标识) 同步时关联学习增强 —
        # 感知忠实反映世界 (时间对齐) → 学得更快; 失同步不增强。
        if person == '感知':
            _sync_s = self.sync_learning_scale()
        else:
            _sync_s = 1.0
        self.strengthen(person, action, "执行", count * _sync_s, "执行者")
        # 相位同步学习 (遗留③): 共现强度→同步强度 (count 放大耦合)
        # 候选① 延伸 (执行层消费): 事件含 explore 概念 → 耦合力度 × 注意增益
        # 内分泌层第二版 (主动采样): 事件含注意目标 → 增益 ×(1+explore_drive)
        # (浓度调制, 目标命中=深度处理 — 注意资源倾斜的活形态)
        # 意识阶段D 消费端 (2026-08-13): 事件含焦点成员 → ×(1+focus_gain)
        # (GWT 焦点=处理资源分配; 与上两者信号源不同, 相乘叠加)
        _scale = self._explore_scale(person, action)
        if (self.explore_drive_enabled and self._attention_target
                and self._attention_target in (person, action, obj)):
            _scale *= 1.0 + self.explore_drive
        _scale *= self._focus_scale(person, action, obj)
        self._step_phase_coupling(person, action, times=count, coupling_scale=_scale)
        if obj:
            self.strengthen(action, obj, "对象", count, "被")
            _scale2 = self._explore_scale(action, obj)
            if (self.explore_drive_enabled and self._attention_target
                    and self._attention_target in (action, obj)):
                _scale2 *= 1.0 + self.explore_drive
            _scale2 *= self._focus_scale(action, obj)
            self._step_phase_coupling(action, obj, times=count, coupling_scale=_scale2)
        # 类别本体化 (缺口 3, B 层, 2026-08-18): 类别概念相位聚合 —
        # 观察事件涉及对象 (person/obj) 属某类别 → 类别相位对齐成员
        # (同类动作同步 → 类别区域相位 = 成员圆形均值)。纯新增: 只写
        # 类别概念自身相位, 成员零改动, 无类别零开销。
        self._category_phase_sync(person)
        if obj:
            self._category_phase_sync(obj)
        # 类别活力注入 (四期, 2026-08-18): 成员被观察 → 类别活性 +0.2
        # (与相位聚合同位置, 同类语义: 类别活性 = 成员活跃度证据)
        _vit = getattr(self, '_category_vitality', None)
        if _vit:
            _cats = getattr(getattr(self, 'emergence', None), 'categories', None)
            if _cats:
                for _cn, _objs in _cats.items():
                    if person in _objs or (obj and obj in _objs):
                        _vit[_cn] = _vit.get(_cn, 1.0) + 0.2
        # 多级概念金字塔成员注入 (2026-09-03): 对象被观察 → 含它的
        # 类别活性注入 (上行活化), 只写自身新表 (未装配零操作)
        self.pyramid_observe(person)
        if obj:
            self.pyramid_observe(obj)
        # MES M4 (默认关, 纯观测): 观察事件=概念活跃证据 → 能量累积
        # (与迸发能量共用 _burst_energy 池; 供冷概念冷却判定能量低)
        # 三铁律: 感知不判定 — 能量累积是观测, 冷却判定由 cooldown_scan 定
        if self.cooldown_observe_enabled:
            self.accumulate_burst_observe(person, energy=0.5 * count)
            self.accumulate_burst_observe(action, energy=1.0 * count)
        # MES 过程耦合 (默认关=零破坏): 事件锚振荡器
        # 事件锚 = 三成员相位均值 (事件自身中心); 成员向锚轻耦合。
        # 低频事件有自己的锚, 不被高频共现主导 (研究 v2 3/3 全绿:
        # 望 0.13→0.99 救回, 高频道/笑保持 0.81/0.69, 被拦项 1→0)。
        # 与成对 _step_phase_coupling 并存: 共现锁相 + 过程锚定双机制。
        if self.process_couple_enabled:
            self._process_couple(person, action, obj, count)
        # 内分泌层第二版: 主动采样 — 注意选择权 (探索欲涨落 + 目标生命周期)
        # ① 涨落: 每观察衰减 (激素代谢), 高档新颖成员 → 推高 (多巴胺)
        # ② 锁定: 无目标且存在高档新颖 → 选增益最高者 = 注意目标
        # ③ 释放: 目标搞懂 (satisfaction ≥ 阈值) → 探索欲大幅回落
        #    (内啡肽负反馈: 满足抑制追求) + 目标释放 → 转移下一个
        if self.explore_drive_enabled:
            self.explore_drive *= self._explore_drive_decay
            if self._novelty_attention:
                for m in (person, action) + ((obj,) if obj else ()):
                    if m in self._novelty_attention:
                        self.explore_drive = min(1.0,
                                                 self.explore_drive + 0.15)
            # 缺口1 情境不确定涨源: 事件含分歧对象 → 探索欲推高
            # (知道"有隐藏变量"= 想采样; 与新颖涨源同构的注意来源,
            #  释放条件不同: 新颖=相位成熟, 情境=分歧消失)
            if self._context_uncertain:
                for m in (person, action) + ((obj,) if obj else ()):
                    if m in self._context_uncertain:
                        self.explore_drive = min(1.0,
                                                 self.explore_drive + 0.12)
            if (self._attention_target is None
                    and self._novelty_attention):
                # 锁定: 高档新类中未解决者, 选增益最高 = 最值得探索的新东西
                # (探索史 _attention_solved 防重复: 搞懂过的不回头)
                cands = {m: g for m, g in self._novelty_attention.items()
                         if m not in self._attention_solved}
                if cands:
                    self._attention_target = max(cands, key=cands.get)
                    self._attention_hold = 0
            # 缺口1 情境不确定锁定: 无新颖候选时 → 锁分歧最强对象
            # (与新颖锁定并列的注意来源; 分歧未解决持续锁定 —
            #  释放条件 = 分歧消失, 见下方 ③)
            if (self._attention_target is None
                    and not self._novelty_attention
                    and self._context_uncertain):
                cands = {m: g for m, g in self._context_uncertain.items()
                         if m not in self._attention_solved}
                if cands:
                    self._attention_target = max(cands, key=cands.get)
                    self._attention_hold = 0
            if (self._attention_target
                    and (self._attention_target
                         not in self._novelty_attention
                         or self.coherence_of(self._attention_target)
                         >= 0.5)
                    and self._attention_target
                    not in self._context_uncertain):
                # 释放条件: 目标不再高档 (novelty_scan 已解决/并入)
                # 或相位成熟 (搞懂了) → 记探索史 + 探索欲大幅回落
                # (内啡肽负反馈: 满足抑制追求) + 目标释放 → 转移下一个
                # 缺口1 扩展: 情境不确定目标 (在 _context_uncertain 中)
                # 不因相位成熟释放 — 它的"搞懂"= 分歧消失
                # (多结果转移被状态条件解释), 不是相位成熟;
                # 相位成熟释放会抽干探索欲 (研究 v1 教训:
                # 水高频相位成熟 → 每轮释放 -0.4 → 探索欲 0.74→0.05)。
                # 分歧消失 = 目标被移出 _context_uncertain (强度归零
                # 时 _refresh_context_uncertain 自动 pop) → 本守卫
                # 恢复 → 释放 (搞懂了, 隐藏变量已可解释)。
                if self._attention_target not in self._attention_solved:
                    self._attention_solved.append(self._attention_target)
                self.explore_drive = max(0.0, self.explore_drive - 0.4)
                self._attention_target = None
                self._attention_hold = 0
            if self._attention_target is not None:
                self._attention_hold += 1
        # 蓝图 M2 内生日标 (默认开, 纯观测): 目标=信号时间累积形态
        # 注意目标持续锁定且未达成 (无内啡肽盖章) → 强度随轮次累积
        # (想要多久 = 多强的方向); 达成 (satisfaction 盖章) → 解除
        # (负反馈) + 达成史。三铁律: 目标只表达方向, 不代行行为。
        if self._attention_target is not None:
            if self.satisfaction_of(self._attention_target) < \
                    self.satisfaction_threshold:
                # 未达成 → 累积 (连续浓度, 饱和 1.0)
                self._goal_hold += 1
                self._goal_strength = min(
                    1.0, self._goal_strength + self._goal_strength_per_hold)
            else:
                # 达成 (内啡肽盖章 = 搞懂了) → 解除 + 达成史
                if self._attention_target not in self._goal_history:
                    self._goal_history.append(self._attention_target)
                self._goal_hold = 0
                self._goal_strength = 0.0
                # 内啡肽负反馈完整化: 达成 → 探索目标同步释放
                # (盖章 = 满足抑制追求; 探索史防重锁, 转向下一个)
                if self._attention_target not in self._attention_solved:
                    self._attention_solved.append(self._attention_target)
                self.explore_drive = max(0.0, self.explore_drive - 0.4)
                self._attention_target = None
                self._attention_hold = 0
        # 蓝图 M3 睡眠压力 (默认开, 纯观测): 每观察累积未沉淀负担
        # (白天编码积累 → 压力上升 → 夜间整合释放; 连续浓度+慢代谢)
        # 三铁律: 感知不判定 — 压力累积是观测, 睡眠触发由调用方/节律定
        if self.sleep_pressure_enabled:
            self._sleep_pressure = min(
                1.0, self._sleep_pressure * self._sleep_pressure_decay
                     + self._sleep_pressure_per_event * count)
        # K3 修复 (2026-08-12): 一词多义自动涌现 — 概念结构本体化
        # 双轨分裂原状: sense_of 接口 (add_sense/senses) 定义但全库零调用
        # (审计 K3 🟠 中; B3/B4/C1 三份独立印证死数据)。修法: 不是手动
        # 注册 API, 而是从事件角色分歧自动涌现 — 同一词在事件槽位中
        # 扮演不同角色 (人物/动作/对象) = 一词多义的结构证据。
        # 例: 网 既是对象 (扣球→网) 又是状态宾语 (球→在→网前)。
        # 三铁律: 纯观测登记 (词→已见角色集), 不判定语义; 消费端
        # senses() 查询可见。零行为变更 (原路径不写 sense_of)。
        self._sense_roles[person].add('人物')
        self._sense_roles[action].add('动作')
        if obj:
            self._sense_roles[obj].add('对象')
        # 多义涌现: 已见角色 ≥2 → 义项注册 (词的多义身份固化)
        for w in (person, action, obj or ''):
            if w and len(self._sense_roles[w]) >= 2:
                self.sense_of[w] |= self._sense_roles[w]
        # 第五刀 (2026-08-12): 状态身份结构涌现 (不依赖词面) —
        # 专用宾语位 (仅'对象'角色) = 状态词候选。角色多样性 ≤1
        # 才可靠 — 一词多义 (角色≥2) 不参与 (身份不稳定)。
        # 第十三刀修复 (2026-08-12): 结构谓词从宾语反推 —
        # 原实现'专用动作位 = 状态谓词候选'过宽: 词面世界所有动作
        # (加柴/推/拉/浇水) 都是专用动作位 → 宾语 (火/门/水) 被误当
        # 状态词 → 状态链被对象词污染 (verify_plan_state 火/门 失败)。
        # 正确语义: 状态谓词 = 宾语是状态词的动作 (状态转移发出者),
        # 不是'任何专用动作位'。先涌现状态词 (专用宾语位), 再由
        # 状态词反推谓词 — 结构与词面一致时才成立。
        for w in (person, action, obj or ''):
            if not w:
                continue
            r = self._sense_roles[w]
            if len(r) == 1 and '对象' in r:
                self._struct_state_words.add(w)
        # 候选③ 原理消费端: 事件 → 滚动时间桶 → 自动涌现原理边
        # (纯感知统计, 不判定; 原理表随经历自然累积, 不依赖语料)
        # 缺口1 状态词在线增量 (O(1)): 状态谓词事件的宾语 = 状态词
        # (在 _principle_ingest 之前 — 本事件 (obj,变,s) 的 s 要
        #  参与本事件转移计数 (a→s) 的状态过滤)
        # 第五刀 (2026-08-12): 词面 ∪ 结构谓词 — 感知锚点概念无词面,
        # 靠专用动作位身份 (结构涌现) 进入状态谓词集, 宾语进状态词集
        # → 感知通道状态识别恢复 (状态维度铁律: 状态进入观察通道)。
        # 第十三刀修复: 结构谓词反推 (宾语 ∈ 结构状态词的动作)
        # 感知锚点世界 (无词面): 感知对象1=变 的宾语 2/3/4 是专用
        # 宾语位 → 感知对象1 反推进 _struct_state_preds;
        # 词面世界: 加柴 的宾语 火 不是专用宾语位 (火 也当主语)
        # → 加柴 不进 _struct_state_preds, 火 不被污染。
        if obj and obj in self._struct_state_words:
            self._struct_state_preds.add(action)
        if (action in ('变', '是', '在') or action in self._struct_state_preds) \
                and obj:
            self._state_words_online.add(obj)
            self._state_words_online |= self._struct_state_words
            # identity_learn 配套: 对象最近状态 (路由判簇依据)
            self._last_obs[person] = obj
            # 符号层对立结构 (2026-09-04 B 路线, 默认关零破坏): 状态
            # 轨迹在线增量 (选项A, O(1)/事件)。与 _last_obs 同挂点同
            # 条件 — 状态谓词事件 (obj,'在'|'变'|'是',s) + 结构谓词
            # 事件 (感知锚点无词面)。门控 False → 单次布尔判断返回,
            # 零统计零 rng 零写入 (生产路径一字不变)。
            if self.opposition_enabled:
                self._opp_observe(person, obj)
        if self.causal_learning_enabled and principle:
            members = [person, action] + ([obj] if obj else [])
            if context:
                # 观察上下文: (关联对象,状态) → (关联对象,在,状态) 成员
                # 2026-08-14 世界模型缺口修复: context 成员进角色识别 —
                # 关联对象状态 (火,在,旺) 的 '旺' 之前从未进 _sense_roles/
                # _struct_state_words → 状态词集缺失 → 复合扫描 c2s 找
                # 不到关联状态 → 复合边永不涌现 (关系投影断链)。
                # 修法: 与主事件同构, 关联状态词走专用宾语位识别。
                # 零破坏: context=None 时本块不执行, 主路径一字不动。
                for _o, _s in context:
                    self._sense_roles[_o].add('对象')
                    self._sense_roles[_s].add('对象')
                    if len(self._sense_roles[_s]) == 1 \
                            and '对象' in self._sense_roles[_s]:
                        self._struct_state_words.add(_s)
                        self._state_words_online.add(_s)
                    members += [_o, '在', _s]
                    # 符号层对立结构 (2026-09-04 B 路线): 上下文成员
                    # 也是真实状态断言 (关联对象状态进观察通道) → 同
                    # 条件收录轨迹 (火在 context 里旺↔灭 也进入转移图,
                    # 与 observe_state 直接断言同数据源)。门控关零开销。
                    if self.opposition_enabled:
                        self._opp_observe(_o, _s)
            self._principle_ingest(members)
        # 缺口1 身份锚增量: 对象→动作集 (从事件涌现, 零预置)
        # (状态谓词事件 (obj,变,s) 的 obj 是状态词, 不是动作对象)
        if obj and action not in ('变', '是', '在'):
            self._obj_actions.setdefault(obj, set()).add(action)
        # 对象身份统一: 每次对象出现都尝试 (动作集可能渐进积累,
        # 早期不同步 → 后期动作集一致后需重试). 零破坏: 纯增量.
        if obj and action not in ('变', '是', '在'):
            self._identity_update(obj)
        # 缺口1 在线分歧检测 (感知查询): 刷新事件对象的情境不确定强度
        # (在 _principle_ingest 之后 — _action_state_results 已含本事件)
        # 状态谓词事件 (水,变,温): 对象是 person (水); 动作事件
        # (我,加热,水): 对象是 obj (水)。两种事件都刷新同一个水。
        _ctx_obj = person if action in ('变', '是', '在') else obj
        if _ctx_obj:
            self._refresh_context_uncertain(_ctx_obj)
        # 缺口1 收尾 (2026-08-11): RPE 自动闭环 — 上次 infer 预测了
        # 本对象的状态 → 本次状态结果事件自动喂 infer_feedback
        # (命中→内啡肽“搞懂了”/落空→探索欲+多巴胺“预期违背=学习时刻”;
        #  不依赖外部脚本, 预测→观察→内分泌反馈自然闭环)
        # 触发条件: 事件对象∈上次推断上下文 且 动作是状态谓词;
        # _last_infer 一次性消费 (避免跨情境误触发)
        if (self._auto_feedback and self._last_infer
                and action in ('变', '是', '在')
                and person in self._last_infer['context']):
            members = [obj] if obj else []
            if members:
                self.infer_feedback(members, self._last_infer['result'])
            self._last_infer = None
        # 空间索引维护 (2026-08-21 事件空间化): spatial 参数携带事件
        # 坐标 → 更新 spatial_index (cell→对象集) + spatial_cooccur
        # (同 cell 对象对共现)。纯新增数据结构, 主事件路径一字不动;
        # spatial=None (所有既有世界) 零开销零破坏。
        if spatial:
            _objs = {person} | ({obj} if obj else set())
            if spatial_objs:
                _objs |= set(spatial_objs)
            _objs.discard(None)
            self.spatial_index[spatial] |= _objs
            if len(_objs) >= 2:
                _sorted = sorted(_objs)
                for _i in range(len(_sorted)):
                    for _j in range(_i + 1, len(_sorted)):
                        self.spatial_cooccur[(_sorted[_i], _sorted[_j])] += 1
            # 空间条件统计 (消费端): 语义状态分桶 (交互类型/生死状态),
            # 对象对 = person ∪ spatial_objs (排除 obj 状态词 — 共现事件
            # obj='捕食'/'进食' 是语义不是对象, 混入配对则捕食/进食
            # 指纹无法区分)。单对象 (生/死) 无配对 → 无空间条件。
            _semantic = obj or action
            self.spatial_cell_cond[spatial][_semantic] += 1
            self._spatial_ev_n += 1
            self.spatial_cell_last[spatial] = self._spatial_ev_n
            self._spatial_regions_cache = None  # 区域聚簇缓存失效 (提速 A)
            _pair_objs = set(spatial_objs or []) | {person}
            _pair_objs.discard(None)
            if len(_pair_objs) >= 2:
                _ps = sorted(_pair_objs)
                for _i in range(len(_ps)):
                    for _j in range(_i + 1, len(_ps)):
                        self.spatial_cond[(_semantic, _ps[_i], _ps[_j])] += 1

    def spatial_cond_top(self, action: str, k: int = 5):
        """空间条件查询 (消费端): 某动作发生时最常同格的对象对.

        从 spatial_cond 按语义状态分桶 — "捕食"返回最常同格对象对
        (真实数据: (兔,狼) 224 次), "进食"返回 (兔,草) 31142 次。
        空间因果条件学习的可查询数据源 (2026-08-21 受益验证后接入)。
        """
        rows = [(a, b, n) for (act, a, b), n in self.spatial_cond.items()
                if act == action]
        rows.sort(key=lambda r: -r[2])
        return rows[:k]

    def spatial_region_stats(self, cell: str, radius: int = 1):
        """空间区域统计 (区域化消费端): 某 cell 邻近区域 (曼哈顿距离
        ≤ radius) 的语义事件聚合 — "某区域捕食多/狼多"可学。

        真实数据: cell 0,5 邻近区域捕食集中 (狼区域), 兔热点区域
        (2,3 附近) 捕食稀疏 — 区域区分度实锤 (2026-08-21 受益分析)。
        纯查询零破坏。
        """
        try:
            x, y = map(int, cell.split(','))
        except Exception:
            return {}
        agg: dict = defaultdict(int)
        for c, stats in self.spatial_cell_cond.items():
            try:
                cx, cy = map(int, c.split(','))
            except Exception:
                continue
            if abs(cx - x) + abs(cy - y) <= radius:
                for sem, n in stats.items():
                    agg[sem] += n
        return dict(agg)

    def spatial_regions(self, danger_ratio: float = 0.3,
                        safe_ratio: float = 0.05) -> list:
        """空间区域聚簇 (区域概念实体化, 2026-08-21): 从 spatial_cell_cond
        涌现空间区域 — 按捕食占比分类 (危险区/安全区/中间区) + 曼哈顿
        邻近 (≤1) 同类合并。

        真实数据 (53886 事件): 8 区域 — 2 大危险区 (狼沿边界巡游带,
        捕食占比 ~42%) + 1 安全区 (兔草原心 20 cells, ~0%) + 中间过渡。
        "地图认知": 危险/安全区域可区分可查询。

        纯查询零破坏; 阈值从数据涌现 (捕食占比区分度 600 倍实锤),
        不做硬编码语义标签 (危险区/安全区是展示名, 数据是占比)。

        2026-08-26 提速 A (6G 条件短路): 聚簇缓存 — 结果缓存在
        _spatial_regions_cache, spatial_cell_cond 写入时失效。行为环
        每步 2 次全量聚簇 (安全区也全算, 链长测量 35049fa 定位 = fusion
        100% 步最重附加环节) → 查询 O(1)。纯提速: 聚簇结果与重算逐位
        一致 (相同输入相同输出), 零 rng 零行为影响。
        """
        _key = (danger_ratio, safe_ratio)
        if self._spatial_regions_cache is not None:
            _cached_key, _cached_regions = self._spatial_regions_cache
            if _cached_key == _key:
                return _cached_regions
        def _pred_ratio(c):
            s = sum(self.spatial_cell_cond.get(c, {}).values())
            return (self.spatial_cell_cond.get(c, {}).get('捕食', 0) / s) \
                if s else 0.0

        def _cls(r):
            return 0 if r >= danger_ratio else (2 if r < safe_ratio else 1)

        cells = sorted(self.spatial_cell_cond.keys())
        assigned = set()
        regions = []
        for c in cells:
            if c in assigned:
                continue
            cls = _cls(_pred_ratio(c))
            region = {'cells': [c], 'cls': cls,
                      'pred_ratio': _pred_ratio(c)}
            assigned.add(c)
            changed = True
            while changed:
                changed = False
                for c2 in cells:
                    if c2 in assigned:
                        continue
                    try:
                        x1, y1 = map(int, c2.split(','))
                    except Exception:
                        continue
                    if any(abs(x1 - int(rc.split(',')[0]))
                           + abs(y1 - int(rc.split(',')[1])) <= 1
                           for rc in region['cells']) \
                            and _cls(_pred_ratio(c2)) == cls:
                        region['cells'].append(c2)
                        region['pred_ratio'] += _pred_ratio(c2)
                        assigned.add(c2)
                        changed = True
            region['pred_ratio'] /= len(region['cells'])
            regions.append(region)
        regions.sort(key=lambda r: -r['pred_ratio'])
        # 缓存写入 (提速 A): 后续同参查询 O(1) 直读
        self._spatial_regions_cache = (_key, regions)
        return regions

    def spatial_region_of(self, cell: str, regions=None) -> Optional[dict]:
        """查询某 cell 属于哪个空间区域 (区域概念消费端).

        行为环可问: 某对象所在位置属于危险区还是安全区 — 空间
        区域知识进决策的数据源 (2026-08-21 区域概念实体化)。
        """
        if regions is None:
            regions = self.spatial_regions()
        for r in regions:
            if cell in r['cells']:
                return r
        return None

    def spatial_regions_sync(self, region_name: str = "区域",
                             expire_events: int = 0) -> int:
        """区域概念实体化第二步 (2026-08-21): 区域注册进 rhythm 概念实体
        并与其主导对象相位锚定 — 区域成为概念生态成员, 参与相位动力学。

        expire_events (cell 时间窗过期, 2026-08-21 环境突变实验修复):
        cell 距最后事件 > expire_events 事件序数 → 移除其计数 — 群落
        迁走后 cell 停止事件 → 过期 → 退出区域聚簇 → 危险区消退
        (自适应生命周期遗忘端)。**无遗忘缺陷实测**: 纯累积计数下
        危险区单向增长 (突变实验 15→22 零消退; 无突变对照 6→22
        净增 16) — 区域认知只反映历史峰值不反映当前状态。
        **等比衰减无效实锤**: 捕食/总数同步 × decay → 占比不变 →
        分类不变 (0.999 重放零消失) — 必须 cell 级时间窗过期。
        默认 0 = 不失效 (逐位兼容); 生产 spatial-aware 装配传
        ~5000 (≈10s 世界时间, 与危险区浮现延迟同量级)。

        机制 (锚定方案, 2026-08-21 15:1x 真实数据修正): 区域事件驱动
        同步 → 区域相位 = 主导对象相位 (区域内最高计数语义对应对象,
        捕食→狼/进食→兔/生长→草) — **继承而非双向耦合**。
        双向耦合实测缺陷: phase_couple_batch 把对象概念从语义簇拉走
        (真实 30000 事件: 无区域 10 概念全同步 coh=1.0, 双向耦合后
        对象簇 3.78 vs 语义簇 2.65 两簇抵消 coh 0.75-0.85, 混沌监护
        读数扰动 0.15-0.25 不可忽略); 锚定 = 区域学对象、对象不动 →
        区域相位 = 主导对象相位 (Δφ=0), 对象相位零变化, coh 完全
        零扰动 (Δ=0.0000 实测)。"危险区=狼活动域" 的空间结构以
        相位继承内化到 Kuramoto 动力学 — 数据驱动不变 (继承谁 =
        区域内语义计数数据涌现)。

        区域命名 = 区域内捕食指派 cell (区域内捕食计数最高者), 低基数
        (8 区域) 不污染 (cell 高基数不可注册的教训不适用)。区域演化
        → 代表 cell 漂移 → 新区域注册 (旧区域实体能量衰减自然遗忘)。

        纯新增零破坏: 默认不被调用 (消费端 spatial_aware 时定期调)。
        返回本次新注册区域实体数。
        """
        rhythm = getattr(self, '_rhythm', None)
        if rhythm is None:
            return 0
        # cell 时间窗过期 (自适应生命周期遗忘端): 群落迁走 → cell 停止
        # 事件 → 过期移除 → 退出区域聚簇 → 危险区消退。
        if expire_events > 0:
            now = self._spatial_ev_n
            for c in list(self.spatial_cell_last):
                if now - self.spatial_cell_last[c] > expire_events:
                    self.spatial_cell_cond.pop(c, None)
                    self.spatial_cell_last.pop(c, None)
                    self._spatial_regions_cache = None  # 聚簇缓存失效 (提速 A)
        n_new = 0
        for r in self.spatial_regions():
            # 区域内捕食指派 cell (捕食计数最高) → 区域概念名
            rep = max(r['cells'],
                      key=lambda c: self.spatial_cell_cond.get(c, {})
                      .get('捕食', 0))
            name = f"{region_name}:{rep}"
            if name not in rhythm.concept_idx:
                rhythm.register(name)
                n_new += 1
            # 区域相位锚定: 主导对象 = 区域内最高计数语义对应对象
            # (继承而非双向耦合 — 双向耦合拉走对象概念, 真实数据实锤)
            dom_obj, dom_n = None, 0
            sem_obj = {'捕食': '狼', '进食': '兔', '生长': '草'}
            for c in r['cells']:
                cond = self.spatial_cell_cond.get(c, {})
                for sem, n in cond.items():
                    if n > dom_n and sem in sem_obj:
                        dom_n, dom_obj = n, sem_obj[sem]
            if dom_obj:
                ph = self._phase_get(dom_obj)
                if ph is not None:
                    self._phase_set(name, ph)
        return n_new


    def _identity_update(self, obj: str) -> None:
        """对象身份统一 (增量涌现, 零破坏): 动作集完全一致 + 相位近 →
        并入同一身份锚. 研究实锤: 同一对象多候选名动作集/链/相位全一致,
        不同对象动作集不同 (误并无风险). 纯增量新结构, 不改既有路径.
        """
        if not self._identity_enabled:
            return
        if obj in self._identity_anchors and \
                self._identity_anchors[obj] == obj:
            # 自建锚: 仍可被更强匹配重定向 (动作集渐进积累,
            # 早期不同步 → 后期一致后需重新评估)。但若已并入过
            # 其他锚则不再反向 (锁定向, 防双向抖动)。
            pass
        elif obj in self._identity_anchors:
            return  # 已并入其他锚, 不用再评估 (锁定)
        acts = self._obj_actions.get(obj)
        if not acts:
            return
        # 动作集渐进积累: 单动作时不合并 (信息不足, 任何对象都可能
        # 先只被观察到一次; 且异步采样下双名动作集常不同步).
        # 双动作以上才评估 (杯/水杯 各积累 2+ 动作后稳定).
        if len(acts) < 2:
            return
        ph_obj = self._phase_get(obj)
        # 找可并入的锚: 动作集完全一致 且 (相位近或锚无相位)
        for anchor, members in list(self._identity_members.items()):
            if anchor == obj:
                continue
            a_acts = self._obj_actions.get(anchor)
            if not a_acts:
                continue
            # 身份判据 (双通道):
            # ① 动作集完全一致 (强信号, 同一对象同动作集)
            # ② 相位极近 (<0.05, 强耦合) + 动作集非空交集 (防误并)
            acts_eq = (acts == a_acts)
            d = float("inf")
            ph_a = self._phase_get(anchor)
            if ph_obj is not None and ph_a is not None:
                d = abs((ph_obj - ph_a + np.pi) % (2 * np.pi) - np.pi)
            if acts_eq:
                if d > 0.15:   # 相位远 → 不是同一对象 (同名不同物)
                    continue
            else:
                # 非一致 → 仅当相位极近且动作有交集才并
                # (异步采样: 双名动作集常差一步; 相位强耦合 + 共享
                #  动作 = 同一物理对象的不同名)
                if not (d < 0.05 and acts & a_acts):
                    continue
            # 合并 (两通道共用)
            was_self = (obj in self._identity_anchors
                        and self._identity_anchors[obj] == obj)
            self._identity_anchors[obj] = anchor
            members.add(obj)
            if was_self and obj in self._identity_members:
                # 迁移旧自建锚成员
                old = self._identity_members.pop(obj)
                old.discard(obj)
                members |= old
                for m in list(old):
                    self._identity_anchors[m] = anchor
            return
        # 无匹配锚 → 自建锚 (保留已有成员: obj 可能已是其他词的锚
        # (杯→水杯), members[obj] 含杯, 不能覆盖为 {obj})
        if obj not in self._identity_members:
            self._identity_anchors[obj] = obj
            self._identity_members[obj] = {obj}

    def identity(self, word: str) -> str:
        """对象身份查询: 返回身份锚 (词自身若无锚则返回自身)."""
        if not self._identity_enabled:
            return word
        return self._identity_anchors.get(word, word)

    def same_object(self, a: str, b: str) -> bool:
        """两词是否同一对象 (身份锚相等)."""
        if not self._identity_enabled:
            return a == b
        return self.identity(a) == self.identity(b)

    def identity_members(self, word: str) -> set:
        """身份锚成员集 (含自身; 词自身无锚则 {word})."""
        if not self._identity_enabled:
            return {word}
        return self._identity_members.get(self.identity(word), {word})

    def _process_couple(self, person: str, action: str, obj: Optional[str],
                        count: int = 1):
        """过程耦合: 事件三成员向事件锚相位耦合 (v2 过程锚振荡器)

        事件锚 = 成员相位均值 (事件自身的"中心"); 成员向锚耦合
        (力度 = sin(Δφ) × coupling × count × 0.5, 轻力度不覆盖共现耦合)。
        低频事件有自己的锚, 不被高频共现主导。
        """
        mem = [person, action] + ([obj] if obj else [])
        mem = [m for m in mem if m in self._phases]
        if len(mem) < 2:
            return
        # 事件锚 = 成员相位均值 (事件自身的"中心", 随成员演化)
        # 与研究 v2 一致: 现算均值, 锚是动态的 — 缓存会僵化锚
        anchor = np.mean([self._phase_get(m) for m in mem])
        for m in mem:
            self._init_phase(m)
            dphi = anchor - self._phase_get(m)
            dphi = (dphi + np.pi) % (2 * np.pi) - np.pi
            c = np.sin(dphi) * self._phase_coupling * max(1, count) * 0.5
            self._phase_set(m, (self._phase_get(m) + c) % (2 * np.pi))
        self._n_phase_steps += 1


            # ⚠️ 预留接口 (2026-08-17 重新定性): 符号监督感知/关系注入 — 语言·社会认知层消费端;
            #    输入=符号命名/关系三元组 (外部告诉系统"这是什么"/"谁喜欢谁"), 非感知流!
            #    感知流 (连续向量→无监督区域涌现) 走 PerceptionAdapter, 两者互补不重叠;
            #    生产零消费待语言层接线; 勿删勿归档
    def entrenchment(self, word: str) -> float:
        """固化强度: 高频词强固化 → 整词通道优先"""
        return self.entrench.get(word, 0.0)

    def observe_emotion(self, subject: str, emotion: str, target: str,
                        reason: Optional[str] = None, count: int = 1):
        """观察情感事件: 我 喜欢/讨厌 谁 (因为什么)

        NBA 场景: "我喜欢湖人, 因为他们的防守"
        → 我[人物] 喜欢[情感] 湖人[物体] (因为防守)
        """
        self.types[subject].add(PERSON)
        self.types[emotion].add(EMOTION)
        self.types[target].add(OBJECT)
        self.events[(subject, emotion, target)] += count
        # 关系边 (联想通道) — 机制化: 全部经 strengthen (第二十二课)
        # 情感本身即关系: 我→喜欢→湖人; 对象/主体是情感的关系角色
        self.strengthen(subject, target, emotion, count)         # 我 喜欢 湖人
        self.strengthen(emotion, target, "对象", count)          # 喜欢 的对象 湖人
        self.strengthen(emotion, subject, "主体", count)         # 喜欢 的主体 我
        self._step_phase_coupling(subject, target)
        self._step_phase_coupling(emotion, target)
        self._step_phase_coupling(emotion, subject)
        if reason:
            self.types[reason].add(OBJECT)
            self.strengthen(emotion + ":" + target, reason, "原因",
                            count, "被因")

    # ── 整词概念化: 词↔部件 (双通道, 第十六课) ───────────

    def compose(self, word: str, chars: List[str], strength: float = 1.0):
        """词概念化: 整词 + 部件 + part-of 边

        认知依据: Langacker 词汇化/固着 — 高频组合 (扣球/发球) 从
        "可分解的字义组合"固化为独立整词概念, 但仍保留与组成字的
        部分-整体关系 (组合性残留); Coltheart 双通道阅读: 整词通道
        (熟练快速) + 拼读通道 (分解) 并存。
        """
        self.types[word].add(ACTION)  # 动词组合默认动作 (扣球/发球/托球)
        for ch in chars:
            self.types[ch].add("部件")
            self.part_of[word].append(ch)
            self.wholes_of[ch].add(word)
            # 机制化: 组成/属于边经 strengthen (第二十二课)
            self.strengthen(word, ch, "组成", strength, "属于")
            self._step_phase_coupling(word, ch)
        self.entrench[word] += strength
    def add_sense(self, word: str, sense: str):
        """注册义项: 网 → 球网 / 网络"""
        self.sense_of[word].add(sense)
    def emerge(self) -> Dict[str, dict]:
        """涌现默认路径: 角色 → 类别 → 状态维度 (V3 图纸 M5)"""
        if self.emergence is None:
            return {'roles': {}, 'categories': {}, 'state_dims': {}}
        return self.emergence.emerge()

    # (归档 2026-08-16: emergence_summary → _archive_legacy/dead_interfaces_20260816.py)

    # ── M4 移植 (2026-08-12): ProcessCore 五段编排入口 ──
    # (归档 2026-08-16: process → _archive_legacy/dead_interfaces_20260816.py)

    # ── M9 移植 (2026-08-12): 统计采集入口 (感知层信号, 非判定) ──
    def memory(self) -> "MemoryShadow":
        """获取记忆影子 (惰性构建, 事件流投影 + 内容索引)

        单真源铁律: 影子零独立写入, 事件写入只经 observe/event_stream;
        遗忘只动投影 (真源保留), 语义查询走概念空间 (M7 零统计)。
        """
        if self.memory_shadow is None and MemoryShadow is not None:
            self.memory_shadow = MemoryShadow(self.event_stream)
            self.memory_shadow.refresh()
        elif self.memory_shadow is not None:
            self.memory_shadow.refresh()  # 增量投影
        return self.memory_shadow

    # ── M2 移植 (2026-08-12): 四类原生结构视图 (概念本体) ──
    def store(self) -> "ConceptStore":
        """概念空间本体视图 (惰性构建)

        ObjectC/ActionC/CauseEdge/Dim 四类类型化视图;
        数据本体 = 既有存储 (学习成果单份), 相位经 M3 读出,
        零复制零双写 (文件分离 ≠ 数据分离)。
        """
        if self.ontology_store is None and ConceptStore is not None:
            self.ontology_store = ConceptStore(self)
        return self.ontology_store

    # ── M3 移植 (2026-08-12): 概念时间属性读出层 ──
    def field(self) -> "PhaseField":
        """相位场视图 (惰性构建)

        概念时间属性 (能量/相位/相干/成熟度) 统一读出;
        动力学 = vNext 连续时间, 语义相干 = 能量同步。
        """
        if self.phase_field is None and PhaseField is not None:
            self.phase_field = PhaseField(self)
        return self.phase_field

    # ── M10 移植 (2026-08-12): 语言末端表达层 ──
    def observe_visual(self, concept: str, count: int = 1):
        """感知事件: 看见概念 → 固化强度+1 (视觉喂食)

        认知依据: 视觉经验积累 — 看得越多概念越牢固
        (看到猫100次 vs 1次, 猫概念强100倍)
        同时强化部件→整词关系 (看到'扣'也强化'扣球')
        """
        self.entrench[concept] += count
        for ch in concept:
            if ch in self.wholes_of:
                for w in self.wholes_of[ch]:
                    self.entrench[w] += count * 0.5
                    # 机制化: 视觉强化同时走 strengthen (第二十二课)
                    self.strengthen(w, ch, "组成", count * 0.5, "属于")
                    self._step_phase_coupling(w, ch)


            # ⚠️ 预留接口 (2026-08-17 重新定性): 符号监督感知/关系注入 — 语言·社会认知层消费端;
            #    输入=符号命名/关系三元组 (外部告诉系统"这是什么"/"谁喜欢谁"), 非感知流!
            #    感知流 (连续向量→无监督区域涌现) 走 PerceptionAdapter, 两者互补不重叠;
            #    生产零消费待语言层接线; 勿删勿归档
    def observe_audio(self, concept: str, count: int = 1):
        """感知事件: 听到概念 → 固化强度+1 (听觉喂食, 阶段 E)

        与 observe_visual 完全对称 — 视觉/听觉是不同的感知门禁,
        喂食同一套机制 (多模态汇聚): 听得越多概念越牢固;
        同样强化部件→整词关系 (听到'扣'也强化'扣球')
        同样走 strengthen("组成") → B2 桥跨模态联动自动接通
        """
        self.entrench[concept] += count
        for ch in concept:
            if ch in self.wholes_of:
                for w in self.wholes_of[ch]:
                    self.entrench[w] += count * 0.5
                    # 机制化: 听觉强化同样走 strengthen (第二十二课)
                    self.strengthen(w, ch, "组成", count * 0.5, "属于")
                    self._step_phase_coupling(w, ch)


            # ⚠️ 预留接口 (2026-08-17 标注): 语言层消费端 (08-13 语言后置拍板) —
            #    符号绑定/词义索引; 生产零消费待语言接线; 勿删勿归档
    def bind_word(self, word: str, concept: str, strength: float = 1.0):
        """词↔概念绑定: 词是概念的符号出口 (命名反射通道)

        2026-08-13 语言位置改造: 绑定 = 纯表达层索引 (word_bind /
        word_to_concept 双向表), 零概念空间写入。语言=外部映射:
        概念 (空间区域) 从事件结构/过程涌现, 不由词绑定创建;
        绑定不触发 Hebbian 边 (strengthen) 与相位耦合 — 表达层
        操作不驱动认知机制 (旧版: 新词绑定凭空创建相位, 违反
        零结构写入断言, verify_language_zero_write 实证)。
        """
        self.word_bind.setdefault(concept, {})[word] = \
            self.word_bind.get(concept, {}).get(word, 0.0) + strength
        self.word_to_concept.setdefault(word, {})[concept] = \
            self.word_to_concept.get(word, {}).get(concept, 0.0) + strength


            # ⚠️ 预留接口 (2026-08-17 标注): 语言层消费端 (08-13 语言后置拍板) —
            #    符号绑定/词义索引; 生产零消费待语言接线; 勿删勿归档
    def word_concepts(self, word: str, top_k: int = 3) -> List[Tuple[str, float]]:
        """理解反查: 听到词 → 激活概念 (按绑定强度排序)

        2026-08-09 双词绑定合一: 替代旧 BindingChannel.hear。
        对称索引 word_to_concept O(1) 反查, 词本身也是概念节点
        (learn 时进 types), 但命名边被 STRUCTURAL_RELS 过滤不参与
        语义扩散, 故反查用绑定索引而非 associate。
        """
        binds = self.word_to_concept.get(word, {})
        return sorted(binds.items(), key=lambda x: -x[1])[:top_k]


    def name(self, concept: str, top_k: int = 3) -> List[str]:
        """命名反射: 看到概念 → 说出绑定词 (脱口而出)"""
        binds = self.word_bind.get(concept, {})
        if not binds:
            return []
        return [w for w, _ in sorted(binds.items(), key=lambda x: -x[1])[:top_k]]

    # ── 概念合并 (2026-08-14, 区域合并消费端) ────────────

    # ── 抽象梯度 (2026-08-29, 实验54 概念空间层级设计) ──────────
    # 系统已有类别体系 (M5 共享动作聚簇: emergence.categories +
    # _category_members 本体化 + _category_rules 类别规则 + _category_
    # vitality 活力)。抽象梯度 = 把已有类别体系升级为显式层级查询:
    # 类型角色标签 (types) 是扁平层, 类别归属 (_category_members) 是
    # 抽象层 — 两层构成「实例 → 类别」抽象梯度, 全部只读零行为。

    def member_categories(self, concept: str) -> List[str]:
        """抽象梯度 A: 概念所属类别列表 (只读, 类别本体化查询)

        类别体系来自 emergence.categories (共享动作聚簇涌现, 零预置)。
        概念可属多个类别 (跨类共享动作模式)。无类别 → 空列表。
        纯只读: 不写 types/类别表, 零行为影响。
        """
        cats = getattr(getattr(self, 'emergence', None), 'categories', None)
        if not cats:
            return []
        return [name for name, objs in cats.items()
                if concept in objs]

    def category_members(self, cat: str) -> List[str]:
        """抽象梯度 A: 类别成员列表 (只读)

        类别本体化表 _category_members (类别 → 成员集合)。无表/无类
        别 → 空列表。纯只读零行为。
        """
        members = getattr(self, '_category_members', None)
        if not members:
            return []
        return sorted(members.get(cat, set()))

    def abstract_level(self, concept: str) -> int:
        """抽象梯度 A: 概念抽象度 (只读)

        Rosch 基本层次语义: 0 = 游离实例 (无类别归属非类别概念),
        1 = 基本层次实例 (有类别归属), 2 = 类别概念 (categories 键)。
        若类别概念自身也是成员 (二阶抽象) → 递归加层。
        纯只读零行为。
        """
        cats = getattr(getattr(self, 'emergence', None), 'categories', None)
        if not cats:
            return 0
        if concept in cats:
            # 类别概念: 1 + 自身是否也是成员 (二阶抽象链)
            if any(concept in objs for objs in cats.values()):
                return 2
            return 1
        if self.member_categories(concept):
            return 1  # 基本层次实例 (有类别归属)
        return 0  # 游离实例

    def abstract_up(self, concept: str) -> bool:
        """抽象上移 (实验54 组件 B, 2026-08-29): 实例统计并入类别

        操作 (全部幂等, 零删除):
          1. _abstract_dirty = True → 类别/抽象规则下次读取时惰性重扫
             (实例的边统计在 _state_cond/_det_edges 保留, 重扫自动
             吸收实例贡献 — 类别规则 = 成员共享转移的最大公约数)
          2. 类别活力 +0.2 (成员贡献吸收, 防类别休眠误杀)
          3. _abstracted[concept] = True (上移标记, 冻结/复活保留)

        消费端关 (use_abstract=False, 生产未装配) → 纯统计沉淀零行为;
        未来装配 use_abstract 时类别规则已含实例贡献 = 样本效率 7.6x
        (实验54) 兑现前提 — 新实例借类别先验, 不用攒自身样本。

        无类别归属 → False 零操作 (幂等, 安全高频调用)。
        """
        cats = self.member_categories(concept)
        if not cats:
            return False
        self._abstract_dirty = True  # 类别规则下次读取重扫 (吸收)
        _vit = getattr(self, '_category_vitality', None)
        if _vit:
            for cn in cats:
                _vit[cn] = _vit.get(cn, 1.0) + 0.2
        self._abstracted[concept] = True
        return True

# 2026-08-17 决策(用户拍板): 执行端不接 — 注释修正(此前误记"find_overlapping
#   未实现"系 companion/ 爬虫盲区): find_overlapping 已实现
#   (companion/backends/probe_engine.py:304) 且被感知模糊仲裁消费
#   (metacognition._consume_ambiguous_pairs, 生产活线); 本方法
#   (merge_concepts 执行端) 无调用方的真实原因 = 2026-08-14 审计否决:
#   统计重叠推断概念同源 = 把统计当认知本身 (候选⑩ 世界反馈) —
#   只标注 merge_candidate 不执行合并; 表达层(说人话)不需要合并仲裁, 预留。
    def merge_concepts(self, a: str, b: str) -> dict:
        """身份统一: 把 b 合并进 a (b 变 a 的别名, 本体零删除).

        执行不决策: 本方法只执行 — 是否合并由仲裁层
        (Metacognition.adjudicate 读 find_overlapping 重叠信号)
        裁定后显式调用, 不自动触发。

        合并语义 (b → a 重定向, b 保留别名映射):
          - types: b 的类型并入 a (并集)
          - events 聚合: (b,act,obj)/(subj,act,b) 重定向到 a
          - event_stream 真源: 不可变 (Event frozen, 时间不可约铁律)
            不重定向 — 真源保留历史事实 (本体零删除); 消费端
            经 resolve_concept (aliases) 映射 b→a
          - 相位场: _phases[b] 加权并入 _phases[a] (圆平均)
          - word_bind: b 的词绑定并入 a (词→a), b 保留
          - 别名表: self._aliases[b] = a (本体保留可追溯)

        返回 {'merged': b→a, 'types', 'events_moved', 'phases'}
        """
        if a == b:
            return {'merged': False, 'reason': 'noop'}
        # 概念存在性: 类型/事件/相位场任一出现即存在
        # (types 只记录有类型标签的概念 — 人物约束下主语可能不在 types)
        def _exists(c):
            return (c in self.types or c in self._phases
                    or any(c in (s, o) for (s, _, o) in self.events))
        if not _exists(b):
            return {'merged': False, 'reason': 'noop'}
        # 0. 类型并集
        self.types[a] |= self.types.get(b, set())
        moved_types = len(self.types.get(b, set()))
        # 1. events 聚合重定向
        moved = 0
        for (s, ac, o) in list(self.events.keys()):
            ns, no = s, o
            if s == b:
                ns = a
            if o == b:
                no = a
            if ns != s or no != o:
                cnt = self.events.pop((s, ac, o))
                self.events[(ns, ac, no)] += cnt
                moved += 1
        # 2. event_stream 真源: 不可变 (Event frozen, 时间不可约铁律)
        #    — 不重定向, 真源保留历史事实 (本体零删除);
        #    查询层经 aliases 映射 (消费端读时 b→a)
        # 3. 相位场: 圆平均并入 (有相位才并)
        if b in self._phases:
            pb, pa = self._phase_get(b), self._phase_get(a)
            if pa is None:
                self._phase_set(a, pb)
            else:
                self._phase_set(a, float(np.angle(
                    np.mean(np.exp(1j * np.array([pb, pa]))))))
            self._phases.pop(b, None)
        # 4. word_bind 并入 (词→a), b 保留别名
        for w, s in self.word_bind.pop(b, {}).items():
            self.word_bind.setdefault(a, {})[w] = \
                self.word_bind[a].get(w, 0.0) + s
            # 对称索引更新
            self.word_to_concept.setdefault(w, {})[a] = \
                self.word_to_concept[w].get(a, 0.0) + s
            self.word_to_concept[w].pop(b, None)
        # 5. 别名表 (本体零删除: b 保留为 a 的别名)
        if not hasattr(self, '_aliases'):
            self._aliases = {}
        self._aliases[b] = a
        return {'merged': True, 'into': a, 'from': b,
                'types_moved': moved_types, 'events_moved': moved,
                'alias': b}
# 2026-08-17 决策(用户拍板): 执行端不接 — 注释修正(此前误记"find_overlapping
#   未实现"系 companion/ 爬虫盲区): find_overlapping 已实现
#   (companion/backends/probe_engine.py:304) 且被感知模糊仲裁消费
#   (metacognition._consume_ambiguous_pairs, 生产活线); 本方法
#   (merge_concepts 执行端) 无调用方的真实原因 = 2026-08-14 审计否决:
#   统计重叠推断概念同源 = 把统计当认知本身 (候选⑩ 世界反馈) —
#   只标注 merge_candidate 不执行合并; 表达层(说人话)不需要合并仲裁, 预留。
    def resolve_concept(self, concept: str) -> str:
        """别名解析: 合并后 b → a (消费端读事件流时用).

        事件流真源不可变 (frozen Event, 时间不可约铁律) —
        历史事件保留 b, 查询层经此映射统一到当前身份。
        """
        aliases = getattr(self, '_aliases', {})
        seen = set()
        while concept in aliases and concept not in seen:
            seen.add(concept)
            concept = aliases[concept]
        return concept

    def innovation_rate(self, window: int = 500) -> float:
        """创新率 λ (2026-08-25 λ感知立项): 最近 window 个事件中
        新组合比例 (事件级组合口径, 与 K*/T* 对偶公式同源)。

        数据源: observe 汇流点维护的 _triple_win (deque, is_new 标记)
        + _triple_seen (全历史组合)。纯只读查询, 零写零行为影响。
        默认关时无统计 (win 空) → 返回 0.0 (零破坏)。

        λ 高 = 知识扩展期 (环境持续出新事件 → 探索学习价值高);
        λ 低 = 知识饱和 (事件流稳定 → 探索边际收益低 → 聚焦巩固)。
        """
        win = getattr(self, '_triple_win', None)
        if win is None:
            return 0.0
        n = len(win)
        if n == 0:
            return 0.0
        w = min(window, n)
        return sum(list(win)[-w:]) / w

    # ── 情景记忆挂载: 海马体角色 (第十八课) ──────────────
