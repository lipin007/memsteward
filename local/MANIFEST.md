# MANIFEST — Local Edition (C) parts list (revised 2026-11-19 after composition review)

> Version: v2026.11.19

## Composition list (actual import evidence)

| # | Part | Purpose |
|---|---|---|
| 1/2/3/5 | tokenizer/quality_gate/distiller/tiered_decay | memory chain |
| 7/8 | landing_store/summarizer | persistence / summarization (kernel calldecacy) |
| 10/11 | mechanism_learn/planner | hypothesis lifecycle + planning (C-tree flattened shadow) |
| 12 | m3 | m3_judge (kernel) |
| 20 | calldecacy-sdk | memory engine package |
| 21/22 | admission/semantic_recall | admission + semantic arm |
| 23 | core-kit | hebbian/events/concept_space (true source core.hebbian, not hebbian_link) |

> Composition review corrections: removed #4 hebbian_link (C uses core.hebbian, not this part) and #6 memory_core (C does not import it) — originally over-reported.

## Product body

memsteward_local.py / observed_env.py / sdk/memsteward (pip)

## Change workflow

same as A
