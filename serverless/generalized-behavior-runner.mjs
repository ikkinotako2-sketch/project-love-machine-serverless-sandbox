import {readFileSync} from 'node:fs';
import {PLAN_SHA,planCheck} from './generalized-behavior-contract.mjs';
import {ACCOUNT,DB,canonical,sha} from './atomicity-schema-audit.mjs';
import {readTransport} from './generalized-behavior-preflight.mjs';
import {jsonBounded} from './d1-v2-migration.mjs';
import {reconcile,classify} from './generalized-backend-reconcile.mjs';
export const TARGET=`https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}/d1/database/${DB}`;
export function fixedPlan(){const raw=readFileSync(new URL('./generalized-behavior-test-plan.json',import.meta.url));if(sha(raw)!==PLAN_SHA)throw Error('RT_EXEC_PLAN_RAW_DRIFT');return JSON.parse(raw);}
export function behaviorReadTransport(e,f){const p=fixedPlan(),reads=new Set(Object.values(p.readback_sql)),read=readTransport({PLM_CF_D1_READ_TOKEN:e.PLM_CF_D1_READ_TOKEN},f);return async(u,o)=>{
 if(o.redirect!=='error'||o.headers?.Authorization!==`Bearer ${e.PLM_CF_D1_READ_TOKEN}`||Object.keys(o.headers||{}).some(k=>!['Authorization','Content-Type'].includes(k))||o.headers['Content-Type']!==undefined&&o.headers['Content-Type']!=='application/json')throw Error('RT_EXEC_READ_AUTH_REJECTED');
 if(u===TARGET+'/query'&&o.method==='POST'){const b=JSON.parse(o.body);if(Object.keys(b).sort().join(',')==='params,sql'&&b.params?.length===0&&reads.has(b.sql))return f(u,o);}return read(u,o);
};}
export function mutationTransport(e,f,counts){const p=fixedPlan();let next=0;return async(u,o)=>{
 if(u!==TARGET+'/query'||o.method!=='POST'||o.redirect!=='error'||o.headers?.Authorization!==`Bearer ${e.PLM_CF_D1_ROUNDTRIP_BEHAVIOR_TOKEN}`||o.headers['Content-Type']!=='application/json'||Object.keys(o.headers).sort().join(',')!=='Authorization,Content-Type'||counts.mutation_sends>=33)throw Error('RT_EXEC_MUTATION_ROUTE_REJECTED');
 const b=JSON.parse(o.body),s=p.steps[next];if(!s||canonical(b)!==canonical({sql:s.sql,params:s.params}))throw Error('RT_EXEC_FIXED_SEQUENCE_DRIFT');
 next++;counts.mutation_sends++;return f(u,o);
};}
const options=(token,sql,params=[])=>({method:'POST',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},body:JSON.stringify({sql,params})});
export async function fullReadback(e,f){const p=fixedPlan(),rows={};for(const [t,sql] of Object.entries(p.readback_sql)){
 const r=await f(TARGET+'/query',options(e.PLM_CF_D1_READ_TOKEN,sql));if(!r.ok)throw Error('RT_EXEC_READ_HTTP_UNKNOWN');const b=await jsonBounded(r,65536),q=b.result?.[0];if(b.success!==true||b.result?.length!==1||q?.success!==true||!Array.isArray(q.results)||q.results.length>8||q.meta?.served_by_primary!==true||q.meta?.rows_written!==0||q.meta?.changed_db!==false)throw Error('RT_EXEC_PRIMARY_READ_UNKNOWN');rows[t]=q.results;
 }return rows;}
