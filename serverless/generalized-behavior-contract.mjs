import {readFileSync,readdirSync} from 'node:fs';
import {candidate} from './generalized-backend-contract.mjs';
import {sha,canonical} from './atomicity-schema-audit.mjs';
export const PLAN_SHA='452fd980ba62164f71cfe3841ea7d399ef988c6e259945d5c67487a44eaf52c7';
export const MIGRATION_RECEIPT_SHA='c421f7fe9a22dd3a63b5b00c68837e43f1b1a27c77020f1262169242a844a614';
export const TEST_WORKFLOW='.github/workflows/plm-generalized-behavior-test-once.yml';
export function planCheck(){
 const c=candidate(),raw=readFileSync(new URL('./generalized-behavior-test-plan.json',import.meta.url));if(sha(raw)!==PLAN_SHA)throw Error('RT_BEHAVIOR_PLAN_RAW_DRIFT');const p=JSON.parse(raw),b=p.budgets;
 const receipt=readFileSync(new URL('../audit-evidence/generalized-backend-success-37164056976.json',import.meta.url));if(sha(receipt)!==MIGRATION_RECEIPT_SHA)throw Error('RT_MIGRATION_RECEIPT_DRIFT');const r=JSON.parse(receipt);if(r.result?.status!=='SUCCESS'||r.result?.classification!=='FULL_APPLIED'||!r.result.post?.pass)throw Error('RT_MIGRATION_NOT_SUCCESS');
 if(new Set(p.steps.map(s=>s.id)).size!==33||p.steps.length!==33||b.mutation_sends!==33||b.successful_logical_row_changes!==18||p.steps.reduce((n,s)=>n+s.expected.logical_changes,0)!==18||p.steps.some((s,i)=>s.sequence!==i+1||!/^\w+$/.test(s.id)||!/^(INSERT|UPDATE)\b/.test(s.sql)||/\b(DELETE|DROP|ALTER|RENAME|REPLACE)\b/.test(s.sql)||s.on_mismatch_timeout_unknown!=='STOP_NO_RESEND_ONE_READ_ONLY_RECONCILIATION'||!Array.isArray(s.params)))throw Error('RT_BEHAVIOR_STEPS_DRIFT');
 if(p.execution_approved!==false||p.allow!==false||p.live_ready!==false||p.posting_permitted!==false||Object.values(p.safety_flags).some(v=>v!==true)||['delete','drop','reset','retry','resend','fallback','automatic_rollback','external_provider','worker','ai','render_execution','youtube','sns'].some(k=>b[k]!==0)||['job','script','render','generation_effect','render_effect','upload_effect','callback','runner','read_only_reconciliation_sets'].some(k=>b[k]!==1))throw Error('RT_BEHAVIOR_BUDGET_DRIFT');
 const counts={callback:1,effect:3,job:1,render:1,script:1};for(const [k,v] of Object.entries(counts))if(p.before_rows['plm_rt_v1_'+k].length!==0||p.expected_final_rows['plm_rt_v1_'+k].length!==v)throw Error('RT_BEHAVIOR_ROW_BUDGET_DRIFT');
 if(p.steps.some((s,i)=>canonical(s.before_rows)!==canonical(i?p.steps[i-1].after_rows:p.before_rows))||canonical(p.steps.at(-1).after_rows)!==canonical(p.expected_final_rows))throw Error('RT_BEHAVIOR_SNAPSHOT_CHAIN_DRIFT');
 if(readdirSync(new URL('../audit-evidence/',import.meta.url)).some(n=>/^generalized-behavior-(sent|success|partial|unknown|failure|execution)-/.test(n)))throw Error('RT_BEHAVIOR_PRIOR_SEND_STOP');
 const wf=readFileSync(new URL('../'+TEST_WORKFLOW,import.meta.url),'utf8');if(!/if: false/.test(wf)||!/PLM_RT_BEHAVIOR_ALLOW: 'false'/.test(wf)||wf.includes('secrets.')||!wf.includes('UNAPPROVED'))throw Error('RT_BEHAVIOR_WORKFLOW_NOT_DISABLED');
 return {plan_sha256:PLAN_SHA,migration_receipt_sha256:MIGRATION_RECEIPT_SHA,migration_hashes:c.hashes,steps:33,budgets:b,prior_execution_evidence:false,workflow_hard_disabled:true,allow:false,execution_approved:false,expected_final_rows:p.expected_final_rows};
}
