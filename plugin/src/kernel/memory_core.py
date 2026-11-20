"""Memory Core - unified entry point for all versions.

Shared capabilities (must be identical across all versions):
- quality gate, tokenizer, distillation, dedup, Hebbian
- semantic recall, tiered decay, persistence, backup

Version adapters plug into this core with different configs.
"""
import sys, os, time, json, threading
from pathlib import Path

# Add shared_kernel to path
_SK = os.path.dirname(os.path.abspath(__file__))
if _SK not in sys.path: sys.path.insert(0, _SK)

from tokenizer import tokenize
from quality_gate import check_quality
from knowledge_distiller import KnowledgeDistiller
from hebbian_link import HebbianLink
from tiered_decay import apply_tiered_decay

class MemoryCore:
    """Unified memory core - all versions use this."""
    
    def __init__(self, persist_path=None, config=None):
        self._entries = {}
        self._lock = threading.RLock()
        self._index = {}
        self._persist_path = persist_path
        self._config = config or {}
        self._hebbian = HebbianLink(persist_path + '.hebbian.json') if persist_path else None
        self._stats = {'deposits': 0, 'quarantined': 0}
        
    def deposit(self, obj, act, actual='', kind='fact', source=''):
        with self._lock:
            if not check_quality(actual):
                self._stats['quarantined'] += 1
                return None
            eid = f"{obj}:{act}:{int(time.time()*1000)}"
            entry = {'eid': eid, 'obj': obj, 'act': act, 'actual': actual, 'kind': kind, 'source': source, 'liveness': 1.0, 'ts': time.time()}
            self._entries[eid] = entry
            self._stats['deposits'] += 1
            # Index
            for w in tokenize(f"{obj} {act} {actual}"):
                self._index.setdefault(w, set()).add(eid)
            # Distill
            distilled = KnowledgeDistiller.distill_from_text(f"{obj} {act} {actual}")
            distilled = KnowledgeDistiller.deduplicate(distilled, similarity_threshold=0.5)
            distilled = KnowledgeDistiller.filter_by_confidence(distilled, min_confidence=0.5)
            for d in distilled[:3]:
                if d.get('knowledge'):
                    keid = f"knowledge:{d.get('type','learned')}:{int(time.time()*1000)}"
                    self._entries[keid] = {'eid': keid, 'obj': 'knowledge', 'act': d.get('type','learned'), 'actual': d['knowledge'], 'kind': 'knowledge', 'source': 'distilled', 'liveness': 1.0, 'ts': time.time()}
            # Hebbian
            if self._hebbian:
                toks = tokenize(f"{obj} {act}")
                for i, w1 in enumerate(toks):
                    for w2 in toks[i+1:]:
                        self._hebbian.boost(w1, w2, 0.1)
            return eid
    
    def recall(self, query, top_k=5):
        with self._lock:
            words = tokenize(query)
            candidates = set()
            for w in words:
                candidates.update(self._index.get(w, set()))
            results = []
            for eid in candidates:
                e = self._entries.get(eid)
                if e:
                    results.append(e)
            results.sort(key=lambda x: x.get('liveness', 1.0), reverse=True)
            return results[:top_k]
    
    def compact(self):
        with self._lock:
            apply_tiered_decay(self._entries)
    
    def stats(self):
        return {**self._stats, 'n_entries': len(self._entries)}
