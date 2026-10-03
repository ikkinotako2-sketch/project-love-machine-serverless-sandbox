import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {ACCOUNT,DB,baseContext} from './atomicity-schema-audit.mjs';
import {stage2Plan,STAGE2_PLAN_SHA} from './durable-stage2-contract.mjs';
import {recoveryCandidate} from './stage3-recovery-contract.mjs';
import {reconcileStage3,MESSAGE as RECONCILE_MESSAGE} from './stage3-reconcile-read-only.mjs';
export const MESSAGE='PLM stage2 preparation read-only once 20261003-r1';
export function planCheck(){const p=stage2Plan(),b=p.budget;
 if(p.steps.length!==14||p.steps.some((s,i)=>s.sequence!==i+1||!/^\d\d_[a-z_]+$/.test(s.id)||!['INSERT','UPDATE'].includes(s.sql.split(' ')[0])||/\b(DELETE|DROP|ALTER|RENAME)\b/i.test(s.sql)||s.on_mismatch_or_unknown!=='STOP_NO_RESEND_ONE_READ_RECONCILIATION')||new Set(p.steps.map(s=>s.id)).size!==14||p.steps.reduce((n,s)=>n+s.expected_changes,0)!==9)throw Error('STAGE2_FIXED_STEPS_DRIFT');
 if(b.mutation_sends!==14||b.successful_logical_row_changes!==9||b.job_identities!==1||b.checkpoint_rows!==1||b.callback_rows!==1||b.concurrent_runners!==1||['delete','retry','resend'].some(k=>b[k]!==0)||p.execution_approved!==false||p.allow!==false||p.live_ready!==false||p.posting_permitted!==false||p.AI_and_side_effect!=='SENT/UNKNOWN simulated SQL state only; actual outbound=0')throw Error('STAGE2_BUDGET_APPROVAL_DRIFT');
 if(Object.values(p.expected_final_rows).some(rows=>rows.length!==1))throw Error('STAGE2_IDENTITY_BUDGET_DRIFT');
 return {plan_sha256:STAGE2_PLAN_SHA,steps:14,mutation_sends_max:14,logical_row_changes_max:9,job:1,checkpoint:1,callback:1,runner:1,delete:0,retry:0,resend:0,fallback:0,automatic_rollback:0,external_provider_calls:0,sent_unknown:'SQL_STATE_SIMULATION_ONLY',execution_approved:false,allow:false};
}
export function readOnlyTransport(e,f){const base=`https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}/d1/database`,target=base+'/'+DB,reads=new Set(["SELECT type, name, tbl_name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name",'PRAGMA table_info(test_jobs)','PRAGMA table_info(backend_probe_v1)','PRAGMA index_list(backend_probe_v1)','SELECT * FROM backend_probe_v1','SELECT COUNT(*) AS n FROM test_jobs',...Object.keys(recoveryCandidate().expected.columns).flatMap(t=>['PRAGMA table_info('+t+')','PRAGMA index_list('+t+')','SELECT COUNT(*) AS n FROM '+t])]);
 return async(u,o)=>{if(o.headers?.Authorization!==`Bearer ${e.PLM_CF_D1_READ_TOKEN}`||o.redirect!=='error')throw Error('STAGE2_READ_AUTH_REJECTED');let ok=false;
 if(o.method==='GET'&&!o.body)ok=u==='https://api.cloudflare.com/client/v4/user/tokens/verify'||u===target||u===target+'/time_travel/bookmark'||new RegExp('^'+base+'\\?page=[1-9][0-9]*&per_page=100$').test(u);
 if(o.method==='POST'&&u===target+'/query'){const b=JSON.parse(o.body);ok=Object.keys(b).sort().join(',')==='params,sql'&&b.params?.length===0&&reads.has(b.sql);}
 if(!ok)throw Error('STAGE2_READ_ONLY_TRANSPORT_REJECTED');return f(u,o);};
}
export async function preflight(e,f=fetch,{checkout,checks=planCheck,audit=reconcileStage3}={}){const out={pass:false,d1_mutation:0,d1_write:0,worker:0,ai:0,render:0,posting:0,external_provider_calls:0,retry:0,resend:0,fallback:0,automatic_rollback:0,cloudflare_read_only_calls:0,cleanup_owner_evidence:true,live_ready:false,posting_permitted:false};
 try{if(!baseContext(e)||e.GITHUB_EVENT_NAME!=='push'||!/^\d+$/.test(e.GITHUB_RUN_ID||'')||!/^[a-f0-9]{40}$/.test(checkout||'')||checkout!==e.PLM_STAGE2_PREFLIGHT_CODE_PIN||e.PLM_STAGE2_PREFLIGHT_BEFORE!==checkout||e.PLM_STAGE2_PREFLIGHT_MESSAGE!==MESSAGE||e.PLM_STAGE2_ALLOW!=='false'||!e.PLM_CF_D1_READ_TOKEN||['PLM_CF_D1_STAGE3_IMPORT_TOKEN','PLM_CF_D1_STAGE3_RECOVERY_TOKEN','PLM_CF_D1_STAGE3_MIGRATION_TOKEN','PLM_CF_D1_STAGE2_TEST_TOKEN','PLM_CF_WORKER_API_TOKEN'].some(k=>e[k]))throw Error('STAGE2_READ_CONTEXT_REJECTED');
 out.plan=checks();const ce={...e,PLM_RECONCILE_CODE_PIN:checkout,PLM_RECONCILE_BEFORE:checkout,PLM_RECONCILE_MESSAGE:RECONCILE_MESSAGE};const transport=readOnlyTransport(e,async(u,o)=>{out.cloudflare_read_only_calls++;return f(u,o);});out.audit=await audit(ce,transport,{expected:recoveryCandidate().expected});const a=out.audit;
 if(!a.pass||a.classification!=='FULL_APPLIED'||a.objects.length!==9||a.objects.some(x=>!x.exists)||!a.old_schema_unchanged||!a.old_columns_indexes_unchanged||!a.atomicity_row_unchanged||!a.test_jobs_unchanged||!a.kv_schema_unchanged||!a.bookmark||a.database_size_bytes!==102400||Object.values(a.stage3_table_details).some(x=>!x.canonical_match||x.row_count!==0)||Object.values(a.stage3_table_details).flatMap(x=>x.indexes).length!==8)throw Error('STAGE2_REMOTE_SCHEMA_UNCONFIRMED');
 out.kv_schema_unchanged=true;out.kv_content_status='NOT_APPLICABLE_RESERVED_UNQUERYABLE';out.pass=true;out.next_gate='STAGE2_TEST_TOKEN_REGISTRATION_THEN_SEPARATE_APPROVAL';
 }catch(err){out.failure_code=/^[A-Z_]+$/.test(err.message)?err.message:'STAGE2_PREFLIGHT_UNKNOWN_NO_RETRY';}return out;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){const r=await preflight(process.env,fetch,{checkout:readFileSync('.git/HEAD','utf8').trim()});console.log('STAGE2_READ_ONLY_PREFLIGHT '+JSON.stringify(r));if(!r.pass)process.exitCode=1;}
