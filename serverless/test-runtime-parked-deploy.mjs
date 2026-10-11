import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const path=new URL('./youtube-connection/runtime-bundle.mjs',import.meta.url);
const bytes=readFileSync(path);let runtime;let hits=0;
const deny=()=>{hits++;throw new Error('OFFLINE_SIDE_EFFECT_REJECTED');};
const env=new Proxy({}, {get:deny,set:deny});
const oldFetch=globalThis.fetch,oldDB=globalThis.DB,oldWebSocket=globalThis.WebSocket,oldEnv=process.env;
try {globalThis.fetch=deny;globalThis.DB=new Proxy({}, {get:deny});globalThis.WebSocket=deny;process.env=new Proxy(oldEnv,{get(target,key){if(['NODE_V8_COVERAGE','WATCH_REPORT_DEPENDENCIES'].includes(key))return target[key];return deny();},set:deny});runtime=await import(path.href);}
finally {globalThis.fetch=oldFetch;globalThis.DB=oldDB;globalThis.WebSocket=oldWebSocket;process.env=oldEnv;}
test('exact unchanged bundle and no module-load network D1 or credentials',()=>{assert.equal(createHash('sha256').update(bytes).digest('hex'),'8a6615fd020ca6590ba8f5e2c73a3844473d9e6ecd3babb19ea836d604d4a8a9');assert.equal(hits,0);});
test('default exact literal parked exports',()=>{assert.deepEqual(Object.keys(runtime.default).sort(),['fetch','queue','scheduled']);assert.equal(runtime.default.fetch.toString(),"async fetch(){return new Response('PARKED_RUNTIME_COMPOSITION',{status:503});}");});
test('fetch never reads request env context or dispatches legacy TARGET',async()=>{const old=globalThis.fetch;globalThis.fetch=deny;try{const r=await runtime.default.fetch(env,env,env);assert.equal(r.status,503);assert.equal(await r.text(),'PARKED_RUNTIME_COMPOSITION');assert.equal(hits,0);}finally{globalThis.fetch=old;}});
test('cron disabled without side effects',async()=>{await assert.rejects(runtime.default.scheduled(env,env,env),/CRON_DISABLED/);assert.equal(hits,0);});
test('queue disabled without side effects',async()=>{await assert.rejects(runtime.default.queue(env,env,env),/QUEUE_CONSUMER_DISABLED/);assert.equal(hits,0);});
test('live factory always disabled',()=>{assert.throws(()=>runtime.createLiveComposition(env),/PREPARATION_ONLY_REMOTE_ACTIVATION_DISABLED/);assert.equal(hits,0);});
test('offline factory cannot ambiently activate',async()=>{await assert.rejects(runtime.createOfflineComposition({}),/OPERATION_GATE_REQUIRED/);assert.equal(hits,0);});
