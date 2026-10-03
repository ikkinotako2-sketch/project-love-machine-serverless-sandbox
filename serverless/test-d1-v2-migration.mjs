import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {preflight,postCheck,migrateSchemaOnce,candidate,EXPECTED,SQL_SHA,MESSAGE,APPROVED_PARENT,executionContext} from './d1-v2-migration.mjs';
import {entry,historyPageClear} from './d1-v2-migration-entry.mjs';
import {ACCOUNT,DB,BRANCH} from './read-only-diagnostic.mjs';
const BASE=JSON.parse(readFileSync(new URL('../readiness/BACKEND_SCHEMA_READ_RECEIPT_37093009614.json',import.meta.url))).evidence;
const env={GITHUB_REPOSITORY:'ikkinotako2-sketch/project-love-machine-serverless-sandbox',GITHUB_REF:`refs/heads/${BRANCH}`,GITHUB_EVENT_NAME:'push',GITHUB_RUN_ATTEMPT:'1',GITHUB_RUN_ID:'12345678',GITHUB_SHA:'a'.repeat(40),CLOUDFLARE_ACCOUNT_ID:ACCOUNT,PLM_D1_DATABASE_ID:DB,PLM_CF_ACCOUNT_ISOLATION:'unverified',TEST_ONLY:'true',DRY_RUN:'true',NO_PUBLISH:'true',EMERGENCY_STOP:'true',PLM_CF_D1_MIGRATION_V2_TOKEN:'PUBLIC_ACCOUNT_FIXTURE',PLM_CF_D1_READ_TOKEN:'PUBLIC_READ_FIXTURE',PLM_V2_PREFLIGHT_PARENT:APPROVED_PARENT,PLM_V2_PREFLIGHT_MESSAGE:MESSAGE};
let serial=100;
function approvedEnv(){const sha=(serial++).toString(16).padStart(40,'0');return {...env,GITHUB_SHA:sha,PLM_D1_V2_APPROVED_COMMIT:sha,PLM_D1_V2_MIGRATION_ALLOW:'true',PLM_D1_V2_OWNER_APPROVAL:'MIGRATE_FIXED_SCHEMA_V2_ONCE',PLM_D1_V2_SQL_SHA:SQL_SHA};}
function fixture(options={}){
 const calls=[];let migrated=false;
 const fetcher=async(u,o)=>{
  calls.push({url:u,method:o.method,body:o.body,auth:o.headers.Authorization});
  assert(!u.includes('/workers/'));let result,extra={};
  if(u===`https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}/tokens/verify`){
   assert.equal(o.method,'GET');assert.equal(o.headers.Authorization,'Bearer PUBLIC_ACCOUNT_FIXTURE');
   if(options.verifyStatus)return new Response('{}',{status:options.verifyStatus});
   if(options.verifyTimeout)throw Error('PRIVATE_TOKEN_PROVIDER_ERROR');
   result={id:'PRIVATE_TOKEN_ID',status:options.inactive?'disabled':'active',expires_on:options.noExpiry?undefined:options.expired?'2000-01-01T00:00:00Z':'2030-01-01T00:00:00Z'};
  }else if(u.endsWith('/user/tokens/verify')){assert.equal(o.headers.Authorization,'Bearer PUBLIC_READ_FIXTURE');result={status:'active'};}
  else if(u.includes('/d1/database?page=')){result=[{uuid:DB,name:'plm-serverless-sandbox-state'}];if(options.otherDb)result.push({uuid:'11111111-1111-4111-8111-111111111111',name:'other'});extra.result_info={page:1,count:result.length,total_count:result.length};}
  else if(u.endsWith(DB))result={uuid:DB,name:options.wrongName?'wrong':'plm-serverless-sandbox-state',file_size:20480};
  else if(u.endsWith('/time_travel/bookmark'))result={bookmark:migrated?'00000009-00000000-000050ff-11111111111111111111111111111111':BASE.d1.pre_migration_bookmark};
  else if(u.endsWith('/query')){
   const sql=JSON.parse(o.body).sql;
   if(sql===candidate().sql){
    assert.equal(o.headers.Authorization,'Bearer PUBLIC_ACCOUNT_FIXTURE');assert.equal(o.method,'POST');migrated=true;
    if(options.writeTimeout)throw Error('PRIVATE_RESPONSE_LOST');
    if(options.write5xx)return new Response('{}',{status:503});
    if(options.writeParse)return new Response('NOT JSON PRIVATE');
    return new Response(JSON.stringify({success:true,result:[{success:true},{success:true}]}));
   }
   assert.equal(o.headers.Authorization,'Bearer PUBLIC_READ_FIXTURE');assert(/^(SELECT|PRAGMA)/.test(sql));let rows;
   if(sql.startsWith('SELECT sql'))rows=[{sql:BASE.d1.current_schema.find(x=>x.name==='test_jobs').sql}];
   else if(sql==='PRAGMA table_info(test_jobs)')rows=BASE.columns;
   else if(sql.includes('COUNT')&&sql.includes('test_jobs'))rows=[{job_count:options.oldRows?1:0}];
   else if(sql.startsWith('SELECT type')){rows=structuredClone(BASE.d1.current_schema);if(migrated||options.probeExists)rows.push(...structuredClone(EXPECTED.schema));if(options.changedSchema)rows[0].sql='CREATE TABLE _cf_KV (changed TEXT)';if(migrated&&options.badPost)rows=rows.filter(x=>x.type!=='trigger');}
   else if(sql==='PRAGMA index_list(test_jobs)')rows=BASE.indexes;
   else if(sql==='PRAGMA index_info(sqlite_autoindex_test_jobs_1)')rows=BASE.index_columns;
   else if(sql==='PRAGMA table_info(backend_probe_v1)')rows=EXPECTED.columns;
   else if(sql.includes('COUNT')&&sql.includes('backend_probe_v1'))rows=[{probe_count:options.probeRows?1:0}];
   else if(sql==='PRAGMA index_list(backend_probe_v1)')rows=EXPECTED.indexes;
   else assert.fail('unexpected query');
   result=[{success:true,meta:{changed_db:false,rows_written:0},results:rows}];
  }else assert.fail('unexpected endpoint');
  return new Response(JSON.stringify({success:true,result,...extra}));
 };return {calls,fetcher};
}
const writes=f=>f.calls.filter(x=>x.body&&JSON.parse(x.body).sql.startsWith('-- Sandbox'));
const journal=()=>{let used=false;return {reserve(){if(used)throw Error('LOCAL_INTENT_EXISTS');used=true;}};};
test('v2 exact SQL has two additive objects and unchanged fixed hash',()=>{const c=candidate();assert.equal(c.sql_sha256,SQL_SHA);assert.equal(c.create_table,1);assert.equal(c.create_trigger,1);assert.equal(c.destructive_statements,0);assert.equal(c.migration_0001_executions,0);assert.equal(EXPECTED.columns.length,15);});
test('modified SQL bytes reject before API including whitespace change',()=>{assert.throws(()=>candidate(Buffer.from(candidate().sql+'\n')),/SQL_HASH_MISMATCH/);});
test('v2 preflight is twelve calls, read-only, no token id or private values',async()=>{const f=fixture();const r=await preflight(env,f.fetcher);assert.equal(r.pass,true);assert.equal(r.external_api_calls,12);assert.equal(r.get_calls,5);assert.equal(r.read_query_post_calls,7);assert.equal(r.d1_writes,0);assert.equal(writes(f).length,0);assert(!JSON.stringify(r).includes('PRIVATE'));assert.equal(r.migration_permitted,false);});
test('account verify 401 403 404 429 does not fallback or continue',async()=>{for(const verifyStatus of [401,403,404,429]){const f=fixture({verifyStatus});const r=await preflight(env,f.fetcher);assert.equal(r.pass,false);assert.equal(f.calls.length,1);assert.equal(writes(f).length,0);}});
test('verify timeout has no retry and sanitized failure',async()=>{const f=fixture({verifyTimeout:true});const r=await preflight(env,f.fetcher);assert.equal(f.calls.length,1);assert.equal(r.pass,false);assert(!JSON.stringify(r).includes('PRIVATE'));});
test('finite future expiry is mandatory and inactive rejected',async()=>{for(const options of [{expired:true},{noExpiry:true},{inactive:true}]){const f=fixture(options);assert.equal((await preflight(env,f.fetcher)).pass,false);assert.equal(f.calls.length,1);}});
test('wrong repository branch account DB and rerun stop before HTTP',async()=>{for(const d of [{GITHUB_REPOSITORY:'other'},{GITHUB_REF:'refs/heads/main'},{CLOUDFLARE_ACCOUNT_ID:'wrong'},{PLM_D1_DATABASE_ID:'wrong'},{GITHUB_RUN_ATTEMPT:'2'},{PLM_V2_PREFLIGHT_PARENT:'b'.repeat(40)},{PLM_V2_PREFLIGHT_MESSAGE:'other'}]){const f=fixture();assert.equal((await preflight({...env,...d},f.fetcher)).pass,false);assert.equal(f.calls.length,0);}});
test('all four unsafe flags stop before credential access',async()=>{for(const key of ['TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP']){const f=fixture();await preflight({...env,[key]:'false'},f.fetcher);assert.equal(f.calls.length,0);}});
test('missing migration or read secret denies without HTTP',async()=>{for(const key of ['PLM_CF_D1_MIGRATION_V2_TOKEN','PLM_CF_D1_READ_TOKEN']){const f=fixture();await preflight({...env,[key]:''},f.fetcher);assert.equal(f.calls.length,0);}});
test('other D1 rejects narrow isolation before schema queries',async()=>{const f=fixture({otherDb:true});assert.equal((await preflight(env,f.fetcher)).pass,false);assert.equal(writes(f).length,0);});
test('DB name mismatch stops no repair',async()=>{const f=fixture({wrongName:true});assert.equal((await preflight(env,f.fetcher)).pass,false);assert.equal(writes(f).length,0);});
test('old rows or changed cfKV schema deny migration readiness',async()=>{for(const options of [{oldRows:true},{changedSchema:true}]){const f=fixture(options);assert.equal((await preflight(env,f.fetcher)).pass,false);assert.equal(writes(f).length,0);}});
test('existing probe or trigger stops any reapplication',async()=>{const f=fixture({probeExists:true});assert.equal((await preflight(env,f.fetcher)).pass,false);assert.equal(writes(f).length,0);});
test('secret registration is not approval and defaults do not migrate',async()=>{const f=fixture();const r=await migrateSchemaOnce(env,f.fetcher,{pass:true},{historyClear:true,journal:journal()});assert.equal(r.mutation_requests,0);assert.equal(f.calls.length,0);assert.equal(executionContext(env),false);});
test('exact approved pin flags and SQL hash are compulsory for execution',()=>{for(const d of [{PLM_D1_V2_APPROVED_COMMIT:'b'.repeat(40)},{PLM_D1_V2_MIGRATION_ALLOW:'false'},{PLM_D1_V2_SQL_SHA:'0'.repeat(64)},{PLM_D1_V2_OWNER_APPROVAL:'UNAPPROVED'}])assert.equal(executionContext({...approvedEnv(),...d}),false);});
test('history and journal are required before mutation',async()=>{const e=approvedEnv();const f=fixture();const p=await preflight(env,f.fetcher);for(const options of [{historyClear:false,journal:journal()},{historyClear:true}]){const out=await migrateSchemaOnce(e,f.fetcher,p,options);assert.equal(out.mutation_requests,0);}assert.equal(writes(f).length,0);});
test('fresh schema mismatch stops before mutation despite approved old receipt',async()=>{const p=await preflight(env,fixture().fetcher);const f=fixture({changedSchema:true});const r=await migrateSchemaOnce(approvedEnv(),f.fetcher,p,{historyClear:true,journal:journal()});assert.equal(r.mutation_requests,0);assert.equal(writes(f).length,0);});
test('exclusive intent reservation failure causes zero mutation',async()=>{const p=await preflight(env,fixture().fetcher);const f=fixture();const r=await migrateSchemaOnce(approvedEnv(),f.fetcher,p,{historyClear:true,journal:{reserve(){throw Error('EXISTS');}}});assert.equal(r.mutation_requests,0);assert.equal(writes(f).length,0);});
test('one mocked migration plus readback success creates no probe rows',async()=>{const p=await preflight(env,fixture().fetcher);const e=approvedEnv();const f=fixture();const r=await migrateSchemaOnce(e,f.fetcher,p,{historyClear:true,journal:journal()});assert.equal(r.status,'SUCCESS');assert.equal(r.mutation_requests,1);assert.equal(writes(f).length,1);assert.equal(r.post.probe_row_count,0);assert.equal(r.post.remote_atomicity,'UNVERIFIED');assert.equal(r.owner_token_revocation_required,true);const again=await migrateSchemaOnce(e,f.fetcher,p,{historyClear:true,journal:journal()});assert.equal(again.mutation_requests,0);assert.equal(writes(f).length,1);});
test('timeout 5xx parse failure after possible commit reconcile only never success',async()=>{for(const options of [{writeTimeout:true},{write5xx:true},{writeParse:true}]){const p=await preflight(env,fixture().fetcher);const f=fixture(options);const r=await migrateSchemaOnce(approvedEnv(),f.fetcher,p,{historyClear:true,journal:journal()});assert.equal(r.status,'UNKNOWN');assert.equal(r.mutation_requests,1);assert.equal(writes(f).length,1);assert.equal(r.manual_reconciliation_required,true);assert.equal(r.post.pass,true);assert(!JSON.stringify(r).includes('PRIVATE'));}});
test('post-check missing trigger or nonzero probe rows is unknown with no fix',async()=>{for(const options of [{badPost:true},{probeRows:true}]){const p=await preflight(env,fixture().fetcher);const f=fixture(options);const r=await migrateSchemaOnce(approvedEnv(),f.fetcher,p,{historyClear:true,journal:journal()});assert.equal(r.status,'UNKNOWN');assert.equal(writes(f).length,1);assert.equal(r.manual_reconciliation_required,true);}});
test('workflow remains hard-disabled and exact defaults are unapproved',()=>{const wf=readFileSync(new URL('../.github/workflows/plm-d1-v2-migration-once.yml',import.meta.url),'utf8');assert(wf.includes('if: false'));assert(wf.includes("PLM_D1_V2_MIGRATION_ALLOW || 'false'"));assert(wf.includes("PLM_D1_V2_APPROVED_COMMIT || 'UNAPPROVED'"));assert(!wf.includes('PLM_CF_WORKER_API_TOKEN'));assert(!wf.includes('PLM_CF_D1_ATOMICITY_TEST_TOKEN'));});
test('all previous execution states including failed cancelled unknown block history',()=>{for(const conclusion of ['success','failure','cancelled',null])assert.throws(()=>historyPageClear({total_count:1,workflow_runs:[{id:5,conclusion}]},'6',1,null));assert.equal(historyPageClear({total_count:1,workflow_runs:[{id:5,conclusion:'skipped'}]},'6',1,null),1);});
test('entry without final approval performs zero external API calls',async()=>{let n=0;const r=await entry(env,async()=>{n++;throw Error();});assert.equal(n,0);assert.equal(r.mutation_requests,0);});
