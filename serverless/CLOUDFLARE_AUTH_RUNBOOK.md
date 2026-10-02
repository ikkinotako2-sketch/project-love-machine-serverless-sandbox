# Sandbox Cloudflare authentication and setup

Status: credentials-free preparation tested; remote authentication, schema and deployment NOT verified. D1 creation was confirmed by the user's earlier screenshot, not by this script. Never recreate it.

## Least privilege

Use **account-owned API tokens**, not Global API Key or broad Wrangler OAuth. Two separate credentials prevent routine Worker deploy from inheriting D1 query permissions:

| GitHub Actions Secret | Permission | Resource scope |
| --- | --- | --- |
| PLM_CF_D1_API_TOKEN | Account / D1 / Write (includes read; needed for the one CREATE migration) | Only the intended Cloudflare account |
| PLM_CF_WORKER_API_TOKEN | Worker Editor | Only existing plm-serverless-sandbox-control in that account |

For inspection alone D1 Read suffices; use that instead if migration will remain blocked. Replace/revoke the Write credential with Read after setup if no more migrations are required. Set short expiration appropriate to this sandbox trial. Do not use fixed runner IP restrictions: GitHub hosted runner egress is not a single static address.

**Residual privilege:** single-database D1 token scoping is not established by current official documentation. Account-level D1 Write can affect other D1 databases. Name/UUID checks are a code guard, not provider isolation. If the selected account contains production D1 resources and this residual risk is unacceptable, STOP and use an isolated free account; never pretend the token is sandbox-only at the provider level.

Worker Editor cannot create a new Worker. Its scope must be an existing exact Worker. Missing worker is a bootstrap BLOCKER; never substitute account-wide Worker Admin in this CI. A one-time separately authorized owner bootstrap is needed later. No account settings, zones, routes, DNS, Queues, Workflows or billing permissions are required by this implementation. If Wrangler requests additional permissions, STOP and review; do not broaden automatically.

## Nonsecret identifiers: GitHub Actions Variables

- CLOUDFLARE_ACCOUNT_ID: selected Cloudflare account's 32-hex identifier; verify from the actual account, not a guessed screenshot URL.
- PLM_D1_DATABASE_ID: existing database UUID, previously shown as 18050cf6-934e-4f3a-a1cd-5041bac1c35e; remote name/UUID must match before schema queries.

Enter tokens only in the Cloudflare protected issuance flow and sandbox GitHub **Settings → Secrets and variables → Actions → New repository secret**. Never paste a token into chat, repository files, workflow inputs, terminal command arguments or screenshots. Never run token-printing commands. IDs are Variables; tokens are Secrets. No SNS credentials or callback/dispatch secrets are provisioned by this setup.

## Manual setup workflow

`PLM Cloudflare Sandbox Setup Only` / `.github/workflows/plm-cloudflare-setup.yml`, main, exact sandbox only. No push/PR-triggered remote operations. Step-local secrets, contents:read, bounded timeout, serialized setup. Existing offline push CI never reads these credentials.

1. Run `inspect`: verify account token status; retrieve exact existing D1; read sqlite_master, PRAGMA columns and COUNT. Missing table is reported without changes. Existing jobs or mismatched schema STOP.
2. Only when missing, run `migrate`: performs only checked-in CREATE TABLE IF NOT EXISTS from 0001_test_jobs.sql and re-inspects. Already-compatible schema is a no-op. No DROP, DELETE, data update, D1 create, or arbitrary SQL. This is direct D1 API application of canonical migration, **not Wrangler d1_migrations bookkeeping**; do not mix unattended migration engines.
3. Run `inspect` again if needed. An ambiguous response is not retried; read-only reconciliation first, never delete data to obtain a pass.
4. After existing Worker bootstrap and exact Worker Editor token scope are confirmed, `prepare-deploy` first authenticates both tokens, verifies empty compatible D1 and checks that the exact existing Worker is readable. Generates ignored wrangler.local.json with DB binding and all four safety flags true; official wrangler-action v4 deploys with Wrangler 4.119.0. No schedules, domains, resource creation, secret upload or test job.
5. Deployment receipt verifies only command success. Remote binding/flag read-back is still a separate required verification; do not declare it PASS from local config or provider upload alone. No real trial until this is verified and the user explicitly approves.

No credentials are available in Work at preparation time; remote GitHub secret existence is unconfirmed, not assumed absent. Missing credential halts before HTTP. No live setup workflow has been dispatched during preparation.

## Official references (checked 2026-10-02)

- https://developers.cloudflare.com/workers/authorization/
- https://developers.cloudflare.com/workers/authorization/workers/
- https://developers.cloudflare.com/fundamentals/api/get-started/account-owned-tokens/
- https://developers.cloudflare.com/fundamentals/api/reference/permissions/
- https://blog.cloudflare.com/workers-granular-authorization/
- https://developers.cloudflare.com/api/resources/accounts/subresources/tokens/methods/verify/
- https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/get/
- https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/
- https://developers.cloudflare.com/workers/ci-cd/external-cicd/github-actions/

No upgrades, cards, production changes or SNS/API posts are authorized. Stop before live round trip. Keep TEST_ONLY=true, DRY_RUN=true, NO_PUBLISH=true, EMERGENCY_STOP=true.
