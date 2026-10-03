// No automatic resume. This entry requires a separately approved future workflow edit.
import {readFileSync,existsSync,readdirSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {executionGate,validatePlan,historyClear,exclusiveJournal,runProbe,READ_ROW,PLAN} from './atomicity-test.mjs';
import {auditSchema,ACCOUNT,DB,REPO} from './atomicity-schema-audit.mjs';
import {jsonBounded} from './d1-v2-migration.mjs';
export async function entry(e,fetcher=fetch){
 if(!executionGate(e))return {status:'BLOCKED',failure_code:'EXECUTION_HARD_DISABLED_OR_CONTEXT_REJECTED',mutation_submissions:0};validatePlan();
 const head=readFileSync('.git/HEAD','utf8').trim();if(head!==e.PLM_ATOMICITY_APPROVED_COMMIT)return {status:'BLOCKED',failure_code:'ACTUAL_CHECKOUT_PIN_MISMATCH',mutation_submissions:0};
 if(readdirSync('audit-evidence').some(n=>/^atomicity-test-.*receipt.*\.json$/.test(n)))return {status:'BLOCKED',failure_code:'PRIOR_TEST_RECEIPT_NO_RESUME',mutation_submissions:0};
 if(!e.PLM_HISTORY_GITHUB_TOKEN)return {status:'BLOCKED',failure_code:'HISTORY_CREDENTIAL_REQUIRED',mutation_submissions:0};
 const clear=await historyClear(async page=>{const r=await fetcher(`https://api.github.com/repos/${REPO}/actions/workflows/plm-d1-atomicity-test-once.yml/runs?per_page=100&page=${page}`,{method:'GET',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${e.PLM_HISTORY_GITHUB_TOKEN}`}});if(!r.ok)throw Error('HISTORY_UNKNOWN');return jsonBounded(r,1048576);},e.GITHUB_RUN_ID);
 if(!clear)return {status:'BLOCKED',failure_code:'PRIOR_RUN_OR_HISTORY_UNKNOWN_NO_RESUME',mutation_submissions:0};
 const v=await fetcher(`https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}/tokens/verify`,{method:'GET',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${e.PLM_CF_D1_ATOMICITY_TEST_TOKEN}`}});if(!v.ok)throw Error('TOKEN_VERIFY_REJECTED_NO_FALLBACK');const token=await jsonBounded(v,16384);if(token.success!==true||token.result?.status!=='active'||!Number.isFinite(Date.parse(token.result.expires_on))||Date.parse(token.result.expires_on)<=Date.now())throw Error('TOKEN_ACTIVE_EXPIRY_UNCONFIRMED');
 const audit=await auditSchema(e,fetcher);if(!audit.pass||!audit.primary_reads_confirmed)return {status:'BLOCKED',failure_code:'FRESH_SCHEMA_PRIMARY_READ_GATE_REJECTED',mutation_submissions:0};
 const journal=exclusiveJournal('atomicity-journal');
 const url=`https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}/d1/database/${DB}/query`;
 let readCalls=0,mutations=0;
 async function query(payload,secret){const r=await fetcher(url,{method:'POST',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${secret}`,'Content-Type':'application/json'},body:JSON.stringify(payload)});if(!r.ok)throw Error('HTTP_UNKNOWN');const b=await jsonBounded(r);const q=b.result?.[0];if(b.success!==true||b.result?.length!==1||q?.success!==true)throw Error('RESULT_UNKNOWN');return q;}
 const io={async mutate(payload){if(++mutations>9)throw Error('SUBMISSION_BUDGET');const q=await query(payload,e.PLM_CF_D1_ATOMICITY_TEST_TOKEN);return {changes:q.meta?.changes};},async read(){if(++readCalls>10)throw Error('READ_BUDGET');const q=await query({sql:READ_ROW,params:[PLAN.identity.platform,PLAN.identity.account_id,PLAN.identity.intent_id]},e.PLM_CF_D1_READ_TOKEN);if(!Array.isArray(q.results)||q.results.length>1||q.meta?.rows_written>0||q.meta?.changed_db===true)throw Error('READ_UNKNOWN');return {row:q.results[0]||null,primary:q.meta?.served_by_primary===true};}};
 const result=await runProbe(e,io,{journal,historyVerified:true,schemaVerified:true});return {...result,cloudflare_read_only_calls:1+audit.external_api_calls+readCalls,token_scope_api_verified:false,token_scope_owner_evidence:true,owner_token_revocation_required:true};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){try{const r=await entry(process.env);console.log('ATOMICITY_TEST_RECEIPT '+JSON.stringify(r));if(r.status!=='PASS_BOUNDED_FIRST_PROBE')process.exitCode=1;}catch{console.error('ATOMICITY_ENTRY_UNKNOWN_NO_RETRY_NO_RESUME');process.exitCode=1;}}
