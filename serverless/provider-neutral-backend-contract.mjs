// Offline candidate validation only. No transport, credentials or executor.
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
export const PINS = {
  "serverless/migrations/0008_provider_neutral_roundtrip_backend.sql": "7734fe9ae6d950b5af444cc9a3f917b3da8d050c5e63083f51a79ea42d620bfe",
  "serverless/provider-neutral-backend-after.json": "d0de3cd14ac3aa1afb55a358635c5a32a9c0f90528d1ca42f84ab4beb6fd54c3",
  "serverless/provider-neutral-backend-before.json": "02d8d6c9e0d131dfbfc4088af072ca704589f31e3753a59a80a10cd71b2e31b9",
  "serverless/provider-neutral-backend-plan.json": "277fcf6ae8f465ae574e4c5f903b8c506689baf632a0e1e2d68ed2bd7dd5820a"
};
export function validate(root=new URL('../',import.meta.url)) {
 for (const [path,sha] of Object.entries(PINS)) {
  if(createHash('sha256').update(readFileSync(new URL(path,root))).digest('hex')!==sha) throw Error('raw_sha_drift');
 }
 const plan=JSON.parse(readFileSync(new URL('serverless/provider-neutral-backend-plan.json',root)));
 const before=JSON.parse(readFileSync(new URL(plan.before_file,root)));
 const after=JSON.parse(readFileSync(new URL(plan.after_file,root)));
 if(JSON.stringify(after.preserved_before)!==JSON.stringify(before))throw Error('protected_reference_drift');
 if(plan.allow!==false||plan.execution_approved!==false||plan.workflow_hard_disabled!==true)throw Error('disabled_gate');
 for(const k of ['delete','drop','alter_existing','rename','reset','backfill','old_rows_copy','retry','resend','fallback','automatic_rollback','query_mutation_max','remote_applications'])if(plan[k]!==0)throw Error('unsafe_budget');
 if(plan.route!=='REST_IMPORT_SQL_FILE'||plan.execution_max!==1||plan.runner_max!==1||plan.side_effect_http_max!==3||plan.import_http_total_max!==6||plan.status_poll_max!==3)throw Error('route_budget_drift');
 if(!plan.unknown_policy.startsWith('INIT_MAY_APPLY_CACHED_FILE_STOP_')||!plan.stop_on_non_full)throw Error('unknown_policy_drift');
 return {classification:'OFFLINE_CANDIDATE_NOT_APPROVED',remote_applications:0};
}
