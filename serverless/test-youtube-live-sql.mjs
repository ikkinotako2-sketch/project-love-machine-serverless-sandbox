import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
import {D1Adapter,Boundary,SQL,hash,TARGET,canonical,offlineBoundedTrigger} from './youtube-live/worker.mjs';
const inputs={job_id:'job',account_id:'youtube_game_001',privacy_status:'private',notify_subscribers:'false',scheduled_for:'',narration:'offline'};
const key=new TextEncoder().encode('PUBLIC_FIXTURE_ONLY_NEVER_LIVE_00000000000');
async function fixture(seedQueue=true){
 const db=new DatabaseSync(':memory:');db.exec('PRAGMA foreign_keys=ON');
 for(const file of ['0008_provider_neutral_roundtrip_backend.sql','0009_youtube_queue_result_proposal.sql'])db.exec(readFileSync(new URL('./migrations/'+file,import.meta.url),'utf8'));
 const script=JSON.stringify({dispatch_inputs:inputs});const sh=await hash(script);const media='c'.repeat(64);const ah='a'.repeat(64);
 const run=(sql,args=[])=>db.prepare(sql).run(...args);
 run("INSERT INTO plm_rt_v2_job VALUES ('job','youtube','youtube_game_001','intent','owner',1,1,1,'ACTIVE',NULL,NULL,100,100)");
 run("INSERT INTO plm_rt_v2_script VALUES ('cp','job','owner',1,1,1,'STARTED','fixture','fixed',?,NULL,NULL,100,100)",[ah]);
 run("INSERT INTO plm_rt_v2_effect VALUES ('gen','job','GENERATION','owner',1,1,?,'gen-delivery',NULL,1,'RESERVED',100,100)",[ah]);
 run("UPDATE plm_rt_v2_effect SET state='SENT',version=2,updated_at=101 WHERE effect_id='gen'");
 run("UPDATE plm_rt_v2_script SET state='COMPLETED',version=2,script_json=?,script_sha256=?,updated_at=102",[script,sh]);
 run("UPDATE plm_rt_v2_effect SET state='CONFIRMED',version=3,result_id='gen-result',updated_at=103 WHERE effect_id='gen'");
 if(seedQueue)run("INSERT INTO plm_ytq_v1_queue VALUES ('job','youtube_game_001','intent',?,'owner',1,1,104,'QUEUED',1,104,104)",[sh]);
 let batches=0;let direct=0;const sqliteD1={withSession(mode){assert.equal(mode,'first-primary');return {
 prepare(sql){return {bind(...args){return {first:async()=>db.prepare(sql).get(...args)||null,sql,args};}};},
 async batch(statements){batches++;db.exec('BEGIN IMMEDIATE');try{const out=statements.map(s=>{direct++;const r=run(s.sql,s.args);return {success:true,meta:{changes:r.changes}};});db.exec('COMMIT');return out;}catch{db.exec('ROLLBACK');throw new Error('FIXED_SQL_FAILURE');}}
 };}};
 const adapter=new D1Adapter(sqliteD1);const c=new Boundary(adapter);
 const seedRender=()=>{
 run("INSERT INTO plm_rt_v2_effect VALUES ('render','job','RENDER','owner',1,1,?,'render-delivery',NULL,1,'RESERVED',108,108)",[ah]);
 run("UPDATE plm_rt_v2_effect SET state='SENT',version=2,updated_at=109 WHERE effect_id='render'");
 run("INSERT INTO plm_rt_v2_render VALUES ('artifact','job','owner',1,1,?,?,'artifact://offline','123','PASS',110)",[sh,media]);
 run("UPDATE plm_rt_v2_effect SET state='CONFIRMED',version=3,result_id='render-result',updated_at=111 WHERE effect_id='render'");
 run("INSERT INTO plm_rt_v2_effect VALUES ('upload','job','UPLOAD','owner',1,1,?,'upload-delivery',NULL,1,'RESERVED',112,112)",[media]);
 run("UPDATE plm_rt_v2_effect SET state='SENT',version=2,updated_at=113 WHERE effect_id='upload'");
 };
 const send=async(status=204)=>{await c.claim('job','owner',1,1,1,105);const d=await c.reserve('job',2,inputs,106);await c.mockSend(d,{offlineMock:true,send:async()=>status},107);return d;};
 const signed=async d=>{
 const body={protocol:'plm-youtube-result-v2',key_id:'fixture',account_id:'youtube_game_001',intent_id:'intent',job_id:'job',owner:'owner',owner_epoch:1,fencing_token:1,dispatch_id:d,run_id:'123',run_attempt:1,workflow_sha256:TARGET.workflow_sha256,script_sha256:sh,media_sha256:media,result_id:'result',video_id:'offline0001',privacy_status:'private',notify_subscribers:false,processing_status:'processed',quality_gate:'PASS',issued_at:114};
 const raw=canonical(body);const k=await crypto.subtle.importKey('raw',key,{name:'HMAC',hash:'SHA-256'},false,['sign']);const sig=[...new Uint8Array(await crypto.subtle.sign('HMAC',k,new TextEncoder().encode('plm-youtube-result-v2\n'+raw)))].map(x=>x.toString(16).padStart(2,'0')).join('');return [raw,sig,key,'fixture',114];};
 return {db,c,adapter,send,seedRender,signed,run,count:()=>({batches,direct})};
}
test('exact Worker SQL + both real migrations: atomic result / COMPLETE, 10 logical row writes excluding enqueue',async()=>{const f=await fixture();try{const d=await f.send();f.seedRender();const before=f.db.prepare('SELECT total_changes() n').get().n;await f.c.callback(...await f.signed(d));assert.equal(f.db.prepare('SELECT total_changes() n').get().n-before,6);assert.equal(f.db.prepare('SELECT state FROM plm_ytq_v1_queue').get().state,'COMPLETE');assert.equal(f.db.prepare('SELECT state FROM plm_ytq_v1_outbox').get().state,'CONFIRMED');assert.equal(f.db.prepare('SELECT state FROM plm_rt_v2_job').get().state,'SUCCEEDED');assert.equal(f.count().direct,6);assert.equal(f.adapter.writeStatements,6);await f.c.callback(...await f.signed(d));assert.equal(f.count().direct,6);}finally{f.db.close();}});
test('result second-statement failure rolls back callback/job/effect triggers',async()=>{const f=await fixture();try{const d=await f.send();f.seedRender();f.db.exec("CREATE TRIGGER fixture_failure BEFORE INSERT ON plm_ytq_v1_result BEGIN SELECT RAISE(ABORT,'fixture'); END");await assert.rejects(f.c.callback(...await f.signed(d)));assert.equal(f.db.prepare('SELECT count(*) n FROM plm_rt_v2_callback').get().n,0);assert.equal(f.db.prepare('SELECT state FROM plm_rt_v2_job').get().state,'ACTIVE');assert.equal(f.db.prepare('SELECT state FROM plm_ytq_v1_queue').get().state,'DISPATCHED');assert.equal(f.adapter.stopped,true);}finally{f.db.close();}});
test('UNKNOWN permanently blocks next eligible and SQL reset',async()=>{const f=await fixture();try{await assert.rejects(f.send(500));assert.equal(f.db.prepare('SELECT state FROM plm_ytq_v1_queue').get().state,'UNKNOWN');assert.equal(f.db.prepare(SQL.eligible).get(200),undefined);assert.throws(()=>f.run("UPDATE plm_ytq_v1_queue SET state='QUEUED',version=version+1,updated_at=200"));assert.throws(()=>f.run('DELETE FROM plm_ytq_v1_outbox'));}finally{f.db.close();}});
test('claim fencing stale rejects, SQL contention second claim fails',async()=>{const f=await fixture();try{await assert.rejects(f.c.claim('job','wrong',1,1,1,105));const c=new Boundary(new D1Adapter({withSession(){return {prepare(sql){return {bind(...args){return {first:async()=>f.db.prepare(sql).get(...args),sql,args};}};},batch:async s=>s.map(x=>({success:true,meta:{changes:f.run(x.sql,x.args).changes}}))};}}));await c.claim('job','owner',1,1,1,105);await assert.rejects(c.claim('job','owner',1,1,1,106));}finally{f.db.close();}});
test('send crash after durable consumption cannot reopen',async()=>{const f=await fixture();try{await f.c.claim('job','owner',1,1,1,105);const d=await f.c.reserve('job',2,inputs,106);await assert.rejects(new Boundary(f.adapter).mockSend(d,{offlineMock:true,send:async()=>204},107));assert.equal(f.db.prepare('SELECT send_attempts FROM plm_ytq_v1_outbox').get().send_attempts,0);}finally{f.db.close();}});

test('enqueue actual checkpoint and bounded trigger: no acknowledgement or next eligibility on 204',async()=>{const f=await fixture(false);try{const sh=f.db.prepare('SELECT script_sha256 FROM plm_rt_v2_script').get().script_sha256;const before=f.db.prepare('SELECT total_changes() n').get().n;await f.c.enqueue({job_id:'job',account_id:'youtube_game_001',intent_id:'intent',script_sha256:sh,owner:'owner',owner_epoch:1,fencing_token:1,not_before:104},104);assert.equal(f.db.prepare('SELECT total_changes() n').get().n-before,1);const receipt=await offlineBoundedTrigger(f.c,{job_id:'job',owner:'owner',owner_epoch:1,fencing_token:1,version:1},inputs,{offlineMock:true,send:async()=>204},105);assert.equal(receipt.acknowledgeMessage,false);assert.equal(await f.c.eligible(200),null);await assert.rejects(offlineBoundedTrigger(f.c,{job_id:'job'},inputs,{offlineMock:true,send:async()=>204},200));}finally{f.db.close();}});
