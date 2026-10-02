import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
import {setup,REPO} from './cloudflare-setup.mjs';
const id='18050cf6-934e-4f3a-a1cd-5041bac1c35e';
const env={GITHUB_REPOSITORY:REPO,GITHUB_REF:'refs/heads/main',GITHUB_EVENT_NAME:'workflow_dispatch',TEST_ONLY:'true',DRY_RUN:'true',NO_PUBLISH:'true',EMERGENCY_STOP:'true',CLOUDFLARE_ACCOUNT_ID:'a'.repeat(32),PLM_D1_DATABASE_ID:id,PLM_CF_D1_API_TOKEN:'fixture-d1',PLM_CF_WORKER_API_TOKEN:'fixture-worker'};
const sql=readFileSync(new URL('./schema.sql',import.meta.url),'utf8');
function mock({exists=true,wrongName=false,inactive=false,workerMissing=false,writeLost=false}={}) {
 const db=new DatabaseSync(':memory:');if(exists) db.exec(sql);const calls=[];
 const fetcher=async (url,options)=>{
  calls.push({url,options});let result;
  if(url.endsWith('/tokens/verify')) result={status:inactive?'expired':'active'};
  else if(url.endsWith(`/d1/database/${id}`)) result={uuid:id,name:wrongName?'production':'plm-serverless-sandbox-state'};
  else if(url.endsWith('/query')) {
   const query=JSON.parse(options.body).sql;
   if(query.includes('CREATE TABLE')) {if(writeLost)throw Error('private-provider-detail');db.exec(query);result=[{success:true,results:[]}];}
   else result=[{success:true,results:db.prepare(query).all()}];
  } else if(url.endsWith('/settings')) {if(workerMissing)return {ok:false,status:404}; result={};}
  else throw Error('unexpected_endpoint');
  return {ok:true,status:200,json:async()=>({success:true,result})};
 };return {db,calls,fetcher};
}
test('missing auth/context/flags rejected before any network',async()=>{
 for(const delta of [{PLM_CF_D1_API_TOKEN:''},{GITHUB_REPOSITORY:'production'},{GITHUB_REF:'refs/heads/other'},{GITHUB_EVENT_NAME:'push'},{EMERGENCY_STOP:'false'},{CLOUDFLARE_ACCOUNT_ID:'../'},{PLM_D1_DATABASE_ID:'../db'}]) {
  const m=mock();await assert.rejects(setup({...env,...delta},'inspect',m.fetcher));assert.equal(m.calls.length,0);m.db.close();
 }
});
test('inspect verifies token and exact existing database; no writes',async()=>{
 const m=mock();const r=await setup(env,'inspect',m.fetcher);assert.equal(r.schema,'pass');assert.equal(r.live_job_sent,false);
 assert(m.calls.every(c=>c.options.redirect==='error'));assert(!m.calls.some(c=>c.options.body?.includes('CREATE TABLE')));m.db.close();
});
test('inactive token and wrong database stop',async()=>{
 for(const opts of [{inactive:true},{wrongName:true}]) {const m=mock(opts);await assert.rejects(setup(env,'migrate',m.fetcher));assert(!m.calls.some(c=>c.url.endsWith('/query')));m.db.close();}
});
test('missing schema inspect does not migrate',async()=>{
 const m=mock({exists:false});assert.equal((await setup(env,'inspect',m.fetcher)).schema,'missing');assert.equal(m.calls.length,3);m.db.close();
});
test('migration creates only missing table and second run is no-op',async()=>{
 const m=mock({exists:false});assert.equal((await setup(env,'migrate',m.fetcher)).migration_applied,true);
 assert.equal((await setup(env,'migrate',m.fetcher)).migration_applied,false);
 assert.equal(m.calls.filter(c=>c.options.body?.includes('CREATE TABLE')).length,1);m.db.close();
});
test('schema mismatch and existing job stop without migration',async()=>{
 for(const populated of [true,false]) {
  const m=mock();if(populated)m.db.exec("INSERT INTO test_jobs VALUES ('test','test_reference_001','test-one','hash','owner','ready',1,'claim',NULL,1,1)");else m.db.exec('ALTER TABLE test_jobs ADD COLUMN forbidden TEXT');
  await assert.rejects(setup(env,'migrate',m.fetcher));assert(!m.calls.some(c=>c.options.body?.includes('CREATE TABLE')));m.db.close();
 }
});
test('ambiguous migration is never retried or raw error exposed',async()=>{
 const m=mock({exists:false,writeLost:true});await assert.rejects(setup(env,'migrate',m.fetcher),{message:'write_or_query_unconfirmed'});
 assert.equal(m.calls.filter(c=>c.options.body?.includes('CREATE TABLE')).length,1);m.db.close();
});
test('prepare deploy requires existing Worker and produces stopped exact binding',async()=>{
 const m=mock();const r=await setup(env,'prepare-deploy',m.fetcher);assert.equal(r.config.vars.EMERGENCY_STOP,'true');assert.equal(r.config.d1_databases[0].database_id,id);
 assert.equal(m.calls.at(-1).options.headers.Authorization,'Bearer fixture-worker');assert(!JSON.stringify(r).includes('fixture-'));m.db.close();
});
test('missing worker never creates worker; missing schema stops deploy',async()=>{
 for(const opts of [{workerMissing:true},{exists:false}]) {const m=mock(opts);await assert.rejects(setup(env,'prepare-deploy',m.fetcher));assert(m.calls.every(c=>['GET','POST'].includes(c.options.method)));assert(!m.calls.some(c=>c.url.includes('/scripts/')&&c.options.method!=='GET'));m.db.close();}
});
test('invalid operation cannot access API',async()=>{const m=mock();await assert.rejects(setup(env,'dispatch',m.fetcher));assert.equal(m.calls.length,0);m.db.close();});
test('every unsafe flag and alternative valid DB UUID fail before HTTP',async()=>{
 for(const delta of ['TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP'].map(k=>({[k]:'false'})).concat([{PLM_D1_DATABASE_ID:'00000000-0000-4000-8000-000000000000'}])) {
  const m=mock();await assert.rejects(setup({...env,...delta},'migrate',m.fetcher));assert.equal(m.calls.length,0);m.db.close();
 }
});
test('all remote requests stay in exact account/DB/Worker allowlist',async()=>{
 const m=mock({exists:false});await setup(env,'migrate',m.fetcher);await setup(env,'prepare-deploy',m.fetcher);
 const base=`https://api.cloudflare.com/client/v4/accounts/${env.CLOUDFLARE_ACCOUNT_ID}`;
 const allowed=new Set([base+'/tokens/verify',base+`/d1/database/${id}`,base+`/d1/database/${id}/query`,base+'/workers/scripts/plm-serverless-sandbox-control/settings']);
 for(const c of m.calls) {
  assert(allowed.has(c.url));
  if(c.options.method==='POST') {
   const q=JSON.parse(c.options.body).sql;
   assert(q===readFileSync(new URL('./migrations/0001_test_jobs.sql',import.meta.url),'utf8') || /^(SELECT|PRAGMA) /.test(q));
  }
 }
 m.db.close();
});
test('provider error containing a token is never exposed by setup error',async()=>{
 const m=mock();const fetcher=async()=>{throw Error(env.PLM_CF_D1_API_TOKEN+' raw response Authorization');};
 await assert.rejects(setup(env,'inspect',fetcher),{message:'read_unconfirmed'});m.db.close();
});
test('setup and offline CI never call the callback runner or send a live job',()=>{
 const setupWorkflow=readFileSync(new URL('../.github/workflows/plm-cloudflare-setup.yml',import.meta.url),'utf8');
 assert(!setupWorkflow.includes('test-runner.mjs'));assert(!setupWorkflow.includes('repository_dispatch'));assert(!setupWorkflow.includes('cron:'));
 assert(setupWorkflow.includes("EMERGENCY_STOP: 'true'"));assert(setupWorkflow.includes('command: deploy --config wrangler.local.json'));
 const source=readFileSync(new URL('./cloudflare-setup.mjs',import.meta.url),'utf8');
 assert(!source.includes('console.log(token'));assert(!source.includes('console.error(error'));assert(!source.includes('dispatches'));
});
