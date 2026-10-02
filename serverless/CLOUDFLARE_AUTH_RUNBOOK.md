# Cloudflare authentication and setup — latest security gates

2026-10-02. Authoritative detailed policy: [ISOLATION_AND_BOOTSTRAP_JA.md](ISOLATION_AND_BOOTSTRAP_JA.md).
Exact deferred owner registration steps: [TOKEN_REGISTRATION_JA.md](TOKEN_REGISTRATION_JA.md).

Do not issue any Token now: production D1 inventory and exact Worker existence are unverified. D1 creation was confirmed by an earlier user screenshot; its remote schema and deployment remain unverified. Never recreate D1.

## Credentials

- PLM_CF_D1_READ_TOKEN: account-owned D1 Read, intended verified sandbox account only. Used by inspect and prepare-deploy; Write credential is not supplied in those steps.
- PLM_CF_D1_API_TOKEN: temporary account-owned D1 Write, same account; explicit migrate step only. No issuance/use if any protected production D1 exists or inventory is unknown. Revoke immediately after success or interruption and remove GitHub Secret. A TTL is additional protection, not account isolation or guaranteed single-use.
- PLM_CF_WORKER_API_TOKEN: account-owned Editor for exact existing plm-serverless-sandbox-control only. No Admin or account-wide Worker Editor fallback.

Account-wide D1 permissions cannot be claimed to be single-database permissions. Code-fixed UUID/name is a separate guard. Worker Editor can modify code/settings/bindings; resource access through bindings must also be considered. Full production data isolation needs an account boundary.

Nonsecret Variables: CLOUDFLARE_ACCOUNT_ID, PLM_D1_DATABASE_ID, PLM_CF_ACCOUNT_ISOLATION. The isolation Variable defaults to unverified. Only the owner with complete current inventory/use evidence may record sandbox_only_verified. Production presence records production_present. Mutation fails before HTTP otherwise; this software assertion is not provider enforcement.

## Staged manual workflow

PLM Cloudflare Sandbox Setup Only / plm-cloudflare-setup.yml, sandbox/main only, contents:read, no automatic remote push/PR operation.

1. inspect: Read auth active → exact existing D1 → ID/name → canonical schema/columns/COUNT. Missing table reports missing without changes. Existing job or mismatch stops.
2. migrate: explicit selection, verified isolation and temporary Write needed; fixed checked-in CREATE IF NOT EXISTS only if schema absent; re-inspect. Already matching empty schema no-op. Ambiguous write is not retried; revoke and reconcile using Read.
3. Owner revokes Write and removes the Write Secret. The CI does not acquire Token-management power to revoke itself. Secret deletion alone does not revoke a Cloudflare Token.
4. If Worker is absent, owner may separately approve one-time always-stopped placeholder creation in Dashboard. No Admin Token in this route. Bootstrap placeholder has no binding, cron, credentials, outbound fetch or job submission.
5. prepare-deploy: Read schema check + Editor auth/existing Worker check → safe config → official wrangler-action v4 with Wrangler 4.119.0. No new Worker fallback.
6. Active remote binding and flags need read-only evidence. Deployment receipt/local generated config is not that evidence. Automatic remote read-back is still unimplemented.
7. Stop before live trial, callback/dispatch credential introduction or Emergency Stop release. Explicit user trial approval required.

Direct API migration applies 0001_test_jobs.sql's canonical SQL, not Wrangler d1_migrations bookkeeping. Do not mix unattended migration engines. No arbitrary SQL, DROP, DELETE, D1 create/delete, job data mutation, SNS/n8n/production repository operation in setup.

Tokens never in chat, files, workflow inputs, screenshots or artifacts. No debug env dumps or token-printing commands. API errors are sanitized; real credential-bearing runtime log verification remains pending.

GitHub connector currently has no new workflow_dispatch tool; initial/manual staged Run workflow may require the owner unless another authorized safe interface is available. Do not claim Secret registration starts the entire setup automatically.
