// Pure pre-deploy validation. Never calls Wrangler, fetch, DB or a credential API.
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
export const CODE_SHA='6c5d726f96d56dac792ff739f87227926197891f1149b1dedeeac38e67128451';
const expected=JSON.parse(readFileSync(new URL('./wrangler.stopped.json',import.meta.url),'utf8'));
function canonical(x){
 if(x===null||typeof x!=='object')return JSON.stringify(x);
 if(Array.isArray(x))return '['+x.map(canonical).join(',')+']';
 return '{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+canonical(x[k])).join(',')+'}';
}
export function validateStoppedDeploy(config,policy,code){
 // Fixed trusted candidate; unknown fields, environments, overrides or bindings refuse.
 if(createHash('sha256').update(canonical(expected)).digest('hex')!=='cefa60606ca3e3820116a56671d83125ea86ac6e3a5e771761dd2e3508c96cf5'||canonical(config)!==canonical(expected))throw Error('stopped_config_mismatch');
 if(policy?.deploy_permitted!==false||policy?.create_permitted!==false||policy?.design_only!==true||policy?.owner_approval_required!==true||policy?.worker_name!==config.name||policy?.account_id!==config.account_id||policy?.entrypoint!=='serverless/bootstrap-placeholder.mjs'||policy?.workers_dev!==false||policy?.preview_urls!==false)throw Error('stopped_policy_mismatch');
 if(canonical(policy.d1_binding)!==canonical(config.d1_databases[0])||canonical(policy.flags)!==canonical(config.vars))throw Error('stopped_policy_binding_or_flags_mismatch');
 for(const k of ['custom_domains','routes','cron','queues','secrets','service_bindings','outbound_endpoints'])if(!Array.isArray(policy[k])||policy[k].length!==0)throw Error('stopped_policy_exposure');
 if(typeof code!=='string'||createHash('sha256').update(code).digest('hex')!==CODE_SHA)throw Error('stopped_code_hash_mismatch');
 return {status:'OFFLINE PASS',code_sha256:CODE_SHA,config_sha256:createHash('sha256').update(canonical(config)).digest('hex'),deploy_permitted:false,remote_settings_verified:false,db_access_permitted:false,outbound_fetch_permitted:false};
}
export function rollbackReadiness(snapshot){
 if(!snapshot||snapshot.evidence_kind!=='WORK_READ_ONLY_SNAPSHOT'||snapshot.account_id!==expected.account_id||snapshot.worker_name!==expected.name||!/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(snapshot.deployment_id||'')||!/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(snapshot.version_id||'')||snapshot.code_sha256!==CODE_SHA||snapshot.bindings?.length!==0||snapshot.secrets?.length!==0||snapshot.workers_dev!==false||snapshot.preview_urls!==false||snapshot.public_routes_owner_confirmed_none!==true||snapshot.cron?.length!==0||snapshot.handlers?.join(',')!=='fetch'||snapshot.stable_deployment_readback!==true)return {status:'BLOCKED',reason:'CURRENT_REMOTE_VERSION_SNAPSHOT_REQUIRED',automatic_rollback:false};
 return {status:'DESIGN PASS',previous_deployment_id:snapshot.deployment_id,previous_version_id:snapshot.version_id,automatic_rollback:false,settings_snapshot_required:true};
}
