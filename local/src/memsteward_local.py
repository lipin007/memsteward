"""
MemStewardLocal — 本地版（C 版本）

★ 从完整版（B）抽取本地调用接口，不写新实现。
  直接 import MemGate/src/ 的真实代码（semantic_recall / admission / m3_judge）。
  这是版本 C = 版本 B 的进程内调用方式，不是新系统。

能力映射：
  记忆存储     → 本地 store（dataclass，带 liveness）
  语义检索     → MemGate/src/semantic_recall.py 的 hybrid_recall
  质量门       → MemGate/src/admission.py 的 classify_entry
  验证判据     → MemGate/src/m3_judge.py 的 classify/self_cert
  KV cache    → EmbedCache（已有的嵌入缓存）
"""

import sys
import os
import json

# Shared kernel (2026-11-18 unified architecture)
# 标准化锚具(2026-11-19): 树内自含 kernel(正源=组件总文件夹, sync_kernel.sh 装配), 零开发机绝对路径;
# 运行时家 MEMSTEWARD_HOME(默认 ~/.memsteward)供上架后任意用户家目录安家
_KERNEL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'kernel')
if _KERNEL not in sys.path: sys.path.insert(0, _KERNEL)
try:
    from tokenizer import tokenize as _kernel_tokenize
    from quality_gate import check_quality as _kernel_quality
    from tiered_decay import apply_tiered_decay
    _HAS_KERNEL = True
except ImportError:
    _HAS_KERNEL = False
import time
import re
from dataclasses import dataclass, field
from collections import OrderedDict
import time
import fcntl
import logging

logger = logging.getLogger('memsteward')

# 知识蒸馏器（接线）
try:
    from knowledge_distiller import KnowledgeDistiller
    _HAS_DISTILLER = True
except ImportError:
    _HAS_DISTILLER = False

# Hebbian 学习 (接线)
try:
    from core.hebbian import HebbianFamily
    _HAS_HEBBIAN = True
except ImportError:
    _HAS_HEBBIAN = False

# 事件流 (接线)
try:
    from core.events import EventStream
    _HAS_EVENTS = True
except ImportError:
    _HAS_EVENTS = False

# 机制学习+顾问 (接线)
try:
    from mechanism_learner import MechanismLearner
    from mechanism_advisor import MechanismAdvisor
    _HAS_MECH = True
except ImportError:
    _HAS_MECH = False

# 摘要引擎 (接线 CallDecay Summarizer)
try:
    from calldecay.summarize import Summarizer
    _HAS_SUMMARIZER = True
except ImportError:
    _HAS_SUMMARIZER = False

# ★ 关键：接入真实中间件代码（MemGate/src/）
# (semantic_recall/admission/m3_judge 已平铺进树内 kernel, 无需外部 src 锚)

# 真实中间件能力（有则用，无则降级）
try:
    from semantic_recall import EmbedCache, hybrid_recall, interleave, semantic_topk
    _HAS_SEMANTIC = True
except ImportError:
    _HAS_SEMANTIC = False


# V3 ConceptSpace (semantic reasoning engine)
try:
    _v3_core = os.environ.get('MEMSTEWARD_V3_CORE', '')  # 产品形态可选扩展默认关
    if not _v3_core: raise ImportError('MEMSTEWARD_V3_CORE 未设')
    if _v3_core not in sys.path: sys.path.insert(0, _v3_core)
    from core.concept_space import ConceptSpace
    _HAS_CONCEPT_SPACE = True
except ImportError as e:
    import logging
    logging.getLogger("memsteward").debug(f"ConceptSpace: {e}")
    _HAS_CONCEPT_SPACE = False
try:
    from admission import classify_entry, is_quarantined, mark_quarantine
    _HAS_ADMISSION = True
except ImportError:
    _HAS_ADMISSION = False

try:
    from m3_judge import classify as m3_classify, self_cert
    _HAS_JUDGE = True
except ImportError:
    _HAS_JUDGE = False


import itertools as _itertools
_EID_C = _itertools.count()  # C11: 进程内 eid 计数器

