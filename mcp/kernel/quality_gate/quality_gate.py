"""Quality gate."""
def check_quality(text):
    if not text or not text.strip(): return False
    t = text.strip()
    if len(t) < 2: return False
    if t in ('.', ',', 'null', 'undefined', 'none', 'None', '?', '-', '--'): return False
    return True
