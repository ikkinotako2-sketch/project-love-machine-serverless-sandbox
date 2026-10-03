import {readFileSync} from 'node:fs';
import {sha,canonical} from './atomicity-schema-audit.mjs';
export const HASHES={"migrations/0007_generalized_roundtrip_backend.sql": "45f042a1342676ceeeed587490d80eb132e31a2c3d9b33cceeab3045ffdf37b5", "generalized-backend-plan.json": "59cb7545f1d54976e19d74a2dd08c38987698d0271e1aa1ac6d79b72cc25b9cb", "generalized-backend-before.json": "64f4b23b9265bb2f4576b9670241d7afab5f003a5375fca8e8a598aa1a39a468", "generalized-backend-after.json": "d77d27b2e14ec333ca5ee4b8aad49c3b99e372e9004acbff3c6425979cb4049d"};
export function candidate(){
 const raw=Object.fromEntries(Object.keys(HASHES).map(p=>[p,readFileSync(new URL('./'+p,import.meta.url),'utf8')]));
 for(const [p,v] of Object.entries(raw))if(sha(v)!==HASHES[p])throw Error('GENERALIZED_RAW_SHA_DRIFT');
 const plan=JSON.parse(raw['generalized-backend-plan.json']),before=JSON.parse(raw['generalized-backend-before.json']),after=JSON.parse(raw['generalized-backend-after.json']);
 const sql=raw[plan.sql_file],names=[...sql.matchAll(/^CREATE (TABLE|TRIGGER) (plm_rt_v1_[a-z_]+) /gm)].map(x=>x[2]);
 if(names.length!==16||new Set(names).size!==16||after.new.schema.length!==16||names.some(n=>!after.new.schema.some(x=>x.name===n))||/\b(DROP|DELETE|ALTER|RENAME|REPLACE)\b/i.test(sql)||/IF NOT EXISTS/i.test(sql))throw Error('GENERALIZED_NONDESTRUCTIVE_DRIFT');
 if(plan.sql_sha256!==HASHES[plan.sql_file]||plan.before_sha256!==HASHES[plan.before_file]||plan.after_sha256!==HASHES[plan.after_file]||plan.sql_bytes!==Buffer.byteLength(sql)||plan.tables!==5||plan.triggers!==11||plan.autoindexes!==14||plan.top_level_create!==16||plan.new_rows!==0)throw Error('GENERALIZED_SCHEMA_PLAN_DRIFT');
 if(plan.transport!=='REST_IMPORT_SQL_FILE'||plan.flow.join(',')!=='init,upload,ingest,status_poll'||plan.init_max!==1||plan.upload_max!==1||plan.ingest_max!==1||plan.status_poll_max!==3||plan.side_effect_http_max!==3||plan.import_http_total_max!==6||plan.runner_max!==1||plan.execution_max!==1||['query_mutation_max','delete','drop','alter_existing','rename','reset','retry','resend','fallback','automatic_rollback'].some(k=>plan[k]!==0)||plan.read_postcheck_sets_max!==1||plan.allow!==false||plan.owner_execution_approval!==false||plan.workflow_hard_disabled!==true||plan.unknown_policy!=='STOP_BEFORE_NEXT_SIDE_EFFECT_NO_RESEND_READ_RECONCILIATION_MAX1')throw Error('GENERALIZED_EXECUTION_GUARDS_DRIFT');
 if(canonical(after.preserved_before)!==canonical(before))throw Error('GENERALIZED_PRESERVATION_DRIFT');
 const workflow=readFileSync(new URL('../.github/workflows/plm-generalized-backend-migration-once.yml',import.meta.url),'utf8');
 if(!workflow.includes('if: false')||!workflow.includes("PLM_GENERALIZED_ALLOW: 'false'")||!workflow.includes('PLM_GENERALIZED_OWNER_APPROVAL: UNAPPROVED')||workflow.includes('secrets.'))throw Error('GENERALIZED_MIGRATION_NOT_DISABLED');
 return {sql,plan,before,after,hashes:HASHES};
}
