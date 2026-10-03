// Prepared only. Production entry is denied without a separate exact commit approval.
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {editorPreflight,WORKER} from './worker-editor-preflight.mjs';
import {ACCOUNT,BRANCH} from './read-only-diagnostic.mjs';
import {CODE_SHA,validateStoppedDeploy,rollbackReadiness} from './stopped-deploy-contract.mjs';
import {readBoundedContent,parseWorkerContent} from './worker-content-parser.mjs';
export const RECEIPT_SHA='84ab929bcb389ff8d75c36832bc039c07fb763145b0a4786bc48a0eb87b00538';
const root=`https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}`;
const base=root+`/workers/scripts/${WORKER}`;
const hash=x=>createHash('sha256').update(x).digest('hex');
const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const UUID=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const consumed=new Set();
export function candidate(){
 const config=JSON.parse(readFileSync(new URL('./wrangler.stopped.json',import.meta.url)));
 const policy=JSON.parse(readFileSync(new URL('./stopped-deploy-plan.json',import.meta.url)));
 const code=readFileSync(new URL('./bootstrap-placeholder.mjs',import.meta.url));
 const validation=validateStoppedDeploy(config,policy,code.toString('utf8'));
 const raw=readFileSync(new URL('../readiness/WORKER_STOPPED_ROLLBACK_BASE_37088180262.json',import.meta.url));
 if(hash(raw)!==RECEIPT_SHA)throw Error('ROLLBACK_RECEIPT_HASH_MISMATCH');
 const receipt=JSON.parse(raw);
 if(rollbackReadiness(receipt.snapshot).status!=='DESIGN PASS'||receipt.owner_acceptance?.replacement_policy_approved!==true||receipt.owner_acceptance.deploy_approved!==false)throw Error('ROLLBACK_BASE_REJECTED');
 const metadata={main_module:'bootstrap-placeholder.mjs',compatibility_date:config.compatibility_date,bindings:[{type:'d1',name:'DB',id:config.d1_databases[0].database_id},...Object.entries(config.vars).map(([name,text])=>({type:'plain_text',name,text}))],keep_bindings:[],keep_assets:false,logpush:false,tail_consumers:[]};
 return {config,validation,receipt,metadata,code};
}
export function checkBase(snapshot,receipt){
 if(rollbackReadiness(snapshot).status!=='DESIGN PASS')throw Error('BASE_SNAPSHOT_INCOMPLETE');
 // Entire sanitized base is checked. A timestamp alone is permitted to change.
 const clean=x=>Object.fromEntries(Object.entries(x).filter(([k])=>k!=='checked_at'));
 if(!same(clean(snapshot),clean(receipt.snapshot)))throw Error('BASE_CHANGED_NO_WRITE');
}
export function executionContextApproved(env){
 return typeof env.PLM_CF_WORKER_API_TOKEN==='string'&&!!env.PLM_CF_WORKER_API_TOKEN&&!/[\r\n]/.test(env.PLM_CF_WORKER_API_TOKEN)&&env.PLM_STOPPED_DEPLOY_ALLOW==='true'&&env.PLM_STOPPED_DEPLOY_OWNER_APPROVAL==='DEPLOY_CANONICAL_STOPPED_ONCE'&&env.GITHUB_SHA===env.PLM_STOPPED_DEPLOY_APPROVED_COMMIT&&/^[a-f0-9]{40}$/.test(env.GITHUB_SHA||'')&&env.GITHUB_RUN_ATTEMPT==='1'&&env.GITHUB_EVENT_NAME==='push'&&env.GITHUB_REPOSITORY==='ikkinotako2-sketch/project-love-machine-serverless-sandbox'&&env.GITHUB_REF===`refs/heads/${BRANCH}`&&env.PLM_CF_WORKER_TOKEN_KIND==='account'&&env.CLOUDFLARE_ACCOUNT_ID===ACCOUNT&&/^\d+$/.test(env.GITHUB_RUN_ID||'')&&['TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP'].every(k=>env[k]==='true');
}
function active(d){const a=d?.deployments?.[0];if(!UUID.test(a?.id||'')||a.versions?.length!==1||a.versions[0].percentage!==100||!UUID.test(a.versions[0].version_id||''))throw Error('DEPLOYMENT_NOT_SINGLE_100');return a;}
export function checkPost(s,c){
 const expected=[{type:'d1',name:'DB',id:c.config.d1_databases[0].database_id},...Object.entries(c.config.vars).map(([name,text])=>({type:'plain_text',name,text}))];
 const sort=x=>[...x].sort((a,b)=>a.name.localeCompare(b.name));
 if(s.deployment_id===c.receipt.snapshot.deployment_id||s.version_id===c.receipt.snapshot.version_id||!UUID.test(s.deployment_id)||!UUID.test(s.version_id)||s.stable!==true)throw Error('NEW_STABLE_VERSION_UNCONFIRMED');
 if(s.inventory.module_count!==1||s.inventory.main_module_name!=='bootstrap-placeholder.mjs'||s.inventory.main_module_sha256!==CODE_SHA)throw Error('POST_CODE_MISMATCH');
 if(!same(sort(s.bindings),sort(expected))||!same(s.handlers,['fetch'])||s.compatibility_date!==c.config.compatibility_date||s.workers_dev!==false||s.preview_urls!==false||s.secrets.length!==0||s.cron.length!==0)throw Error('POST_SETTINGS_MISMATCH');
 return {status:'PASS',worker_invoked:false,db_queried:false,routes:'OWNER CONFIRMED NONE; NOT API VERIFIED',custom_domains:'OWNER CONFIRMED NONE; NOT API VERIFIED'};
}
export async function postReadback(env,fetcher,c,counts){
 const allowed=new Set([base+'/settings',base+'/deployments',base+'/subdomain',base+'/schedules',base+'/secrets',base+'/content/v2']);
 async function get(url,raw=false){
  if(!allowed.has(url))throw Error('READ_ENDPOINT_REJECTED');counts.get++;
  const r=await fetcher(url,{method:'GET',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${env.PLM_CF_WORKER_API_TOKEN}`}});
  if(!r.ok)throw Error('POST_HTTP_'+r.status);
  const bytes=await readBoundedContent(r,{});
  if(raw)return parseWorkerContent(bytes,r.headers,{});
  const d=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));if(d.success!==true)throw Error('POST_RESPONSE_REJECTED');return d.result;
 }
 await get(base+'/settings');
 const start=active(await get(base+'/deployments'));
 const url=base+'/versions/'+start.versions[0].version_id;allowed.add(url);
 const v=await get(url);if(v.id!==start.versions[0].version_id)throw Error('POST_VERSION_ID_MISMATCH');
 const b=v.resources?.bindings;if(!Array.isArray(b)||b.length>8)throw Error('POST_BINDINGS_REJECTED');
 const bindings=b.map(x=>{
  if(x.type==='d1'&&x.name==='DB'&&x.id===c.config.d1_databases[0].database_id)return {type:x.type,name:x.name,id:x.id};
  if(x.type==='plain_text'&&Object.hasOwn(c.config.vars,x.name)&&x.text==='true')return {type:x.type,name:x.name,text:'true'};
  throw Error('POST_UNEXPECTED_BINDING'); // Never expose arbitrary text / secret values.
 });
 const sub=await get(base+'/subdomain'),cron=await get(base+'/schedules'),secrets=await get(base+'/secrets');
 if(!Array.isArray(cron?.schedules)||!Array.isArray(secrets)||secrets.some(x=>!/^[_A-Za-z][_A-Za-z0-9]{0,127}$/.test(x.name||'')))throw Error('POST_METADATA_REJECTED');
 const inventory=await get(base+'/content/v2',true),end=active(await get(base+'/deployments'));
 const out={deployment_id:start.id,version_id:v.id,stable:start.id===end.id&&v.id===end.versions[0].version_id,inventory,bindings,workers_dev:sub.enabled,preview_urls:sub.previews_enabled,secrets:secrets.map(x=>x.name),cron:cron.schedules.length===0?[]:['NONEMPTY_REDACTED'],handlers:v.resources?.script?.handlers,compatibility_date:v.resources?.script_runtime?.compatibility_date};
 const check=checkPost(out,c);return {snapshot:out,check};
}
export async function deployOnce(env,{fetcher,preflight=editorPreflight,consumeIntent}={}){
 const out={get:0,mutation_attempts:0,deploy_attempts:0,retries:0,fallbacks:0,live_jobs:0,render_executions:0,db_queries:0,worker_invocations:0,live_ready:false,posting_permitted:false,automatic_rollback:false,token_revocation_required:true};
 // No default transport: caller must explicitly wire the permitted production entry.
 if(typeof fetcher!=='function'||typeof consumeIntent!=='function'||!executionContextApproved(env))return {...out,status:'BLOCKED',failure_code:'DEPLOY_NOT_OWNER_APPROVED_NO_HTTP'};
 if(consumed.has(RECEIPT_SHA))return {...out,status:'BLOCKED',failure_code:'DEPLOY_ALREADY_CONSUMED'};
 const c=candidate();
 try{
  const p=await preflight({...env,PLM_WORKER_PREFLIGHT_APPROVED_COMMIT:env.GITHUB_SHA},fetcher);out.get+=p.external_api_calls;
  if(!p.snapshot_acquired||p.token_active!==true)throw Error('PREDEPLOY_READ_FAILED');
  checkBase(p.snapshot,c.receipt);
  // Persist before sending, even if an exception/cancellation subsequently occurs.
  await consumeIntent({operation:'STOPPED_DEPLOY_ONCE',receipt_sha:RECEIPT_SHA,commit:env.GITHUB_SHA,run_id:env.GITHUB_RUN_ID});consumed.add(RECEIPT_SHA);
  const form=new FormData();form.set('metadata',new Blob([JSON.stringify(c.metadata)],{type:'application/json'}),'metadata.json');form.set('bootstrap-placeholder.mjs',new Blob([c.code],{type:'application/javascript+module'}),'bootstrap-placeholder.mjs');
  out.mutation_attempts=1;out.deploy_attempts=1;
  let acknowledged=false;
  try{
   const r=await fetcher(base,{method:'PUT',redirect:'error',signal:AbortSignal.timeout(30000),headers:{Authorization:`Bearer ${env.PLM_CF_WORKER_API_TOKEN}`},body:form});
   if(r.ok){const d=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(await readBoundedContent(r,{})));acknowledged=d.success===true;}
   else out.write_http_status=r.status;
  }catch{out.write_response_unknown=true;}
  // Always attempt a single GET-only reconciliation; never resend PUT.
  try{out.post=await postReadback(env,fetcher,c,out);}catch{out.post={check:{status:'UNVERIFIED'}};}
  out.status=acknowledged&&out.post.check.status==='PASS'?'PASS':'MANUAL_RECONCILIATION_REQUIRED';
  if(out.status!=='PASS')out.failure_code='WRITE_OR_POSTCHECK_UNCONFIRMED_NO_RESEND';
 }catch{out.status=out.mutation_attempts?'MANUAL_RECONCILIATION_REQUIRED':'BLOCKED';out.failure_code=out.mutation_attempts?'AFTER_INTENT_NO_RESEND':'PREDEPLOY_GATE_FAILED_NO_WRITE';}
 return out;
}
// GitHub run history is the conservative cross-run fence. Every previous executed
// deployment run consumes this operation, including failure/cancellation/unknown.
export async function assertUnusedWorkflow(env,fetcher){
 const prefix=`https://api.github.com/repos/${env.GITHUB_REPOSITORY}/actions/workflows/plm-stopped-worker-deploy-once.yml/runs?per_page=100&page=`;
 let currentConfirmed=false;
 for(let page=1;page<=100;page++){
  const r=await fetcher(prefix+page,{method:'GET',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${env.GITHUB_TOKEN}`,'X-GitHub-Api-Version':'2022-11-28'}});
  if(!r.ok)throw Error('RUN_HISTORY_UNCONFIRMED');const data=await r.json();
  if(!Array.isArray(data.workflow_runs)||!Number.isSafeInteger(data.total_count))throw Error('RUN_HISTORY_INVALID');
  const current=data.workflow_runs.find(x=>String(x.id)===env.GITHUB_RUN_ID);
  if(current){if(current.head_sha!==env.GITHUB_SHA||current.run_attempt!==1||current.event!=='push')throw Error('CURRENT_RUN_IDENTITY_UNCONFIRMED');currentConfirmed=true;}
  if(data.workflow_runs.some(x=>String(x.id)!==env.GITHUB_RUN_ID&&x.conclusion!=='skipped'))throw Error('PREVIOUS_DEPLOY_RUN_CONSUMED');
  if(page*100>=data.total_count){if(!currentConfirmed)throw Error('CURRENT_RUN_MISSING_NO_WRITE');return;}
 }
 throw Error('RUN_HISTORY_PAGINATION_UNCONFIRMED');
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 try{
  // Permission checks are repeated in deployOnce; history is not called until approved.
  if(!executionContextApproved(process.env))throw Error('NOT_APPROVED');
  const authorization=JSON.parse(readFileSync('readiness/STOPPED_DEPLOY_EXECUTION_AUTHORIZATION.json','utf8'));
  if(authorization.deploy_approved!==true||authorization.rollback_receipt_sha256!==RECEIPT_SHA||authorization.code_sha256!==CODE_SHA||authorization.config_sha256!=='cefa60606ca3e3820116a56671d83125ea86ac6e3a5e771761dd2e3508c96cf5'||authorization.max_deploy_attempts!==1)throw Error('EXECUTION_AUTHORIZATION_REQUIRED');
  await assertUnusedWorkflow(process.env,fetch);
  const r=await deployOnce(process.env,{fetcher:fetch,consumeIntent:async x=>writeFileSync('stopped-deploy-intent.json',JSON.stringify(x),{flag:'wx',mode:0o600})});
  writeFileSync('stopped-deploy-receipt.json',JSON.stringify(r,null,2)+'\n',{flag:'wx',mode:0o600});
  console.log('STOPPED_DEPLOY_EVIDENCE '+JSON.stringify(r));if(r.status!=='PASS')process.exitCode=1;
 }catch{console.error('STOPPED_DEPLOY_BLOCKED_NO_AUTOMATIC_RETRY');process.exitCode=1;}
}
