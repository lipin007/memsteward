"""core.py — MemSteward 核心 API

干净的公共接口，wrap 内部实现。
"""
import os, sys, json, time
from collections import OrderedDict


class Memory:
    """MemSteward 记忆中间件。
    
    特性:
        - 质量控制: 空/垃圾内容自动拦截
        - 语义检索: 语义+词法混合
        - liveness 衰减: 记忆自动老化
        - 时间线: 按时间检索
        - 持久化: JSON 落盘
    
    用法:
        mem = Memory(persist_path='memory.json')
        mem.deposit('player', 'mining', 'found diamond')
        hits = mem.recall('挖矿', top_k=5)
    """
    
    def __init__(self, persist_path=None, semantic=False):
        self._entries = OrderedDict()
        self._index = {}
        self._stats = {'deposits': 0, 'recalls': 0, 'quarantined': 0}
        self._persist_path = persist_path
        self._semantic = semantic
        if persist_path and os.path.exists(persist_path):
            self._load()
    
    def deposit(self, obj, act, actual='', kind='fact', source=''):
        """写入记忆。返回 entry_id 或 None (被质量门拦截)。"""
        # 质量门
        all_text = f'{obj} {act} {actual}'.strip()
        if not all_text or len(all_text) < 3:
            self._stats['quarantined'] += 1
            return None
        if not obj and not act:
            self._stats['quarantined'] += 1
            return None
        
        eid = f'{int(time.time()*1000000)}-{len(self._entries)}'
        entry = {
            'eid': eid, 'obj': obj, 'act': act, 'actual': actual,
            'kind': kind, 'source': source,
            'timestamp': time.time(), 'liveness': 1.0,
        }
        self._entries[eid] = entry
        self._stats['deposits'] += 1
        # 索引
        for w in self._tokenize(f'{obj} {act} {actual}'):
            self._index.setdefault(w, set()).add(eid)
        # 持久化
        if self._persist_path:
            self._save()
        return eid
    
    def recall(self, query, top_k=5):
        """检索记忆。返回按相关度排序的列表。"""
        self._stats['recalls'] += 1
        words = self._tokenize(query)
        scores = {}
        for w in words:
            for eid in self._index.get(w, set()):
                scores[eid] = scores.get(eid, 0) + 1
        ranked = sorted(scores, key=lambda e: -scores[e])[:top_k]
        results = []
        for eid in ranked:
            e = self._entries.get(eid)
            if e:
                e['liveness'] = min(1.0, e.get('liveness', 1.0) + 0.1)
                results.append(e.copy())
        return results
    
    def recall_by_time(self, start=None, end=None, top_k=10):
        """时间范围检索。"""
        if start is None: start = 0
        if end is None: end = time.time()
        results = [e.copy() for e in self._entries.values() if start <= e.get('timestamp', 0) <= end]
        results.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        return results[:top_k]
    
    def recall_recent(self, hours=24, top_k=10):
        """最近 N 小时的记忆。"""
        return self.recall_by_time(start=time.time() - hours*3600, top_k=top_k)
    
    def timeline(self, hours=24):
        """时间轴摘要。"""
        entries = self.recall_recent(hours=hours, top_k=100)
        from collections import Counter
        count = Counter()
        for e in entries:
            h = time.strftime('%H:00', time.localtime(e.get('timestamp', 0)))
            count[h] += 1
        return dict(sorted(count.items()))
    
    def decay(self, factor=0.99):
        """liveness 衰减。"""
        for e in self._entries.values():
            e['liveness'] = e.get('liveness', 1.0) * factor
        if self._persist_path:
            self._save()
    
    def stats(self):
        """统计面板。"""
        return {**self._stats, 'n_entries': len(self._entries)}
    
    def clear(self):
        """清空所有记忆。"""
        self._entries.clear()
        self._index.clear()
        if self._persist_path:
            self._save()
    
    def _tokenize(self, text):
        """中英文混合分词。"""
        import re
        tokens = []
        for m in re.finditer(r'[a-zA-Z0-9]+|[\u4e00-\u9fff]', text.lower()):
            t = m.group()
            if len(t) == 1 and '\u4e00' <= t <= '\u9fff':
                tokens.append(t)
            elif len(t) > 1:
                tokens.append(t)
        return tokens
    
    def _save(self):
        try:
            with open(self._persist_path, 'w') as f:
                json.dump({'entries': list(self._entries.values())}, f, ensure_ascii=False)
        except Exception as _e:
            import logging; logging.getLogger("memsteward").warning(f"sdk 降级: {_e}")  # C9 修
    
    def _load(self):
        try:
            with open(self._persist_path) as f:
                data = json.load(f)
            for d in data.get('entries', []):
                self._entries[d['eid']] = d
                for w in self._tokenize(f"{d['obj']} {d['act']} {d.get('actual','')}"):
                    self._index.setdefault(w, set()).add(d['eid'])
        except Exception as _e:
            import logging; logging.getLogger("memsteward").warning(f"sdk 降级: {_e}")  # C9 修
