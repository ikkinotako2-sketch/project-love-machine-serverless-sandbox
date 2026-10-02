import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
import {validateStoppedDeploy,rollbackReadiness} from './stopped-deploy-contract.mjs';
const config=JSON.parse(readFileSync(new URL('./wrangler.stopped.json',import.meta.url),'utf8'));
const policy=JSON.parse(readFileSync(new URL('./stopped-deploy-plan.json',import.meta.url),'utf8'));
const code=readFileSync(new URL('./bootstrap-placeholder.mjs',import.meta.url),'utf8');
function rejected(change){const c=structuredClone(config);change(c);assert.throws(()=>validateStoppedDeploy(c,policy,code));}
test('stopped candidate exact code config D1 flags and no-public-URL policy pass only offline',()=>{const r=validateStoppedDeploy(config,policy,code);assert.equal(r.status,'OFFLINE PASS');assert.equal(r.deploy_permitted,false);assert.equal(r.remote_settings_verified,false);});
test('wrong Worker rejected',()=>rejected(c=>c.name='production'));
test('wrong Account rejected including environment override',()=>{rejected(c=>c.account_id='a'.repeat(32));rejected(c=>c.env={production:{}});});
test('wrong DB binding id or name rejected',()=>{for(const key of ['binding','database_name','database_id'])rejected(c=>c.d1_databases[0][key]='wrong');});
test('workers.dev true and preview URL true rejected independently',()=>{rejected(c=>c.workers_dev=true);rejected(c=>c.preview_urls=true);});
test('every unsafe or missing flag rejected',()=>{for(const key of Object.keys(config.vars)){rejected(c=>c.vars[key]='false');rejected(c=>delete c.vars[key]);}});
test('routes custom domains cron queues secrets and outbound endpoints rejected',()=>{rejected(c=>c.routes=[{pattern:'example.invalid',custom_domain:true}]);rejected(c=>c.triggers.crons=['* * * * *']);rejected(c=>c.queues.consumers=[{queue:'x'}]);rejected(c=>c.queues.producers=[{queue:'x',binding:'Q'}]);rejected(c=>c.secrets=['x']);for(const key of ['custom_domains','routes','cron','queues','secrets','outbound_endpoints']){const p=structuredClone(policy);p[key]=['x'];assert.throws(()=>validateStoppedDeploy(config,p,code));}});
test('external fetch code rejected before runtime',()=>{assert.throws(()=>validateStoppedDeploy(config,policy,code+'\nfetch("https://fixture.invalid")'),/code_hash/);});
test('DB access code rejected before runtime',()=>{assert.throws(()=>validateStoppedDeploy(config,policy,code+'\nenv.DB.prepare("SELECT 1")'),/code_hash/);});
test('stopped handler touches neither DB nor fetch and returns503 for every request method',async()=>{const mod=(await import('./bootstrap-placeholder.mjs')).default;let db=0,http=0;const saved=globalThis.fetch;globalThis.fetch=()=>{http++;throw Error('outbound_denied');};try{for(const method of ['GET','POST','PUT','DELETE']){const r=mod.fetch(new Request('https://fixture.invalid/',{method}),new Proxy({},{get(){db++;throw Error('DB_or_env_denied');}}));assert.equal(r.status,503);const b=await r.json();assert.equal(b.status,'disabled');assert.equal(b.EMERGENCY_STOP,true);}assert.equal(db,0);assert.equal(http,0);}finally{globalThis.fetch=saved;}});
test('rollback refuses invented missing owner-only or incomplete remote snapshot',()=>{for(const s of [null,{}, {evidence_kind:'OWNER_EVIDENCE',deployment_id:'not-verified',version_id:'not-verified'}])assert.equal(rollbackReadiness(s).status,'BLOCKED');});
