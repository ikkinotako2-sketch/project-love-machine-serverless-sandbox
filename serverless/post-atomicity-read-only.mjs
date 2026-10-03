// One post-cleanup Read Token audit. The old completed row is evidence, never reset.
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {auditSchema,ACCOUNT,DB,canonical,sha} from './atomicity-schema-audit.mjs';
import {jsonBounded} from './d1-v2-migration.mjs';
import {READ_ROW,PLAN} from './atomicity-test.mjs';
export const MESSAGE='PLM post atomicity cleanup read-only audit 20261003-r1';
export const PARENT='36c263a7e7f96e8c66a74ebe9c2bb21c4305c6a3';
const RECEIPT=readFileSync(new URL('../audit-evidence/atomicity-test-once-receipt-37101718265.json',import.meta.url));
export const SUCCESS_RECEIPT_SHA=sha(RECEIPT);
export const FINAL_ROW=JSON.parse(RECEIPT).evidence.final_row;
export async function postAtomicityAudit(e,fetcher=fetch){
 if(e.PLM_POST_ATOMICITY_PARENT!==PARENT||e.PLM_POST_ATOMICITY_MESSAGE!==MESSAGE||e.GITHUB_EVENT_NAME!=='push'||e.PLM_CF_D1_ATOMICITY_TEST_TOKEN||e.PLM_CF_WORKER_API_TOKEN||e.PLM_CF_D1_MIGRATION_V2_TOKEN)return {pass:false,failure_code:'CONTEXT_REJECTED_NO_HTTP',external_api_calls:0,d1_writes:0};
 const a=await auditSchema(e,fetcher,{expectedProbeCount:1});if(!a.pass)return a;
 a.pass=false;a.success_receipt_sha256=SUCCESS_RECEIPT_SHA;
 try{a.external_api_calls++;a.read_query_post_calls++;
  const r=await fetcher(`https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}/d1/database/${DB}/query`,{method:'POST',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${e.PLM_CF_D1_READ_TOKEN}`,'Content-Type':'application/json'},body:JSON.stringify({sql:READ_ROW,params:[PLAN.identity.platform,PLAN.identity.account_id,PLAN.identity.intent_id]})});if(!r.ok)throw Error();const b=await jsonBounded(r);const q=b.result?.[0];if(b.success!==true||b.result?.length!==1||q?.success!==true||q.meta?.served_by_primary!==true||q.meta?.rows_written>0||q.meta?.changed_db===true||q.results?.length!==1||canonical(q.results[0])!==canonical(FINAL_ROW))throw Error();a.final_row=q.results[0];a.completed_atomicity_row_unchanged=true;a.pass=true;
 }catch{a.failure_code='FINAL_ROW_UNCONFIRMED_NO_RETRY';}return a;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){const r=await postAtomicityAudit(process.env);console.log('POST_ATOMICITY_AUDIT '+JSON.stringify(r));if(!r.pass)process.exitCode=1;}
