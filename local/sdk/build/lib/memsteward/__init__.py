"""MemSteward — LLM memory middleware.

Quick start:
    from memsteward import Memory
    
    mem = Memory(persist_path='memory.json')
    mem.deposit('player', 'mining', 'found diamond')
    hits = mem.recall('挖矿', top_k=5)
"""

from .core import Memory
from .version import __version__

__all__ = ['Memory', '__version__']
