// One authorized Read credential audit; no SQL mutation or credential fallback.
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {diagnose,ACCOUNT,DB,BRANCH} from './read-only-diagnostic.mjs';
export const AUDIT_MESSAGE='PLM post-migration read-only audit 20261003-r1';
export async function inspectAfterMigration(env,fetcher=fetch){
 const out={mode:'POST_MIGRATION_READ_ONLY',external_api_calls:0,d1_writes:0,deploy:0,live_jobs:0,render_executions:0,migration_permitted:false,posting_permitted:false,live_ready:false};
 if(env.GITHUB_RUN_ATTEMPT!=='1'||env.PLM_POST_MIGRATION_AUDIT_MESSAGE!==AUDIT_MESSAGE||!/^[a-f0-9]{40}$/.test(env.GITHUB_SHA||'')||env.GITHUB_REF!==`refs/heads/${BRANCH}`||env.GITHUB_REPOSITORY!=='ikkinotako2-sketch/project-love-machine-serverless-sandbox'||env.GITHUB_EVENT_NAME!=='push'||['TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP'].some(k=>env[k]!=='true'))throw Error('audit_context_rejected');
 out.migration_write_secret_present=env.PLM_MIGRATION_WRITE_SECRET_PRESENT==='true';
 if(env.PLM_MIGRATION_WRITE_SECRET_PRESENT!=='false')throw Error('write_secret_absence_not_confirmed');
 const receipt=JSON.parse(readFileSync(new URL('../readiness/MIGRATION_RECEIPT_37063527954.json',import.meta.url),'utf8'));
 if(receipt.run_id!==37063527954||receipt.remote_write_attempts!==1||receipt.resends!==0||receipt.sql_sha256!=='ac01f6d9d7eac877b802688d4f1d3c4dd40e8940876ed3ce0dc441c10297d0e2')throw Error('receipt_mismatch');
 const read=await diagnose({...env,PLM_CF_D1_READ_TOKEN_KIND:'user',PLM_MIGRATION_PREFLIGHT:'true'},fetcher);
 out.external_api_calls=read.external_api_calls;out.d1=read;
 out.receipt={id:receipt.receipt_id,run_id:receipt.run_id,commit:receipt.commit,sql_sha256:receipt.sql_sha256};
 const before=receipt.events[0].precheck.read_evidence.current_schema;
 out.preexisting_schema_unchanged=Array.isArray(read.current_schema)&&JSON.stringify(read.current_schema.filter(x=>x.name!=='test_jobs'))===JSON.stringify(before);
 out.test_jobs_table_count=read.current_schema?.filter(x=>x.type==='table'&&x.name==='test_jobs').length??null;
 out.d1_pass=read.schema==='PASS_EMPTY'&&read.row_count===0&&out.test_jobs_table_count===1&&out.preexisting_schema_unchanged&&read.inventory==='COMPLETE'&&read.d1_count===1&&read.other_d1_count===0&&read.time_travel==='BOOKMARK_READ_CONFIRMED';
 if(!out.d1_pass){out.stop_reason='D1_RECONCILIATION_REQUIRED_NO_RETRY';return out;}
 // Official List Worker Scripts: one GET only; never follow a denied/unknown endpoint.
 out.external_api_calls++;out.worker={name:'plm-serverless-sandbox-control',status:'UNVERIFIED',attempts:1};
 try{
  const r=await fetcher(`https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}/workers/scripts`,{method:'GET',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${env.PLM_CF_D1_READ_TOKEN}`}});
  out.worker.http_status=r.status;
  if(!r.ok){out.worker.status=r.status===403?'READ_PERMISSION_REQUIRED':'UNVERIFIED';out.stop_reason='WORKER_DASHBOARD_EVIDENCE_REQUIRED';return out;}
  const reader=r.body.getReader();let len=0,chunks=[];
  for(;;){const {done,value}=await reader.read();if(done)break;len+=value.length;if(len>131072){await reader.cancel();throw Error();}chunks.push(value);}
  const bytes=new Uint8Array(len);let offset=0;for(const c of chunks){bytes.set(c,offset);offset+=c.length;}
  const data=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
  if(data.success!==true||!Array.isArray(data.result)||data.result.some(x=>typeof x.id!=='string')||data.result_info?.total_pages>1)throw Error();
  const matches=data.result.filter(x=>x.id===out.worker.name);
  out.worker.status=matches.length===1?'EXISTS':matches.length===0?'ABSENT_IN_CONFIRMED_LIST':'UNVERIFIED';
  out.stop_reason='WORKER_NEXT_OWNER_GATE_REQUIRED';
 }catch{out.worker.status='UNKNOWN_NO_RETRY';out.stop_reason='MANUAL_RECONCILIATION_REQUIRED';}
 return out;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 try{const r=await inspectAfterMigration(process.env);console.log('PLM_POST_MIGRATION_EVIDENCE '+JSON.stringify(r));if(!r.d1_pass)process.exitCode=1;}
 catch{console.error('POST_MIGRATION_AUDIT_BLOCKED_NO_RETRY');process.exitCode=1;}
}
