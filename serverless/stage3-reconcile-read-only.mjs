import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {ACCOUNT,DB,NAME,REPO,baseContext,canonical,sha,CONTRACT} from './atomicity-schema-audit.mjs';
import {EXPECTED} from './durable-stage2-contract.mjs';
import {FINAL_ROW} from './post-atomicity-read-only.mjs';
import {jsonBounded} from './d1-v2-migration.mjs';
export const MESSAGE='PLM stage3 manual read-only reconciliation 20261003-r1';
const norm=s=>s.map(x=>({...x,sql:typeof x.sql==='string'?x.sql.trim().replace(/;$/,''):null})).sort((a,b)=>(a.type+':'+a.name)<(b.type+':'+b.name)?-1:1);
export function classify(schema,details,oldUnchanged,{expected:expectation=EXPECTED}={}){
 const expected=new Map(expectation.schema.map(x=>[x.name,x]));const found=schema.filter(x=>expected.has(x.name));
 const objects=EXPECTED.schema.map(x=>({type:x.type,name:x.name,exists:found.some(y=>y.name===x.name&&y.type===x.type)}));
 if(!oldUnchanged)return {classification:'STILL_UNKNOWN',objects};
 if(!found.length)return {classification:'NOT_APPLIED',objects};
 if(found.length<expected.size)return {classification:'PARTIAL_APPLIED',objects};
 if(canonical(norm(found))!==canonical(norm(expectation.schema)))return {classification:'STILL_UNKNOWN',objects};
 if(Object.keys(expectation.columns).some(t=>!details[t]?.canonical_match||details[t].row_count!==0))return {classification:'STILL_UNKNOWN',objects};
 return {classification:'FULL_APPLIED',objects};
}
export async function reconcileStage3(e,fetcher=fetch,{expected:expectation=EXPECTED}={}){
 const out={classification:'STILL_UNKNOWN',pass:false,cloudflare_api_calls:0,get_calls:0,read_query_post_calls:0,d1_mutation:0,d1_write:0,worker_deploy:0,worker_invocation:0,ai_api:0,render:0,posting:0,retry:0,resend:0,fallback:0,live_ready:false,posting_permitted:false};
 if(!baseContext(e)||e.GITHUB_EVENT_NAME!=='push'||e.PLM_RECONCILE_MESSAGE!==MESSAGE||e.PLM_RECONCILE_BEFORE!==e.PLM_RECONCILE_CODE_PIN||!/^[a-f0-9]{40}$/.test(e.PLM_RECONCILE_CODE_PIN||'')||!e.PLM_CF_D1_READ_TOKEN||[e.PLM_CF_D1_STAGE3_MIGRATION_TOKEN,e.PLM_CF_D1_STAGE2_TEST_TOKEN,e.PLM_CF_WORKER_API_TOKEN].some(Boolean))return {...out,failure_code:'RECONCILE_CONTEXT_REJECTED_NO_HTTP'};
 const base=`https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}/d1/database`,target=base+'/'+DB;
 async function api(url,sql){out.cloudflare_api_calls++;sql?out.read_query_post_calls++:out.get_calls++;
  if(sql&&!/^(SELECT|PRAGMA)\b/.test(sql))throw Error('RECONCILE_NON_READ_SQL_REJECTED');
  const r=await fetcher(url,{method:sql?'POST':'GET',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${e.PLM_CF_D1_READ_TOKEN}`,'Content-Type':'application/json'},...(sql?{body:JSON.stringify({sql,params:[]})}:{})});if(!r.ok)throw Error('RECONCILE_HTTP_REJECTED');const b=await jsonBounded(r);if(b.success!==true)throw Error('RECONCILE_RESPONSE_UNKNOWN');
  if(!sql)return b;const q=b.result?.[0];if(b.result?.length!==1||q?.success!==true||!Array.isArray(q.results)||q.meta?.served_by_primary!==true||q.meta?.rows_written>0||q.meta?.changed_db===true)throw Error('RECONCILE_PRIMARY_READ_UNKNOWN');return q.results;
 }
 try{
  const v=await api('https://api.cloudflare.com/client/v4/user/tokens/verify');if(v.result?.status!=='active')throw Error('RECONCILE_READ_TOKEN_INACTIVE');
  const inv=[];let total;for(let p=1;p<=100;p++){const b=await api(base+`?page=${p}&per_page=100`);if(!Array.isArray(b.result)||b.result_info?.page!==p||b.result_info.count!==b.result.length||!Number.isSafeInteger(b.result_info.total_count))throw Error('RECONCILE_INVENTORY_UNKNOWN');if(total===undefined)total=b.result_info.total_count;if(total!==b.result_info.total_count)throw Error('RECONCILE_INVENTORY_CHANGED');inv.push(...b.result);if(inv.length===total)break;if(!b.result.length||p===100)throw Error('RECONCILE_INVENTORY_INCOMPLETE');}
  if(inv.length!==1||inv[0].uuid!==DB||inv[0].name!==NAME)throw Error('RECONCILE_INVENTORY_NOT_TARGET_ONLY');out.inventory={account:ACCOUNT,db_id:DB,db_name:NAME,total:1,other_d1:0,complete:true};
  const m=await api(target);if(m.result?.uuid!==DB||m.result?.name!==NAME||!Number.isSafeInteger(m.result.file_size))throw Error('RECONCILE_DB_METADATA_UNKNOWN');out.database_size_bytes=m.result.file_size;out.size_unchanged=m.result.file_size===40960;
  const schema=await api(target+'/query',"SELECT type, name, tbl_name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name");out.schema=norm(schema);
  const expectedNames=new Set(expectation.schema.map(x=>x.name));const old=schema.filter(x=>!expectedNames.has(x.name));
  const tc=await api(target+'/query','PRAGMA table_info(test_jobs)'),pc=await api(target+'/query','PRAGMA table_info(backend_probe_v1)'),pi=await api(target+'/query','PRAGMA index_list(backend_probe_v1)');
  const row=await api(target+'/query','SELECT * FROM backend_probe_v1'),jobs=await api(target+'/query','SELECT COUNT(*) AS n FROM test_jobs');
  out.old_schema_unchanged=canonical(norm(old))===canonical(norm(CONTRACT.snapshot.schema));out.old_columns_indexes_unchanged=canonical(tc)===canonical(CONTRACT.snapshot.test_jobs_columns)&&canonical(pc)===canonical(CONTRACT.snapshot.probe_columns)&&canonical([...pi].sort((a,b)=>a.name<b.name?-1:1))===canonical(CONTRACT.snapshot.probe_indexes);out.atomicity_row_unchanged=row.length===1&&canonical(row[0])===canonical(FINAL_ROW);out.atomicity_row=row.length===1?row[0]:null;out.test_jobs_unchanged=jobs.length===1&&jobs[0].n===0;out.kv_schema_unchanged=out.old_schema_unchanged;out.kv_content_verified=false;
  const details={};for(const t of Object.keys(expectation.columns)){if(!schema.some(x=>x.type==='table'&&x.name===t))continue;const c=await api(target+'/query','PRAGMA table_info('+t+')'),i=await api(target+'/query','PRAGMA index_list('+t+')'),r=await api(target+'/query','SELECT COUNT(*) AS n FROM '+t);if(r.length!==1||!Number.isSafeInteger(r[0].n))throw Error('RECONCILE_ROW_COUNT_UNKNOWN');details[t]={columns:c,indexes:i,row_count:r[0].n,canonical_match:canonical(c)===canonical(expectation.columns[t])&&canonical(i)===canonical(expectation.indexes[t])};}out.stage3_table_details=details;
  const b=await api(target+'/time_travel/bookmark');if(!/^[a-f0-9-]{16,128}$/.test(b.result?.bookmark||''))throw Error('RECONCILE_BOOKMARK_UNKNOWN');out.bookmark=b.result.bookmark;
  Object.assign(out,classify(schema,details,out.old_schema_unchanged&&out.old_columns_indexes_unchanged&&out.atomicity_row_unchanged&&out.test_jobs_unchanged,{expected:expectation}));out.pass=out.classification!=='STILL_UNKNOWN';out.canonical_before_schema_fingerprint=CONTRACT.schema_fingerprint;return out;
 }catch(err){return {...out,failure_code:/^RECONCILE_[A-Z_]+$/.test(err.message)?err.message:'RECONCILE_UNKNOWN_NO_RETRY'};}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){const head=readFileSync('.git/HEAD','utf8').trim();if(head!==process.env.PLM_RECONCILE_CODE_PIN){console.error('RECONCILE_CHECKOUT_PIN_REJECTED');process.exitCode=1;}else{const r=await reconcileStage3(process.env);console.log('STAGE3_MANUAL_RECONCILIATION '+JSON.stringify(r));if(!r.pass)process.exitCode=1;}}
