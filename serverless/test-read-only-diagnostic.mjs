import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {diagnose,ACCOUNT,DB,BRANCH} from './read-only-diagnostic.mjs';
const token='PUBLIC_FIXTURE_TOKEN_NOT_A_SECRET';
const env={GITHUB_REPOSITORY:'ikkinotako2-sketch/project-love-machine-serverless-sandbox',GITHUB_REF:`refs/heads/${BRANCH}`,GITHUB_EVENT_NAME:'push',TEST_ONLY:'true',DRY_RUN:'true',NO_PUBLISH:'true',EMERGENCY_STOP:'true',CLOUDFLARE_ACCOUNT_ID:ACCOUNT,PLM_D1_DATABASE_ID:DB,PLM_CF_ACCOUNT_ISOLATION:'unverified',PLM_CF_D1_READ_TOKEN:token};
const schema=readFileSync(new URL('./schema.sql',import.meta.url),'utf8');
const columns=[['platform','TEXT',1,1],['account_id','TEXT',1,2],['job_id','TEXT',1,3],['content_fingerprint','TEXT',1,0],['claimant','TEXT',1,0],['state','TEXT',1,0],['version','INTEGER',1,0],['last_operation','TEXT',1,0],['run_id','TEXT',0,0],['created_at','INTEGER',1,0],['updated_at','INTEGER',1,0]].map(([name,type,notnull,pk])=>({name,type,notnull,pk}));
function fixture(options={}) {
  const calls=[];
  async function fetcher(url,request){
    calls.push({url,request});
    if(options.throwAt===calls.length)throw Error(token+' raw sensitive provider text');
    let result,status=200,success=true,extra={};
    if(url.endsWith('/tokens/verify')){
      if(url.includes('/accounts/')&&options.user){status=403;success=false;result=null;}
      else if(options.invalid){status=401;success=false;result=null;}
      else result={status:options.expired?'expired':'active',id:token};
    }else if(url.includes('/d1/database?page=')){
      result=options.missing?[]:[{uuid:DB,name:options.wrongName?'wrong': 'plm-serverless-sandbox-state'}];
      if(options.other)result.push({uuid:'11111111-1111-4111-8111-111111111111',name:token});
      extra={result_info:{page:1,per_page:100,count:result.length,total_count:result.length}};
      if(options.badPages)extra.result_info.total_count=10;
    }else if(url.endsWith(`/d1/database/${DB}`))result={uuid:DB,name:'plm-serverless-sandbox-state',file_size:12288};
    else if(url.endsWith('/time_travel/bookmark'))result={bookmark:'00000001-00000002-00000003-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'};
    else if(url.endsWith('/query')){
      const sql=JSON.parse(request.body).sql;
      result=[{success:true,meta:{rows_written:options.writes?1:0,changed_db:!!options.writes},results:sql.startsWith('SELECT type')?[]:sql.startsWith('SELECT sql')?(options.schemaMissing?[]:[{sql:options.badSchema?'bad':schema}]):sql.startsWith('PRAGMA')?columns:[{job_count:options.rows||0}]}];
    }else if(url.endsWith('/settings')){status=options.workerDenied?403:200;success=status===200;result={bindings:[{name:'SECRET',text:token}]};}
    else throw Error('unexpected fixture endpoint');
    return new Response(JSON.stringify({success,result,...extra,errors:success?[]:[{code:10000,message:token}]}),{status});
  }
  return {calls,fetcher};
}
test('read-only diagnostic refuses changed context flags IDs and isolation before HTTP',async()=>{
  for(const delta of [{GITHUB_REF:'refs/heads/main'},{GITHUB_REPOSITORY:'production'},{GITHUB_EVENT_NAME:'pull_request'},{CLOUDFLARE_ACCOUNT_ID:'b'.repeat(32)},{PLM_D1_DATABASE_ID:'other'},{PLM_CF_ACCOUNT_ISOLATION:'sandbox_only_verified'},...['TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP'].map(k=>({[k]:'false'}))]){
    const m=fixture();await diagnose({...env,...delta},m.fetcher);assert.equal(m.calls.length,0);
  }
});
test('read-only diagnostic missing credential never sends HTTP',async()=>{const m=fixture();const r=await diagnose({...env,PLM_CF_D1_READ_TOKEN:''},m.fetcher);assert.equal(r.stop_reason,'READ_CREDENTIAL_REQUIRED');assert.equal(m.calls.length,0);});
test('account active exact target inventory and missing schema require migration approval',async()=>{const m=fixture({schemaMissing:true});const r=await diagnose(env,m.fetcher);assert.equal(r.authentication,'ACTIVE');assert.equal(r.inventory,'COMPLETE');assert.equal(r.d1_count,1);assert.equal(r.schema,'MISSING');assert.equal(r.migration_required,true);assert.equal(r.cloudflare_mutations,0);assert.equal(r.live_jobs,0);});
test('complete existing empty schema requires no migration and never writes',async()=>{const m=fixture();const r=await diagnose(env,m.fetcher);assert.equal(r.schema,'PASS_EMPTY');assert.equal(r.row_count,0);assert.equal(r.migration_required,false);assert(m.calls.every(c=>c.request.method==='GET'||/^(SELECT sql|PRAGMA table_info|SELECT COUNT)/.test(JSON.parse(c.request.body).sql)));});
test('definitive account rejection diagnoses user ownership without retrying same endpoint',async()=>{const m=fixture({user:true,schemaMissing:true});const r=await diagnose(env,m.fetcher);assert.equal(r.token_kind,'USER_TOKEN_ACCOUNT_VERIFY_INCOMPATIBLE');assert.equal(r.authentication,'ACTIVE');assert.equal(m.calls.filter(x=>x.url.endsWith('/tokens/verify')).length,2);assert.notEqual(m.calls[0].url,m.calls[1].url);});
test('ambiguous response stops after one call and cannot probe alternate auth',async()=>{const m=fixture({throwAt:1});const r=await diagnose(env,m.fetcher);assert.equal(r.stop_reason,'READ_DIAGNOSTIC_UNCONFIRMED_NO_RETRY');assert.equal(m.calls.length,1);assert(!JSON.stringify(r).includes(token));});
test('invalid credential cannot reach inventory',async()=>{const m=fixture({invalid:true});const r=await diagnose(env,m.fetcher);assert.equal(r.stop_reason,'CREDENTIAL_REJECTED');assert.equal(m.calls.length,2);assert(!m.calls.some(x=>x.url.includes('/d1/')));});
test('expired token cannot reach inventory',async()=>{const m=fixture({expired:true});const r=await diagnose(env,m.fetcher);assert.equal(r.stop_reason,'TOKEN_NOT_ACTIVE');assert.equal(m.calls.length,1);});
test('other D1 is potentially protected and stops before schema or worker',async()=>{const m=fixture({other:true});const r=await diagnose(env,m.fetcher);assert.equal(r.stop_reason,'OTHER_D1_POTENTIALLY_PROTECTED_NO_WRITE');assert.equal(r.other_d1_count,1);assert(!m.calls.some(x=>x.url.endsWith('/query')));assert(!JSON.stringify(r).includes(token));});
test('missing or renamed target never recreates DB',async()=>{for(const options of [{missing:true},{wrongName:true}]){const m=fixture(options);const r=await diagnose(env,m.fetcher);assert.equal(r.stop_reason,'TARGET_D1_MISSING_OR_ID_NAME_MISMATCH');assert.equal(m.calls.length,2);}});
test('incomplete pagination fails closed rather than claiming complete inventory',async()=>{const m=fixture({badPages:true});const r=await diagnose(env,m.fetcher);assert.notEqual(r.inventory,'COMPLETE');assert.equal(m.calls.length,3);});
test('existing rows and mismatched schema stop without migration',async()=>{for(const options of [{rows:1},{badSchema:true}]){const m=fixture(options);const r=await diagnose(env,m.fetcher);assert.equal(r.schema,'MISMATCH_OR_EXISTING_ROWS');assert.equal(r.stop_reason,'SCHEMA_REQUIRES_RECONCILIATION');assert(!m.calls.some(x=>x.url.endsWith('/settings')));}});
test('unexpected write metadata stops immediately',async()=>{const m=fixture({writes:true});const r=await diagnose(env,m.fetcher);assert.equal(r.stop_reason,'READ_DIAGNOSTIC_UNCONFIRMED_NO_RETRY');assert.equal(m.calls.length,4);});
test('Worker permission denied does not request Admin or claim absence',async()=>{const m=fixture({workerDenied:true});const r=await diagnose(env,m.fetcher);assert.equal(r.worker,'READ_PERMISSION_REQUIRED');assert.equal(r.free_plan,'UNVERIFIED');assert.equal(r.account_isolation,'unverified');});
test('sanitized evidence omits raw token metadata settings and provider errors',async()=>{for(const options of [{},{user:true},{invalid:true}]){const m=fixture(options);const r=await diagnose(env,m.fetcher);assert(!JSON.stringify(r).includes(token));assert.equal(r.external_api_calls,m.calls.length);}});
test('malformed oversized and rate limited bodies never retry',async()=>{
  for(const response of [()=>new Response('bad',{status:200}),()=>new Response('x'.repeat(131073),{status:200}),()=>new Response(JSON.stringify({success:false,errors:[]}),{status:429})]){
    let n=0;const r=await diagnose(env,async()=>{n++;return response();});assert.equal(n,1);assert.notEqual(r.authentication,'ACTIVE');
  }
});

