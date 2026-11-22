# MemSteward Complete Edition (B) · Manual

> **In one line**: a multi-tenant memory service backend — give any LLM agent memory it can keep, afford, and govern; model-agnostic (API / local / any), with built-in auth, quotas, billing, and multi-tenant isolation.

## Buyer quick start (10 minutes)

### ① Run multi-tenant locally (2 minutes)

```bash
cd src
python3 -c "from cloud_api.tenant.manager import TenantStore; a=TenantStore('acme'); a.deposit('player','mining','found diamond'); b=TenantStore('globex'); print('acme:', a.recall('diamond')); print('globex (should be empty):', b.recall('diamond')); print(a.stats())"
```

Each tenant gets its own storage directory, **mutually invisible** (in the example globex cannot see acme memories).

### ② Start the REST service (5 minutes)

```bash
cd src/cloud_api
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
# or containerized: docker-compose up -d
```

API surface (auth via API key): memory read/write, tenant management, quotas/billing — full reference in `src/cloud_api/docs/api-reference.md`, multi-language examples in `src/cloud_api/examples/{curl,node,python}`, deployment details in `src/cloud_api/docs/quickstart.md`.

## What is in the box

| Path | Contents |
|---|---|
| `src/cloud_api/` | multi-tenant REST service (FastAPI): auth / quotas / billing / tenant management — **future paid line (cloud memory storage); currently a reserved seed, not deployed, not listed** (positioned 2026-11-20); not part of the three-edition feature split |
| `src/kernel/` | memory core assembly (calldecay storage engine + admission quality gate + distillation/decay) — component single-source sync |
| `src/vendor/` | shipped dependencies (regenerable, rebuilt by the pack script) |
| `config/` | configuration surface |
| `src/health_dashboard.py` | ops health dashboard (development artifact) |
| `MANIFEST.md` | assembly list (component origin and status) |

## Optional service form (component #26 daemon)

When you need a web UI + resident landing-engine service, install the daemon component (the memory service): into B = B runs as a service; without it = B is a pure library stack. Both states are legal (the component is both part of the combination and sold standalone).

## Version scheme

Product family = CalVer (build date); SDK = SemVer (0.x = API-unstable period). See the top-level README.
