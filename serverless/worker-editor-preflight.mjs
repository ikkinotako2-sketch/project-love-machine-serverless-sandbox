// Offline-repaired parser. A future read requires separate owner approval and a new exact pin.
// Exact approved push SHA only. No deploy/mutation/DB/dispatch; no retries or fallback.
import {ContentError,readBoundedContent,parseWorkerContent} from './worker-content-parser.mjs';
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {ACCOUNT,BRANCH} from './read-only-diagnostic.mjs';
import {CODE_SHA,validateStoppedDeploy,rollbackReadiness} from './stopped-deploy-contract.mjs';
export const WORKER='plm-serverless-sandbox-control';
const UUID=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const used=new Set();
export async function editorPreflight(env,fetcher=fetch){
 const out={mode:'EDITOR_READ_ONLY_PREFLIGHT',remote_mutations:0,deploy_executions:0,live_jobs:0,render_executions:0,external_api_calls:0,deploy_permitted:false,live_ready:false,posting_permitted:false,token_owner:'account',token_scope_api_verified:false,other_worker_access_api_verified:false,probes:[]};
 if(env.GITHUB_REPOSITORY!=='ikkinotako2-sketch/project-love-machine-serverless-sandbox'||env.GITHUB_REF!==`refs/heads/${BRANCH}`||env.GITHUB_EVENT_NAME!=='push'||env.GITHUB_RUN_ATTEMPT!=='1'||!/^\d+$/.test(env.GITHUB_RUN_ID||'')||!/^[a-f0-9]{40}$/.test(env.GITHUB_SHA||'')||env.GITHUB_SHA!==env.PLM_WORKER_PREFLIGHT_APPROVED_COMMIT||env.CLOUDFLARE_ACCOUNT_ID!==ACCOUNT||env.PLM_CF_WORKER_TOKEN_KIND!=='account'||['TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP'].some(k=>env[k]!=='true'))throw Error('preflight_context_rejected');
 const token=env.PLM_CF_WORKER_API_TOKEN;
 if(typeof token!=='string'||!token||/[\r\n]/.test(token))throw Error('editor_credential_required');
 const receipt=env.GITHUB_SHA+':'+env.GITHUB_RUN_ID;if(used.has(receipt))throw Error('preflight_already_consumed_no_retry');used.add(receipt);
 const root=`https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}`,base=root+`/workers/scripts/${WORKER}`;
 const allowed=new Set([root+'/tokens/verify',base+'/settings',base+'/deployments',base+'/subdomain',base+'/schedules',base+'/secrets',base+'/content/v2']);
 async function get(stage,url,raw=false){
  if(!allowed.has(url))throw Error('endpoint_not_allowed');
  const p={stage};out.probes.push(p);out.external_api_calls++;
  const r=await fetcher(url,{method:'GET',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${token}`}});p.http_status=r.status;
  if(!r.ok)throw Error('read_rejected');
  if(raw){out.content_diagnostics={};const bytes=await readBoundedContent(r,out.content_diagnostics);return parseWorkerContent(bytes,r.headers,out.content_diagnostics);}
  const bytes=await readBoundedContent(r,{});
  const d=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));if(d?.success!==true)throw Error('provider_rejected');p.status='PASS';return d.result;
 }
 try{
  const auth=await get('account_token_verify',root+'/tokens/verify');
  if(auth.status!=='active')throw Error('inactive');
  out.token_active=true;
  if(typeof auth.expires_on!=='string'||!Number.isFinite(Date.parse(auth.expires_on))||Date.parse(auth.expires_on)<=Date.now())throw Error('expiry_unconfirmed');
  out.token_expires_at=new Date(auth.expires_on).toISOString();
  const settings=await get('worker_settings',base+'/settings');
  const deployments=await get('active_deployment',base+'/deployments');
  function active(d){const a=d?.deployments?.[0];if(!UUID.test(a?.id||'')||a.versions?.length!==1||a.versions[0].percentage!==100||!UUID.test(a.versions[0].version_id||''))throw Error('active_version_unconfirmed');return a;}
  const dep=active(deployments),versionID=dep.versions[0].version_id;
  const versionURL=base+'/versions/'+versionID;allowed.add(versionURL);
  const version=await get('active_version_metadata',versionURL);
  if(version.id!==versionID)throw Error('version_identity_mismatch');
  out.observed_deployment_id=dep.id;out.observed_version_id=versionID;
  const resource=version.resources;
  if(!Array.isArray(resource?.bindings)||resource.bindings.length>64||!Array.isArray(resource?.script?.handlers)||resource.script.handlers.some(x=>!['fetch','scheduled','queue','email','tail','trace','alarm','connect'].includes(x)))throw Error('bindings_handlers_unconfirmed');
  const bindings=[],vars={},secrets=[];
  for(const b of resource.bindings){
   if(typeof b?.name!=='string'||!/^[_A-Za-z][_A-Za-z0-9]{0,127}$/.test(b.name)||typeof b.type!=='string')throw Error('binding_shape_unconfirmed');
   if(b.type==='plain_text'&&['TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP'].includes(b.name)&&['true','false'].includes(b.text)){vars[b.name]=b.text;}
   else if(b.type==='secret_text')secrets.push(b.name); // Never retrieve a secret value.
   else bindings.push({name:b.name,type:b.type}); // Do not log arbitrary values.
  }
  const sub=await get('worker_public_subdomain',base+'/subdomain');
  if(typeof sub.enabled!=='boolean'||typeof sub.previews_enabled!=='boolean')throw Error('public_state_unconfirmed');
  const schedules=await get('worker_cron',base+'/schedules');
  if(!Array.isArray(schedules?.schedules))throw Error('cron_unconfirmed');
  const listedSecrets=await get('worker_secret_names_only',base+'/secrets');
  if(!Array.isArray(listedSecrets)||listedSecrets.some(x=>typeof x.name!=='string'||!/^[_A-Za-z][_A-Za-z0-9]{0,127}$/.test(x.name)))throw Error('secret_metadata_unconfirmed');
  const content=await get('worker_code_hash_only',base+'/content/v2',true);
  const sha=content.main_module_sha256;
  const again=active(await get('deployment_stability_readback',base+'/deployments'));
  if(again.id!==dep.id||again.versions[0].version_id!==versionID)throw Error('deployment_changed');
  const owner=JSON.parse(readFileSync(new URL('../readiness/STOPPED_WORKER_READINESS_2026_10_03.json',import.meta.url),'utf8')).owner_evidence;
  const publicOwner=owner.api_readback===false&&owner.custom_domains===0&&owner.routes===0&&owner.workers_dev_enabled===false&&owner.preview_enabled===false;
  const snapshot={evidence_kind:'WORK_READ_ONLY_SNAPSHOT',account_id:ACCOUNT,worker_name:WORKER,deployment_id:dep.id,version_id:versionID,code_sha256:sha,code_inventory:content,snapshot_complete:true,code_metadata_etag:typeof resource.script.etag==='string'&&/^[A-Za-z0-9-]{1,128}$/.test(resource.script.etag)?resource.script.etag:null,bindings,vars,secrets:[...new Set([...secrets,...listedSecrets.map(x=>x.name)])],workers_dev:sub.enabled,preview_urls:sub.previews_enabled,compatibility_date:typeof resource.script_runtime?.compatibility_date==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(resource.script_runtime.compatibility_date)?resource.script_runtime.compatibility_date:null,handlers:resource.script.handlers.filter(x=>typeof x==='string'),cron:schedules.schedules.length===0?[]:['NONEMPTY_REDACTED'],stable_deployment_readback:true,public_routes_owner_confirmed_none:publicOwner,routes:{status:'OWNER CONFIRMED NONE',api_readback:false},custom_domains:{status:'OWNER CONFIRMED NONE',api_readback:false},queue_external_consumers:'UNVERIFIED_NO_QUEUE_PERMISSION',observability:{enabled:typeof settings.observability?.enabled==='boolean'?settings.observability.enabled:null,logs_enabled:typeof settings.observability?.logs?.enabled==='boolean'?settings.observability.logs.enabled:null,logpush:typeof settings.logpush==='boolean'?settings.logpush:null,tail_consumers_count:Array.isArray(settings.tail_consumers)?settings.tail_consumers.length:null,logs_destinations_count:Array.isArray(settings.observability?.logs?.destinations)?settings.observability.logs.destinations.length:null,traces_destinations_count:Array.isArray(settings.observability?.traces?.destinations)?settings.observability.traces.destinations.length:null},checked_at:new Date().toISOString()};
  out.snapshot=snapshot;out.snapshot_acquired=true;out.snapshot_pass=true;out.rollback=rollbackReadiness(snapshot);
  out.placeholder_hash_matches=sha===CODE_SHA;
  const candidate=validateStoppedDeploy(JSON.parse(readFileSync(new URL('./wrangler.stopped.json',import.meta.url),'utf8')),JSON.parse(readFileSync(new URL('./stopped-deploy-plan.json',import.meta.url),'utf8')),readFileSync(new URL('./bootstrap-placeholder.mjs',import.meta.url),'utf8'));
  out.offline_candidate=candidate;
  out.scope_evidence='EXACT_WORKER_GET_SUCCEEDED_POLICY_EXCLUSIVITY_REQUIRES_OWNER_SCREEN';
  out.deploy_readiness=out.rollback.status==='DESIGN PASS'&&out.placeholder_hash_matches&&content.module_count===1&&snapshot.bindings.length===0&&snapshot.secrets.length===0&&snapshot.cron.length===0&&snapshot.handlers.join(',')==='fetch'&&snapshot.workers_dev===false&&snapshot.preview_urls===false&&publicOwner&&Object.values(vars).every(x=>x==='true')&&snapshot.compatibility_date!==null;
  out.preflight_pass=out.deploy_readiness;
  out.stop_reason=out.preflight_pass?'OWNER_SCOPE_CI_AND_FINAL_DEPLOY_APPROVAL_REQUIRED':'REMOTE_SNAPSHOT_REQUIRES_REVIEW_NO_DEPLOY';
 }catch(e){out.preflight_pass=false;out.deploy_readiness=false;out.failure_code=e instanceof ContentError?e.code:'READ_ONLY_PREFLIGHT_UNCONFIRMED';out.failure_stage=out.probes.at(-1)?.stage??'CONTEXT';out.stop_reason='READ_ONLY_PREFLIGHT_UNCONFIRMED_NO_RETRY_NO_DEPLOY';}
 return out;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 try{const r=await editorPreflight(process.env);console.log('PLM_EDITOR_PREFLIGHT_EVIDENCE '+JSON.stringify(r));if(!r.preflight_pass)process.exitCode=1;}
 catch{console.error('EDITOR_PREFLIGHT_BLOCKED_NO_HTTP_NO_DEPLOY');process.exitCode=1;}
}