test('preflight explicitly user verifies once and reads schema/bookmark without mutation',async()=>{
 const m=fixture({schemaMissing:true});const r=await diagnose({...env,PLM_CF_D1_READ_TOKEN_KIND:'user',PLM_MIGRATION_PREFLIGHT:'true'},m.fetcher);
 assert.equal(r.token_kind,'USER_TOKEN');assert.equal(m.calls.filter(c=>c.url.endsWith('/tokens/verify')).length,1);assert(m.calls[0].url.includes('/user/'));
 assert.equal(r.time_travel,'BOOKMARK_READ_CONFIRMED');assert.equal(r.schema_object_count,0);assert.equal(r.sql.destructive_statements,0);assert.equal(r.migration_permitted,false);
 assert(!m.calls.some(c=>c.url.includes('/restore')));assert(!m.calls.some(c=>c.request.body?.includes('CREATE TABLE')));assert(!m.calls.some(c=>c.url.endsWith('/settings')));
});
test('explicit owner rejection cannot fall back or retry',async()=>{
 const m=fixture({invalid:true});const r=await diagnose({...env,PLM_CF_D1_READ_TOKEN_KIND:'user',PLM_MIGRATION_PREFLIGHT:'true'},m.fetcher);assert.notEqual(r.authentication,'ACTIVE');assert.equal(m.calls.length,1);
});
test('preflight bookmark403 leaves restore availability unverified',async()=>{
 const m=fixture({schemaMissing:true});const f=async(u,o)=>u.endsWith('/time_travel/bookmark')?new Response(JSON.stringify({success:false,errors:[]}),{status:403}):m.fetcher(u,o);
 const r=await diagnose({...env,PLM_CF_D1_READ_TOKEN_KIND:'user',PLM_MIGRATION_PREFLIGHT:'true'},f);assert.equal(r.time_travel,'READ_PERMISSION_REQUIRED');assert.equal(r.pre_migration_bookmark,undefined);assert.equal(r.migration_permitted,false);
});
test('ambiguous bookmark never retries or reports confirmed backup',async()=>{
 const m=fixture({schemaMissing:true});let n=0;const f=async(u,o)=>{if(u.endsWith('/time_travel/bookmark')){n++;throw Error('private');}return m.fetcher(u,o);};
 const r=await diagnose({...env,PLM_CF_D1_READ_TOKEN_KIND:'user',PLM_MIGRATION_PREFLIGHT:'true'},f);assert.equal(n,1);assert.equal(r.pre_migration_bookmark,undefined);assert.equal(r.stop_reason,'READ_DIAGNOSTIC_UNCONFIRMED_NO_RETRY');
});
