import {test} from 'node:test';
import assert from 'node:assert/strict';
import worker,{TARGET,FIELDS,SQL,canonical,hash,verifyCallback,D1Adapter,Boundary,offlineIngress} from './youtube-live/worker.mjs';
const key=new TextEncoder().encode('PUBLIC_FIXTURE_ONLY_NEVER_LIVE_00000000000');
const b={protocol:'plm-youtube-result-v2',key_id:'fixture',account_id:'youtube_game_001',intent_id:'intent',job_id:'job',owner:'owner',owner_epoch:1,fencing_token:1,dispatch_id:'a'.repeat(64),run_id:'123',run_attempt:1,workflow_sha256:TARGET.workflow_sha256,script_sha256:'b'.repeat(64),media_sha256:'c'.repeat(64),result_id:'result',video_id:'offline0001',privacy_status:'private',notify_subscribers:false,processing_status:'processed',quality_gate:'PASS',issued_at:1000};
async function signed(body=b){const raw=canonical(body);const k=await crypto.subtle.importKey('raw',key,{name:'HMAC',hash:'SHA-256'},false,['sign']);const bytes=new Uint8Array(await crypto.subtle.sign('HMAC',k,new TextEncoder().encode('plm-youtube-result-v2\n'+raw)));return [raw,[...bytes].map(x=>x.toString(16).padStart(2,'0')).join('')];}
test('valid dedicated protocol HMAC',async()=>assert.deepEqual(await verifyCallback(...await signed(),key,'fixture',1000),b));
for(const [field,value] of Object.entries({protocol:'other',key_id:'other',account_id:'other',job_id:'!',owner_epoch:0,fencing_token:1.5,run_id:'0',run_attempt:2,workflow_sha256:'d'.repeat(64),script_sha256:'bad',privacy_status:'public',notify_subscribers:true,processing_status:'queued',quality_gate:'FAIL',issued_at:699,video_id:'bad'}))test('reject '+field,async()=>await assert.rejects(verifyCallback(...await signed({...b,[field]:value}),key,'fixture',1000)));
for(const delta of [-301,31])test('skew '+delta,async()=>await assert.rejects(verifyCallback(...await signed({...b,issued_at:1000+delta}),key,'fixture',1000)));
for(const delta of [-300,30])test('skew accepted '+delta,async()=>assert.ok(await verifyCallback(...await signed({...b,issued_at:1000+delta}),key,'fixture',1000)));
test('changed signature',async()=>await assert.rejects(verifyCallback((await signed())[0],'0'.repeat(64),key,'fixture',1000)));
test('duplicate JSON keys rejected',async()=>await assert.rejects(verifyCallback((await signed())[0].replace('{','{"job_id":"evil",'),'0'.repeat(64),key,'fixture',1000)));
test('body limit',async()=>await assert.rejects(verifyCallback(' '.repeat(8193),'0'.repeat(64),key,'fixture',1000)));
const inputs={job_id:'job',account_id:'youtube_game_001',privacy_status:'private',notify_subscribers:'false',scheduled_for:'',narration:'offline'};
const script=JSON.stringify({dispatch_inputs:inputs});
async function fixture(){const q={...b,state:'CLAIMED',job_state:'ACTIVE',version:2,script_sha256:await hash(script)};const calls=[];const a={read:async(n)=>n==='row'?q:n==='script'?{script_json:script}:null,batch:async entries=>{calls.push(entries);return entries.map(()=>({success:true,meta:{changes:1}}));}};return {q,calls,a,c:new Boundary(a)};}
test('reservation commits before one mock send; 204 is not upload',async()=>{const {c,calls}=await fixture();const d=await c.reserve('job',2,inputs,1000);let sends=0;const t={offlineMock:true,send:async(target,p)=>{sends++;assert.equal(calls.length,2);assert.equal(target.ref,TARGET.ref);assert.equal(p.ref,TARGET.ref);return 204;}};assert.equal((await c.mockSend(d,t,1000)).uploadSucceeded,false);await assert.rejects(c.mockSend(d,t,1000));assert.equal(sends,1);});
for(const status of [200,202,400,500,'204'])test('non204 permanent UNKNOWN '+status,async()=>{const {c,calls}=await fixture();const d=await c.reserve('job',2,inputs,1000);await assert.rejects(c.mockSend(d,{offlineMock:true,send:async()=>status},1000));assert.equal(calls.at(-1)[0][0],'unknownOut');await assert.rejects(c.eligible(1000));});
test('timeout UNKNOWN',async()=>{const {c}=await fixture();const d=await c.reserve('job',2,inputs,1000);await assert.rejects(c.mockSend(d,{offlineMock:true,send:async()=>{throw new Error('timeout');}},1000));assert.equal(c.stopped,true);});
test('reopened instance cannot resume reservation',async()=>{const {c,a}=await fixture();const d=await c.reserve('job',2,inputs,1000);await assert.rejects(new Boundary(a).mockSend(d,{offlineMock:true,send:async()=>204},1000));});
test('live transport rejected',async()=>{const {c}=await fixture();const d=await c.reserve('job',2,inputs,1000);await assert.rejects(c.mockSend(d,{send:async()=>204},1000));});
test('durable script input mismatch',async()=>{const {c}=await fixture();await assert.rejects(c.reserve('job',2,{...inputs,narration:'changed'},1000));});
test('D1 primary and fixed query; unknown poisons adapter',async()=>{let primary;const db={withSession:x=>{primary=x;return {prepare:()=>({bind:()=>({first:async()=>null})}),batch:async()=>[{success:true,meta:{changes:0}}]};}};const a=new D1Adapter(db);assert.equal(primary,'first-primary');await assert.rejects(a.batch([['claim',[]]]));await assert.rejects(a.read('row',[]));});
async function cbFixture(){let writes=0;const q={...b,state:'DISPATCHED',job_state:'ACTIVE'};const r={...b,render_run_id:b.run_id,artifact_sha256:b.media_sha256,upload_state:'SENT',delivery_id:'upload'};const a={read:async n=>n==='row'?q:n==='outbox'?{job_id:b.job_id,state:'SENT',send_attempts:1}:n==='render'?r:null,batch:async entries=>{writes++;assert.equal(entries[0][0],'callback');assert.equal(entries[1][0],'result');}};return {q,r,c:new Boundary(a),writes:()=>writes};}
test('callback atomic batch',async()=>{const f=await cbFixture();assert.equal((await f.c.callback(...await signed(),key,'fixture',1000)).queueComplete,true);assert.equal(f.writes(),1);});
for(const field of ['owner','owner_epoch','fencing_token','intent_id','script_sha256'])test('durable binding '+field,async()=>{const f=await cbFixture();f.q[field]='other';await assert.rejects(f.c.callback(...await signed(),key,'fixture',1000));assert.equal(f.writes(),0);});
for(const field of ['render_run_id','artifact_sha256','quality_gate','upload_state'])test('render binding '+field,async()=>{const f=await cbFixture();f.r[field]='other';await assert.rejects(f.c.callback(...await signed(),key,'fixture',1000));assert.equal(f.writes(),0);});
test('identical result replay zero writes',async()=>{const {c}=await cbFixture();const raw=(await signed())[0];c.a.read=async()=>({result_id:b.result_id,job_id:b.job_id,payload_sha256:await hash(raw)});assert.equal((await c.callback(...await signed(),key,'fixture',1000)).replay,true);});
test('changed replay rejected',async()=>{const {c}=await cbFixture();c.a.read=async()=>({result_id:b.result_id,job_id:b.job_id,payload_sha256:'0'.repeat(64)});await assert.rejects(c.callback(...await signed(),key,'fixture',1000));});
test('ingress verifies and rejects oversized stream before writes',async()=>{const f=await cbFixture();const ingress=offlineIngress(f.c,key,'fixture',()=>1000);const [raw,sig]=await signed();assert.equal((await ingress(new Request('https://offline.test/youtube/result',{method:'POST',headers:{'content-type':'application/json','x-plm-signature':sig},body:raw}))).status,200);assert.equal((await ingress(new Request('https://offline.test/youtube/result',{method:'POST',headers:{'content-type':'application/json'},body:'x'.repeat(8193)}))).status,409);assert.equal(f.writes(),1);});
test('deployed ingress and both triggers permanently disabled',async()=>{assert.equal((await worker.fetch()).status,503);await assert.rejects(worker.scheduled());await assert.rejects(worker.queue());});