@dataclass
class Entry:
    obj: str
    act: str
    actual: str
    kind: str = "fact"
    source: str = ""
    liveness: float = 1.0
    ts: float = field(default_factory=time.time)
    touches: int = 0
    eid: str = field(default_factory=lambda: f"e{(int(time.time()*1000000)%100000000)*100 + next(_EID_C)%100:010d}")  # C11 修: 同微秒内计数器消撞

    def to_dict(self):
        return {"eid": self.eid, "obj": self.obj, "act": self.act,
                "actual": self.actual, "kind": self.kind, "source": self.source,
                "liveness": round(self.liveness, 3), "touches": self.touches,
                "timestamp": round(self.ts, 3)}  # 漏洞#1 修(2026-11-19): source 落盘, 重载不再丢 distilled 标记  # C7 修复(2026-11-19): 持久化带时间戳，重启后时间排序不再全 0

    def touch(self):
        self.touches += 1
        self.liveness = min(1.0, self.liveness + 0.05)


class MemStewardLocal:
    """本地版：进程内调用，wrap 真实中间件。"""

    def __init__(self, embed_cache_path=None, quarantine_path=None, persist_path=None, config=None):
        self._entries = OrderedDict()
        self._index = {}
        self._hypotheses = {}
        self._stats = {"deposits": 0, "recalls": 0, "holds": 0, "checks": 0,
                        "quarantined": 0, "judge_calls": 0}
        # ★ 真实中间件组件（不是替代品）
        self._concept_space = None
        if _HAS_CONCEPT_SPACE:
            try:
                self._concept_space = ConceptSpace()
            except Exception as e:
                logger.debug(f'ConceptSpace init: {e}')
        self._embed_cache = EmbedCache(embed_cache_path) if _HAS_SEMANTIC and embed_cache_path else None
        self._semantic_field = None
        self._embed_cache = None
        if _HAS_SEMANTIC:
            _ecp = embed_cache_path or (persist_path + '.emb.json' if persist_path else None)  # C6 修: 显式参数优先, 不再死参
            if _ecp:
                try:
                    self._embed_cache = EmbedCache(_ecp)
                except Exception as e:
                    logger.debug(f'embed cache: {e}')
        self._quarantine_path = quarantine_path
        self._persist_path = persist_path
        # ★ 可配置参数 (默认值合理, 可按需覆盖)
        self._config = {
            'decay_factor': 0.95,           # 默认衰减速度
            'knowledge_decay': 0.999,       # 知识衰减 (几乎不衰减)
            'experience_decay': 0.995,      # 经验衰减 (慢)
            'hit_decay': 0.99,              # 被检索过 (中)
            'liveness_freeze': 0.03,        # 冻结阈值
            'hebbian_assoc_k': 2,           # Hebbian 关联数
            'distill_max': 2,               # 每次蒸馏最多条数
            'top_k_default': 5,             # 默认检索条数
        }
        if config: self._config.update(config)
        
        # Hebbian 学习 (关联强化)
        self._hebbian = HebbianFamily() if _HAS_HEBBIAN else None
        # 事件流 (时序追踪)
        self._events = EventStream() if _HAS_EVENTS else None
        self._mech_learner = MechanismLearner() if _HAS_MECH else None
        self._mech_advisor = MechanismAdvisor(self._mech_learner) if _HAS_MECH else None
        # 摘要引擎 (两段式: 确定性底稿+模型增强)
        self._summarizer = None
        if _HAS_SUMMARIZER:
            try:
                class _MiniLanding:
                    def __init__(self): self.meta = {}; self.entries = []
                    def save(self): pass
                    def deposit(self, **kw): self.entries.append(kw); return kw
                    def deposit_summary(self, **kw): self.entries.append(kw); return {"id": str(len(self.entries))}
                self._summarizer = Summarizer(_MiniLanding(), session='memsteward')
            except Exception as e:
                logger.debug(f'summarizer init: {e}')
        # 启动时加载持久化记忆
        if persist_path:
            self._load_persisted()
            self.load_structure()

    @staticmethod
    def _check_quality(actual):
        if _HAS_KERNEL: return _kernel_quality(actual)
        if not actual or not actual.strip():
            return False
        t = actual.strip()
        if len(t) < 2:
            return False
        if t in ('.', ',', 'null', 'undefined', 'none', 'None', '?', '-', '--'):
            return False
        return True

    def deposit(self, obj, act, actual="", kind="fact", source=""):
        if not self._check_quality(actual):
            self._stats['quarantined'] += 1
            return None
        """写入记忆。质量门检查。"""
        # ★ 内容质量门（基础验证，拦空/垃圾）
        all_text = f"{obj} {act} {actual}".strip()
        if not all_text or len(all_text) < 3:
            self._stats["quarantined"] += 1
            return None  # 空内容/太短，拒收
        if not obj and not act:
            self._stats["quarantined"] += 1
            return None  # 没有主体和动作，无意义
        
        # ★ admission 质量门（回声污染过滤）
        if _HAS_ADMISSION:
            entry = Entry(obj, act, actual, kind, source)
            if is_quarantined({"obj": obj, "act": act, "actual": actual, "kind": kind}):
                self._stats["quarantined"] += 1
                return None
            classify_result = classify_entry({"obj": obj, "act": act, "actual": actual, "kind": kind})
            if classify_result.get("quarantine"):
                self._stats["quarantined"] += 1
                return None

        entry = Entry(obj, act, actual, kind, source)
        entry.timestamp = time.time()  # 时间戳
        self._entries[entry.eid] = entry
        self._stats["deposits"] += 1
        # 建索引
        words = self._tokenize(f"{obj} {act} {actual} {kind}")
        for w in words:
            self._index.setdefault(w, set()).add(entry.eid)
        # ConceptSpace: structured event encoding
        if self._concept_space:
            try:
                self._concept_space.remember(
                    time=str(int(entry.timestamp)),
                    person=obj or 'system',
                    action=act or 'observe',
                    obj=actual[:50] if actual else None,
                    place=kind or 'memory'
                )
                self._concept_space.observe_transition(
                    prev=obj, act=act, new=actual[:30] if actual else ''
                )
            except Exception as e:
                logger.debug(f'CS deposit: {e}')
        # semantic index: vectorize into resonance field
        if self._semantic_field and self._llm_backend and actual:
            try:
                vec = self._llm_backend.vectorize(f"{obj} {act} {actual}")
                self._semantic_field.put(f"mem:{entry.eid}", vec, strength=1.0)
            except Exception as e:
                logger.debug(f'semantic idx: {e}')
        # ★ 自动蒸馏: 从对话/事件提取结构化知识
        if _HAS_DISTILLER and kind in ('dialogue', 'chat', 'experience', 'event', 'knowledge', 'decision', 'lesson'):
            try:
                distilled = KnowledgeDistiller.distill_from_text(f"{obj} {act} {actual}")
                for d in distilled[:self._config['distill_max']]:
                    if d.get('knowledge'):
                        # 跨条目去重: 和已有的 distilled 知识比较
                        is_dup = False
                        for existing in self._entries.values():
                            if existing.source == 'distilled':
                                k_bigrams = set(d['knowledge'][i:i+2] for i in range(len(d['knowledge'])-1))
                                e_bigrams = set(existing.actual[i:i+2] for i in range(len(existing.actual)-1))
                                if k_bigrams and e_bigrams:
                                    overlap = len(k_bigrams & e_bigrams) / max(len(k_bigrams), len(e_bigrams))
                                    if overlap > 0.5:
                                        is_dup = True
                                        break
                        if not is_dup:
                            ke = Entry('knowledge', d.get('type', 'learned'), d['knowledge'], 'knowledge', 'distilled')
                            ke.timestamp = time.time()
                            self._entries[ke.eid] = ke
            except Exception as e:
                logger.warning(f'蒸馏沉淀降级: {e}')  # C9 修: 原静默吞
        
        # Hebbian 关联强化: 同时出现的概念互相加强
        if self._hebbian:
            try:
                words = self._tokenize(f"{obj} {act}")
                for w1 in words:
                    for w2 in words:
                        if w1 != w2:
                            self._hebbian.boost('memory_usage', w1, w2, 'co-occur', delta=0.1, source='deposit')
            except Exception as e:
                logger.debug(f'hebbian boost: {e}')
        
        # 事件流追踪 (Event 接口: t/subj/act/obj/changes)
        if self._events:
            try:
                from core.events import Event
                self._events.append(Event(
                    t=int(time.time()),
                    subj=obj,
                    act=act,
                    obj=actual[:50] if actual else None,
                ))
            except Exception as e:
                logger.warning(f'事件流降级: {e}')  # C9 修: 原静默吞
        
        # 机制学习: 从经验中提取因果模式
        if self._mech_learner:
            try:
                # C2 修复(2026-11-19): observe 签名对齐 (pos, action, world_before, world_after)
                # 文本经验映射进世界变化格式（learner 的 _detect_changes 认 changers/targets dict）
                self._mech_learner.observe(
                    pos=(0, 0),
                    action=act,
                    world_before={"changers": [], "targets": []},
                    world_after={"changers": [[obj, act, actual[:50]]], "targets": []},
                )
            except Exception as e:
                logger.warning(f'机制学习 observe 失败(不再静默): {e}')
        
        # 喂摘要引擎 (两段式蒸馏)
        if self._summarizer:
            try:
                self._summarizer.feed(f"{obj} {act} {actual}", kind=kind)
            except Exception as e:
                logger.debug(f'summarizer feed: {e}')
        
        # 落盘
        if self._persist_path:
            self._save_persisted()
            if self._stats['deposits'] % 100 == 0:
                self.save_structure()
        return entry.eid

    def recall_by_time(self, start=None, end=None, top_k=10):
        """时间线检索: 按时间范围查记忆。"""
        import time as _time
        now = _time.time()
        if start is None: start = 0
        if end is None: end = now
        
        results = []
        for e in self._entries.values():
            ts = getattr(e, 'timestamp', 0)
            if start <= ts <= end:
                results.append(e.to_dict())
        # 按时间倒序 (最新在前)
        results.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        return results[:top_k]
    
    def recall_recent(self, hours=24, top_k=10):
        """查最近 N 小时的记忆。"""
        import time as _time
        start = _time.time() - hours * 3600
        return self.recall_by_time(start=start, top_k=top_k)
    
    def timeline(self, hours=24):
        """时间线视图: 返回时间轴摘要。"""
        entries = self.recall_recent(hours=hours, top_k=100)
        # 按小时分组
        import time as _time
        from collections import Counter
        hours_count = Counter()
        for e in entries:
            ts = e.get('timestamp', 0)
            h = _time.strftime('%H:00', _time.localtime(ts))
            hours_count[h] += 1
        return dict(sorted(hours_count.items()))
    
    def consolidate(self, rounds=3):
        """Memory consolidation: ConceptSpace sleep + causal learning"""
        if self._concept_space:
            try:
                self._concept_space.consolidate(threshold=3)
                self._concept_space.sleep(rounds=rounds, threshold=3)
                return True
            except Exception as e:
                logger.error(f'consolidate: {e}'); return False
        return False

    def learn_causal_from_history(self):
        """Learn causal relationships from event history (Granger)"""
        if not self._concept_space:
            return None
        try:
            series = {}
            for e in self._entries.values():
                concept = e.obj or 'unknown'
                series.setdefault(concept, []).append(e.liveness)
            return self._concept_space.learn_causal(series_map=series)
        except Exception as e:
            logger.error(f'learn_causal: {e}'); return None

    def summarize(self, topic=None):
        """触发摘要引擎定稿 (两段式: 确定性底稿+模型增强)"""
        if not self._summarizer:
            return None
        try:
            result = self._summarizer.flush(topic=topic)
            return result
        except Exception as e:
            logger.error(f'summarize: {e}'); return None

    def suggest_action(self, context, actions, goal=None):
        """机制顾问: 根据学到的模式建议动作。"""
        if self._mech_advisor:
            try:
                return self._mech_advisor.suggest_action(context, actions, goal)
            except Exception as e:
                logger.warning(f'suggest_action 降级: {e}')  # C13 修: 原静默回 None
        return None
    
    def get_hypotheses(self):
        """查询学到的机制假设。"""
        if self._mech_learner:
            try:
                return self._mech_learner.get_hypotheses()
            except Exception as e:
                logger.warning(f'get_hypotheses 降级: {e}')  # C13 修: 原静默回 []
        return []
    
    def _load_persisted(self):
        """从磁盘加载记忆。"""
        import json as _json, os as _os
        if not _os.path.exists(self._persist_path):
            return
        try:
            with open(self._persist_path) as f:
                data = _json.load(f)
            for d in data.get("entries", []):
                e = Entry(d["obj"], d["act"], d.get("actual", ""), d.get("kind", "fact"), d.get("source", ""))
                e.eid = d["eid"]
                e.liveness = d.get("liveness", 1.0)
                e.timestamp = d.get("timestamp", 0)
                e.ts = e.timestamp  # C7b 修复(2026-11-19): ts/timestamp 双轨同步，时间排序不再全 0
                self._entries[e.eid] = e
                words = self._tokenize(f"{e.obj} {e.act} {e.actual} {e.kind}")
                for w in words:
                    self._index.setdefault(w, set()).add(e.eid)
        except Exception as e:
            logger.warning(f'持久化加载失败(不再静默): {e}')

    def _save_persisted(self):
        """保存记忆到磁盘。"""
        import json as _json
        try:
            data = {"entries": [e.to_dict() for e in self._entries.values()]}
            with open(self._persist_path, 'w') as f:
                _json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass

    def recall(self, query, top_k=5):
        """检索记忆。用真实 hybrid_recall（语义+词法），不可用则降级到词法。"""
        self._stats["recalls"] += 1

        # ★ 语义检索（如果可用）
        if _HAS_SEMANTIC and self._embed_cache is not None:
            try:
                store = {"entries": [e.to_dict() for e in self._entries.values()]}
                hits = hybrid_recall(store, [], query, k=top_k,
                                     cache=self._embed_cache)
                results = []
                for h in hits[:top_k]:
                    eid = h.get("eid")
                    if eid in self._entries:
                        self._entries[eid].touch()
                        results.append(self._entries[eid].to_dict())
                return results
            except Exception:
                pass  # 降级到词法

        results = []  # C1 修复(2026-11-19): 语义分支未走时 results 未定义，CS 分支一进即 NameError 被吞
        # ConceptSpace: causal reasoning + inference chain
        if self._concept_space and query:
            try:
                eps = self._concept_space.recall(top_k=top_k*2)
                for ep in eps:
                    eid = f"cs:{ep.get('time','')}:{ep.get('action','')}"
                    if eid not in self._entries:
                        e = Entry(ep.get('person',''), ep.get('action',''), ep.get('obj','') or '', 'fact', 'concept_space')
                        e.eid = eid
                        e.timestamp = 0
                        self._entries[eid] = e
                    results.append({'eid': eid, 'obj': ep.get('person',''), 'act': ep.get('action',''), 'actual': ep.get('obj','') or '', 'kind': 'fact', 'liveness': 1.0, 'touch': 1, 'ts': 0, 'sim': 0.8})
                chain = self._concept_space.infer_chain(subj=query, top_k=top_k)
                for c in chain:
                    if isinstance(c, dict):
                        eid = f"cs:chain:{c.get('concept','')}"
                        if eid not in self._entries:
                            e = Entry(query, c.get('relation','inference'), c.get('concept',''), 'knowledge', 'concept_space')
                            e.eid = eid
                            e.timestamp = 0
                            self._entries[eid] = e
                        results.append({'eid': eid, 'obj': query, 'act': c.get('relation',''), 'actual': c.get('concept',''), 'kind': 'knowledge', 'liveness': 1.0, 'touch': 1, 'ts': 0, 'sim': 0.9})
                if results:
                    results.sort(key=lambda x: x.get('sim', 0) * x['liveness'], reverse=True)
                    return results[:top_k]
            except Exception as e:
                logger.debug(f'CS recall: {e}')
        # semantic recall: embedding similarity via daemon's hybrid_recall
        if _HAS_SEMANTIC and self._embed_cache and query:
            try:
                lex_hits = []  # will be filled by keyword fallback
                sem_hits = semantic_topk(
                    store=self._entries, query=query, k=top_k,
                    cache=self._embed_cache
                )
                for h in sem_hits:
                    eid = h.get('eid') or h.get('id')
                    if eid and eid in self._entries:
                        e = self._entries[eid]
                        e.touches = getattr(e, 'touches', 0) + 1
                        e.liveness = min(1.0, e.liveness + 0.05)
                        results.append({'eid': eid, 'obj': e.obj, 'act': e.act, 'actual': e.actual, 'kind': e.kind, 'liveness': e.liveness, 'touch': e.touches, 'ts': getattr(e, 'ts', 0), 'sim': h.get('score', h.get('sim', 0.5))})
                if results:
                    results.sort(key=lambda x: x.get('sim', 0) * x['liveness'], reverse=True)
                    return results[:top_k]
            except Exception as e:
                logger.debug(f'semantic recall: {e}')
        # 降级：词法检索 + Hebbian 扩展
        words = self._tokenize(query)
        # Hebbian: 扩展关联词
        if self._hebbian:
            try:
                # Hebbian 扩展: 用 recent 事件找关联词
                recent = self._hebbian.recent(n=20)
                query_words = set(words)
                for ev in recent:
                    if isinstance(ev, dict):
                        a, b = ev.get('a', ''), ev.get('b', '')
                        if a in query_words and b:
                            words.append(b)
                        if b in query_words and a:
                            words.append(a)
            except Exception as e:
                logger.debug(f'hebbian extend: {e}')
        scores = {}
        for w in words:
            for eid in self._index.get(w, set()):
                scores[eid] = scores.get(eid, 0) + 1
        ranked = sorted(scores.items(), key=lambda x: (-x[1], -self._entries[x[0]].liveness))
        results = []
        for eid, _ in ranked[:top_k]:
            self._entries[eid].touch()
            results.append(self._entries[eid].to_dict())
        return results

    def hold(self, entry_id):
        self._stats["holds"] += 1
        if entry_id in self._entries:
            self._entries[entry_id].liveness = 1.0

    def check(self, **kw):
        self._stats["checks"] += 1
        eid = kw.get("id") or kw.get("eid")
        if eid in self._entries:
            return self._entries[eid].to_dict()
        return None

    def judge(self, query, hits):
        """★ 真实 m3_judge 验证判据。"""
        if _HAS_JUDGE:
            self._stats["judge_calls"] += 1
            try:
                return m3_classify(query, hits=hits)
            except Exception:
                return None
        return None

    def quarantine(self, entry_id, reason=""):
        """★ 真实 admission 隔离。"""
        if _HAS_ADMISSION:
            e = self._entries.get(entry_id)
            if e:
                mark_quarantine({"eid": entry_id, "obj": e.obj}, reason)
                self._stats["quarantined"] += 1

    def decay(self, factor=0.99):
        """智能 liveness 衰减: 重要内容衰减慢, 垃圾衰减快."""
        for e in self._entries.values():
            if e.liveness < self._config['liveness_freeze']:
                continue  # 冻结
            kind = e.kind or ''
            if kind in ('knowledge', 'lesson', 'principle'):
                imp = self._config['knowledge_decay']
            elif kind in ('experience', 'decision'):
                imp = self._config['experience_decay']
            elif getattr(e, 'touches', 0) > 0:  # C10 修: Entry 实为 touches 字段, 原 hits 恒 0 死码
                imp = self._config['hit_decay']
            else:
                imp = factor if factor != 0.99 else self._config['decay_factor']
            e.liveness = max(0.0, e.liveness * imp)

    def load_landing(self, path=None):
        """兼容读取 landing.json 格式 (daemon 数据)"""
        lp = path or os.path.expanduser('~/.memsteward/landing/landing.json')
        if not os.path.exists(lp): return 0
        try:
            with open(lp) as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                data = json.load(f)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            entries = data.get('entries', data if isinstance(data, list) else [])
            loaded = 0
            for d in entries:
                eid = d.get('id') or d.get('eid') or str(len(self._entries))
                entry = Entry(d.get('obj',''), d.get('act',''), d.get('actual', d.get('body','')), d.get('kind','fact'), d.get('provenance',''))
                entry.eid = eid
                entry.liveness = d.get('liveness', 1.0)
                entry.timestamp = d.get('ts', d.get('timestamp', 0))
                self._entries[eid] = entry
                for w in self._tokenize(f"{entry.obj} {entry.act} {entry.actual}"):
                    self._index.setdefault(w, set()).add(eid)
                loaded += 1
            return loaded
        except Exception as e:
            logger.error(f'load_landing: {e}'); return 0

    def save_landing(self, path=None):
        """保存为 landing.json 兼容格式"""
        lp = path or os.path.expanduser('~/.memsteward/landing/landing.json')
        try:
            entries = []
            for e in self._entries.values():
                entries.append({
                    'id': e.eid, 'obj': e.obj, 'act': e.act,
                    'actual': e.actual, 'kind': e.kind,
                    'liveness': e.liveness, 'ts': e.timestamp,
                    'provenance': e.source,
                })
            tmp = lp + '.tmp'
            with open(tmp, 'w') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                json.dump({'entries': entries}, f, ensure_ascii=False, default=str)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            os.replace(tmp, lp)
            return True
        except Exception as e:
            logger.error(f'save_landing: {e}'); return False

    def save_structure(self, path=None):
        """保存结构记忆: 概念空间/Hebbian/机制假设/事件流"""
        if not self._persist_path: return None
        sp = path or self._persist_path + '.struct.json'
        struct = {'config': self._config}
        # Hebbian
        if self._hebbian:
            try:
                struct['hebbian'] = {k: dict(v) for k, v in self._hebbian._weights.items()} if hasattr(self._hebbian, '_weights') else {}
            except: struct['hebbian'] = {}
        # 机制假设
        if self._mech_learner:
            try:
                struct['hypotheses'] = [h.__dict__ for h in self._mech_learner.get_hypotheses()]
            except: struct['hypotheses'] = []
        # 事件流摘要
        if self._events:
            try:
                struct['event_count'] = self._events.count()
            except: struct['event_count'] = 0
        try:
            with open(sp, 'w') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                json.dump(struct, f, ensure_ascii=False, default=str)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            return sp
        except Exception as e:
            logger.error(f'save_structure: {e}'); return None

    def load_structure(self, path=None):
        """加载结构记忆"""
        if not self._persist_path: return False
        sp = path or self._persist_path + '.struct.json'
        if not os.path.exists(sp): return False
        try:
            with open(sp) as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                struct = json.load(f)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            if 'config' in struct: self._config.update(struct['config'])
            return True
        except Exception as e:
            logger.error(f'load_structure: {e}'); return False

    def backup(self, backup_path=None):
        import shutil
        if not self._persist_path: return None
        bp = backup_path or self._persist_path + '.bak'
        try:
            shutil.copy2(self._persist_path, bp)
            return bp
        except Exception as e:
            logger.error(f'backup: {e}'); return None

    def restore(self, backup_path):
        import shutil
        try:
            shutil.copy2(backup_path, self._persist_path)
            self._entries.clear(); self._index.clear()
            self._load_persisted()
            return True
        except Exception as e:
            logger.error(f'restore: {e}'); return False

    def clear(self):
        self._entries.clear(); self._index.clear()
        if self._persist_path:
            self._save_persisted()

    def stats(self):
        n_prior = sum(1 for e in self._entries.values() if e.kind == "prior")
        return {
            **self._stats,
            "n_entries": len(self._entries),
            "n_prior": n_prior,
            "n_learned": len(self._entries) - n_prior,
            "n_hypotheses": (len(self._mech_learner.get_hypotheses()) if self._mech_learner else 0),  # C12 修: 原 _hypotheses 从未写入恒 0
            "semantic_available": _HAS_SEMANTIC,
            "concept_space": _HAS_CONCEPT_SPACE,
            "admission_available": _HAS_ADMISSION,
            "judge_available": _HAS_JUDGE,
        }

    def load_prior(self, path_or_dict):
        if isinstance(path_or_dict, str):
            with open(path_or_dict) as f:
                data = json.load(f)
        else:
            data = path_or_dict
        loaded = 0
        for ed in data.get("entries", []):
            eid = self.deposit(ed.get("obj",""), ed.get("act",""),
                              ed.get("actual",""), ed.get("kind","prior"))
            if eid:
                loaded += 1
        return {"entries": loaded}

    def export_prior(self, path):
        data = {"entries": [e.to_dict() for e in self._entries.values()]}
        with open(path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return {"entries": len(data["entries"])}

    @staticmethod
    def _tokenize(text):
        if _HAS_KERNEL: return _kernel_tokenize(text)
        text_lower = text.lower()
        words = re.findall(r"[a-z0-9]+", text_lower)
        for ch in text_lower:
            if "\u4e00" <= ch <= "\u9fff":
                words.append(ch)
        for i2 in range(len(text_lower)-1):
            c1, c2 = text_lower[i2], text_lower[i2+1]
            if "\u4e00" <= c1 <= "\u9fff" and "\u4e00" <= c2 <= "\u9fff":
                words.append(c1 + c2)
        return words
