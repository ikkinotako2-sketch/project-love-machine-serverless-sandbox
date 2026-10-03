import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {inspectBackendSchema,MESSAGE} from './backend-schema-read-only.mjs';
import {ACCOUNT,DB,BRANCH} from './read-only-diagnostic.mjs';
const schema=readFileSync(new URL('./schema.sql',import.meta.url),'utf8');
const cols=[['platform','TEXT',1,1],['account_id','TEXT',1,2],['job_id','TEXT',1,3],['content_fingerprint','TEXT',1,0],['claimant','TEXT',1,0],['state','TEXT',1,0],['version','INTEGER',1,0],['last_operation','TEXT',1,0],['run_id','TEXT',0,0],['created_at','INTEGER',1,0],['updated_at','INTEGER',1,0]].map(([name,type,notnull,pk],cid)=>({cid,name,type,notnull,pk,dflt_value:null}));
const env={GITHUB_REPOSITORY:'ikkinotako2-sketch/project-love-machine-serverless-sandbox',GITHUB_REF:`refs/heads/${BRANCH}`,GITHUB_EVENT_NAME:'push',GITHUB_RUN_ATTEMPT:'1',GITHUB_SHA:'a'.repeat(40),PLM_BACKEND_SCHEMA_AUDIT_MESSAGE:MESSAGE,CLOUDFLARE_ACCOUNT_ID:ACCOUNT,PLM_D1_DATABASE_ID:DB,PLM_CF_ACCOUNT_ISOLATION:'unverified',PLM_CF_D1_READ_TOKEN:'PUBLIC_READ_ONLY_FIXTURE',TEST_ONLY:'true',DRY_RUN:'true',NO_PUBLISH:'true',EMERGENCY_STOP:'true'};
function fixture(bad){const calls=[];return {calls,fetcher:async(u,o)=>{
 calls.push([u,o]);let result,extra={};
 if(bad==='timeout')throw Error('PRIVATE_MUST_NOT_LOG');
 if(u.endsWith('/tokens/verify'))result={status:'active',id:'PRIVATE_TOKEN_ID'};
 else if(u.includes('/d1/database?page=')){result=[{uuid:DB,name:'plm-serverless-sandbox-state'}];extra.result_info={page:1,count:1,total_count:1};}
 else if(u.endsWith(DB))result={uuid:DB,name:'plm-serverless-sandbox-state',file_size:20480};
 else if(u.endsWith('/time_travel/bookmark'))result={bookmark:'00000006-00000002-000050f8-f5a2de6e938ce4dd2b75da1a3fbe5624'};
 else{
 assert.equal(o.method,'POST');assert(u.endsWith('/query'));const sql=JSON.parse(o.body).sql;assert(/^(SELECT|PRAGMA)/.test(sql));
 let rows;
 if(sql.startsWith('SELECT sql'))rows=[{sql:schema}];else if(sql.includes('COUNT'))rows=[{job_count:0}];else if(sql.startsWith('SELECT type'))rows=[{type:'table',name:'test_jobs',tbl_name:'test_jobs',sql:schema}];else if(sql.startsWith('PRAGMA table_info'))rows=cols;else if(sql.startsWith('PRAGMA index_list'))rows=[{name:bad==='index'?'wrong':'sqlite_autoindex_test_jobs_1',unique:1,origin:'pk'}];else if(sql.startsWith('PRAGMA index_info'))rows=['platform','account_id','job_id'].map(name=>({name}));else assert.fail('unexpected SQL');
 result=[{success:true,meta:{changed_db:false,rows_written:0},results:rows}];
 }
 return new Response(JSON.stringify({success:true,result,...extra}));
 }};}
test('backend read audit uses eleven bounded calls, no Worker or mutation SQL and no token metadata',async()=>{const f=fixture();const r=await inspectBackendSchema(env,f.fetcher);assert.equal(r.pass,true);assert.equal(r.external_api_calls,11);assert.equal(r.get_calls,4);assert.equal(r.read_query_post_calls,7);assert.equal(r.d1_writes,0);assert(!JSON.stringify(r).includes('PRIVATE'));assert(f.calls.every(([u])=>!u.includes('/workers/')));});
test('audit context rerun and wrong flags deny before credential use',async()=>{for(const d of [{GITHUB_RUN_ATTEMPT:'2'},{PLM_BACKEND_SCHEMA_AUDIT_MESSAGE:'wrong'},{NO_PUBLISH:'false'}]){const f=fixture();const r=await inspectBackendSchema({...env,...d},f.fetcher).catch(()=>null);assert.equal(f.calls.length,0);assert(r===null||r.pass===false);}});
test('backend index mismatch stops without retry',async()=>{const f=fixture('index');const r=await inspectBackendSchema(env,f.fetcher);assert.equal(r.pass,false);assert.equal(f.calls.length,11);});
test('read timeout does not retry or fallback',async()=>{const f=fixture('timeout');const r=await inspectBackendSchema(env,f.fetcher);assert.equal(r.pass,false);assert.equal(f.calls.length,1);assert(!JSON.stringify(r).includes('PRIVATE'));});
