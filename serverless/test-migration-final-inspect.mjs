import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {finalInspect,d1Isolation} from './migration-final-inspect.mjs';
import {ACCOUNT,DB,BRANCH} from './read-only-diagnostic.mjs';
import {setup,REPO} from './cloudflare-setup.mjs';
const env={GITHUB_REPOSITORY:REPO,GITHUB_REF:`refs/heads/${BRANCH}`,GITHUB_EVENT_NAME:'push',CLOUDFLARE_ACCOUNT_ID:ACCOUNT,PLM_D1_DATABASE_ID:DB,PLM_CF_ACCOUNT_ISOLATION:'unverified',TEST_ONLY:'true',DRY_RUN:'true',NO_PUBLISH:'true',EMERGENCY_STOP:'true',PLM_CF_D1_API_TOKEN:'PUBLIC_WRITE_FIXTURE',PLM_CF_D1_READ_TOKEN:'PUBLIC_READ_FIXTURE'};
function fixture(o={}) {
 const calls=[];
 const f=async(url,req)=>{
  calls.push({url,req});let result,extra={};
  if(url.endsWith(`/accounts/${ACCOUNT}/tokens/verify`)){
   assert.equal(req.method,'GET');assert.equal(req.headers.Authorization,'Bearer PUBLIC_WRITE_FIXTURE');
   if(o.status)return new Response(JSON.stringify({success:false,errors:[{message:'PRIVATE_PROVIDER_TOKEN_ID'}]}),{status:o.status});
   if(o.unknown)throw Error('PUBLIC_WRITE_FIXTURE PRIVATE_PROVIDER_TOKEN_ID');
   if(o.malformed)return new Response('PUBLIC_WRITE_FIXTURE');
   if(o.oversized)return new Response('x'.repeat(16385));
   result={id:'PRIVATE_PROVIDER_TOKEN_ID',status:o.inactive?'expired':'active',...(o.expiry?{expires_on:o.expiry}:{})};
  }else {
   assert.equal(req.headers.Authorization,'Bearer PUBLIC_READ_FIXTURE');
   if(url.endsWith('/user/tokens/verify'))result={status:'active'};
   else if(url.includes('/d1/database?page=')){
    result=[{uuid:DB,name:'plm-serverless-sandbox-state'}];if(o.other)result.push({uuid:'11111111-1111-4111-8111-111111111111',name:'production'});
    extra={result_info:{page:1,count:result.length,total_count:result.length}};
   }else if(url.endsWith(`/d1/database/${DB}`))result={uuid:DB,name:o.wrongName?'production':'plm-serverless-sandbox-state',file_size:12288};
   else if(url.endsWith('/query')){
    const sql=JSON.parse(req.body).sql;assert(sql.startsWith('SELECT '));
    const rows=sql.startsWith('SELECT type')?(o.extraTable?[{type:'table',name:'protected',tbl_name:'protected',sql:'CREATE TABLE protected(a)'}]:[{type:'table',name:'_cf_KV',tbl_name:'_cf_KV',sql:'CREATE TABLE _cf_KV(key TEXT PRIMARY KEY, value BLOB) WITHOUT ROWID'}]):[];
    result=[{success:true,meta:{rows_written:0,changed_db:false},results:rows}];
   }else if(url.endsWith('/time_travel/bookmark')){
    if(o.bookmarkUnknown)throw Error('private');result={bookmark:'00000001-00000002-00000003-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'};
   }else throw Error('Unexpected path');
  }
  return new Response(JSON.stringify({success:true,result,...extra}));
 };return {calls,f};
}
test('Write existence and account active then Read exact resources; no remote mutation',async()=>{
 const m=fixture();const r=await finalInspect(env,m.f);assert.equal(r.write_secret_present,true);assert.equal(r.write_token_active,true);assert.equal(r.write_token_owner,'account');assert.equal(r.read_preconditions_pass,true);assert.equal(r.external_api_calls,7);assert.equal(r.migration_permitted,false);assert.equal(r.d1_isolation,'SINGLE_TARGET_D1_VERIFIED');
 assert.equal(m.calls.filter(c=>c.req.headers.Authorization==='Bearer PUBLIC_WRITE_FIXTURE').length,1);
 assert(!m.calls.some(c=>c.req.body?.includes('CREATE TABLE')));assert(!JSON.stringify(r).includes('FIXTURE'));assert(!JSON.stringify(r).includes('PRIVATE_PROVIDER_TOKEN_ID'));
});
test('Write absent or changed context flags fails before any HTTP',async()=>{
 for(const delta of [{PLM_CF_D1_API_TOKEN:''},{PLM_CF_D1_API_TOKEN:'bad\n'},{GITHUB_REF:'refs/heads/main'},{EMERGENCY_STOP:'false'},{CLOUDFLARE_ACCOUNT_ID:'a'.repeat(32)},{PLM_D1_DATABASE_ID:'other'},{PLM_CF_ACCOUNT_ISOLATION:'sandbox_only_verified'}]){const m=fixture();const r=await finalInspect({...env,...delta},m.f);assert.equal(r.write_token_active,false);assert.equal(m.calls.length,0);}
});
test('account401403429500 never falls back to user verify or retries',async()=>{
 for(const status of [401,403,429,500]){const m=fixture({status});const r=await finalInspect(env,m.f);assert.equal(m.calls.length,1);assert.equal(r.write_token_active,false);assert(!JSON.stringify(r).includes('PRIVATE_PROVIDER_TOKEN_ID'));}
});
test('Write timeout malformed oversized responses never retry',async()=>{
 for(const options of [{unknown:true},{malformed:true},{oversized:true}]){const m=fixture(options);const r=await finalInspect(env,m.f);assert.equal(m.calls.length,1);assert.equal(r.write_token_active,false);assert.equal(r.migration_permitted,false);}
});
test('inactive or expired Write never reaches Read D1',async()=>{
 for(const o of [{inactive:true},{expiry:'2020-01-01T00:00:00Z'},{expiry:'garbage'}]){const m=fixture(o);const r=await finalInspect(env,m.f);assert.equal(m.calls.length,1);assert.equal(r.write_token_active,false);}
});
test('finite future expiry returned safely; absent expiry requires owner revocation',async()=>{
 const m=fixture({expiry:new Date(Date.now()+3600000).toISOString()});const r=await finalInspect(env,m.f);assert.equal(typeof r.write_token_expires_at,'string');assert.equal(r.write_scope_api_verified,false);
 assert.equal((await finalInspect(env,fixture().f)).write_token_expiry,'NOT_RETURNED_IMMEDIATE_OWNER_REVOCATION_REQUIRED');
});
test('other D1 wrong target and unknown bookmark cannot pass preconditions',async()=>{
 for(const o of [{other:true},{wrongName:true},{bookmarkUnknown:true},{extraTable:true}]){const m=fixture(o);const r=await finalInspect(env,m.f);assert.equal(r.read_preconditions_pass,false);assert.equal(r.migration_permitted,false);}
});
test('narrow isolation never upgrades account-wide variable or permits missing inventory',async()=>{
 const r=await finalInspect(env,fixture().f);assert.equal(r.account_isolation,'unverified');assert.equal(d1Isolation({...r.read_evidence,inventory:'UNVERIFIED'}),false);assert.equal(d1Isolation({...r.read_evidence,d1_count:2}),false);
});
test('concurrent/replayed preflight calls cannot execute a migration',async()=>{
 const m=fixture();const results=await Promise.all([finalInspect(env,m.f),finalInspect(env,m.f)]);await finalInspect(env,m.f);
 assert(results.every(x=>x.migration_executions===0));assert(!m.calls.some(c=>c.req.body?.includes('CREATE TABLE')));
});
test('workflow remains disabled for migration and ambiguous write is never auto-scheduled',async()=>{
 const wf=readFileSync(new URL('../.github/workflows/plm-cloudflare-setup.yml',import.meta.url),'utf8');assert(wf.includes("PLM_CF_MIGRATION_EXECUTION_APPROVED: 'false'"));assert(wf.includes('cancel-in-progress: false'));
 let calls=0;const e={...env,GITHUB_REF:'refs/heads/main',GITHUB_EVENT_NAME:'workflow_dispatch',PLM_CF_ACCOUNT_ISOLATION:'sandbox_only_verified',PLM_CF_MIGRATION_EXECUTION_APPROVED:'false'};
 await Promise.all([setup(e,'migrate',async()=>{calls++;}),setup(e,'migrate',async()=>{calls++;})].map(p=>assert.rejects(p,{message:'migration_execution_not_approved'})));assert.equal(calls,0);
 const source=readFileSync(new URL('./migration-final-inspect.mjs',import.meta.url),'utf8');assert(!source.includes("setup(env, 'migrate'"));
});
