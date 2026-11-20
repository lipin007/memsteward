"""Hebbian association tracker - simple word co-occurrence learning."""
import json
from collections import defaultdict
from pathlib import Path

class HebbianLink:
    def __init__(self, persist_path=None):
        self._links = defaultdict(float)
        self._path = persist_path
        if persist_path:
            p = Path(persist_path)
            if p.exists():
                try:
                    self._links.update(json.loads(p.read_text()))
                except: pass

    def boost(self, a, b, delta=0.1):
        if a and b and a != b:
            key = f"{a}|{b}"
            self._links[key] = min(2.0, self._links.get(key, 0) + delta)
            if self._path:
                Path(self._path).write_text(json.dumps(dict(self._links)))

    def get_associated(self, word, top_k=5):
        results = []
        for key, weight in sorted(self._links.items(), key=lambda x: -x[1]):
            a, b = key.split('|')
            if a == word:
                results.append((b, weight))
            elif b == word:
                results.append((a, weight))
            if len(results) >= top_k:
                break
        return [r[0] for r in results]
