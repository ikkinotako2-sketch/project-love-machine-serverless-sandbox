# PLM isolated TEST_ONLY sandbox preparation

Source: production Draft PR #16, head e5ad13c; only the test-only reference
files are copied here. Production repository, PR #15/16 and n8n are not
changed. This public sandbox has no SNS clients, credentials, URLs, publish
claim schema, renderer, or scheduled jobs.

## Guards and boundaries

- The Worker dispatch target is fixed to this sandbox's `main` and
  `plm-serverless-test.yml`; payloads cannot select a repository/ref/workflow.
- TEST_ONLY, DRY_RUN and NO_PUBLISH must all be true. Emergency Stop defaults
  to true in the configuration template, preventing any dispatch or callback.
- The D1 test_jobs table admits only one distinct job over its entire
  lifetime. Replays use the existing record; conflicting fingerprints are
  rejected. There is no reset/delete endpoint or automatic retry of dispatch.
- A durable dispatch attempt precedes GitHub communication; a lost response
  becomes unknown and cannot automatically dispatch again.
- Signed callback binds job ID, dispatch ID, and run ID. A conflicting runner
  cannot pass the start gate. The only task after it is a dummy result.
- GitHub push/PR events execute offline tests only. The live callback step
  requires workflow_dispatch and test-only authentication supplied later.
- The workflow has contents:read permission, standard ubuntu-latest runner,
  a five-minute timeout, and no artifact upload/cache/media generation.

No Cloudflare resources exist as a result of these files. The example config
contains no real resource ID, account ID, or credential; it is not deployable
as supplied. D1 is tested through a local SQLite shim, not a deployed database.
No Workers/Queues/Workflows live provisioning is authorized by committing it.

## Next human gates (stop before each credential/access operation)

1. Verify the actual Cloudflare account's Workers Free plan and $0 conditions,
   existing account-wide usage/headroom, and absence of a required paid/card
   step. If payment is requested, stop. A Free zone label alone does not prove
   Workers Free. The previous agent browser encountered a security challenge;
   its Free plan has not been verified.
2. Only after verification and permission, create sandbox Worker/D1 and apply
   test_jobs schema. Keep EMERGENCY_STOP=true. No queues/timers are needed for
   the single-job test.
3. User creates minimum test-only GitHub authentication scoped exclusively to
   this sandbox (Actions write). No access to the production repository.
   TEST_REQUEST_KEY, TEST_CALLBACK_KEY and GITHUB_DISPATCH_TOKEN belong only
   in protected secret fields. User enters the callback key into this
   sandbox's PLM_TEST_CALLBACK_KEY secret, and its non-secret callback URL
   into PLM_TEST_CALLBACK_URL variable. Never paste keys/tokens in chat or
   source code. No secret is generated, displayed or registered in this phase.
4. Record Free usage before the test; verify the workflow and only this
   sandbox's main. Enable exactly one supervised test with the three flags
   still true, temporarily allowing dispatch through the emergency gate.
   While EMERGENCY_STOP=true the current Worker deliberately cannot run;
   never bypass the gate. Obtain the user's explicit gate-setting approval
   before that step. Do not dispatch an extra job to test duplicates.
5. Confirm one Actions run and one D1 record, started/succeeded callbacks,
   no conflicting run, and no second dispatch. Inspect existing evidence for
   duplicate handling rather than issuing additional live jobs. Restore the
   stop gate after final state is recorded.

## Evidence and usage for the future one-job test

Before/after collect Workers requests and CPU outcomes, D1 rows_read and
rows_written (including index writes), DB size, GitHub run duration/count,
and registered plan. Dashboard metrics can lag and may include other account
traffic. Report measured deltas separately from estimates; never label an
estimate as actual consumption. The schema stores only allowlisted test
fields, not authentication/upload URLs/raw responses.

Expected happy path is one dispatch request, two signed callbacks, one
GitHub run, and one retained job record. Tests and platform overhead also
consume resources. Actual usage, deploy success and live round trip remain
UNVERIFIED until the human gates are completed.

## Offline checks

`node --test serverless/test-worker.mjs` runs ten network-free checks for
claim/replay/conflict, fixed sandbox dispatch, ambiguity, signed callbacks,
stale auth/CAS, timeout, restart, independent connections, one-job budget and
the actual dummy runner's mocked round trip. This does not prove Cloudflare
D1 remote atomicity or CPU compliance.

Rollback is to leave Emergency Stop on and revoke test-only access if later
registered. Preserve the one-job record; do not erase it or resend an unknown
dispatch. The production baseline stays untouched.
