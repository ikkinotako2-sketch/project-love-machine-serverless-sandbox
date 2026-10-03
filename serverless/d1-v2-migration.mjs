// Prepared schema migration only. CLI defaults to read-only; workflow mutation is retired/disabled.
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {inspectBackendSchema} from './backend-schema-read-only.mjs';
import {ACCOUNT,DB,BRANCH} from './read-only-diagnostic.mjs';
import {verificationUrl,REPO} from './cloudflare-setup.mjs';
export const SQL_SHA='ca2ee1a2c618c5f71b43ade4620d9ded3eb105282be9a610c492632fec59fdc3';
export const MESSAGE='PLM D1 v2 final read-only preflight 20261003-r1';
export const APPROVED_PARENT='75113cc2e7d08cd708b1fe4399cc66c463cfb5c1';
const ROOT=`https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}`;
const TARGET=ROOT+`/d1/database/${DB}`;
const FLAGS=['TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP'];
const NAME='plm-serverless-sandbox-state';
const BASE=JSON.parse(readFileSync(new URL('../readiness/BACKEND_SCHEMA_READ_RECEIPT_37093009614.json',import.meta.url))).evidence;
export const EXPECTED=JSON.parse(readFileSync(new URL('./d1-v2-expected-post.json',import.meta.url)));
const hash=x=>createHash('sha256').update(x).digest('hex');
export function candidate(raw=readFileSync(new URL('./migrations/0002_backend_probe_v1.sql',import.meta.url))){
 if(hash(raw)!==SQL_SHA)throw Error('SQL_HASH_MISMATCH');
 // Exact approved bytes, not a general SQL classifier. Trigger BEGIN/END belongs to DDL 2.
 return {raw,sql:new TextDecoder('utf-8',{fatal:true}).decode(raw),sql_sha256:SQL_SHA,create_table:1,create_trigger:1,destructive_statements:0,alter:0,rename:0,existing_test_jobs_changes:0,migration_0001_executions:0};
}
function context(env){
 return env.GITHUB_REPOSITORY===REPO&&env.GITHUB_REF===`refs/heads/${BRANCH}`&&env.GITHUB_EVENT_NAME==='push'&&env.GITHUB_RUN_ATTEMPT==='1'&&/^[a-f0-9]{40}$/.test(env.GITHUB_SHA||'')&&/^\d+$/.test(env.GITHUB_RUN_ID||'')&&env.CLOUDFLARE_ACCOUNT_ID===ACCOUNT&&env.PLM_D1_DATABASE_ID===DB&&env.PLM_CF_ACCOUNT_ISOLATION==='unverified'&&FLAGS.every(k=>env[k]==='true');
}
export function readContext(env){return context(env)&&env.PLM_V2_PREFLIGHT_PARENT===APPROVED_PARENT&&env.PLM_V2_PREFLIGHT_MESSAGE===MESSAGE;}
export function executionContext(env){return context(env)&&env.PLM_D1_V2_MIGRATION_ALLOW==='true'&&env.PLM_D1_V2_OWNER_APPROVAL==='MIGRATE_FIXED_SCHEMA_V2_ONCE'&&env.GITHUB_SHA===env.PLM_D1_V2_APPROVED_COMMIT&&/^[a-f0-9]{40}$/.test(env.PLM_D1_V2_APPROVED_COMMIT||'')&&env.PLM_D1_V2_SQL_SHA===SQL_SHA;}
function secret(token){return typeof token==='string'&&token.length>0&&token.length<=4096&&!/[\r\n]/.test(token);}
function cleanSql(s){return typeof s==='string'?s.trim().replace(/;$/,''):null;}
function schemaEqual(a,b){
 const clean=x=>x.map(y=>({type:y.type,name:y.name,tbl_name:y.tbl_name,sql:cleanSql(y.sql)})).sort((x,y)=>(x.type+':'+x.name).localeCompare(y.type+':'+y.name));
 return Array.isArray(a)&&Array.isArray(b)&&JSON.stringify(clean(a))===JSON.stringify(clean(b));
}
export async function jsonBounded(r,max=131072){
 const reader=r.body?.getReader();if(!reader)throw Error('RESPONSE_PARSE_UNKNOWN');let size=0,chunks=[];
 for(;;){const {done,value}=await reader.read();if(done)break;size+=value.byteLength;if(size>max){await reader.cancel();throw Error('RESPONSE_TOO_LARGE');}chunks.push(value);}
 const bytes=new Uint8Array(size);let n=0;for(const c of chunks){bytes.set(c,n);n+=c.byteLength;}
 return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
}
export function validateBefore(r){
 if(r.pass!==true||r.d1.authentication!=='ACTIVE'||r.d1.account!=='D1_ACCESS_CONFIRMED_AT_EXACT_ACCOUNT'||r.d1.inventory!=='COMPLETE'||r.d1.d1_count!==1||r.d1.other_d1_count!==0||JSON.stringify(r.d1.d1_ids)!==JSON.stringify([DB])||r.d1.database!=='ID_AND_NAME_MATCHED'||r.d1.row_count!==0||r.d1.database_size_bytes!==BASE.d1.database_size_bytes||r.d1.time_travel!=='BOOKMARK_READ_CONFIRMED'||!schemaEqual(r.d1.current_schema,BASE.d1.current_schema)||JSON.stringify(r.columns)!==JSON.stringify(BASE.columns)||JSON.stringify(r.indexes)!==JSON.stringify(BASE.indexes)||JSON.stringify(r.index_columns)!==JSON.stringify(BASE.index_columns))throw Error('BEFORE_SCHEMA_OR_INVENTORY_CHANGED');
 if(r.d1.current_schema.some(x=>x.name==='backend_probe_v1'||x.name==='backend_probe_v1_guard'))throw Error('PROBE_ALREADY_EXISTS_NO_REEXECUTION');
 return true;
}
export async function preflight(env,fetcher=fetch,{execution=false,now=Date.now()}={}){
 const report={mode:'D1_V2_SCHEMA_READ_ONLY_PREFLIGHT',pass:false,token_kind:'ACCOUNT_TOKEN',token_scope_owner_evidence:true,token_scope_api_verified:false,migration_execution_approved:false,migration_permitted:false,account_isolation:'unverified',external_api_calls:0,get_calls:0,read_query_post_calls:0,cloudflare_mutations:0,d1_writes:0,deploy:0,worker_invocation:0,live_jobs:0,render:0,posting:0};
 const stop=code=>({...report,failure_code:code});
 if(!(execution?executionContext(env):readContext(env)))return stop('CONTEXT_REJECTED_NO_HTTP');
 try{
  const c=candidate();report.sql={sql_sha256:c.sql_sha256,create_table:1,create_trigger:1,destructive_statements:0,existing_test_jobs_changes:0,migration_0001_executions:0};
  const token=env.PLM_CF_D1_MIGRATION_V2_TOKEN;report.write_secret_present=secret(token);
  if(!report.write_secret_present||!secret(env.PLM_CF_D1_READ_TOKEN))return stop('CREDENTIAL_MISSING_NO_HTTP');
  report.get_calls++;report.external_api_calls++;
  const r=await fetcher(verificationUrl('account',ACCOUNT),{method:'GET',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${token}`}});
  report.verify_http_status=r.status;
  if(!r.ok)return stop('ACCOUNT_TOKEN_VERIFY_REJECTED_NO_FALLBACK');
  const d=await jsonBounded(r,16384);
  if(d.success!==true||d.result?.status!=='active')return stop('TOKEN_NOT_ACTIVE');
  const expires=d.result.expires_on;
  if(typeof expires!=='string'||!/^\d{4}-\d{2}-\d{2}T/.test(expires)||!Number.isFinite(Date.parse(expires))||Date.parse(expires)<=now)return stop('TOKEN_EXPIRY_UNVERIFIED_OR_EXPIRED');
  report.token_active=true;report.token_expires_at=new Date(expires).toISOString();
  // This exact function uses user-owned Read Token; Write token is removed.
  const clean={...env,PLM_CF_D1_MIGRATION_V2_TOKEN:undefined,PLM_BACKEND_SCHEMA_AUDIT_MESSAGE:'PLM backend schema read-only 20261003-r1'};
  const before=await inspectBackendSchema(clean,fetcher);
  report.before=before;report.external_api_calls+=before.external_api_calls;report.get_calls+=before.get_calls;report.read_query_post_calls+=before.read_query_post_calls;
  validateBefore(before);
  report.expected_post_schema={sql_sha256:EXPECTED.sql_sha256,table:'backend_probe_v1',table_count:1,column_count:EXPECTED.columns.length,trigger:'backend_probe_v1_guard',trigger_count:1,probe_row_count:0,old_schema_unchanged:true,inventory_unchanged:true,new_bookmark_required:true};
  report.d1_isolation='LATEST_COMPLETE_INVENTORY_TARGET_ONLY';report.checked_at=new Date(now).toISOString();report.pass=true;
  return report;
 }catch(e){return stop(['SQL_HASH_MISMATCH','BEFORE_SCHEMA_OR_INVENTORY_CHANGED','PROBE_ALREADY_EXISTS_NO_REEXECUTION','RESPONSE_TOO_LARGE'].includes(e?.message)?e.message:'READ_ONLY_UNKNOWN_NO_RETRY');}
}
const POST_QUERIES=["SELECT type, name, tbl_name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name",'PRAGMA table_info(test_jobs)','SELECT COUNT(*) AS job_count FROM test_jobs','PRAGMA table_info(backend_probe_v1)','SELECT COUNT(*) AS probe_count FROM backend_probe_v1','PRAGMA index_list(backend_probe_v1)'];
export async function postCheck(env,fetcher,before,counts){
 const token=env.PLM_CF_D1_READ_TOKEN;if(!secret(token))throw Error('READ_CREDENTIAL_REQUIRED');
 async function api(url,sql){
  if(sql!==undefined&&!POST_QUERIES.includes(sql))throw Error('POSTCHECK_SQL_REJECTED');
  counts.read++;if(sql===undefined)counts.get++;else counts.read_query_post++;
  const r=await fetcher(url,{method:sql===undefined?'GET':'POST',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},...(sql===undefined?{}:{body:JSON.stringify({sql,params:[]})})});
  if(!r.ok)throw Error('POSTCHECK_HTTP_UNKNOWN');const d=await jsonBounded(r);if(d.success!==true)throw Error('POSTCHECK_RESPONSE_UNKNOWN');
  if(sql!==undefined){const q=d.result?.[0];if(d.result?.length!==1||q?.success!==true||!Array.isArray(q.results)||q.meta?.changed_db===true||q.meta?.rows_written>0)throw Error('POSTCHECK_QUERY_UNKNOWN');return q.results;}return d;
 }
 // Single target at preflight; if inventory now expands stop immediately, never repair.
 const inv=await api(ROOT+'/d1/database?page=1&per_page=100');
 if(inv.result_info?.page!==1||inv.result_info?.count!==1||inv.result_info?.total_count!==1||inv.result?.length!==1||inv.result[0].uuid!==DB||inv.result[0].name!==NAME)throw Error('POSTCHECK_INVENTORY_CHANGED');
 const values=[];for(const sql of POST_QUERIES)values.push(await api(TARGET+'/query',sql));
 const [schema,columns,oldCount,probeColumns,probeCount,indexes]=values;
 const oldSchema=schema.filter(x=>!['backend_probe_v1','backend_probe_v1_guard'].includes(x.name));
 const added=schema.filter(x=>['backend_probe_v1','backend_probe_v1_guard'].includes(x.name));
 if(!schemaEqual(oldSchema,before.d1.current_schema)||!schemaEqual(added,EXPECTED.schema)||JSON.stringify(columns)!==JSON.stringify(BASE.columns)||JSON.stringify(probeColumns)!==JSON.stringify(EXPECTED.columns)||oldCount.length!==1||oldCount[0].job_count!==0||probeCount.length!==1||probeCount[0].probe_count!==0||JSON.stringify(indexes)!==JSON.stringify(EXPECTED.indexes))throw Error('POSTCHECK_SCHEMA_MISMATCH');
 const travel=await api(TARGET+'/time_travel/bookmark');const bookmark=travel.result?.bookmark;
 if(typeof bookmark!=='string'||!/^[a-f0-9-]{16,128}$/.test(bookmark)||bookmark===before.d1.pre_migration_bookmark)throw Error('POSTCHECK_NEW_BOOKMARK_UNCONFIRMED');
 return {pass:true,old_schema_unchanged:true,current_schema:schema,probe_columns:probeColumns,probe_indexes:indexes,probe_row_count:0,test_jobs_row_count:0,inventory_unchanged:true,bookmark,remote_atomicity:'UNVERIFIED'};
}
const consumed=new Set();
export async function migrateSchemaOnce(env,fetcher,approvedReceipt,{historyClear=false,journal}={}){
 const out={mode:'D1_V2_SCHEMA_ONLY_ONCE',status:'BLOCKED',mutation_requests:0,d1_row_mutations:0,retry:0,fallback:0,deploy:0,worker_invocation:0,live_jobs:0,render:0,posting:0,live_ready:false,posting_permitted:false,read:0,get:0,read_query_post:0,manual_reconciliation_required:false,owner_token_revocation_required:true};
 if(!executionContext(env)||historyClear!==true||!journal||typeof journal.reserve!=='function'||approvedReceipt?.pass!==true||approvedReceipt?.sql?.sql_sha256!==SQL_SHA||consumed.has(env.GITHUB_SHA))return out;
 try{
  validateBefore(approvedReceipt.before);const c=candidate();
  const fresh=await preflight(env,fetcher,{execution:true});out.preflight=fresh;out.read+=fresh.external_api_calls;out.get+=fresh.get_calls;out.read_query_post+=fresh.read_query_post_calls;
  if(!fresh.pass||!schemaEqual(fresh.before.d1.current_schema,approvedReceipt.before.d1.current_schema))return out;
  consumed.add(env.GITHUB_SHA);journal.reserve({sql_sha256:SQL_SHA,run_id:env.GITHUB_RUN_ID,commit:env.GITHUB_SHA,status:'SENT_BEFORE_HTTP'});
  out.mutation_requests=1;out.status='UNKNOWN';out.manual_reconciliation_required=true;
  try{
   const r=await fetcher(TARGET+'/query',{method:'POST',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${env.PLM_CF_D1_MIGRATION_V2_TOKEN}`,'Content-Type':'application/json'},body:JSON.stringify({sql:c.sql,params:[]})});
   out.http_status=r.status;const d=await jsonBounded(r);
   if(r.ok&&d.success===true&&Array.isArray(d.result)&&d.result.length>0&&d.result.length<=2&&d.result.every(x=>x.success===true)){out.status='ACKNOWLEDGED_NEEDS_POSTCHECK';}
  }catch{/* Never retry. Only bounded read-only reconciliation below. */}
  try{out.post=await postCheck(env,fetcher,fresh.before,out);if(out.status==='ACKNOWLEDGED_NEEDS_POSTCHECK'&&out.post.pass){out.status='SUCCESS';out.manual_reconciliation_required=false;}else out.reconciliation='EXPECTED_SCHEMA_PRESENT_BUT_RESPONSE_UNKNOWN';}
  catch{out.reconciliation='POSTCHECK_UNCONFIRMED_STOP';out.status='UNKNOWN';}
  return out;
 }catch{out.status=out.mutation_requests?'UNKNOWN':'BLOCKED';out.manual_reconciliation_required=out.mutation_requests===1;return out;}
}
// Default executable path is preflight only. No CLI migration mode exists in this preparation.
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 try{const r=await preflight(process.env);console.log('D1_V2_PREFLIGHT_EVIDENCE '+JSON.stringify(r));if(!r.pass)process.exitCode=1;}
 catch{console.error('D1_V2_PREFLIGHT_UNKNOWN_NO_RETRY');process.exitCode=1;}
}
export function exclusiveJournal(path){return {reserve:e=>writeFileSync(path,JSON.stringify(e)+'\n',{flag:'wx',mode:0o600})};}
