# Sandbox D1 connection preparation

## Status and scope (2026-10-01)

User-reported official Free limits and Workers dashboard 0/100,000 requests
are accepted as the Free/$0 gate PASS. This is not an agent observation of
the authenticated account. D1 existence, Worker deployment, binding, secrets
and live round trip remain UNVERIFIED. Cloud Browser is blocked by security
verification. No remote command below has been executed.

Only `ikkinotako2-sketch/project-love-machine-serverless-sandbox` is a target.
Database: `plm-serverless-sandbox-state`. Worker: `plm-serverless-sandbox-control`.
Binding: `DB` (Worker uses `env.DB`). No location hint, paid plan, card,
production resource, SNS adapter, schedules, Queues or Workflows are needed.
All three test flags stay string `true`; EMERGENCY_STOP stays string `true`
through connection preparation. No test job is inserted by setup/verification.

## Human operations, only after the relevant previous result is verified

1. Open D1 database list in the intended Free account. If the exact named
   database exists, select it without recreating it. Otherwise create that
   name with default location/settings. Payment/upgrade/card request: stop.
   This operation alone does not prove table initialization or a binding.
2. In that database's Console, inspect first:

   ```sql
   SELECT name, sql FROM sqlite_master WHERE type='table' AND name='test_jobs';
   ```

   If absent, run the contents of `migrations/0001_test_jobs.sql` in this
   database only. It is CREATE TABLE IF NOT EXISTS, with no job INSERT,
   DROP, DELETE or reset. If present, inspect the existing definition and
   rows before initialization. IF NOT EXISTS does not repair a wrong schema.
3. Run `verify-d1.sql` statements separately if the Console displays one
   result at a time. Compare table SQL/columns to `schema.sql` (see below).
   Required initial job_count: **0**. Any existing row, unexpected column,
   constraint mismatch or SQL error: stop and preserve evidence. Never delete
   rows, change state to ready, or create another database to bypass the cap.
4. Create the named sandbox Worker using dashboard Hello World if absent,
   then replace its code with `worker.mjs`. This is one self-contained module.
   Before use, configure vars TEST_ONLY=true, DRY_RUN=true, NO_PUBLISH=true,
   EMERGENCY_STOP=true as text values. Missing vars also fail closed. Bind
   D1 with variable name **DB** to the exact verified sandbox database.
   Do not connect production repositories or use a GitHub deployment wizard
   with broad repository permissions. No API request or job is necessary.
5. Verify dashboard binding and var names/values and deployed Worker source.
   Keep stopped. Record D1/Workers usage baseline after initialization and
   immediately before the future job; setup costs are distinct from job costs.

Steps are a runbook, not authorization to jump past a human login/permission
gate. No credential is required for the SQL dashboard operations. Do not
request or share credential values in chat or screenshots.

## Expected schema and pure inspection helper

Column order/types/NOT NULL/composite primary key positions:

| Column | Type | NOT NULL | PK position |
| --- | --- | --- | --- |
| platform | TEXT | 1 | 1 |
| account_id | TEXT | 1 | 2 |
| job_id | TEXT | 1 | 3 |
| content_fingerprint | TEXT | 1 | 0 |
| claimant | TEXT | 1 | 0 |
| state | TEXT | 1 | 0 |
| version | INTEGER | 1 | 0 |
| last_operation | TEXT | 1 | 0 |
| run_id | TEXT | 0 | 0 |
| created_at | INTEGER | 1 | 0 |
| updated_at | INTEGER | 1 | 0 |

Checks: platform=test; account_id=test_reference_001; state in ready,
dispatching, running, succeeded, unknown; version>0. Unique identity is
(platform,account_id,job_id). No publish_id, upload URL or secret columns.
The one-job lifetime admission cap is in the Worker's atomic claim INSERT;
it is not a general DB restriction against a human writing arbitrary SQL.

`d1-setup.mjs` exports two offline functions:

- `bindingConfig(databaseID)`: builds stopped sandbox-only config from an
  observed UUID. Does not create a file, call any API or prove DB existence.
  Use only after verifying the real named resource and account. Save locally
  as `serverless/wrangler.local.json`; do not commit local account config.
