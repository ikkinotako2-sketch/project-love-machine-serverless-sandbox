// Verify/read-only only. This entry cannot invoke recoveryOnce.
import {readFileSync,readdirSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {ACCOUNT,DB,REPO,baseContext,sha} from './atomicity-schema-audit.mjs';
import {recoveryCandidate,recoveryPreflight,recoveryHistory,SQL_SHA,REQUEST_SHA} from './stage3-recovery-contract.mjs';
import {jsonBounded} from './d1-v2-migration.mjs';
export const MESSAGE='PLM stage3 recovery verify read-only once 20261003-r1';
export function localChecks(){
 recoveryCandidate();const w=readFileSync(new URL('../.github/workflows/plm-stage3-explicit-batch-recovery-once.yml',import.meta.url),'utf8');
 if(!w.includes('if: false')||!w.includes("PLM_STAGE3_RECOVERY_ALLOW: 'false'")||!w.includes('PLM_STAGE3_RECOVERY_OWNER_APPROVAL: UNAPPROVED'))throw Error('MIGRATION_WORKFLOW_ENABLED');
 const names=readdirSync(new URL('../audit-evidence/',import.meta.url));if(names.some(n=>/^stage3-recovery-(sent|unknown|success|failure|timeout)/.test(n)))throw Error('PRIOR_RECOVERY_SENT_OR_RESULT');
 return true;
}
export function readOnlyTransport(e,fetcher){return async(url,o)=>{
 const auth=o.headers?.Authorization;const base=`https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}`;let valid=false;
 if(url===base+'/tokens/verify')valid=o.method==='GET'&&auth===`Bearer ${e.PLM_CF_D1_STAGE3_RECOVERY_TOKEN}`&&!o.body;
 else if(auth===`Bearer ${e.PLM_CF_D1_READ_TOKEN}`){if(o.method==='GET'&&!o.body)valid=url==='https://api.cloudflare.com/client/v4/user/tokens/verify'||new RegExp('^'+base+'/d1/database\\?page=[1-9][0-9]*&per_page=100$').test(url)||url===base+'/d1/database/'+DB||url===base+'/d1/database/'+DB+'/time_travel/bookmark';else if(o.method==='POST'&&url===base+'/d1/database/'+DB+'/query'){const b=JSON.parse(o.body);valid=Object.keys(b).sort().join(',')==='params,sql'&&b.params?.length===0&&(/^(SELECT type, name, tbl_name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name|SELECT \* FROM backend_probe_v1|SELECT COUNT\(\*\) AS n FROM test_jobs|PRAGMA table_info\((test_jobs|backend_probe_v1)\)|PRAGMA index_list\(backend_probe_v1\))$/.test(b.sql));}}
 if(!valid)throw Error('RECOVERY_READ_ONLY_TRANSPORT_REJECTED');return fetcher(url,o);
};}
export async function finalPreflight(e,fetcher=fetch,{checkout,checks=localChecks}={}){
 const out={pass:false,cloudflare_read_only_api_calls:0,github_history_get_calls:0,d1_mutation:0,d1_write:0,worker_deploy:0,worker_invocation:0,ai_api:0,render:0,posting:0,retry:0,resend:0,fallback:0,live_ready:false,posting_permitted:false};
 const pin=e.PLM_RECOVERY_PREFLIGHT_CODE_PIN;
 if(!baseContext(e)||!/^\d+$/.test(e.GITHUB_RUN_ID||'')||e.GITHUB_EVENT_NAME!=='push'||!/^[a-f0-9]{40}$/.test(pin||'')||checkout!==pin||e.PLM_RECOVERY_EVENT_BEFORE!==pin||e.PLM_RECOVERY_EVENT_MESSAGE!==MESSAGE||e.PLM_STAGE3_RECOVERY_ALLOW!=='false'||e.PLM_STAGE3_RECOVERY_OWNER_APPROVAL!=='UNAPPROVED'||!e.PLM_HISTORY_GITHUB_TOKEN)return {...out,failure_code:'RECOVERY_ACTIVATION_OR_PIN_REJECTED_NO_HTTP'};
 try{checks();out.history=await recoveryHistory(async page=>{out.github_history_get_calls++;const r=await fetcher(`https://api.github.com/repos/${REPO}/actions/runs?per_page=100&page=${page}`,{method:'GET',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${e.PLM_HISTORY_GITHUB_TOKEN}`,Accept:'application/vnd.github+json'}});if(!r.ok)throw Error('RECOVERY_HISTORY_HTTP_REJECTED');return jsonBounded(r,1048576);});
 const ce={...e,GITHUB_SHA:pin,PLM_STAGE3_RECOVERY_APPROVED_COMMIT:pin,PLM_STAGE3_RECOVERY_SQL_SHA:SQL_SHA,PLM_STAGE3_RECOVERY_REQUEST_SHA:REQUEST_SHA};
 const transport=readOnlyTransport(ce,async(url,o)=>{out.cloudflare_read_only_api_calls++;return fetcher(url,o);});out.preflight=await recoveryPreflight(ce,transport);if(!out.preflight.pass)throw Error('RECOVERY_FRESH_PREFLIGHT_UNCONFIRMED');const c=recoveryCandidate();out.sql_sha256=SQL_SHA;out.request_sha256=REQUEST_SHA;out.explicit_batch_elements=c.batch_elements;out.destructive_statement_count=0;out.existing_table_changes=0;out.expected_post_schema={tables:3,triggers:6,column_counts:[16,11,9],autoindexes:8,new_rows:0};out.migration_workflow_hard_disabled=true;out.migration_owner_approval=false;out.pass=true;
 }catch(err){out.failure_code=/^[A-Z_]+$/.test(err.message)?err.message:'RECOVERY_READ_ONLY_UNKNOWN_NO_RETRY';}return out;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){const r=await finalPreflight(process.env,fetch,{checkout:readFileSync('.git/HEAD','utf8').trim()});console.log('STAGE3_RECOVERY_FINAL_PREFLIGHT '+JSON.stringify(r));if(!r.pass)process.exitCode=1;}
