import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
import {inspectAfterMigration,AUDIT_MESSAGE} from './post-migration-inspect.mjs';
import {ACCOUNT,DB,BRANCH} from './read-only-diagnostic.mjs';
const env={GITHUB_RUN_ATTEMPT:'1',GITHUB_SHA:'a'.repeat(40),PLM_POST_MIGRATION_AUDIT_MESSAGE:AUDIT_MESSAGE,PLM_MIGRATION_WRITE_SECRET_PRESENT:'false',GITHUB_REPOSITORY:'ikkinotako2-sketch/project-love-machine-serverless-sandbox',GITHUB_REF:`refs/heads/${BRANCH}`,GITHUB_EVENT_NAME:'push',CLOUDFLARE_ACCOUNT_ID:ACCOUNT,PLM_D1_DATABASE_ID:DB,PLM_CF_ACCOUNT_ISOLATION:'unverified',PLM_CF_D1_READ_TOKEN:'PUBLIC_FIXTURE',TEST_ONLY:'true',DRY_RUN:'true',NO_PUBLISH:'true',EMERGENCY_STOP:'true'};
function fixture(o={}){
 const db=new DatabaseSync(':memory:');const receipt=JSON.parse(readFileSync(new URL('../readiness/MIGRATION_RECEIPT_37063527954.json',import.meta.url),'utf8'));
 db.exec(receipt.events[0].precheck.read_evidence.current_schema[0].sql);db.exec(readFileSync(new URL('./migrations/0001_test_jobs.sql',import.meta.url),'utf8'));if(o.changed)db.exec('ALTER TABLE _cf_KV ADD COLUMN extra TEXT');let calls=0;
 const f=async(url,req)=>{calls++;let result,extra={};assert.equal(req.headers.Authorization,'Bearer PUBLIC_FIXTURE');
 if(url.endsWith('/workers/scripts')){if(o.unknown)throw Error('private');return new Response(JSON.stringify({success:true,result:[]}),{status:o.workerStatus||403});}
 if(url.endsWith('/tokens/verify'))result={status:'active'};
 else if(url.includes('/d1/database?page=')){result=[{uuid:DB,name:'plm-serverless-sandbox-state'}];extra={result_info:{page:1,count:1,total_count:1}};}
 else if(url.endsWith(`/d1/database/${DB}`))result={uuid:DB,name:'plm-serverless-sandbox-state',file_size:20480};
 else if(url.endsWith('/time_travel/bookmark'))result={bookmark:'00000005-00000002-000050f8-44161778ce1452373d1284c8a93eb6c4'};
 else {const sql=JSON.parse(req.body).sql;assert(/^(SELECT|PRAGMA) /.test(sql));result=[{success:true,meta:{rows_written:0,changed_db:false},results:db.prepare(sql).all()}];}
 return new Response(JSON.stringify({success:true,result,...extra}));};return {db,f,count:()=>calls};
}
test('post migration read audit links receipt confirms schema and cannot infer absence from403',async()=>{const m=fixture();const r=await inspectAfterMigration(env,m.f);assert.equal(r.d1_pass,true);assert.equal(r.d1_writes,0);assert.equal(r.external_api_calls,9);assert.equal(r.worker.status,'READ_PERMISSION_REQUIRED');assert.equal(r.migration_write_secret_present,false);assert(!JSON.stringify(r).includes('PUBLIC_FIXTURE'));m.db.close();});
test('changed old schema stops before Worker probe',async()=>{const m=fixture({changed:true});const r=await inspectAfterMigration(env,m.f);assert.equal(r.d1_pass,false);assert.equal(m.count(),8);m.db.close();});
test('Write Secret present missing receipt context rerun and unsafe flags refuse before HTTP',async()=>{for(const delta of [{PLM_MIGRATION_WRITE_SECRET_PRESENT:'true'},{PLM_MIGRATION_WRITE_SECRET_PRESENT:undefined},{GITHUB_RUN_ATTEMPT:'2'},{GITHUB_REF:'refs/heads/main'},{EMERGENCY_STOP:'false'}]){const m=fixture();await assert.rejects(inspectAfterMigration({...env,...delta},m.f));assert.equal(m.count(),0);m.db.close();}});
test('Worker unknown never retries and remains unverified',async()=>{const m=fixture({unknown:true});const r=await inspectAfterMigration(env,m.f);assert.equal(r.worker.status,'UNKNOWN_NO_RETRY');assert.equal(m.count(),9);m.db.close();});
test('stopped deploy candidate binds exact identifiers and has no triggers secrets endpoints',()=>{
 const p=JSON.parse(readFileSync(new URL('./stopped-deploy-plan.json',import.meta.url),'utf8'));assert.equal(p.deploy_permitted,false);assert.equal(p.create_permitted,false);assert.equal(p.account_id,ACCOUNT);assert.equal(p.worker_name,'plm-serverless-sandbox-control');assert.equal(p.d1_binding.database_id,DB);assert(Object.values(p.flags).every(x=>x==='true'));for(const k of ['custom_domains','routes','cron','queues','secrets','outbound_endpoints'])assert.deepEqual(p[k],[]);assert.equal(p.workers_dev,false);
});
test('bootstrap stopped handler never touches DB env or network even under hostile input',async()=>{
 const placeholder=(await import('./bootstrap-placeholder.mjs')).default;const env=new Proxy({},{get(){throw Error('env_or_DB_access');}});
 for(const method of ['GET','POST','DELETE']){const r=placeholder.fetch(new Request('https://fixture.invalid/test-jobs',{method}),env);assert.equal(r.status,503);assert.equal((await r.json()).EMERGENCY_STOP,true);}
});