- `validateInspection({tableSql,columns,jobCount})`: checks read-only
  sqlite_master/table_info/COUNT results against the canonical schema,
  rejecting populated/incompatible tables. Returns posting_permission=false.
  It does not inspect the live account itself or confer posting authority.

Migration/schema equality is tested so there is no independent schema drift.
An applied migration file is immutable; future changes require a new file.

## Optional Wrangler route (future authenticated non-Windows environment)

Dashboard is sufficient; this route is not required for the user and is not
executed here. No Windows/WSL/Docker or local n8n setup is involved.
Use the verified UUID/config, run from `serverless/`, and review the installed
official Wrangler version before executing. Account selection must be verified.

```sh
npx wrangler d1 migrations list plm-serverless-sandbox-state --remote --config wrangler.local.json
npx wrangler d1 migrations apply plm-serverless-sandbox-state --remote --config wrangler.local.json
npx wrangler d1 execute plm-serverless-sandbox-state --remote --config wrangler.local.json --file verify-d1.sql
```

Remote apply writes schema and Wrangler migration bookkeeping; it is not an
offline check. Do not add it to Actions or run unattended. The migration is
the same SQL used by the dashboard route; dashboard does not create Wrangler's
migration tracking entry. Pick one primary route, record which was used, and
do not assume migration listing proves the existing schema is correct.

## Later one-job round trip (NOT authorized to send in this preparation)

1. Complete binding/schema/deployment verification above with Stop on.
2. At the explicit human credential gate, configure test-only GitHub Actions
   dispatch access scoped exclusively to sandbox. Use protected secret fields
   only: Cloudflare TEST_REQUEST_KEY, TEST_CALLBACK_KEY, GITHUB_DISPATCH_TOKEN;
   sandbox PLM_TEST_CALLBACK_KEY; sandbox variable PLM_TEST_CALLBACK_URL is the
   deployed HTTPS workers.dev URL ending `/test-callback`. No values in chat,
   repository, D1, payload logs or screenshots. No SNS credentials.
3. Record account-wide Free usage and headroom; verify runner workflow ref main.
   Emergency Stop blocks callbacks too. Temporarily set false only for the
   separately authorized supervised one-job window; restore true afterwards.
4. Submit exactly one signed POST `/test-jobs` with platform=test,
   account_id=test_reference_001, validated test-* job_id, SHA256 fingerprint,
   TEST_ONLY/DRY_RUN/NO_PUBLISH boolean true. No manual workflow_dispatch, extra
   healthcheck request, second job or test replay. Signed headers use
   x-plm-timestamp and HMAC-SHA256(timestamp.body), never logged in chat.
5. Observe one workflow_dispatch Actions run, one D1 row and started/succeeded
   callbacks bound to the same claimant/run. Expected row state succeeded,
   version 4, last_operation runner_done. If ambiguous/unknown, do not resend:
   reconcile existing Actions run and retained D1 evidence using read-only tools.
6. Restore Stop. Collect actual requests, CPU outcomes, D1 rows_read/written,
   DB size, Actions count/duration before/after. Account-wide metrics may lag
   or include other traffic: distinguish estimates from actual attributable
   deltas. Count offline push CI separately from the one live test run.

## Limits and rollback

Local SQLite validates SQL and state rules, not deployed D1 concurrency,
Cloudflare CPU or authenticated GitHub transport. Those remain live-test
questions. An external GitHub dispatch and DB write cannot be one transaction;
unknown is intentional and cannot automatically redispatch. Retain the record.
Rollback: keep Stop on, later revoke test-only credentials through human
protected UI. No table/resource deletion, state reset or production change.

Official references checked 2026-10-01:
- https://developers.cloudflare.com/d1/get-started/
- https://developers.cloudflare.com/d1/reference/migrations/
- https://developers.cloudflare.com/d1/wrangler-commands/
- https://developers.cloudflare.com/d1/worker-api/d1-database/
