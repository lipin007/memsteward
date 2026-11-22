# MANIFEST — Plugin Edition (A) parts list (revised 2026-11-19 after composition review: rewritten to the actual import surface)

> Version: v2026.11.19 (CalVer)

## Composition list (actual import evidence: bridge_cli / admission / m3 chain)

| # | Part | Purpose |
|---|---|---|
| 1 | tokenizer | Chinese/English tokenization |
| 2 | quality_gate | quality gate |
| 3 | knowledge_distiller | distillation |
| 4 | hebbian_link | co-occurrence / query expansion |
| 5 | tiered_decay | compact decay |
| 7/8 | landing_store/summarizer | persistence / summarization (inside the calldecacy package) |
| 9 | memgate | packaging chain (pack.sh/plugin.json) |
| 10 | mechanism_learn | mechanism learning (m3 chain consumer) |
| 12 | m3 | collector + verdict (A-tree flattened shadow) |
| 20 | calldecacy-sdk | memory engine package |
| 21 | admission | write admission |
| 22 | semantic_recall | semantic arm hybrid_recall |

> Composition review corrections: removed #6 memory_core (A does not import it; originally over-reported); added #2/#10/#21/#22 (originally under-reported).

## Product body

bridge_cli.py (same text as B) / MemGate test bed (test/ 83 criteria)

## Install forms

npm/tgz plugin; _bootstrap prefers the shipped vendor; home MEMSTEWARD_HOME

## Change workflow

change a part -> upstream source -> sync_kernel -> eight gates -> this artifact -> one line in COMPONENTS.md
