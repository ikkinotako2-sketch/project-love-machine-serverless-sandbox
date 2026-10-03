// Verify-only import credential; exact Read Token audit. No import execution entry.
import {readFileSync,readdirSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {ACCOUNT,DB,REPO,baseContext} from './atomicity-schema-audit.mjs';
import {candidate,SQL_SHA,PLAN_SHA} from './stage3-file-import-contract.mjs';
import {reconcileStage3,MESSAGE as RECONCILE_MESSAGE} from './stage3-reconcile-read-only.mjs';
import {jsonBounded} from './d1-v2-migration.mjs';
export const MESSAGE='PLM stage3 import verify read-only once 20261003-r1';
const base=`https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}`,target=base+'/d1/database/'+DB;
const READS=new Set(["SELECT type, name, tbl_name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name",'PRAGMA table_info(test_jobs)','PRAGMA table_info(backend_probe_v1)','PRAGMA index_list(backend_probe_v1)','SELECT * FROM backend_probe_v1','SELECT COUNT(*) AS n FROM test_jobs','SELECT COUNT(*) AS n FROM _cf_KV']);
export function localChecks(){
 const c=candidate(),p=c.plan;
 const w=readFileSync(new URL('../.github/workflows/plm-stage3-file-import-once.yml',import.meta.url),'utf8');
 if(!w.includes('if: false')||!w.includes("PLM_STAGE3_IMPORT_ALLOW: 'false'")||!w.includes('PLM_STAGE3_IMPORT_OWNER_APPROVAL: UNAPPROVED'))throw Error('IMPORT_WORKFLOW_ENABLED');
 if(readdirSync(new URL('../audit-evidence/',import.meta.url)).some(n=>/^stage3-import-(sent|unknown|success|failure|timeout)/.test(n)))throw Error('IMPORT_PRIOR_SEND_STOP');
 if(p.top_level_create!==9||p.tables!==3||p.triggers!==6||p.destructive!==0||p.existing_table_changes!==0||p.import_http_total_max!==6||p.init_max!==1||p.upload_max!==1||p.ingest_max!==1||p.sql_query_mutation_max!==0||['retry','resend','fallback','automatic_rollback'].some(k=>p[k]!==0)||p.workflow_hard_disabled!==true||p.owner_execution_approval!==false)throw Error('IMPORT_BUDGET_OR_APPROVAL_DRIFT');
 return true;
}
export function readOnlyTransport(e,fetcher){return async(url,o)=>{
 let valid=false;const auth=o.headers?.Authorization;
 if(url===base+'/tokens/verify')valid=o.method==='GET'&&!o.body&&auth===`Bearer ${e.PLM_CF_D1_STAGE3_IMPORT_TOKEN}`;
 else if(auth===`Bearer ${e.PLM_CF_D1_READ_TOKEN}`){
  if(o.method==='GET'&&!o.body)valid=url==='https://api.cloudflare.com/client/v4/user/tokens/verify'||new RegExp('^'+base+'/d1/database\\?page=[1-9][0-9]*&per_page=100$').test(url)||url===target||url===target+'/time_travel/bookmark';
  else if(o.method==='POST'&&url===target+'/query'){const b=JSON.parse(o.body);valid=Object.keys(b).sort().join(',')==='params,sql'&&Array.isArray(b.params)&&b.params.length===0&&READS.has(b.sql);}
 }
 if(!valid)throw Error('IMPORT_PREFLIGHT_READ_ONLY_TRANSPORT_REJECTED');return fetcher(url,o);
};}
export async function importPreflight(e,fetcher=fetch,{checkout,checks=localChecks,now=Date.now()}={}){
 const out={pass:false,audit_pass:false,cloudflare_read_only_api_calls:0,github_history_get_calls:0,d1_mutation:0,d1_write:0,worker_deploy:0,worker_invocation:0,ai_api:0,render:0,posting:0,retry:0,resend:0,fallback:0,automatic_rollback:0,live_ready:false,posting_permitted:false};
 const pin=e.PLM_IMPORT_PREFLIGHT_CODE_PIN;
 if(!baseContext(e)||e.GITHUB_EVENT_NAME!=='push'||!/^\d+$/.test(e.GITHUB_RUN_ID||'')||!/^[a-f0-9]{40}$/.test(pin||'')||checkout!==pin||e.PLM_IMPORT_EVENT_BEFORE!==pin||e.PLM_IMPORT_EVENT_MESSAGE!==MESSAGE||e.PLM_STAGE3_IMPORT_ALLOW!=='false'||e.PLM_STAGE3_IMPORT_OWNER_APPROVAL!=='UNAPPROVED'||!e.PLM_CF_D1_STAGE3_IMPORT_TOKEN||!e.PLM_CF_D1_READ_TOKEN||!e.PLM_HISTORY_GITHUB_TOKEN||['PLM_CF_D1_STAGE3_RECOVERY_TOKEN','PLM_CF_D1_STAGE3_MIGRATION_TOKEN','PLM_CF_D1_STAGE2_TEST_TOKEN','PLM_CF_WORKER_API_TOKEN'].some(k=>e[k]))return {...out,failure_code:'IMPORT_PREFLIGHT_CONTEXT_REJECTED_NO_HTTP'};
 try{
  checks();out.github_history_get_calls++;
  const hr=await fetcher(`https://api.github.com/repos/${REPO}/actions/workflows/plm-stage3-file-import-once.yml/runs?per_page=20&page=1`,{method:'GET',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${e.PLM_HISTORY_GITHUB_TOKEN}`,Accept:'application/vnd.github+json'}});
  if(!hr.ok)throw Error('IMPORT_HISTORY_HTTP_REJECTED');const h=await jsonBounded(hr,1048576);
  if(!Number.isSafeInteger(h.total_count)||!Array.isArray(h.workflow_runs)||h.total_count!==h.workflow_runs.length||h.workflow_runs.some(r=>r.path!=='.github/workflows/plm-stage3-file-import-once.yml'||r.conclusion!=='skipped'||r.status!=='completed'||r.run_attempt!==1))throw Error('IMPORT_HISTORY_UNKNOWN_OR_PRIOR_SEND');out.history={complete:true,total:h.total_count,all_skipped:true};
  const f=readOnlyTransport(e,async(url,o)=>{out.cloudflare_read_only_api_calls++;return fetcher(url,o);});
  const vr=await f(base+'/tokens/verify',{method:'GET',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${e.PLM_CF_D1_STAGE3_IMPORT_TOKEN}`}});
  if(!vr.ok)throw Error('IMPORT_TOKEN_VERIFY_REJECTED');const v=await jsonBounded(vr,16384),exp=Date.parse(v.result?.expires_on);
  if(v.success!==true||v.result?.status!=='active'||!Number.isFinite(exp)||exp<=now)throw Error('IMPORT_TOKEN_INACTIVE_OR_NO_FINITE_EXPIRY');out.token_active=true;out.token_expires_at=new Date(exp).toISOString();out.token_scope_api_verified=false;out.token_registration_owner_evidence=true;
  const ce={...e,PLM_CF_D1_STAGE3_IMPORT_TOKEN:undefined,PLM_RECONCILE_CODE_PIN:pin,PLM_RECONCILE_BEFORE:pin,PLM_RECONCILE_MESSAGE:RECONCILE_MESSAGE};
  out.before=await reconcileStage3(ce,f);
  if(!out.before.pass||out.before.classification!=='NOT_APPLIED'||!out.before.size_unchanged||!out.before.old_schema_unchanged||!out.before.old_columns_indexes_unchanged||!out.before.atomicity_row_unchanged||!out.before.test_jobs_unchanged||!out.before.kv_schema_unchanged||out.before.objects.length!==9||out.before.objects.some(x=>x.exists))throw Error('IMPORT_FRESH_AUDIT_UNCONFIRMED');
  // Count only: no provider KV keys/values are exposed. Historical contents had no baseline.
  const kr=await f(target+'/query',{method:'POST',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${e.PLM_CF_D1_READ_TOKEN}`,'Content-Type':'application/json'},body:JSON.stringify({sql:'SELECT COUNT(*) AS n FROM _cf_KV',params:[]})});
  if(!kr.ok)throw Error('IMPORT_KV_READ_UNCONFIRMED');const kb=await jsonBounded(kr,16384),q=kb.result?.[0];
  if(kb.success!==true||kb.result?.length!==1||q?.success!==true||q.meta?.served_by_primary!==true||q.meta?.rows_written>0||q.meta?.changed_db===true||q.results?.length!==1||!Number.isSafeInteger(q.results[0].n)||q.results[0].n<0)throw Error('IMPORT_KV_READ_UNCONFIRMED');
  out.kv_current_row_count=q.results[0].n;out.kv_content_unchanged='UNVERIFIED_NO_HISTORICAL_CONTENT_BASELINE';
  const c=candidate();out.sql_sha256=SQL_SHA;out.plan_sha256=PLAN_SHA;out.flow=['init','upload','ingest','status_poll'];out.side_effect_http_max=c.plan.side_effect_http_max;out.poll_max=c.plan.poll_read_post_max;out.query_mutation_max=0;out.diagnostics='ERROR_CODES_AND_SAFE_BOUNDED_MESSAGES_ONLY';out.migration_workflow_hard_disabled=true;out.owner_execution_approval=false;out.expected_post_schema={tables:3,triggers:6,column_counts:[16,11,9],autoindexes:8,new_rows:0};out.audit_pass=true;
  // Requested all-PASS includes unchanged KV contents. Do not infer that from unchanged schema.
  out.failure_code='KV_HISTORICAL_CONTENT_BASELINE_MISSING';out.next_gate='STOP_NO_EXECUTION_APPROVAL_REQUEST';
 }catch(err){out.failure_code=/^[A-Z_]+$/.test(err.message)?err.message:'IMPORT_PREFLIGHT_UNKNOWN_NO_RETRY';}return out;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){const r=await importPreflight(process.env,fetch,{checkout:readFileSync('.git/HEAD','utf8').trim()});console.log('STAGE3_IMPORT_FINAL_PREFLIGHT '+JSON.stringify(r));if(!r.pass)process.exitCode=1;}
