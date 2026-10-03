// Fixed read-only D1 audit. No write credential, Worker invocation or retry.
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {jsonBounded} from './d1-v2-migration.mjs';
export const CONTRACT=JSON.parse(readFileSync(new URL('./atomicity-schema-contract.json',import.meta.url)));
export const ACCOUNT='6c8ccd6aface937ab5dabef61cb64534', DB='18050cf6-934e-4f3a-a1cd-5041bac1c35e', NAME='plm-serverless-sandbox-state';
export const FLAGS=['TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP'];
export const REPO='ikkinotako2-sketch/project-love-machine-serverless-sandbox', BRANCH='plm-offline-readiness-v1-20261002';
export const canonical=x=>JSON.stringify(x,(_,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(k=>[k,v[k]])):v);
export const sha=x=>createHash('sha256').update(x).digest('hex');
export const READ_SQL=["SELECT type, name, tbl_name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name",'PRAGMA table_info(test_jobs)','SELECT COUNT(*) AS job_count FROM test_jobs','PRAGMA table_info(backend_probe_v1)','SELECT COUNT(*) AS probe_count FROM backend_probe_v1','PRAGMA index_list(backend_probe_v1)'];
const root=`https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}`, target=root+`/d1/database/${DB}`;
export function baseContext(e){return e.GITHUB_REPOSITORY===REPO&&e.GITHUB_REF===`refs/heads/${BRANCH}`&&e.GITHUB_RUN_ATTEMPT==='1'&&e.CLOUDFLARE_ACCOUNT_ID===ACCOUNT&&e.PLM_D1_DATABASE_ID===DB&&FLAGS.every(k=>e[k]==='true');}
export async function auditSchema(env,fetcher=fetch){
 const out={pass:false,external_api_calls:0,get_calls:0,read_query_post_calls:0,cloudflare_mutations:0,d1_writes:0,deploy:0,worker_invocation:0,live_jobs:0,render:0,posting:0,primary_reads_confirmed:true};
 if(!baseContext(env)||!env.PLM_CF_D1_READ_TOKEN)return {...out,failure_code:'READ_CONTEXT_REJECTED'};
 async function api(url,sql){out.external_api_calls++;sql===undefined?out.get_calls++:out.read_query_post_calls++;
  const r=await fetcher(url,{method:sql===undefined?'GET':'POST',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${env.PLM_CF_D1_READ_TOKEN}`,'Content-Type':'application/json'},...(sql===undefined?{}:{body:JSON.stringify({sql,params:[]})})});
  if(!r.ok)throw Error('READ_HTTP_REJECTED');const d=await jsonBounded(r);if(d.success!==true)throw Error('READ_RESPONSE_UNKNOWN');
  if(sql!==undefined){const q=d.result?.[0];if(d.result?.length!==1||q?.success!==true||!Array.isArray(q.results)||q.results.length>64||q.meta?.changed_db===true||q.meta?.rows_written>0)throw Error('READ_QUERY_REJECTED');out.primary_reads_confirmed&&=q.meta?.served_by_primary===true;return q.results;}return d;
 }
 try{
  const v=await api('https://api.cloudflare.com/client/v4/user/tokens/verify');if(v.result?.status!=='active')throw Error('READ_TOKEN_INACTIVE');out.token_active=true;out.read_token_owner='user';
  const all=[];let total;
  for(let p=1;p<=100;p++){const d=await api(root+`/d1/database?page=${p}&per_page=100`),i=d.result_info;if(!Array.isArray(d.result)||i?.page!==p||i.count!==d.result.length||!Number.isSafeInteger(i.total_count)||i.total_count<0||i.total_count>10000)throw Error('INVENTORY_PAGINATION_UNKNOWN');if(total===undefined)total=i.total_count;if(total!==i.total_count)throw Error('INVENTORY_CHANGED');all.push(...d.result);if(all.length===total)break;if(d.result.length===0||all.length>total||p===100)throw Error('INVENTORY_INCOMPLETE');}
  if(all.length!==1||all[0].uuid!==DB||all[0].name!==NAME)throw Error('INVENTORY_NOT_TARGET_ONLY');out.inventory={account:ACCOUNT,db_id:DB,db_name:NAME,total:1,other_d1:0,complete:true};
  const meta=await api(target);if(meta.result?.uuid!==DB||meta.result?.name!==NAME||!Number.isSafeInteger(meta.result.file_size)||meta.result.file_size<0)throw Error('DB_METADATA_UNCONFIRMED');out.database_size_bytes=meta.result.file_size;
  const values=[];for(const sql of READ_SQL)values.push(await api(target+'/query',sql));
  const [schema,columns,jobs,probe,rows,indexes]=values;
  const cleaned=schema.map(x=>({type:x.type,name:x.name,tbl_name:x.tbl_name,sql:typeof x.sql==='string'?x.sql.trim().replace(/;$/,''):null})).sort((a,b)=>(a.type+':'+a.name)<(b.type+':'+b.name)?-1:1);
  const snapshot={schema:cleaned,test_jobs_columns:columns,probe_columns:probe,probe_indexes:[...indexes].sort((a,b)=>a.name<b.name?-1:1)};
  if(sha(canonical(snapshot))!==CONTRACT.schema_fingerprint||canonical(snapshot)!==canonical(CONTRACT.snapshot)||jobs.length!==1||jobs[0].job_count!==0||rows.length!==1||rows[0].probe_count!==0)throw Error('SCHEMA_OR_ROW_DRIFT');
  const t=await api(target+'/time_travel/bookmark');if(!/^[a-f0-9-]{16,128}$/.test(t.result?.bookmark||''))throw Error('BOOKMARK_UNKNOWN');
  out.bookmark=t.result.bookmark;out.schema_fingerprint=CONTRACT.schema_fingerprint;out.snapshot=snapshot;out.probe_row_count=0;out.test_jobs_row_count=0;out.old_schema_unchanged=true;out.account_isolation='unverified';out.d1_isolation='COMPLETE_INVENTORY_TARGET_ONLY';out.pass=true;
 }catch(e){out.failure_code=['READ_HTTP_REJECTED','READ_RESPONSE_UNKNOWN','READ_QUERY_REJECTED','READ_TOKEN_INACTIVE','INVENTORY_PAGINATION_UNKNOWN','INVENTORY_CHANGED','INVENTORY_NOT_TARGET_ONLY','INVENTORY_INCOMPLETE','DB_METADATA_UNCONFIRMED','SCHEMA_OR_ROW_DRIFT','BOOKMARK_UNKNOWN'].includes(e.message)?e.message:'READ_ONLY_UNKNOWN_NO_RETRY';}
 return out;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){const e=process.env;if(e.PLM_AUDIT_PARENT!=='fd59bc72b3d41412d51ab403435da1db3bbcdf48'||e.PLM_AUDIT_MESSAGE!=='PLM atomicity preparation read-only audit 20261003-r1'||e.GITHUB_EVENT_NAME!=='push'){console.error('AUDIT_ACTIVATION_REJECTED');process.exitCode=1;}else{const r=await auditSchema(e);console.log('ATOMICITY_SCHEMA_AUDIT '+JSON.stringify(r));if(!r.pass)process.exitCode=1;}}
