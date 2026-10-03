import {readFileSync,readdirSync,existsSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {ACCOUNT,DB,REPO,baseContext,sha} from './atomicity-schema-audit.mjs';
import {candidate,importOnce,uploadURL,SQL_SHA,PLAN_SHA} from './stage3-file-import-contract.mjs';
import {importPreflight,readOnlyTransport,MESSAGE as PREFLIGHT_MESSAGE} from './stage3-import-final-preflight.mjs';
import {reconcileStage3,MESSAGE as RECONCILE_MESSAGE} from './stage3-reconcile-read-only.mjs';
import {recoveryCandidate} from './stage3-recovery-contract.mjs';
import {exclusiveJournal} from './atomicity-test.mjs';
import {jsonBounded} from './d1-v2-migration.mjs';
export const MESSAGE='PLM execute approved fixed file import once 20261003-r1';
export const RECEIPT_SHA='3752f35cb2996dd2e7676fbabc7ca1aa8cd042bb8c5d7857e9260d0b6f98b0ef';
const WORKFLOW='.github/workflows/plm-stage3-file-import-approved-once.yml';
export function localChecks(){
 candidate();const raw=readFileSync(new URL('../audit-evidence/stage3-import-read-only-preflight-37120908659.json',import.meta.url));
 if(sha(raw)!==RECEIPT_SHA)throw Error('IMPORT_APPROVED_RECEIPT_DRIFT');
 const r=JSON.parse(raw);if(r.run_id!==37120908659||r.result.pass!==true||r.result.sql_sha256!==SQL_SHA||r.result.plan_sha256!==PLAN_SHA||r.result.before.classification!=='NOT_APPLIED')throw Error('IMPORT_APPROVED_RECEIPT_INVALID');
 recoveryCandidate();if(readdirSync(new URL('../audit-evidence/',import.meta.url)).some(n=>/^stage3-import-(sent|unknown|success|failure|timeout)-receipt/.test(n)))throw Error('IMPORT_PRIOR_SENT_NO_RESUME');return true;
}
export async function executionHistory(e,f){let total,seen=0,pages=0;const ids=new Set();
 for(let page=1;page<=100;page++){pages++;const r=await f(`https://api.github.com/repos/${REPO}/actions/runs?per_page=20&page=${page}`,{method:'GET',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${e.PLM_HISTORY_GITHUB_TOKEN}`,Accept:'application/vnd.github+json'}});if(!r.ok)throw Error('IMPORT_EXEC_HISTORY_HTTP_UNKNOWN');const b=await jsonBounded(r,1048576);if(!Number.isSafeInteger(b.total_count)||!Array.isArray(b.workflow_runs))throw Error('IMPORT_EXEC_HISTORY_UNKNOWN');if(total===undefined)total=b.total_count;if(total!==b.total_count)throw Error('IMPORT_EXEC_HISTORY_CHANGED');for(const x of b.workflow_runs){if(ids.has(x.id))throw Error('IMPORT_EXEC_HISTORY_DUPLICATE');ids.add(x.id);seen++;if(x.path===WORKFLOW&&String(x.id)!==e.GITHUB_RUN_ID&&(x.status!=='completed'||x.conclusion!=='skipped'||x.run_attempt!==1))throw Error('IMPORT_EXEC_PRIOR_RUN_NO_RESUME');}if(seen===total)return {complete:true,total,pages};if(!b.workflow_runs.length||seen>total)throw Error('IMPORT_EXEC_HISTORY_INCOMPLETE');}throw Error('IMPORT_EXEC_HISTORY_INCOMPLETE');
}
export function executionTransport(e,f,counts){
 const read=readOnlyTransport(e,f),target=`https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}/d1/database/${DB}`,c=candidate(),postReads=new Set(Object.keys(recoveryCandidate().expected.columns).flatMap(t=>['PRAGMA table_info('+t+')','PRAGMA index_list('+t+')','SELECT COUNT(*) AS n FROM '+t]));const sent=new Set();
 return async(u,o)=>{
  if(u===target+'/import'&&o.method==='POST'&&o.headers?.Authorization===`Bearer ${e.PLM_CF_D1_STAGE3_IMPORT_TOKEN}`){const b=JSON.parse(o.body),a=b.action;if(o.redirect!=='error'||!['init','ingest','poll'].includes(a))throw Error('IMPORT_TRANSPORT_REJECTED');if(a==='poll'){if(counts.poll>=3||Object.keys(b).sort().join(',')!=='action,current_bookmark'||!/^[a-f0-9-]{16,128}$/.test(b.current_bookmark))throw Error('IMPORT_POLL_REJECTED');counts.poll++;}else{if(sent.has(a)||counts.side_effect>=3||b.etag!==c.plan.sql_md5||Object.keys(b).sort().join(',')!==(a==='init'?'action,etag':'action,etag,filename')||(a==='ingest'&&(!sent.has('upload')||typeof b.filename!=='string')))throw Error('IMPORT_SIDE_EFFECT_REJECTED');sent.add(a);counts.side_effect++;}counts.import_http++;return f(u,o);}
  if(o.method==='PUT'){if(!sent.has('init')||sent.has('upload')||counts.side_effect>=3||o.headers?.Authorization||o.redirect!=='error'||!Buffer.isBuffer(o.body)||!o.body.equals(c.sql)||uploadURL(u)!==u)throw Error('IMPORT_UPLOAD_REJECTED');sent.add('upload');counts.side_effect++;counts.import_http++;return f(u,o);}
  if(u===target+'/query'&&o.method==='POST'&&o.headers?.Authorization===`Bearer ${e.PLM_CF_D1_READ_TOKEN}`){const b=JSON.parse(o.body);if(Object.keys(b).sort().join(',')==='params,sql'&&b.params?.length===0&&postReads.has(b.sql)){counts.read_only++;return f(u,o);}}
  counts.read_only++;return read(u,o);
 };
}
export async function executionEntry(e,f=fetch,{checkout,checks=localChecks,journalFactory,preflight=importPreflight,postAudit=reconcileStage3}={}){
 const counts={read_only:0,side_effect:0,poll:0,import_http:0},out={status:'BLOCKED',query_mutations:0,retry:0,resend:0,fallback:0,automatic_rollback:0,worker:0,ai:0,render:0,posting:0,post_sets:0,owner_token_cleanup_required:true,live_ready:false,posting_permitted:false};
 try{
 if(!baseContext(e)||e.GITHUB_EVENT_NAME!=='push'||!/^[a-f0-9]{40}$/.test(checkout||'')||checkout!==e.PLM_IMPORT_EXEC_CODE_PIN||e.PLM_IMPORT_EXEC_BEFORE!==checkout||e.PLM_IMPORT_EXEC_MESSAGE!==MESSAGE||e.PLM_STAGE3_IMPORT_ALLOW!=='true'||e.PLM_STAGE3_IMPORT_OWNER_APPROVAL!=='APPROVE_NEW_FILE_IMPORT_ONCE'||e.PLM_IMPORT_SQL_SHA!==SQL_SHA||e.PLM_IMPORT_PLAN_SHA!==PLAN_SHA||e.PLM_IMPORT_RECEIPT_SHA!==RECEIPT_SHA||!/^\d+$/.test(e.GITHUB_RUN_ID||'')||['PLM_CF_D1_STAGE3_RECOVERY_TOKEN','PLM_CF_D1_STAGE3_MIGRATION_TOKEN','PLM_CF_D1_STAGE2_TEST_TOKEN','PLM_CF_WORKER_API_TOKEN'].some(k=>e[k]))throw Error('IMPORT_EXEC_CONTEXT_REJECTED');
 if(![e.PLM_CF_D1_READ_TOKEN,e.PLM_CF_D1_STAGE3_IMPORT_TOKEN,e.PLM_HISTORY_GITHUB_TOKEN].every(x=>typeof x==='string'&&x.length>0&&x.length<=4096&&!/[\r\n]/.test(x)))throw Error('IMPORT_EXEC_CREDENTIAL_MISSING');checks();out.history=await executionHistory(e,f);
 const preEnv={...e,PLM_IMPORT_PREFLIGHT_CODE_PIN:checkout,PLM_IMPORT_EVENT_BEFORE:checkout,PLM_IMPORT_EVENT_MESSAGE:PREFLIGHT_MESSAGE,PLM_STAGE3_IMPORT_ALLOW:'false',PLM_STAGE3_IMPORT_OWNER_APPROVAL:'UNAPPROVED'};
 out.preflight=await preflight(preEnv,f,{checkout});counts.read_only=out.preflight.cloudflare_read_only_api_calls||0;if(!out.preflight.pass)throw Error('IMPORT_EXEC_FRESH_PREFLIGHT_UNCONFIRMED');
 let j;if(journalFactory)j=journalFactory();else{if(!e.RUNNER_TEMP?.startsWith('/'))throw Error('IMPORT_EXEC_JOURNAL_PATH_REQUIRED');const path=e.RUNNER_TEMP+'/stage3-file-import-once';if(existsSync(path))throw Error('IMPORT_EXEC_PRIOR_JOURNAL');const disk=exclusiveJournal(path);j={reserve(action,data){disk.reserve(action,{...data,run_id:e.GITHUB_RUN_ID,code_commit:checkout});console.log('STAGE3_IMPORT_SENT '+JSON.stringify({action,run_id:e.GITHUB_RUN_ID,sql_sha256:SQL_SHA,plan_sha256:PLAN_SHA,status:'SENT'}));}};}
 const ce={...e,GITHUB_SHA:checkout,PLM_STAGE3_IMPORT_APPROVED_COMMIT:checkout},transport=executionTransport(ce,f,counts);
 const r=await importOnce(ce,transport,{freshAuditApproved:true,historyClear:true,journal:j,postRead:async()=>{const clean={...ce,PLM_CF_D1_STAGE3_IMPORT_TOKEN:undefined,PLM_RECONCILE_CODE_PIN:checkout,PLM_RECONCILE_BEFORE:checkout,PLM_RECONCILE_MESSAGE:RECONCILE_MESSAGE};const p=await postAudit(clean,transport,{expected:recoveryCandidate().expected});p.kv_content_status='NOT_APPLICABLE_RESERVED_UNQUERYABLE';return p;}});
 Object.assign(out,r);out.classification=r.post?.classification||'STILL_UNKNOWN';if(out.status==='SUCCESS'&&(!r.post.kv_schema_unchanged||!r.post.bookmark||Object.values(r.post.stage3_table_details||{}).flatMap(x=>x.indexes).length!==8))out.status='UNKNOWN';
 }catch(err){out.failure_code=/^[A-Z_]+$/.test(err.message)?err.message:'IMPORT_EXEC_UNKNOWN_NO_RETRY';out.status=counts.side_effect?'UNKNOWN':'BLOCKED';}
 return {...out,transport_counts:counts,code_commit:checkout,event_commit:e.GITHUB_SHA,sql_sha256:SQL_SHA,plan_sha256:PLAN_SHA,completed_at:new Date().toISOString()};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){const r=await executionEntry(process.env,fetch,{checkout:readFileSync('.git/HEAD','utf8').trim()});console.log('STAGE3_IMPORT_EXECUTION_RECEIPT '+JSON.stringify(r));if(r.status!=='SUCCESS')process.exitCode=1;}
