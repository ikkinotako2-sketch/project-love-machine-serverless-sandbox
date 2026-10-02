// Manual setup only. Fixed Cloudflare control-plane endpoints; no job dispatch.
import {readFileSync, writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {bindingConfig, validateInspection} from './d1-setup.mjs';
export const REPO='ikkinotako2-sketch/project-love-machine-serverless-sandbox';
export const WORKER='plm-serverless-sandbox-control';
// Previously confirmed sandbox D1; configuration cannot redirect setup to another DB.
export const ACCOUNT_ID='6c8ccd6aface937ab5dabef61cb64534';
export const DATABASE_ID='18050cf6-934e-4f3a-a1cd-5041bac1c35e';
export function verificationUrl(kind, account) {
  if(account!==ACCOUNT_ID) throw Error('account_id_not_allowlisted');
  if(kind==='user') return 'https://api.cloudflare.com/client/v4/user/tokens/verify';
  if(kind==='account') return `https://api.cloudflare.com/client/v4/accounts/${account}/tokens/verify`;
  throw Error('token_kind_required');
}
export const MIGRATION_SHA='ac01f6d9d7eac877b802688d4f1d3c4dd40e8940876ed3ce0dc441c10297d0e2';
export function validateMigration(sql) {
  if(typeof sql!=='string' || createHash('sha256').update(sql).digest('hex')!==MIGRATION_SHA) throw Error('migration_sha_mismatch');
  return {sql_sha256:MIGRATION_SHA,destructive_statements:0,statements:1};
}
const FLAGS=['TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP'];
const migration=readFileSync(new URL('./migrations/0001_test_jobs.sql',import.meta.url),'utf8');
export async function setup(env, operation, fetcher=fetch) {
  if(env.GITHUB_REPOSITORY!==REPO || env.GITHUB_REF!=='refs/heads/main' || env.GITHUB_EVENT_NAME!=='workflow_dispatch') throw Error('context_rejected');
  if(FLAGS.some(k=>env[k]!=='true')) throw Error('unsafe_flags');
  if(!['inspect','migrate','prepare-deploy'].includes(operation)) throw Error('invalid_operation');
  const account=env.CLOUDFLARE_ACCOUNT_ID, db=env.PLM_D1_DATABASE_ID;
  if(!/^[a-f0-9]{32}$/.test(account||'')) throw Error('invalid_account_id');
  if(db!==DATABASE_ID) throw Error('database_id_not_allowlisted');
  if(account!==ACCOUNT_ID) throw Error('account_id_not_allowlisted');
  const config=bindingConfig(db);
  // Human account inventory is a prerequisite, not proof supplied by this code.
  // Time-limited credentials cannot replace provider/account isolation.
  if(operation!=='inspect' && env.PLM_CF_ACCOUNT_ISOLATION!=='sandbox_only_verified')
    throw Error('account_isolation_not_verified');
  if(operation==='migrate') validateMigration(migration);
  if(operation==='migrate' && env.PLM_CF_MIGRATION_EXECUTION_APPROVED!=='true') throw Error('migration_execution_not_approved');
  const tokenKind=operation==='migrate'?env.PLM_CF_D1_WRITE_TOKEN_KIND:env.PLM_CF_D1_READ_TOKEN_KIND;
  const authUrl=verificationUrl(tokenKind,account);
  const workerAuthUrl=operation==='prepare-deploy'?verificationUrl(env.PLM_CF_WORKER_TOKEN_KIND,account):null;
  const token=operation==='migrate'?env.PLM_CF_D1_API_TOKEN:env.PLM_CF_D1_READ_TOKEN;
  if(!token || /[\r\n]/.test(token)) throw Error('missing_auth');
  const base=`https://api.cloudflare.com/client/v4/accounts/${account}`;
  async function api(path, method='GET', body, credential=token, absoluteUrl) {
    let response;
    try { response=await fetcher(absoluteUrl||base+path,{method,redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${credential}`,'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})}); }
    catch { throw Error(method==='POST'?'write_or_query_unconfirmed':'read_unconfirmed'); }
    // Do not log body, headers, provider errors, raw responses or credentials.
    if(!response.ok) throw Error(response.status===404?'resource_missing':'api_rejected');
    let data; try {data=await response.json();} catch {throw Error('response_unconfirmed');}
    if(data.success!==true) throw Error('api_rejected');
    return data.result;
  }
  // Explicit owner selection: no endpoint fallback or retry on rejection/unknown.
  const auth=await api('', 'GET', undefined, token, authUrl);
  if(auth?.status!=='active') throw Error('inactive_token');
  const database=await api(`/d1/database/${db}`);
  if(database?.uuid!==db || database?.name!=='plm-serverless-sandbox-state') throw Error('database_mismatch');
  async function query(sql) {
    const rows=await api(`/d1/database/${db}/query`,'POST',{sql,params:[]});
    if(!Array.isArray(rows)||rows.length!==1||rows[0].success!==true||!Array.isArray(rows[0].results)) throw Error('query_unconfirmed');
    return rows[0].results;
  }
  async function inspect() {
    const tables=await query("SELECT sql FROM sqlite_master WHERE type='table' AND name='test_jobs'");
    if(tables.length===0) return {schema:'missing'};
    if(tables.length!==1) throw Error('schema_mismatch');
    const columns=await query('PRAGMA table_info(test_jobs)');
    const count=await query('SELECT COUNT(*) AS job_count FROM test_jobs');
    return validateInspection({tableSql:tables[0].sql,columns,jobCount:count[0]?.job_count});
  }
  let inspection=await inspect(), applied=false;
  if(inspection.schema==='missing' && operation==='migrate') {
    // Exact checked-in CREATE IF NOT EXISTS only. Never retry an ambiguous write.
    await query(migration); applied=true; inspection=await inspect();
  }
  if(operation==='prepare-deploy') {
    if(inspection.schema!=='pass') throw Error('schema_not_ready');
    const workerToken=env.PLM_CF_WORKER_API_TOKEN;
    if(!workerToken || /[\r\n]/.test(workerToken)) throw Error('missing_worker_auth');
    const workerAuth=await api('', 'GET', undefined, workerToken, workerAuthUrl);
    if(workerAuth?.status!=='active') throw Error('inactive_worker_token');
    // Existing Worker only. 404/403 stop: no Admin fallback or bootstrap.
    await api(`/workers/scripts/${WORKER}/settings`,'GET',undefined,workerToken);
  }
  return {authentication:'pass',database:'matched',schema:inspection.schema,migration_applied:applied,
    posting_permission:false,live_job_sent:false,...(operation==='prepare-deploy'?{config}:{})};
}
if(process.argv[1] && import.meta.url===pathToFileURL(process.argv[1]).href) {
  try {
    const result=await setup(process.env,process.argv[2]);
    if(result.config) {writeFileSync(new URL('./wrangler.local.json',import.meta.url),JSON.stringify(result.config,null,2));delete result.config;}
    console.log(JSON.stringify(result));
  } catch { console.error('SETUP_BLOCKED: inspect permissions/resource/schema; no automatic retry; no job sent');process.exitCode=1; }
}
