// Owner-approved fixed schema only. No stage2 row mutation, Worker, AI or posting.
import {readFileSync,existsSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {candidate,SQL_SHA,EXPECTED,stage3MigrationOnce} from './durable-stage2-contract.mjs';
import {ACCOUNT,DB,REPO,baseContext,sha,READ_SQL,CONTRACT} from './atomicity-schema-audit.mjs';
import {READ_ROW,exclusiveJournal} from './atomicity-test.mjs';
import {localStage3Checks,migrationHistory,readOnlyTransport} from './d1-stage3-final-preflight.mjs';
import {jsonBounded} from './d1-v2-migration.mjs';
export const MESSAGE='PLM execute approved stage3 schema once 20261003-r1';
export const PREFLIGHT_RECEIPT_SHA='2c3f36f52093082072d2764c9dd341b5018519f001293806204f7d67c9cc235d';
export function executionContext(e,checkout){return baseContext(e)&&e.GITHUB_EVENT_NAME==='push'&&/^\d+$/.test(e.GITHUB_RUN_ID||'')&&/^[a-f0-9]{40}$/.test(e.GITHUB_SHA||'')&&/^[a-f0-9]{40}$/.test(e.PLM_STAGE3_APPROVED_COMMIT||'')&&checkout===e.PLM_STAGE3_APPROVED_COMMIT&&e.PLM_STAGE3_EVENT_BEFORE===checkout&&e.PLM_STAGE3_MESSAGE===MESSAGE&&e.PLM_STAGE3_ALLOW==='true'&&e.PLM_STAGE3_OWNER_APPROVAL==='MIGRATE_STAGE3_FIXED_SCHEMA_ONCE'&&e.PLM_STAGE3_SQL_SHA===SQL_SHA&&e.PLM_STAGE3_PREFLIGHT_RECEIPT_SHA===PREFLIGHT_RECEIPT_SHA&&![e.PLM_CF_WORKER_API_TOKEN,e.PLM_CF_D1_ATOMICITY_TEST_TOKEN,e.PLM_CF_D1_STAGE2_TEST_TOKEN,e.PLM_CF_D1_MIGRATION_V2_TOKEN,e.PLM_CF_D1_API_TOKEN].some(Boolean);}
export function approvedReceipt(raw=readFileSync(new URL('../audit-evidence/stage3-final-preflight-success-37107515426.json',import.meta.url))){if(sha(raw)!==PREFLIGHT_RECEIPT_SHA)throw Error('STAGE3_APPROVED_PREFLIGHT_RECEIPT_DRIFT');const r=JSON.parse(raw);if(r.run_id!==37107515426||r.evidence?.pass!==true||r.evidence.sql_sha256!==SQL_SHA||r.evidence.schema_fingerprint!==CONTRACT.schema_fingerprint)throw Error('STAGE3_APPROVED_PREFLIGHT_UNCONFIRMED');return r;}
export function executionTransport(e,fetcher,counts){
 const read=readOnlyTransport(e,fetcher),target=`https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}/d1/database/${DB}/query`;
 const postSQL=new Set([READ_SQL[0],'SELECT * FROM backend_probe_v1','SELECT COUNT(*) AS n FROM test_jobs',...Object.keys(EXPECTED.columns).flatMap(t=>['PRAGMA table_info('+t+')','PRAGMA index_list('+t+')','SELECT COUNT(*) AS n FROM '+t])]);
 return async(url,o)=>{
  const auth=o?.headers?.Authorization;
  if(url===target&&o.method==='POST'&&auth===`Bearer ${e.PLM_CF_D1_STAGE3_MIGRATION_TOKEN}`){
   const p=JSON.parse(o.body);if(counts.mutation_requests!==0||p.sql!==candidate().sql||JSON.stringify(p.params)!=='[]'||Object.keys(p).sort().join(',')!=='params,sql')throw Error('STAGE3_ONE_SHOT_OR_SQL_REJECTED');
   counts.mutation_requests=1;counts.cloudflare_api_calls++;return fetcher(url,o);
  }
  if(url.startsWith('https://api.github.com/')){counts.github_history_get_calls++;return read(url,o);}
  if(url===target&&o.method==='POST'&&auth===`Bearer ${e.PLM_CF_D1_READ_TOKEN}`){const p=JSON.parse(o.body);if(postSQL.has(p.sql)&&JSON.stringify(p.params)==='[]'&&Object.keys(p).sort().join(',')==='params,sql'){counts.cloudflare_api_calls++;counts.cloudflare_read_only_calls++;return fetcher(url,o);}}
  counts.cloudflare_api_calls++;counts.cloudflare_read_only_calls++;return read(url,o);
 };
}
export async function migrationEntry(e,fetcher=fetch,{checkout,checks=localStage3Checks,journalFactory,receiptCheck=approvedReceipt}={}){
 const counts={cloudflare_api_calls:0,cloudflare_read_only_calls:0,github_history_get_calls:0,mutation_requests:0};
 const base={status:'BLOCKED',retry:0,resend:0,fallback:0,automatic_rollback:0,deploy:0,worker_invocation:0,worker_d1_access:0,live_job:0,ai_api:0,render:0,posting:0,live_ready:false,posting_permitted:false,owner_token_cleanup_required:true,token_scope_api_verified:false,token_scope_owner_evidence:true};
 const stop=code=>({...base,...counts,failure_code:code});let result;
 try{
  if(!executionContext(e,checkout))return stop('STAGE3_EXECUTION_CONTEXT_REJECTED_NO_HTTP');
  if(![e.PLM_CF_D1_STAGE3_MIGRATION_TOKEN,e.PLM_CF_D1_READ_TOKEN,e.PLM_HISTORY_GITHUB_TOKEN].every(s=>typeof s==='string'&&s.length>0&&s.length<=4096&&!/[\r\n]/.test(s)))return stop('STAGE3_CREDENTIAL_MISSING_NO_HTTP');
  checks();const approved=receiptCheck();base.approved_preflight_receipt_sha256=PREFLIGHT_RECEIPT_SHA;base.sql_sha256=SQL_SHA;base.code_commit=checkout;base.event_commit=e.GITHUB_SHA;
  const transport=executionTransport(e,fetcher,counts);
  base.history=await migrationHistory(async page=>{const r=await transport(`https://api.github.com/repos/${REPO}/actions/runs?per_page=20&page=${page}`,{method:'GET',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${e.PLM_HISTORY_GITHUB_TOKEN}`}});if(!r.ok)throw Error('STAGE3_HISTORY_HTTP_UNKNOWN');try{return await jsonBounded(r,1048576);}catch{throw Error('STAGE3_HISTORY_RESPONSE_UNKNOWN');}},{currentRun:e.GITHUB_RUN_ID});
  let factory=journalFactory;
  if(!factory){if(typeof e.RUNNER_TEMP!=='string'||!e.RUNNER_TEMP.startsWith('/'))throw Error('STAGE3_JOURNAL_PATH_REQUIRED');const dir=e.RUNNER_TEMP+'/stage3-migration-journal';if(existsSync(dir))throw Error('STAGE3_PRIOR_SENT_UNKNOWN_JOURNAL');factory=()=>{const j=exclusiveJournal(dir);return {reserve(data){j.reserve('fixed-schema',{...data,run_id:e.GITHUB_RUN_ID,code_commit:checkout,approved_receipt_sha256:PREFLIGHT_RECEIPT_SHA});console.log('STAGE3_MIGRATION_SENT '+JSON.stringify({run_id:e.GITHUB_RUN_ID,sql_sha256:SQL_SHA,mutation_budget:1}));}};};}
  const journal=factory();
  result=await stage3MigrationOnce({...e,GITHUB_SHA:checkout},transport,{historyClear:base.history.complete,journal,checkout});
  if(result.preflight?.sql_sha256&&result.preflight.sql_sha256!==approved.evidence.sql_sha256)throw Error('STAGE3_APPROVED_SQL_CHANGED');
  return {...base,...result,...counts,d1_write_requests:counts.mutation_requests,post_check_sets:counts.mutation_requests?1:0,manual_reconciliation_required:counts.mutation_requests>0&&result.status!=='SUCCESS',completed_at:new Date().toISOString()};
 }catch(err){return {...base,...result,...counts,status:counts.mutation_requests?'UNKNOWN':'BLOCKED',d1_write_requests:counts.mutation_requests,failure_code:/^STAGE3_[A-Z_]+$/.test(err.message)?err.message:'STAGE3_ENTRY_UNKNOWN_NO_RETRY',manual_reconciliation_required:counts.mutation_requests>0};}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){try{const r=await migrationEntry(process.env,fetch,{checkout:readFileSync('.git/HEAD','utf8').trim()});console.log('STAGE3_MIGRATION_RECEIPT '+JSON.stringify(r));if(r.status!=='SUCCESS')process.exitCode=1;}catch{console.error('STAGE3_MIGRATION_UNKNOWN_NO_RETRY');process.exitCode=1;}}
