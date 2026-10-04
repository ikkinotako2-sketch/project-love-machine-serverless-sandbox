import {readFileSync} from 'node:fs';import {pathToFileURL} from 'node:url';
import {baseContext,canonical,sha} from './atomicity-schema-audit.mjs';import {postCheck,behaviorReadTransport} from './generalized-behavior-runner.mjs';
import {v3Plan,V3_PLAN_SHA,V3_ORACLE_SHA} from './generalized-behavior-v3-contract.mjs';
export const MESSAGE='PLM v3 exact migrated schema read only once 20261004-r1';
export async function audit(e,f=fetch,{checkout,post=postCheck}={}){const out={pass:false,d1_mutation:0,d1_write:0,worker:0,ai:0,render:0,youtube:0,sns:0,external_provider:0,retry:0,resend:0,delete:0,reset:0,rollback:0,allow:false,execution_approved:false,live_ready:false,posting_permitted:false,read_only_calls:0};try{
 if(!baseContext(e)||e.GITHUB_EVENT_NAME!=='push'||!/^[a-f0-9]{40}$/.test(checkout||'')||checkout!==e.PLM_RT_V3_READ_PIN||e.PLM_RT_V3_READ_BEFORE!==checkout||e.PLM_RT_V3_READ_MESSAGE!==MESSAGE||e.PLM_RT_V3_ALLOW!=='false'||Object.keys(e).some(k=>/^PLM_CF_.*TOKEN$/.test(k)&&k!=='PLM_CF_D1_READ_TOKEN'&&e[k])||!e.PLM_CF_D1_READ_TOKEN)throw Error('RT_V3_READ_CONTEXT_REJECTED');
 const p=v3Plan();out.plan_sha256=V3_PLAN_SHA;out.offline_oracle_sha256=V3_ORACLE_SHA;
 const clean={PLM_CF_D1_READ_TOKEN:e.PLM_CF_D1_READ_TOKEN},read=behaviorReadTransport(clean,async(u,o)=>{out.read_only_calls++;return f(u,o);});out.post=await post(clean,read);const a=out.post;
 if(!a.preserved||a.schema_classification!=='FULL_APPLIED'||!a.actual_counts_match||canonical(a.rows)!==canonical(p.before_rows)||a.audit.database_size_bytes!==196608||!a.bookmark)throw Error('RT_V3_READ_BASELINE_UNCONFIRMED');
 const schema=a.audit.schema.filter(x=>x.name.startsWith('plm_rt_v1_'));if(canonical(schema)!==canonical(p.exact_migrated_generalized_schema))throw Error('RT_V3_EXACT_REMOTE_SCHEMA_DRIFT');
 out.remote_sql_sha256=Object.fromEntries(schema.map(x=>[x.name,sha(x.sql)]));if(canonical(out.remote_sql_sha256)!==canonical(p.exact_migrated_sql_sha256))throw Error('RT_V3_EXACT_REMOTE_SQL_HASH_DRIFT');
 out.old_two_active_jobs_exact_unchanged=true;out.new_identity_absent_all_five_tables=true;out.schema_sql_exact=true;out.pass=true;out.completed_at=new Date().toISOString();
 }catch(err){out.failure_code=/^[A-Z0-9_]+$/.test(err.message)?err.message:'RT_V3_READ_UNKNOWN_NO_RETRY';}return out;}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){const r=await audit(process.env,fetch,{checkout:readFileSync('.git/HEAD','utf8').trim()});console.log('GENERALIZED_BEHAVIOR_V3_SCHEMA_READ_ONLY '+JSON.stringify(r));if(!r.pass)process.exitCode=1;}
