// Read-only diagnostic. No writes, retry, deployment, job or raw response logs.
import {pathToFileURL} from 'node:url';
import {validateInspection} from './d1-setup.mjs';
export const ACCOUNT='6c8ccd6aface937ab5dabef61cb64534';
export const DB='18050cf6-934e-4f3a-a1cd-5041bac1c35e';
export const BRANCH='plm-offline-readiness-v1-20261002';
const NAME='plm-serverless-sandbox-state';
const ROOT='https://api.cloudflare.com/client/v4';
const FLAGS=['TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP'];
const SQL=["SELECT sql FROM sqlite_master WHERE type='table' AND name='test_jobs'",'PRAGMA table_info(test_jobs)','SELECT COUNT(*) AS job_count FROM test_jobs'];
export async function diagnose(env,fetcher=fetch) {
  const report={mode:'READ_ONLY_DIAGNOSTIC',authentication:'UNVERIFIED',account:'UNVERIFIED',inventory:'UNVERIFIED',schema:'UNVERIFIED',worker:'UNVERIFIED',free_plan:'UNVERIFIED',migration_required:'UNVERIFIED',account_isolation:'unverified',external_api_calls:0,render_executions:0,cloudflare_mutations:0,live_jobs:0,probes:[]};
  function stop(reason){report.stop_reason=reason;return report;}
  if(env.GITHUB_REPOSITORY!=='ikkinotako2-sketch/project-love-machine-serverless-sandbox'||env.GITHUB_REF!==`refs/heads/${BRANCH}`||env.GITHUB_EVENT_NAME!=='push'||FLAGS.some(k=>env[k]!=='true'))return stop('CONTEXT_OR_FLAGS_REJECTED');
  if(env.CLOUDFLARE_ACCOUNT_ID!==ACCOUNT||env.PLM_D1_DATABASE_ID!==DB||env.PLM_CF_ACCOUNT_ISOLATION!=='unverified')return stop('IDENTIFIERS_OR_ISOLATION_REJECTED');
  const token=env.PLM_CF_D1_READ_TOKEN;
  if(typeof token!=='string'||!token||/[\r\n]/.test(token))return stop('READ_CREDENTIAL_REQUIRED');
  async function api(stage,path,sql) {
    // All paths are generated internally. Fixed SELECT/PRAGMA only for POST.
    if(sql!==undefined&&!SQL.includes(sql))throw Error('SQL_NOT_ALLOWED');
    let response,data; report.external_api_calls++;
    const observation={stage};report.probes.push(observation);
    try {response=await fetcher(ROOT+path,{method:sql===undefined?'GET':'POST',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},...(sql===undefined?{}:{body:JSON.stringify({sql,params:[]})})});}
    catch {observation.status='UNKNOWN';throw Error('READ_RESPONSE_UNKNOWN_NO_RETRY');}
    observation.http_status=Number.isInteger(response.status)&&response.status>=100&&response.status<=599?response.status:null;
    try {
      // Bound memory before JSON parsing; production response never persisted.
      const reader=response.body.getReader();let size=0,chunks=[];
      for(;;){const {done,value}=await reader.read();if(done)break;size+=value.byteLength;if(size>131072){await reader.cancel();throw Error();}chunks.push(value);}
      const bytes=new Uint8Array(size);let offset=0;for(const c of chunks){bytes.set(c,offset);offset+=c.byteLength;}
      data=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
    }catch {observation.status='UNCONFIRMED';throw Error('READ_BODY_UNCONFIRMED_NO_RETRY');}
    observation.error_codes=Array.isArray(data?.errors)?data.errors.slice(0,5).map(x=>x?.code).filter(x=>Number.isSafeInteger(x)&&x>=1000&&x<=999999):[];
    observation.status=response.ok&&data?.success===true?'PASS':'REJECTED';
    return {ok:observation.status==='PASS',http:response.status,data};
  }
  const base=`/accounts/${ACCOUNT}`;
  try {
    const accountAuth=await api('account_token_verify',base+'/tokens/verify');
    let auth=accountAuth;
    if(!accountAuth.ok) {
      // One DIFFERENT ownership verification, only after a definitive 4xx.
      // This is not a retry or mutation and never follows an unknown response.
      if(![400,401,403].includes(accountAuth.http))return stop('ACCOUNT_AUTH_REJECTED');
      auth=await api('user_token_type_diagnostic','/user/tokens/verify');
      if(!auth.ok)return stop('CREDENTIAL_REJECTED');
      report.token_kind='USER_TOKEN_ACCOUNT_VERIFY_INCOMPATIBLE';
    }else report.token_kind='ACCOUNT_TOKEN';
    if(auth.data.result?.status!=='active')return stop('TOKEN_NOT_ACTIVE');
    report.authentication='ACTIVE';
    let inventory=[],total=null;const seen=new Set();
    for(let page=1;page<=100;page++) {
      const response=await api('d1_inventory_page_'+page,base+`/d1/database?page=${page}&per_page=100`);
      if(!response.ok)return stop('D1_INVENTORY_DENIED');
      const list=response.data.result,info=response.data.result_info;
      if(!Array.isArray(list)||!info||info.page!==page||!Number.isSafeInteger(info.total_count)||info.total_count<0||info.total_count>10000||info.count!==list.length||list.length>100)return stop('PAGINATION_UNCONFIRMED');
      if(total!==null&&total!==info.total_count)return stop('INVENTORY_CHANGED');total=info.total_count;
      for(const row of list){if(typeof row?.uuid!=='string'||!/^[-a-f0-9]{36}$/.test(row.uuid)||seen.has(row.uuid))return stop('INVENTORY_ID_UNCONFIRMED');seen.add(row.uuid);inventory.push({uuid:row.uuid,target:row.uuid===DB&&row.name===NAME});}
      if(inventory.length===total){report.inventory_pages=page;break;}
      if(inventory.length>total||!list.length||page===100)return stop('PAGINATION_INCOMPLETE');
    }
    report.inventory='COMPLETE';report.d1_count=inventory.length;report.d1_ids=inventory.map(x=>x.uuid);report.account='D1_ACCESS_CONFIRMED_AT_EXACT_ACCOUNT';
    report.other_d1_count=inventory.filter(x=>x.uuid!==DB).length;
    if(report.other_d1_count>0)return stop('OTHER_D1_POTENTIALLY_PROTECTED_NO_WRITE');
    if(inventory.length!==1||!inventory[0].target)return stop('TARGET_D1_MISSING_OR_ID_NAME_MISMATCH');
    report.database='ID_AND_NAME_MATCHED';report.database_purpose='SANDBOX_NAME_MATCH_ONLY';
    const get=await api('target_d1_metadata',base+`/d1/database/${DB}`);
    if(!get.ok||get.data.result?.uuid!==DB||get.data.result?.name!==NAME)return stop('TARGET_METADATA_MISMATCH_OR_DENIED');
    const bytes=get.data.result.file_size;report.database_size_bytes=Number.isSafeInteger(bytes)&&bytes>=0?bytes:null;
    async function query(stage,sql){const r=await api(stage,base+`/d1/database/${DB}/query`,sql);if(!r.ok||!Array.isArray(r.data.result)||r.data.result.length!==1||r.data.result[0].success!==true||!Array.isArray(r.data.result[0].results))throw Error('SCHEMA_READ_DENIED_OR_UNCONFIRMED');const meta=r.data.result[0].meta;if(meta?.changed_db===true||meta?.rows_written>0)throw Error('UNEXPECTED_WRITE_METADATA_STOP');return r.data.result[0].results;}
    const tables=await query('schema_table',SQL[0]);
    if(tables.length===0){report.schema='MISSING';report.row_count=null;report.migration_required=true;}
    else if(tables.length===1){
      const columns=await query('schema_columns',SQL[1]);const counts=await query('schema_count',SQL[2]);
      const count=counts[0]?.job_count;report.row_count=Number.isSafeInteger(count)&&count>=0?count:null;
      try{validateInspection({tableSql:tables[0].sql,columns,jobCount:count});report.schema='PASS_EMPTY';report.migration_required=false;}
      catch {report.schema='MISMATCH_OR_EXISTING_ROWS';return stop('SCHEMA_REQUIRES_RECONCILIATION');}
    }else return stop('SCHEMA_UNCONFIRMED');
    const worker=await api('exact_worker_settings',base+'/workers/scripts/plm-serverless-sandbox-control/settings');
    report.worker=worker.ok?'EXISTS':worker.http===404?'NOT_FOUND_RESPONSE':worker.http===403?'READ_PERMISSION_REQUIRED':'UNVERIFIED';
    // Do not copy settings, binding values or Secret metadata into evidence.
    report.stop_reason=report.migration_required?'MIGRATION_APPROVAL_AND_ISOLATION_REQUIRED':'READ_ONLY_COMPLETE_MORE_LIVE_GATES_REQUIRED';
    return report;
  }catch {return stop('READ_DIAGNOSTIC_UNCONFIRMED_NO_RETRY');}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
  try {const report=await diagnose(process.env);console.log('PLM_READ_ONLY_EVIDENCE '+JSON.stringify(report));if(report.authentication!=='ACTIVE'||report.inventory!=='COMPLETE')process.exitCode=1;}
  catch {console.error('PLM_READ_ONLY_DIAGNOSTIC_BLOCKED');process.exitCode=1;}
}
