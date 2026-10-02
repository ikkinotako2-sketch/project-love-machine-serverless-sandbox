// Historical algorithm for guarded mock tests only. No CLI or live default fetch.
// Prepared, disabled execution route. No credential can enable it without approval.
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {finalInspect} from './migration-final-inspect.mjs';
import {diagnose,ACCOUNT,DB,BRANCH} from './read-only-diagnostic.mjs';
import {REPO,validateMigration} from './cloudflare-setup.mjs';
const attempts=new Set();
async function jsonBounded(r) {
 if(!r.ok)throw Error('response_rejected');
 const reader=r.body.getReader();let length=0,chunks=[];
 for(;;){const {done,value}=await reader.read();if(done)break;length+=value.length;if(length>131072){await reader.cancel();throw Error('response_unconfirmed');}chunks.push(value);}
 const bytes=new Uint8Array(length);let offset=0;for(const c of chunks){bytes.set(c,offset);offset+=c.length;}
 return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
}
export async function migrateOnce(env,fetcher=fetch,emit=()=>{}) {
 if(fetcher===fetch)throw Error("historical_reference_mock_only");
 if(env.PLM_MIGRATION_EXECUTION_APPROVED!=='true')throw Error('execution_not_approved');
 if(env.GITHUB_REPOSITORY!==REPO||env.GITHUB_REF!==`refs/heads/${BRANCH}`||env.GITHUB_EVENT_NAME!=='push'||env.GITHUB_RUN_ATTEMPT!=='1'||!/^\d+$/.test(env.GITHUB_RUN_ID||'')||!/^[a-f0-9]{40}$/.test(env.PLM_MIGRATION_APPROVED_COMMIT||'')||env.GITHUB_SHA!==env.PLM_MIGRATION_APPROVED_COMMIT||['TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP'].some(k=>env[k]!=='true'))throw Error('approval_run_context_rejected');
 if(env.PLM_FREE_OWNER_EVIDENCE!=='confirmed'||env.PLM_WRITE_SCOPE_OWNER_EVIDENCE!=='specific_account_d1_write_only'||env.PLM_REVOCATION_OWNER_READY!=='true')throw Error('owner_evidence_required');
 if(!env.GITHUB_TOKEN)throw Error('workflow_history_read_required');
 const receipt=env.GITHUB_SHA+':'+env.GITHUB_RUN_ID;
 if(attempts.has(receipt))throw Error('attempt_already_started_reconcile');
 attempts.add(receipt); // consumed even if any read fails; no retry/resume entry point.
 const sql=readFileSync(new URL('./migrations/0001_test_jobs.sql',import.meta.url),'utf8');validateMigration(sql);
 try {
  const options={method:'GET',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${env.GITHUB_TOKEN}`,Accept:'application/vnd.github+json'}};
  const runs=await jsonBounded(await fetcher(`https://api.github.com/repos/${REPO}/actions/workflows/373461921/runs?head_sha=${env.GITHUB_SHA}&event=push&per_page=100&page=1`,options));
  const row=runs.workflow_runs?.[0];
  if(runs.total_count!==1||runs.workflow_runs?.length!==1||String(row.id)!==env.GITHUB_RUN_ID||row.head_sha!==env.GITHUB_SHA||row.run_attempt!==1||row.event!=='push'||row.head_branch!==BRANCH)throw Error();
  const history=await jsonBounded(await fetcher(`https://api.github.com/repos/${REPO}/actions/workflows/373461921/runs?per_page=100&page=1`,options));
  if(!Number.isSafeInteger(history.total_count)||history.total_count<1||history.total_count>100||!Array.isArray(history.workflow_runs)||history.workflow_runs.length!==history.total_count||history.workflow_runs.some(x=>String(x.id)!==env.GITHUB_RUN_ID&&x.conclusion!=='skipped'))throw Error();
  const branch=await jsonBounded(await fetcher(`https://api.github.com/repos/${REPO}/branches/${BRANCH}`,options));
  if(branch.commit?.sha!==env.GITHUB_SHA)throw Error();
 }catch{throw Error('workflow_history_or_branch_unconfirmed_no_retry');}
 const evidence=await finalInspect(env,fetcher);
 if(!evidence.write_token_active||!evidence.read_preconditions_pass)throw Error('live_preconditions_not_met');
 emit({phase:'PRECHECK_PASS',remote_write_attempts:0,migration_resend_attempts:0,precheck:evidence});
 // Exactly one canonical CREATE. There is no catch/retry around a second POST.
 let data;
 emit({phase:'WRITE_ATTEMPT',remote_write_attempts:1,migration_resend_attempts:0});
 try{data=await jsonBounded(await fetcher(`https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}/d1/database/${DB}/query`,{method:'POST',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${env.PLM_CF_D1_API_TOKEN}`,'Content-Type':'application/json'},body:JSON.stringify({sql,params:[]})}));}
 catch{emit({phase:'WRITE_OUTCOME_UNKNOWN',remote_write_attempts:1,migration_resend_attempts:0,unknown:true});throw Error('migration_outcome_unknown_revoke_and_reconcile');}
 if(data?.success!==true||!Array.isArray(data.result)||data.result.length!==1||data.result[0].success!==true){emit({phase:'WRITE_OUTCOME_UNCONFIRMED',remote_write_attempts:1,migration_resend_attempts:0,unknown:true});throw Error('migration_outcome_unconfirmed_revoke_and_reconcile');}
 emit({phase:'WRITE_CONFIRMED',remote_write_attempts:1,remote_write_confirmed:1,migration_resend_attempts:0});
 const after=await diagnose({...env,PLM_CF_D1_API_TOKEN:undefined,PLM_CF_D1_READ_TOKEN_KIND:'user',PLM_MIGRATION_PREFLIGHT:'true'},fetcher);
 const otherTables=Array.isArray(after.current_schema)?after.current_schema.filter(x=>x.name!=='test_jobs'):null;
 const targetCount=after.current_schema?.filter(x=>x.type==='table'&&x.name==='test_jobs').length;
 if(after.schema!=='PASS_EMPTY'||after.row_count!==0||targetCount!==1||after.time_travel!=='BOOKMARK_READ_CONFIRMED'||JSON.stringify(otherTables)!==JSON.stringify(evidence.read_evidence.current_schema)){emit({phase:'POSTCHECK_UNCONFIRMED',remote_write_attempts:1,remote_write_confirmed:1,migration_resend_attempts:0,manual_reconciliation_required:true,postcheck:after});throw Error('post_migration_schema_unconfirmed_revoke_and_reconcile');}
 emit({phase:'POSTCHECK_PASS',remote_write_attempts:1,remote_write_confirmed:1,migration_resend_attempts:0,unknown:false,test_jobs_table_count:1,row_count:0,other_table_definitions_unchanged:true,postcheck:after});
 return {migration_executions:1,schema:'PASS_EMPTY',revoke_write_token_now:true,posting_permitted:false,live_jobs:0,deploy_executions:0};
}