test('successor manifest binds exact source/bundle/workflow, immutable old plan and evidence',async()=>{
 const {readFileSync}=await import('node:fs');
 const plan=JSON.parse(readFileSync(new URL('../readiness/youtube-live-worker-successor-plan.json',import.meta.url),'utf8'));
 for(const [file,expected] of Object.entries(plan.source_sha256))assert.equal(await hash(readFileSync(new URL('../'+file,import.meta.url),'utf8')),expected,file);
 assert.equal(plan.exact_parent_sha,'33d2471f65c01fc9397c8d1d04e9299c2fb135a8');
 assert.equal(plan.worker_source_sha256,plan.bundle_sha256);
 assert.equal(plan.budget.maximum_dispatch_sends_this_plan,0);
 assert.equal(plan.budget.physical_d1_rows_written_maximum,'UNVERIFIED');
 assert.equal(plan.deploy_launchable,false);
 assert.equal(plan.trigger_disabled_after_deploy,true);assert.equal(plan.upload_disabled_after_deploy,true);
 const old=JSON.parse(readFileSync(new URL('../readiness/youtube-live-connection-plan.json',import.meta.url),'utf8'));
 assert.equal(old.current_remote_schema,'UNVERIFIED');
 const evidence=JSON.parse(readFileSync(new URL('../readiness/youtube-remote-readonly-37409541462.json',import.meta.url),'utf8'));
 assert.equal(await hash(readFileSync(new URL('../readiness/youtube-live-connection-plan.json',import.meta.url),'utf8')),evidence.plan_sha256);
 assert.equal(evidence.read_only_identity_consumed,true);
});

test('never-resolving mock transport times out and permanently stops',async()=>{const {c}=await fixture();const d=await c.reserve('job',2,inputs,1000);await assert.rejects(c.mockSend(d,{offlineMock:true,send:()=>new Promise(()=>{})},1000,1));assert.equal(c.stopped,true);});
