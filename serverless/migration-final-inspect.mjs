// Read-only final gate. Write credential can reach only account-owned GET verify.
import {pathToFileURL} from 'node:url';
import {diagnose,ACCOUNT,DB,BRANCH} from './read-only-diagnostic.mjs';
import {verificationUrl,REPO} from './cloudflare-setup.mjs';
export function d1Isolation(report) {
  // Narrow proof: absence of other D1s, not isolation of Workers/bindings/account.
  return report.authentication==='ACTIVE' && report.account==='D1_ACCESS_CONFIRMED_AT_EXACT_ACCOUNT'
    && report.inventory==='COMPLETE' && report.d1_count===1 && report.other_d1_count===0
    && JSON.stringify(report.d1_ids)===JSON.stringify([DB]) && report.database==='ID_AND_NAME_MATCHED'
    && report.schema==='MISSING' && Array.isArray(report.current_schema)
    && report.current_schema.every(x=>x.type==='table'&&x.name==='_cf_KV'&&x.tbl_name==='_cf_KV');
}
export async function finalInspect(env,fetcher=fetch) {
  const report={mode:'FINAL_MIGRATION_READ_ONLY',write_secret_present:false,write_token_owner:'account',write_token_active:false,write_scope_api_verified:false,remote_write_calls:0,migration_executions:0,external_api_calls:0,migration_execution_approved:false,migration_permitted:false,account_isolation:'unverified'};
  const stop=reason=>({...report,stop_reason:reason});
  if(env.GITHUB_REPOSITORY!==REPO||env.GITHUB_REF!==`refs/heads/${BRANCH}`||env.GITHUB_EVENT_NAME!=='push'||env.CLOUDFLARE_ACCOUNT_ID!==ACCOUNT||env.PLM_D1_DATABASE_ID!==DB||env.PLM_CF_ACCOUNT_ISOLATION!=='unverified'||['TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP'].some(k=>env[k]!=='true'))return stop('CONTEXT_FLAGS_OR_IDENTIFIERS_REJECTED');
  const token=env.PLM_CF_D1_API_TOKEN;
  report.write_secret_present=typeof token==='string'&&token.length>0&&!/[\r\n]/.test(token);
  if(!report.write_secret_present)return stop('WRITE_SECRET_REQUIRED');
  try {
    report.external_api_calls++;
    const r=await fetcher(verificationUrl('account',ACCOUNT),{method:'GET',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'}});
    report.write_verify_http_status=r.status;
    if(!r.ok)return stop('ACCOUNT_WRITE_VERIFY_REJECTED_NO_FALLBACK');
    const reader=r.body.getReader();let bytes=0,chunks=[];
    for(;;){const {done,value}=await reader.read();if(done)break;bytes+=value.byteLength;if(bytes>16384){await reader.cancel();return stop('ACCOUNT_WRITE_VERIFY_BODY_UNCONFIRMED');}chunks.push(value);}
    const combined=new Uint8Array(bytes);let off=0;for(const c of chunks){combined.set(c,off);off+=c.length;}
    const data=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(combined));
    if(data?.success!==true||data.result?.status!=='active')return stop('ACCOUNT_WRITE_TOKEN_NOT_ACTIVE');
    const expiry=data.result.expires_on;
    if(expiry!==undefined&&expiry!==null){
      if(typeof expiry!=='string'||!/^\d{4}-\d{2}-\d{2}T/.test(expiry)||!Number.isFinite(Date.parse(expiry))||Date.parse(expiry)<=Date.now())return stop('WRITE_EXPIRY_UNCONFIRMED_OR_EXPIRED');
      report.write_token_expires_at=new Date(expiry).toISOString();
    }else report.write_token_expiry='NOT_RETURNED_IMMEDIATE_OWNER_REVOCATION_REQUIRED';
    report.write_token_active=true;
  }catch{return stop('ACCOUNT_WRITE_VERIFY_UNKNOWN_NO_RETRY');}
  // Read-only inventory/schema/bookmark uses only the Read token. Strip Write.
  const read=await diagnose({...env,PLM_CF_D1_API_TOKEN:undefined,PLM_CF_D1_READ_TOKEN_KIND:'user',PLM_MIGRATION_PREFLIGHT:'true'},fetcher);
  report.external_api_calls+=read.external_api_calls;report.read_evidence=read;
  report.d1_isolation=d1Isolation(read)?'SINGLE_TARGET_D1_VERIFIED':'UNVERIFIED_OR_PROTECTED';
  report.read_preconditions_pass=report.d1_isolation==='SINGLE_TARGET_D1_VERIFIED'&&read.time_travel==='BOOKMARK_READ_CONFIRMED'&&read.sql?.destructive_statements===0;
  return stop(report.read_preconditions_pass?'OWNER_SCOPE_EVIDENCE_AND_FINAL_EXECUTION_APPROVAL_REQUIRED':'READ_PRECONDITIONS_NOT_MET');
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
  try{const r=await finalInspect(process.env);console.log('PLM_FINAL_MIGRATION_EVIDENCE '+JSON.stringify(r));if(!r.write_token_active||!r.read_preconditions_pass)process.exitCode=1;}
  catch{console.error('PLM_FINAL_MIGRATION_INSPECT_BLOCKED_NO_RETRY');process.exitCode=1;}
}
