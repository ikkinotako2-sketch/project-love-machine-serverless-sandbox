// Offline helpers only. No authentication, cloud SDK, HTTP or deployment.
import {readFileSync} from 'node:fs';
const schema = readFileSync(new URL('./schema.sql', import.meta.url), 'utf8');
const template = JSON.parse(readFileSync(new URL('./wrangler.example.jsonc', import.meta.url), 'utf8')
  .replace(/^\s*\/\/.*$/gm, ''));
const expectedColumns = [
  ['platform','TEXT',1,1], ['account_id','TEXT',1,2], ['job_id','TEXT',1,3],
  ['content_fingerprint','TEXT',1,0], ['claimant','TEXT',1,0], ['state','TEXT',1,0],
  ['version','INTEGER',1,0], ['last_operation','TEXT',1,0], ['run_id','TEXT',0,0],
  ['created_at','INTEGER',1,0], ['updated_at','INTEGER',1,0]
];
const normalize = sql => sql.replace(/--[^\n]*/g,'').replace(/\bIF\s+NOT\s+EXISTS\b/gi,'')
  .replace(/\s+/g,'').replace(/;$/,'').toLowerCase();

// UUID is a resource identifier, not a credential. This does NOT verify its
// existence, account ownership or plan. Human verification remains mandatory.
export function bindingConfig(databaseID) {
  if(typeof databaseID !== 'string' || !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(databaseID))
    throw Error('invalid_database_id');
  const config = structuredClone(template);
  config.d1_databases[0].database_id = databaseID;
  return config;
}

// Feed the first three read-only inspection results to this pure validator.
// An existing job requires investigation: never delete it to make this pass.
export function validateInspection({tableSql, columns, jobCount}) {
  if(typeof tableSql !== 'string' || normalize(tableSql) !== normalize(schema)) throw Error('schema_mismatch');
  if(!Array.isArray(columns) || JSON.stringify(columns.map(c=>[c.name,c.type,c.notnull,c.pk])) !== JSON.stringify(expectedColumns))
    throw Error('columns_mismatch');
  if(jobCount !== 0) throw Error('existing_job_or_invalid_count');
  return {schema:'pass',empty:'pass',posting_permission:false};
}
