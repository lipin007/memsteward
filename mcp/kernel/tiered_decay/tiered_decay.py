"""Tiered decay."""
def apply_tiered_decay(entries):
    for eid, entry in (entries.items() if isinstance(entries, dict) else enumerate(entries)):
        kind = entry.get('kind', '') if isinstance(entry, dict) else ''
        # Tiered decay with important entry protection
        if kind in ('knowledge', 'lesson', 'decision'):
            f = 0.999  # Knowledge decays very slowly
        elif kind in ('noise', 'junk'):
            f = 0.7    # Noise decays fast
        else:
            f = 0.95   # Normal entries
        if isinstance(entry, dict):
            # Protect important entries: if recalled recently, decay slower
            hits = entry.get('hits', 0)
            if hits > 3:
                f = min(0.999, f + 0.02)  # Frequently accessed = decay slower
            entry['liveness'] = entry.get('liveness', 1.0) * f
