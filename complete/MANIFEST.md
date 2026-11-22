# MANIFEST — Complete Edition (B) parts list (revised 2026-11-19 after composition review)

> Version: v2026.11.19

## Composition list (actual import evidence)

| # | Part | Purpose |
|---|---|---|
| 1/2/3/4/5 | tokenizer/quality_gate/distiller/hebbian_link/tiered_decay | bridge_cli kernel chain |
| 6 | memory_core | cloud_api multi-tenant memory core |
| 7/8 | landing_store/summarizer | persistence / summarization |
| 13-18 | render / telemetry / depscan / registry gate / version binding / health surface | kernel assembly (P1 single-sourced 2026-11-19; inlined sections folded back into the upstream source) |
| 26 | daemon | **optional service form** (component #26: web UI + landing engine; into B = B runs as a service; without it = B pure library stack; upstream source = the memory-daemon tree) |
| 20 | calldecacy-sdk | memory engine package |
| 21 | admission | write admission |
| 22 | semantic_recall | semantic arm |

> Composition review corrections: added #2/#10/#21/#22 (originally under-reported).

## Product body

bridge_cli.py (same text as A) / admission / dashboard_serve / health_dashboard / cloud_api (multi-tenant)

## Notes

daemon body = the memory-daemon component in the research repository (serve.py); ownership pending decision. Local model wrapping = llm-kit #24 (llm_backends / langchain_adapter / llm_gate; decided "of course we use it" 2026-11-19, pending wiring).

## Change workflow

same as A

> **cloud_api positioning (2026-11-20)**: src/cloud_api/ = future paid line (cloud memory storage), currently a reserved seed artifact, not listed and not deployed; the three-edition feature split = model connection mode, not this module.
