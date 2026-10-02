> 2026-10-02 SECURITY UPDATE: ISOLATION_AND_BOOTSTRAP_JA.md supersedes the old token recipe below. No D1 Write issuance/use with production D1 or unknown inventory. Normal inspect/deploy uses PLM_CF_D1_READ_TOKEN; PLM_CF_D1_API_TOKEN is temporary migration-only. Mutation requires verified sandbox-only account; no Admin credential in CI.

# Final credentials-free sandbox safety audit

2026-10-02. Scope: project-love-machine-serverless-sandbox only.

## Evidence and limits

| Requirement | Evidence | Status |
| --- | --- | --- |
| Setup cannot select another repository/ref | Exact repository, main ref and workflow_dispatch checked before HTTP; workflow repeats guard | Offline PASS |
| D1 ID and name | Fixed allowlisted confirmed UUID plus remote UUID/name equality before SQL | Offline PASS; remote pending |
| Worker name | Constant plm-serverless-sandbox-control and generated config; existing-only precheck | Offline PASS; existence pending |
| No production/SNS/n8n path | Setup uses fixed Cloudflare endpoints; Worker dispatch uses fixed sandbox repository; no SNS adapter or n8n URL | Offline PASS |
| No destructive D1 setup | Only fixed CREATE IF NOT EXISTS or fixed read-only schema/count statements; no user SQL or DB create/delete | Offline PASS |
| Migration replay | Existing matching empty schema no-op; mismatched/populated schema stops; rerun preserves existing unknown row in offline canonical migration test | Offline PASS |
| No credential log output | Setup prints only summary; provider error/token fixture sanitized; no response/header/body logs or token-print commands | Offline PASS; actual secret-bearing run not performed |
| All four flags true | Manual setup env and generated config assert true; unsafe values stop before HTTP; stopped Worker rejects before DB/HTTP | Offline PASS; remote config pending |
| Ambiguous/unknown handling | Setup does not retry ambiguous write; dispatch persists unknown and replay cannot dispatch again | Offline PASS |
| Lifetime one-job cap | Transactional INSERT bounded by COUNT<1; distinct second identity rejected; same identity replay cannot second dispatch | Offline PASS |
| Existing PLM protection | Only sandbox files changed; no production repository/PR15/PR16/n8n writes or workflow dispatch | Preserved |

The hardcoded D1 UUID is an identifier, not a credential. Changing a GitHub Variable to another valid DB UUID now fails before token verification or HTTP. Cloudflare account ID remains a validated nonsecret variable; D1 UUID/name must match in that account.

Important: code isolation is not credential capability isolation. Account-scoped D1 Write may access other databases in that account. Only exact per-Worker Editor is acceptable for existing Worker deploy. No account-wide Worker Admin fallback. Token permissions must be inspected by the owner before registration. A dedicated free account is required if production D1 isolation cannot otherwise be accepted.

The existing test runner is still a manual callback-capable workflow for the later explicitly approved trial. Push/PR only execute offline tests; callback step is skipped. The newly added setup workflow never invokes that runner, accepts no job inputs and never sends a live job.

Wrangler and GitHub Actions normal secret masking are used during a future deploy, but no real token-bearing run exists yet. Do not enable debug tracing, echo env, dump responses, upload runner logs/config directories as artifacts, or screenshot token values. Deployment receipt alone does not establish remote binding/flag PASS.

## Short checklist for when authentication becomes available

1. Owner creates short-lived account-owned D1 token scoped only to the intended account (Read for inspection alone, Write for required migration). Confirm residual account-wide D1 risk; never Global API Key.
2. Owner registers token as sandbox Actions Secret PLM_CF_D1_API_TOKEN and identifiers as Variables CLOUDFLARE_ACCOUNT_ID and PLM_D1_DATABASE_ID. Tokens go only into protected inputs, never chat/files.
3. Run setup `inspect`: verify active authentication, exact existing DB, schema/columns and zero jobs. If missing schema, run `migrate` once and `inspect` again. Never recreate D1, delete data, or blindly retry ambiguous writes.
4. Confirm whether exact sandbox Worker already exists. If absent, STOP for separately reviewed one-time bootstrap; do not register Admin in ordinary CI. Once present, register exact Worker Editor token as PLM_CF_WORKER_API_TOKEN.
5. Run `prepare-deploy` for the stopped Worker/DB binding. Verify the remotely active binding and all four true flags with read-only control-plane evidence; missing/uncertain evidence means STOP. Never infer these from generated local config alone.
6. STOP before adding live-test dispatch/callback credentials, disabling emergency stop, or sending the one live job. Those steps require a separate explicit user approval.

Current executable blocker: Cloudflare authentication setup unavailable. Migration, worker existence, deployment, remote binding/flags and callback are unverified gates after authentication, not successful executions. No token issuance, secret registration, remote migration/deploy, or live job occurred in this audit.

## Follow-up A/B security resolution (2026-10-02)

- Split Read and temporary migration Write credentials; setup workflow conditionally supplies Write only for migrate.
- Added PLM_CF_ACCOUNT_ISOLATION mutation gate: unverified/production_present fail before HTTP. Owner evidence is required; gate is not provider isolation.
- Added always-stopped credential-free bootstrap-placeholder.mjs for owner Dashboard creation. No Admin CI implementation/Secret.
- Current tests: 37/37 local PASS, covering isolation refusal, credential separation and stopped placeholder in addition to original 32 tests.
- Revised registration guide removes the old 7-day Write recipe. No Token issuance is allowed yet. If existing D1 shares an account with production D1, dedicated-account separation conflicts with no D1 recreate/move: STOP for a separately authorized plan.
