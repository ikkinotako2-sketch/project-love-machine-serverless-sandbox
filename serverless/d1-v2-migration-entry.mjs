// Future invocation remains disabled by workflow and defaults; no approval from secret registration.
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {executionContext,migrateSchemaOnce,exclusiveJournal,jsonBounded} from './d1-v2-migration.mjs';
const REPO='ikkinotako2-sketch/project-love-machine-serverless-sandbox';
export function checkoutPinVerified(env,head){
 return /^[a-f0-9]{40}$/.test(head)&&head===env.PLM_D1_V2_APPROVED_COMMIT&&head===(env.PLM_D1_V2_EXECUTION_CODE_COMMIT||env.GITHUB_SHA);
}
export function historyPageClear(d,currentRun,page,total){
 if(!Number.isSafeInteger(d?.total_count)||d.total_count<0||d.total_count>10000||!Array.isArray(d.workflow_runs)||d.workflow_runs.length>100||total!==null&&d.total_count!==total)throw Error('HISTORY_UNCONFIRMED');
 if(d.workflow_runs.some(x=>!Number.isSafeInteger(x.id)||x.id!==Number(currentRun)&&x.conclusion!=='skipped'))throw Error('PREVIOUS_EXECUTION_OR_UNKNOWN_NO_WRITE');
 return d.total_count;
}
export async function entry(env,fetcher=fetch){
 if(!executionContext(env))return {status:'BLOCKED',mutation_requests:0};
 // The activation run SHA and immutable checked-out code SHA are distinct.
 // Require an actual detached checkout; env alone is not proof of the code pin.
 if(!checkoutPinVerified(env,readFileSync('.git/HEAD','utf8').trim()))throw Error('ACTUAL_CHECKOUT_PIN_MISMATCH');
 const raw=readFileSync(new URL('../audit-evidence/d1-v2-final-preflight.json',import.meta.url));
 if(!/^[a-f0-9]{64}$/.test(env.PLM_D1_V2_PREFLIGHT_RECEIPT_SHA||'')||createHash('sha256').update(raw).digest('hex')!==env.PLM_D1_V2_PREFLIGHT_RECEIPT_SHA)throw Error('APPROVED_PREFLIGHT_RECEIPT_REQUIRED');
 const approved=JSON.parse(raw).evidence;
 if(typeof env.PLM_HISTORY_GITHUB_TOKEN!=='string'||!env.PLM_HISTORY_GITHUB_TOKEN)throw Error('HISTORY_CREDENTIAL_REQUIRED');
 let total=null,seen=0;const ids=new Set();
 for(let page=1;page<=100;page++){
  const r=await fetcher(`https://api.github.com/repos/${REPO}/actions/workflows/plm-d1-v2-migration-once.yml/runs?per_page=100&page=${page}`,{method:'GET',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${env.PLM_HISTORY_GITHUB_TOKEN}`,'Accept':'application/vnd.github+json'}});
  if(!r.ok)throw Error('HISTORY_HTTP_UNCONFIRMED');
  const d=await jsonBounded(r);total=historyPageClear(d,env.GITHUB_RUN_ID,page,total);
  for(const run of d.workflow_runs){if(ids.has(run.id))throw Error('HISTORY_DUPLICATE');ids.add(run.id);}seen+=d.workflow_runs.length;
  if(seen===total)break;if(!d.workflow_runs.length||seen>total||page===100)throw Error('HISTORY_PAGINATION_UNCONFIRMED');
 }
 if(typeof env.RUNNER_TEMP!=='string'||!env.RUNNER_TEMP.startsWith('/'))throw Error('JOURNAL_PATH_REQUIRED');
 return migrateSchemaOnce(env,fetcher,approved,{historyClear:true,journal:exclusiveJournal(`${env.RUNNER_TEMP}/plm-d1-v2-migration-sent.json`)});
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 try{const r=await entry(process.env);console.log('D1_V2_SCHEMA_MIGRATION_EVIDENCE '+JSON.stringify(r));if(r.status!=='SUCCESS')process.exitCode=1;}
 catch{console.error('D1_V2_SCHEMA_MIGRATION_BLOCKED_NO_RETRY');process.exitCode=1;}
}
