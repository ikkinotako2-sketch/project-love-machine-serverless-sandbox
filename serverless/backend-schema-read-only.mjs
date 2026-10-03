// One owner-authorized D1 read audit; no Worker endpoint, mutation SQL or fallback.
import {pathToFileURL} from 'node:url';
import {diagnose,ACCOUNT,DB,BRANCH} from './read-only-diagnostic.mjs';
import {readBoundedContent} from './worker-content-parser.mjs';
export const MESSAGE='PLM backend schema read-only 20261003-r1';
export const QUERIES=['PRAGMA table_info(test_jobs)','PRAGMA index_list(test_jobs)','PRAGMA index_info(sqlite_autoindex_test_jobs_1)'];
export async function inspectBackendSchema(env,fetcher=fetch){
 if(env.GITHUB_RUN_ATTEMPT!=='1'||env.PLM_BACKEND_SCHEMA_AUDIT_MESSAGE!==MESSAGE||!/^[a-f0-9]{40}$/.test(env.GITHUB_SHA||''))throw Error('CONTEXT_REJECTED');
 const d=await diagnose({...env,PLM_CF_D1_READ_TOKEN_KIND:'user',PLM_MIGRATION_PREFLIGHT:'true'},fetcher);
 const out={mode:'BACKEND_SCHEMA_READ_ONLY',d1:d,external_api_calls:d.external_api_calls,get_calls:d.probes.filter(x=>!['schema_table','schema_columns','schema_count','full_schema_snapshot'].includes(x.stage)).length,read_query_post_calls:d.probes.filter(x=>['schema_table','schema_columns','schema_count','full_schema_snapshot'].includes(x.stage)).length,d1_writes:0,cloudflare_mutations:0,worker_calls:0,deploy:0,live_jobs:0,render:0,pass:false};
 if(d.authentication!=='ACTIVE'||d.database!=='ID_AND_NAME_MATCHED'||d.inventory!=='COMPLETE'||d.d1_count!==1||d.other_d1_count!==0||d.schema!=='PASS_EMPTY'||d.time_travel!=='BOOKMARK_READ_CONFIRMED')return {...out,failure_code:'BASE_SCHEMA_READ_UNCONFIRMED_NO_RETRY'};
 try{
  const results=[];
  for(const sql of QUERIES){
   out.external_api_calls++;out.read_query_post_calls++;
   const r=await fetcher(`https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}/d1/database/${DB}/query`,{method:'POST',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${env.PLM_CF_D1_READ_TOKEN}`,'Content-Type':'application/json'},body:JSON.stringify({sql,params:[]})});
   if(!r.ok)throw Error('READ_HTTP_REJECTED');
   const body=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(await readBoundedContent(r,{})));
   const q=body.result?.[0];if(body.success!==true||body.result.length!==1||q?.success!==true||!Array.isArray(q.results)||q.results.length>32||q.meta?.changed_db===true||q.meta?.rows_written>0)throw Error('READ_RESULT_REJECTED');results.push(q.results);
  }
  const [columns,indexes,index_columns]=results;
  const expected=['platform','account_id','job_id','content_fingerprint','claimant','state','version','last_operation','run_id','created_at','updated_at'];
  if(columns.length!==expected.length||columns.some((x,i)=>x.name!==expected[i])||indexes.length!==1||indexes[0].name!=='sqlite_autoindex_test_jobs_1'||indexes[0].unique!==1||indexes[0].origin!=='pk'||index_columns.map(x=>x.name).join(',')!=='platform,account_id,job_id')throw Error('INDEX_OR_COLUMNS_MISMATCH');
  out.columns=columns;out.indexes=indexes;out.index_columns=index_columns;out.pass=true;
 }catch{out.failure_code='EXTENDED_SCHEMA_READ_UNCONFIRMED_NO_RETRY';}
 return out;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){try{const r=await inspectBackendSchema(process.env);console.log('BACKEND_SCHEMA_READ_EVIDENCE '+JSON.stringify(r));if(!r.pass)process.exitCode=1;}catch{console.error('BACKEND_SCHEMA_READ_BLOCKED_NO_RETRY');process.exitCode=1;}}
