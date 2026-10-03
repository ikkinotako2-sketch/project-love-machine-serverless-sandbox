// New explicit-batch candidate; CLI is verify/read-only preflight only.
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {ACCOUNT,DB,baseContext,sha} from './atomicity-schema-audit.mjs';
import {reconcileStage3,MESSAGE} from './stage3-reconcile-read-only.mjs';
import {jsonBounded} from './d1-v2-migration.mjs';
export const SQL_SHA='c2d3c40447490932df83ecf52797d493787cc2a76a4a4efbc1b0a11a633381c4',REQUEST_SHA='7a22f2ec5eed90e658f934fb6005289752470193a213b084cfb1f21700278d58',EXPECTED_SHA='2a9d432b5820f8d2bd5b0d18e54dad41d5b03369368e0b429ab067ff9c2ffb03',RECONCILIATION_SHA='cae8e4b75f5ce0d2a85c975792d775ff816389add1dd52e25fd76a5cae839305';
const raw=p=>readFileSync(new URL(p,import.meta.url));
export function recoveryCandidate({sql=raw('./migrations/0004_durable_stage2_explicit_batch.sql'),request=raw('./stage3-recovery-request.json'),expected=raw('./stage3-recovery-expected-schema.json'),receipt=raw('../audit-evidence/stage3-manual-reconciliation-37109169905.json')}={}){
 if(sha(sql)!==SQL_SHA||sha(request)!==REQUEST_SHA||sha(expected)!==EXPECTED_SHA||sha(receipt)!==RECONCILIATION_SHA)throw Error('RECOVERY_IMMUTABLE_INPUT_DRIFT');
 const body=JSON.parse(request),schema=JSON.parse(expected),proof=JSON.parse(receipt);
 if(proof.evidence?.classification!=='NOT_APPLIED'||proof.evidence?.pass!==true||Object.keys(body).join(',')!=='batch'||body.batch?.length!==9||body.batch.some(x=>!x.sql.startsWith('CREATE ')||/[\r\n]/.test(x.sql)||x.params?.length!==0)||schema.schema.length!==9)throw Error('RECOVERY_CONTRACT_REJECTED');
 return {sql_sha256:SQL_SHA,request_sha256:REQUEST_SHA,request_raw:request,body,expected:schema,mutation_http_max:1,batch_elements:9,destructive:0,existing_table_changes:0};
}
export function recoveryContext(e,write=false){return baseContext(e)&&e.GITHUB_EVENT_NAME==='push'&&/^\d+$/.test(e.GITHUB_RUN_ID||'')&&/^[a-f0-9]{40}$/.test(e.GITHUB_SHA||'')&&e.GITHUB_SHA===e.PLM_STAGE3_RECOVERY_APPROVED_COMMIT&&e.PLM_STAGE3_RECOVERY_SQL_SHA===SQL_SHA&&e.PLM_STAGE3_RECOVERY_REQUEST_SHA===REQUEST_SHA&&!e.PLM_CF_D1_STAGE3_MIGRATION_TOKEN&&!e.PLM_CF_D1_STAGE2_TEST_TOKEN&&!e.PLM_CF_WORKER_API_TOKEN&&(write?e.PLM_STAGE3_RECOVERY_ALLOW==='true'&&e.PLM_STAGE3_RECOVERY_OWNER_APPROVAL==='EXECUTE_NEW_EXPLICIT_BATCH_ONCE':e.PLM_STAGE3_RECOVERY_ALLOW==='false'&&e.PLM_STAGE3_RECOVERY_OWNER_APPROVAL==='UNAPPROVED');}
const cleanRead=e=>({...e,PLM_CF_D1_STAGE3_RECOVERY_TOKEN:undefined,PLM_RECONCILE_CODE_PIN:e.GITHUB_SHA,PLM_RECONCILE_BEFORE:e.GITHUB_SHA,PLM_RECONCILE_MESSAGE:MESSAGE});
export async function recoveryPreflight(e,fetcher=fetch,{write=false,now=Date.now()}={}){
 const out={pass:false,read_calls:0,mutation_requests:0,token_scope_api_verified:false,token_scope_owner_evidence:true};
 if(!recoveryContext(e,write)||!e.PLM_CF_D1_STAGE3_RECOVERY_TOKEN||!e.PLM_CF_D1_READ_TOKEN)return {...out,failure_code:'RECOVERY_CONTEXT_OR_CREDENTIAL_MISSING_NO_HTTP'};
 try{recoveryCandidate();out.read_calls++;const r=await fetcher(`https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}/tokens/verify`,{method:'GET',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${e.PLM_CF_D1_STAGE3_RECOVERY_TOKEN}`}});if(!r.ok)throw Error();const b=await jsonBounded(r,16384);if(b.success!==true||b.result?.status!=='active'||typeof b.result.expires_on!=='string'||!Number.isFinite(Date.parse(b.result.expires_on))||Date.parse(b.result.expires_on)<=now)throw Error();out.token_active=true;out.token_expires_at=new Date(b.result.expires_on).toISOString();const before=await reconcileStage3(cleanRead(e),fetcher);out.read_calls+=before.cloudflare_api_calls;out.before=before;if(before.classification!=='NOT_APPLIED'||!before.pass||!before.old_schema_unchanged||!before.atomicity_row_unchanged)throw Error();out.pass=true;
 }catch{out.failure_code='RECOVERY_PREFLIGHT_UNCONFIRMED_NO_RETRY';}return out;
}
export async function recoveryHistory(pageFetcher){
 const seen=new Set();let total=null,pages=0,failedKnown=false;
 for(let page=1;page<=100;page++){const b=await pageFetcher(page);pages++;if(!Number.isSafeInteger(b.total_count)||!Array.isArray(b.workflow_runs)||total!==null&&total!==b.total_count)throw Error('RECOVERY_HISTORY_UNKNOWN');total=b.total_count;if(!b.workflow_runs.length&&seen.size<total)throw Error('RECOVERY_HISTORY_INCOMPLETE');for(const r of b.workflow_runs){if(seen.has(r.id))throw Error('RECOVERY_HISTORY_DUPLICATE');seen.add(r.id);if(r.id===37108371746){if(r.run_attempt!==1||r.status!=='completed'||r.conclusion!=='failure')throw Error('OLD_RUN_CHANGED');failedKnown=true;}else if(r.path==='.github/workflows/plm-stage3-explicit-batch-recovery-once.yml'&&r.conclusion!=='skipped')throw Error('PRIOR_RECOVERY_RUN_NO_RESUME');}if(seen.size===total){if(!failedKnown)throw Error('OLD_FAILURE_HISTORY_MISSING');return {complete:true,pages,total,old_failed_run:37108371746,not_applied_receipt_sha256:RECONCILIATION_SHA};}if(seen.size>total)throw Error('RECOVERY_HISTORY_UNKNOWN');}throw Error('RECOVERY_HISTORY_LIMIT');
}
const consumed=new Set();
export async function recoveryOnce(e,fetcher,{historyClear=false,journal,checkout}={}){
 const out={status:'BLOCKED',mutation_requests:0,read_calls:0,retry:0,resend:0,fallback:0,automatic_rollback:0,deploy:0,worker_invocation:0,ai_api:0,render:0,posting:0,live_ready:false,posting_permitted:false,owner_token_cleanup_required:true};
 if(!recoveryContext(e,true)||checkout!==e.GITHUB_SHA||!historyClear||!journal||consumed.has(e.GITHUB_RUN_ID))return out;
 try{const before=await recoveryPreflight(e,fetcher,{write:true});out.read_calls+=before.read_calls;out.preflight=before;if(!before.pass)return out;const c=recoveryCandidate();journal.reserve({status:'SENT',request_sha256:REQUEST_SHA,old_run:37108371746,new_request:true});consumed.add(e.GITHUB_RUN_ID);out.status='UNKNOWN';out.mutation_requests=1;
  try{const r=await fetcher(`https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}/d1/database/${DB}/query`,{method:'POST',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${e.PLM_CF_D1_STAGE3_RECOVERY_TOKEN}`,'Content-Type':'application/json'},body:c.request_raw.toString('utf8')});out.http_status=r.status;const b=await jsonBounded(r);if(r.ok&&b.success===true&&b.result?.length===9&&b.result.every(q=>q.success===true))out.status='ACK_NEEDS_POST';}catch{}
  const post=await reconcileStage3(cleanRead(e),fetcher,{expected:c.expected});out.read_calls+=post.cloudflare_api_calls;out.post=post;out.post_sets=1;out.status=out.status==='ACK_NEEDS_POST'&&post.classification==='FULL_APPLIED'&&post.pass?'SUCCESS':'UNKNOWN';out.manual_reconciliation_required=out.status!=='SUCCESS';return out;
 }catch{return {...out,status:out.mutation_requests?'UNKNOWN':'BLOCKED',failure_code:'RECOVERY_UNKNOWN_NO_RESEND'};}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){const r=await recoveryPreflight(process.env);console.log('STAGE3_RECOVERY_READ_ONLY_PREFLIGHT '+JSON.stringify(r));if(!r.pass)process.exitCode=1;}
