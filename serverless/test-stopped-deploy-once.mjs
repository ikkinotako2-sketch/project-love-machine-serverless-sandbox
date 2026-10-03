import test from 'node:test';
import assert from 'node:assert/strict';
import {candidate,checkBase,checkPost,assertUnusedWorkflow,RECEIPT_SHA} from './stopped-deploy-once.mjs';
import worker from './bootstrap-placeholder.mjs';
const c=candidate(),copy=x=>JSON.parse(JSON.stringify(x));
const good={deployment_id:'2fbeef3b-34a2-4902-89f1-460c055945e2',version_id:'9e4d2c71-1c71-4346-911a-016ce63ef57d',stable:true,inventory:{module_count:1,main_module_name:'bootstrap-placeholder.mjs',main_module_sha256:c.validation.code_sha256},bindings:c.metadata.bindings,workers_dev:false,preview_urls:false,secrets:[],cron:[],handlers:['fetch'],compatibility_date:c.config.compatibility_date};
const env={GITHUB_REPOSITORY:'ikkinotako2-sketch/project-love-machine-serverless-sandbox',GITHUB_REF:'refs/heads/plm-offline-readiness-v1-20261002',GITHUB_EVENT_NAME:'push',GITHUB_RUN_ATTEMPT:'1',GITHUB_SHA:'a'.repeat(40),PLM_STOPPED_DEPLOY_APPROVED_COMMIT:'a'.repeat(40),GITHUB_RUN_ID:'999',CLOUDFLARE_ACCOUNT_ID:c.config.account_id,PLM_CF_WORKER_TOKEN_KIND:'account',PLM_CF_WORKER_API_TOKEN:'PUBLIC_MOCK_ONLY',PLM_STOPPED_DEPLOY_ALLOW:'true',PLM_STOPPED_DEPLOY_OWNER_APPROVAL:'DEPLOY_CANONICAL_STOPPED_ONCE',TEST_ONLY:'true',DRY_RUN:'true',NO_PUBLISH:'true',EMERGENCY_STOP:'true'};
let serial=0;
async function run(overrides={},mode='success',base=c.receipt.snapshot){
 const {deployOnce}=await import('./stopped-deploy-once.mjs?test='+serial++);
 const calls=[],intents=[];
 const fetcher=async(url,opts)=>{
  calls.push({method:opts.method,url});
  if(opts.method==='PUT'){
   assert.equal(opts.redirect,'error');assert.equal(url,`https://api.cloudflare.com/client/v4/accounts/${c.config.account_id}/workers/scripts/${c.config.name}`);
   assert.equal(opts.body.get('bootstrap-placeholder.mjs').size,c.code.length);
   if(mode==='timeout')throw Error('SENSITIVE PROVIDER RAW ERROR MUST NEVER LOG');
   return new Response(JSON.stringify({success:mode!=='5xx'}),{status:mode==='5xx'?503:200});
  }
  let result;
  if(url.endsWith('/settings'))result={};
  else if(url.endsWith('/deployments'))result={deployments:[{id:good.deployment_id,versions:[{percentage:100,version_id:good.version_id}]}]};
  else if(url.includes('/versions/'))result={id:good.version_id,resources:{bindings:good.bindings,script:{handlers:['fetch']},script_runtime:{compatibility_date:c.config.compatibility_date}}};
  else if(url.endsWith('/subdomain'))result={enabled:mode==='public',previews_enabled:false};
  else if(url.endsWith('/schedules'))result={schedules:[]};
  else if(url.endsWith('/secrets'))result=[];
  else if(url.endsWith('/content/v2')){
   const boundary='synthetic';
   const body=`--${boundary}\r\nContent-Disposition: form-data; name="metadata"\r\nContent-Type: application/json\r\n\r\n{"main_module":"bootstrap-placeholder.mjs"}\r\n--${boundary}\r\nContent-Disposition: form-data; name="bootstrap-placeholder.mjs"; filename="bootstrap-placeholder.mjs"\r\nContent-Type: application/javascript+module\r\n\r\n${c.code.toString()}\r\n--${boundary}--\r\n`;
   return new Response(body,{headers:{'content-type':`multipart/form-data; boundary=${boundary}`}});
  }else throw Error('ENDPOINT_NOT_EXPECTED');
  return new Response(JSON.stringify({success:true,result}));
 };
 const preflight=async()=>({external_api_calls:9,token_active:true,snapshot_acquired:true,snapshot:base});
 const result=await deployOnce({...env,...overrides},{fetcher,preflight,consumeIntent:async x=>{intents.push(x);if(mode==='intentfail')throw Error('intent_write_failed');}});
 return {result,calls,intents,deployOnce,fetcher,preflight};
}
test('immutable rollback receipt and fixed candidate produce exact single-module metadata',()=>{
 assert.equal(RECEIPT_SHA,'84ab929bcb389ff8d75c36832bc039c07fb763145b0a4786bc48a0eb87b00538');
 assert.equal(c.metadata.bindings.length,5);assert.deepEqual(c.metadata.keep_bindings,[]);assert.equal(c.metadata.keep_assets,false);
 assert.equal(c.receipt.snapshot.code_inventory.module_count,3);checkBase(copy(c.receipt.snapshot),c.receipt);
});
test('placeholder returns only 503 with all flags true and never accesses env DB',async()=>{
 const inaccessible=new Proxy({}, {get(){throw Error('DB_ACCESS_FORBIDDEN');}});
 const r=worker.fetch(new Request('https://fixture.invalid'),inaccessible);assert.equal(r.status,503);
 assert.deepEqual(await r.json(),{status:'disabled',TEST_ONLY:true,DRY_RUN:true,NO_PUBLISH:true,EMERGENCY_STOP:true});
});
test('owner approval absent blocks before any transport or intent',async()=>{const x=await run({PLM_STOPPED_DEPLOY_ALLOW:'false'});assert.equal(x.result.status,'BLOCKED');assert.equal(x.calls.length,0);assert.equal(x.intents.length,0);});
test('wrong exact context, rerun, secret absence and flags deny every case before GET',async()=>{
 for(const [key,value] of Object.entries({GITHUB_REPOSITORY:'production',GITHUB_REF:'refs/heads/main',GITHUB_RUN_ATTEMPT:'2',GITHUB_EVENT_NAME:'workflow_dispatch',GITHUB_SHA:'b'.repeat(40),CLOUDFLARE_ACCOUNT_ID:'wrong',PLM_CF_WORKER_TOKEN_KIND:'user',PLM_CF_WORKER_API_TOKEN:'',PLM_STOPPED_DEPLOY_OWNER_APPROVAL:'policy_only',TEST_ONLY:'false',DRY_RUN:'false',NO_PUBLISH:'false',EMERGENCY_STOP:'false'})){
  const x=await run({[key]:value});assert.equal(x.result.status,'BLOCKED');assert.equal(x.calls.length,0);
 }
});
test('base deployment, code, module, public and binding changes refuse upload',async()=>{
 for(const key of ['deployment_id','code_sha256','bindings','workers_dev','vars']){
  const b=copy(c.receipt.snapshot);b[key]=key==='bindings'?[{name:'unknown',type:'d1'}]:key==='vars'?{TEST_ONLY:'false'}:key==='workers_dev'?true:'changed';
  const x=await run({},'success',b);assert.equal(x.calls.length,0);assert.equal(x.result.mutation_attempts,0);
 }
});
test('durable intent failure refuses PUT',async()=>{const x=await run({},'intentfail');assert.equal(x.calls.length,0);assert.equal(x.result.mutation_attempts,0);});
test('successful upload is exactly one PUT followed by eight GETs and exact postcheck',async()=>{const x=await run();assert.equal(x.result.status,'PASS');assert.equal(x.calls.filter(x=>x.method==='PUT').length,1);assert.equal(x.calls.filter(x=>x.method==='GET').length,8);assert.equal(x.result.get,17);assert.equal(x.result.retries,0);assert.equal(x.intents.length,1);});
test('timeout and 5xx are reconciled once and never retried or promoted to PASS',async()=>{
 for(const mode of ['timeout','5xx']){const x=await run({},mode);assert.equal(x.result.status,'MANUAL_RECONCILIATION_REQUIRED');assert.equal(x.calls.filter(x=>x.method==='PUT').length,1);assert.equal(x.result.post.check.status,'PASS');assert.equal(x.result.retries,0);assert.equal(JSON.stringify(x.result).includes('SENSITIVE'),false);}
});
test('public postcheck mismatch stops with no corrective mutation or rollback',async()=>{const x=await run({},'public');assert.equal(x.result.status,'MANUAL_RECONCILIATION_REQUIRED');assert.equal(x.calls.filter(x=>x.method!=='GET').length,1);assert.equal(x.result.automatic_rollback,false);});
test('same process replay is denied even with a different run id',async()=>{const x=await run();const r=await x.deployOnce({...env,GITHUB_RUN_ID:'1000'},{fetcher:x.fetcher,preflight:x.preflight,consumeIntent:async()=>assert.fail()});assert.equal(r.failure_code,'DEPLOY_ALREADY_CONSUMED');assert.equal(r.mutation_attempts,0);});
test('postcheck refuses code, flags, DB binding, handlers, stable ids and public drift',()=>{
 for(const key of ['stable','version_id','workers_dev','preview_urls','secrets','cron','bindings','handlers','compatibility_date','inventory']){
  const s=copy(good);s[key]=key==='stable'?false:key.endsWith('urls')||key==='workers_dev'?true:['secrets','cron','bindings','handlers'].includes(key)?['wrong']:key==='inventory'?{module_count:3}:'wrong';assert.throws(()=>checkPost(s,c));
 }
});
test('cross-process GitHub fence paginates and rejects previous failed/cancelled/unknown runs',async()=>{
 let calls=0;
 await assertUnusedWorkflow(env,async()=>new Response(JSON.stringify({total_count:101,workflow_runs:++calls===1?[{id:999,conclusion:null}]:[{id:998,conclusion:'skipped'}]})));assert.equal(calls,2);
 for(const conclusion of ['failure','cancelled',null,'success'])await assert.rejects(assertUnusedWorkflow(env,async()=>new Response(JSON.stringify({total_count:1,workflow_runs:[{id:998,conclusion}]}))));
 await assert.rejects(assertUnusedWorkflow(env,async()=>new Response('',{status:403})));
});
