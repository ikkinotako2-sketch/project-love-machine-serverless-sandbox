import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {CONNECTION_SQL} from './youtube-connection/connection.mjs';
import connection from './youtube-connection/worker.mjs';
import bundle from './youtube-connection/bundle.mjs';
import historical from './youtube-live/worker.mjs';
import legacy from './worker.mjs';
const read=p=>JSON.parse(readFileSync(new URL('../'+p,import.meta.url)));
test('audit SQL map equals actual exported statements',()=>assert.deepEqual(CONNECTION_SQL,read('readiness/runtime-integration-contract.json').fixed_sql));
for(const [name,w]of [['connection',connection],['bundle',bundle],['historical',historical]])test(name+' remains parked without DB/key/transport access',async()=>{
 let accessed=0;const env=new Proxy({},{get(){accessed++;throw Error('AMBIENT_ACCESS');}});
 assert.equal((await w.fetch(new Request('https://offline.test/youtube/result'),env)).status,503);
 await assert.rejects(w.scheduled({},env));await assert.rejects(w.queue({},env));assert.equal(accessed,0);
});
test('legacy test Worker remains emergency stopped',async()=>{let writes=0;const env={TEST_ONLY:'true',DRY_RUN:'true',NO_PUBLISH:'true',EMERGENCY_STOP:'true',DB:{prepare(){writes++;throw Error('WRITE');}}};const r=await legacy.fetch(new Request('https://offline.test/test-jobs',{method:'POST',body:'{}'}),env);assert.notEqual(r.status,200);assert.equal(writes,0);});
test('parked configs no routes cron consumer and safe flags',()=>{for(const file of ['serverless/wrangler.stopped.json','serverless/youtube-live/wrangler.stopped.json','serverless/youtube-connection/wrangler.stopped.json']){const c=read(file);assert.equal(c.workers_dev,false);assert.deepEqual(c.routes,[]);assert.deepEqual(c.triggers.crons,[]);assert.deepEqual(c.queues?.consumers??[],[]);assert.ok(Object.values(c.vars).every(v=>v==='true'));assert.equal(c.d1_databases[0].binding,'DB');}});
