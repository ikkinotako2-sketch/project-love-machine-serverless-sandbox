import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
import {migrateOnce} from './migration-once.mjs';
import {ACCOUNT,DB,BRANCH} from './read-only-diagnostic.mjs';
import {REPO} from './cloudflare-setup.mjs';
let nextID=100;
function fixture(o={}) {
 const run=String(nextID++),sha='f'.repeat(40),db=new DatabaseSync(':memory:');db.exec('CREATE TABLE _cf_KV(key TEXT PRIMARY KEY,value BLOB) WITHOUT ROWID');
 const env={GITHUB_REPOSITORY:REPO,GITHUB_REF:`refs/heads/${BRANCH}`,GITHUB_EVENT_NAME:'push',GITHUB_RUN_ID:run,GITHUB_RUN_ATTEMPT:'1',GITHUB_SHA:sha,PLM_MIGRATION_APPROVED_COMMIT:sha,PLM_MIGRATION_EXECUTION_APPROVED:'true',PLM_FREE_OWNER_EVIDENCE:'confirmed',PLM_WRITE_SCOPE_OWNER_EVIDENCE:'specific_account_d1_write_only',PLM_REVOCATION_OWNER_READY:'true',CLOUDFLARE_ACCOUNT_ID:ACCOUNT,PLM_D1_DATABASE_ID:DB,PLM_CF_ACCOUNT_ISOLATION:'unverified',TEST_ONLY:'true',DRY_RUN:'true',NO_PUBLISH:'true',EMERGENCY_STOP:'true',GITHUB_TOKEN:'PUBLIC_GH',PLM_CF_D1_API_TOKEN:'PUBLIC_WRITE',PLM_CF_D1_READ_TOKEN:'PUBLIC_READ'};
 const calls=[];
 const f=async(url,req)=>{
  calls.push({url,req});if(o.readLost&&calls.length===1)throw Error('private');let result,extra={};
  if(url.includes('api.github.com')) {
   assert.equal(req.method,'GET');assert.equal(req.headers.Authorization,'Bearer PUBLIC_GH');
   const obj=url.includes('/actions/workflows/')?{total_count:o.replay?2:1,workflow_runs:[{id:Number(run),head_sha:sha,run_attempt:1,event:'push',head_branch:BRANCH}]}:{commit:{sha:o.stale?'a'.repeat(40):sha}};
   return new Response(JSON.stringify(obj));
  }
  if(url.endsWith('/tokens/verify')){result={status:'active'};assert.equal(req.headers.Authorization,url.includes('/accounts/')?'Bearer PUBLIC_WRITE':'Bearer PUBLIC_READ');}
  else if(url.includes('/d1/database?page=')){result=[{uuid:DB,name:'plm-serverless-sandbox-state'}];extra={result_info:{page:1,count:1,total_count:1}};}
  else if(url.endsWith(`/d1/database/${DB}`))result={uuid:DB,name:'plm-serverless-sandbox-state',file_size:12288};
  else if(url.endsWith('/query')){
   const sql=JSON.parse(req.body).sql;
   if(sql.includes('CREATE TABLE IF NOT EXISTS')){
    assert.equal(req.headers.Authorization,'Bearer PUBLIC_WRITE');db.exec(sql);if(o.writeLost)throw Error('secret');result=[{success:true,results:[]}];
   }else{assert.equal(req.headers.Authorization,'Bearer PUBLIC_READ');result=[{success:true,meta:{changed_db:false,rows_written:0},results:db.prepare(sql).all()}];}
  }else if(url.endsWith('/time_travel/bookmark'))result={bookmark:'00000001-00000002-00000003-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'};
  else throw Error('unexpected');
  return new Response(JSON.stringify({success:true,result,...extra}));
 };
 if(o.extraTable)db.exec('CREATE TABLE protected(data)');
 return {env,db,calls,f,creates:()=>calls.filter(c=>c.req.body?.includes('CREATE TABLE IF NOT EXISTS')).length};
}
test('execution approval missing rejects before credential use',async()=>{const m=fixture();await assert.rejects(migrateOnce({...m.env,PLM_MIGRATION_EXECUTION_APPROVED:'false'},m.f),{message:'execution_not_approved'});assert.equal(m.calls.length,0);m.db.close();});
test('rerun different SHA and unsafe flags refuse before HTTP',async()=>{
 for(const delta of [{GITHUB_RUN_ATTEMPT:'2'},{GITHUB_SHA:'a'.repeat(40)},{GITHUB_REF:'refs/heads/main'},{EMERGENCY_STOP:'false'},{GITHUB_EVENT_NAME:'workflow_dispatch'}]){const m=fixture();await assert.rejects(migrateOnce({...m.env,...delta},m.f),{message:'approval_run_context_rejected'});assert.equal(m.calls.length,0);m.db.close();}
});
test('owner scope/free/revocation evidence missing cannot write',async()=>{
 for(const key of ['PLM_FREE_OWNER_EVIDENCE','PLM_WRITE_SCOPE_OWNER_EVIDENCE','PLM_REVOCATION_OWNER_READY']){const m=fixture();await assert.rejects(migrateOnce({...m.env,[key]:'unverified'},m.f),{message:'owner_evidence_required'});assert.equal(m.calls.length,0);m.db.close();}
});
test('duplicate workflow history or stale branch prohibits migration',async()=>{for(const o of [{replay:true},{stale:true}]){const m=fixture(o);await assert.rejects(migrateOnce(m.env,m.f),{message:'workflow_history_or_branch_unconfirmed_no_retry'});assert.equal(m.creates(),0);m.db.close();}});
test('one canonical CREATE followed by Read schema validation and stopped flags',async()=>{
 const m=fixture();const r=await migrateOnce(m.env,m.f);assert.equal(r.migration_executions,1);assert.equal(r.schema,'PASS_EMPTY');assert.equal(r.revoke_write_token_now,true);assert.equal(r.posting_permitted,false);assert.equal(m.creates(),1);
 await assert.rejects(migrateOnce(m.env,m.f),{message:'attempt_already_started_reconcile'});assert.equal(m.creates(),1);m.db.close();
});
test('concurrent same approved run has one attempt winner',async()=>{
 const m=fixture();const results=await Promise.allSettled([migrateOnce(m.env,m.f),migrateOnce(m.env,m.f)]);assert.equal(results.filter(x=>x.status==='fulfilled').length,1);assert.equal(m.creates(),1);m.db.close();
});
test('write applied then response lost consumes attempt; never retries',async()=>{
 const m=fixture({writeLost:true});await assert.rejects(migrateOnce(m.env,m.f),{message:'migration_outcome_unknown_revoke_and_reconcile'});
 await assert.rejects(migrateOnce(m.env,m.f),{message:'attempt_already_started_reconcile'});assert.equal(m.creates(),1);assert.equal(m.db.prepare("SELECT COUNT(*) AS c FROM sqlite_master WHERE name='test_jobs'").get().c,1);m.db.close();
});
test('unknown history blocks without retry, even if next call could succeed',async()=>{
 const m=fixture({readLost:true});await assert.rejects(migrateOnce(m.env,m.f),{message:'workflow_history_or_branch_unconfirmed_no_retry'});await assert.rejects(migrateOnce(m.env,m.f),{message:'attempt_already_started_reconcile'});assert.equal(m.calls.length,1);assert.equal(m.creates(),0);m.db.close();
});
test('unexpected schema prevents CREATE',async()=>{const m=fixture({extraTable:true});await assert.rejects(migrateOnce(m.env,m.f),{message:'live_preconditions_not_met'});assert.equal(m.creates(),0);m.db.close();});
test('prepared workflow has disabled job, false execution flag and shared concurrency',()=>{
 const wf=readFileSync(new URL('../.github/workflows/plm-migration-once.yml',import.meta.url),'utf8');assert(wf.includes('if: ${{ false }}'));assert(wf.includes("PLM_MIGRATION_EXECUTION_APPROVED: 'false'"));assert(wf.includes('group: plm-cloudflare-sandbox-setup'));assert(!wf.includes('workflow_dispatch'));assert(!wf.includes('cron:'));assert(!wf.includes('wrangler'));
});