const safeTokens=new Set(fixedPlan().steps.map(s=>s.expected.safe_error_token).filter(Boolean));
export function safeTrigger(message){if(typeof message!=='string'||message.length>160||/[\u0000-\u001f\u007f]/.test(message))return null;for(const token of safeTokens)for(const prefix of ['','D1_ERROR: '])for(const suffix of ['',': SQLITE_CONSTRAINT',': SQLITE_CONSTRAINT_TRIGGER'])if(message===prefix+token+suffix)return token;return null;}
export async function decodeOutcome(r,expected){let b;try{b=await jsonBounded(r,16384);}catch{return {match:false,diagnostics:[],failure_code:'RT_EXEC_RESPONSE_UNKNOWN'};}
 const errors=(Array.isArray(b?.errors)?b.errors:[]).slice(0,4).map(x=>({code:Number.isSafeInteger(x?.code)?x.code:null,safe_message:safeTrigger(x?.message)||'[REDACTED_UNRECOGNIZED_MESSAGE]'}));
 if(expected.outcome==='REJECTED'){
  const match=[200,400].includes(r.status)&&b.success===false&&Array.isArray(b.errors)&&b.errors.length===1&&b.errors[0].code===7500&&safeTrigger(b.errors[0].message)===expected.safe_error_token&&(b.result===undefined||b.result===null||Array.isArray(b.result)&&b.result.length===0);
  return {match,outcome:match?'REJECTED':'UNEXPECTED',logical_changes:match?0:null,safe_trigger_token:match?expected.safe_error_token:null,diagnostics:errors};
 }
 const q=b?.result?.[0],n=q?.meta?.changes,valid=r.ok&&b.success===true&&b.result?.length===1&&q?.success===true&&q.meta?.served_by_primary===true&&Number.isSafeInteger(n)&&n>=0&&Array.isArray(q.results)&&q.results.length===0&&Array.isArray(b.errors)&&b.errors.length===0;
 return {match:valid&&n===expected.meta_changes,outcome:valid?(n===0?'NO_OP':'APPLIED'):'UNEXPECTED',logical_changes:valid?n:null,safe_trigger_token:null,diagnostics:errors};
}
export async function postCheck(e,f){const read=behaviorReadTransport(e,f),a=await reconcile({PLM_CF_D1_READ_TOKEN:e.PLM_CF_D1_READ_TOKEN},read),out={pass:false,schema_classification:'STILL_UNKNOWN',preserved:a.preserved===true,rows:null,bookmark:a.bookmark||null,audit:Object.fromEntries(Object.entries(a).filter(([k])=>!['pass','classification'].includes(k)))};
 // classify()'s migration contract also demands zero rows. Project just that row-count
 // gate to zero to validate schema; preserve ACTUAL counts and rows separately below.
 if(a.schema&&a.new_details)out.schema_classification=classify(a.schema,Object.fromEntries(Object.entries(a.new_details).map(([t,d])=>[t,{...d,row_count:0}])),a.preserved);
 if(!a.preserved||out.schema_classification!=='FULL_APPLIED'||!a.bookmark)return out;
 try{out.rows=await fullReadback(e,read);out.actual_counts_match=Object.entries(out.rows).every(([t,rows])=>a.new_details[t]?.row_count===rows.length);out.final_rows_match=canonical(out.rows)===canonical(fixedPlan().expected_final_rows);out.pass=out.actual_counts_match&&out.final_rows_match;}catch{out.failure_code='RT_EXEC_POST_UNKNOWN_NO_RETRY';}return out;
}
export async function runFixed(e,{mutate,read,post,journal}){const p=fixedPlan(),out={status:'STOP',mutation_sends:0,successful_logical_row_changes:0,matched_steps:0,steps:[],post_sets:0,reconciliation_sets:0,retry:0,resend:0,fallback:0,automatic_rollback:0,delete:0,drop:0,reset:0,external_provider:0,worker:0,ai:0,render_execution:0,youtube:0,sns:0,live_ready:false,posting_permitted:false};
 try{
  if(canonical(await fullReadback(e,read))!==canonical(p.before_rows))throw Error('RT_EXEC_IMMEDIATE_BASELINE_DRIFT');
  for(const s of p.steps){if(out.mutation_sends>=33||out.successful_logical_row_changes+s.expected.logical_changes>18)throw Error('RT_EXEC_BUDGET_STOP');
   journal.reserve(s.id,{status:'SENT',sequence:s.sequence,plan_sha256:PLAN_SHA});out.mutation_sends++;
   let decoded;try{decoded=await decodeOutcome(await mutate(TARGET+'/query',options(e.PLM_CF_D1_ROUNDTRIP_BEHAVIOR_TOKEN,s.sql,s.params)),s.expected);}catch{throw Error('RT_EXEC_MUTATION_UNKNOWN_NO_RESEND');}
   out.steps.push({sequence:s.sequence,id:s.id,expected_outcome:s.expected.outcome,expected_logical_changes:s.expected.logical_changes,...decoded});
   if(!decoded.match||decoded.outcome!==s.expected.outcome||decoded.logical_changes!==s.expected.logical_changes)throw Error('RT_EXEC_OUTCOME_MISMATCH_STOP');
   out.successful_logical_row_changes+=decoded.logical_changes;
   const rows=await fullReadback(e,read);if(canonical(rows)!==canonical(s.after_rows))throw Error('RT_EXEC_FULL_READBACK_MISMATCH_STOP');
   out.steps.at(-1).full_readback_match=true;out.steps.at(-1).rows=rows;out.matched_steps++;journal.finish?.(s.id,'MATCHED');
  }
  out.all_steps_matched=true;
 }catch(err){out.failure_code=/^[A-Z_]+$/.test(err.message)?err.message:'RT_EXEC_UNKNOWN_STOP_NO_RESEND';}
 if(out.mutation_sends){out.post_sets=1;if(!out.all_steps_matched)out.reconciliation_sets=1;try{out.post=await post();out.result_classification=out.post.rows?(canonical(out.post.rows)===canonical(p.expected_final_rows)?'FULL_APPLIED':canonical(out.post.rows)===canonical(p.before_rows)?'NOT_APPLIED':'PARTIAL_APPLIED'):'STILL_UNKNOWN';if(out.all_steps_matched&&out.matched_steps===33&&out.mutation_sends===33&&out.successful_logical_row_changes===18&&out.post.pass)out.status='SUCCESS';}catch{out.post_failure_code='RT_EXEC_POST_UNKNOWN_NO_RETRY';out.result_classification='STILL_UNKNOWN';}}
 else out.result_classification='NOT_APPLIED';return out;
}
