from oracle_bridge import require_guard
require_guard()
import copy
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import unittest
from checkpoint_e2e import (OfflineCheckpointE2E, mock_signed_callback, verify_mock_callback,
                            parse_generation_fixture, PUBLIC_FIXTURE_KEY)
from intent_ledger import Conflict, Ledger
from offline_readiness import FLAGS
from oracle_bridge import oracle

GOLDEN=json.loads(Path(__file__).with_name('parity_fixture.json').read_text())
FLAGS_ON=dict.fromkeys(FLAGS,True)
OWNER='worker-fixture'
NOW=1790942400


def entry(source='manual'):
    return {'source':source,'platform':'youtube','account_id':'youtube_game_001',
            'intent_id':'intent-e2e-001','theme':GOLDEN['theme']}


def response(): return copy.deepcopy(GOLDEN['script_response'])


def callback_body(record,outcome='succeeded'):
    return {'platform':record.intent.platform,'account_id':record.intent.account_id,
            'intent_id':record.intent.intent_id,'job_id':record.job_id,'owner':OWNER,
            'version':record.version,'callback_id':'callback-e2e-001',
            'result_id':'video-fixture-001','outcome':outcome,'issued_at':NOW}


class CheckpointE2ETests(unittest.TestCase):
    def setUp(self):
        self.flow=OfflineCheckpointE2E(FLAGS_ON)
        self.mints=[]
        self.record=self.flow.begin(entry(),OWNER,lambda:self.mints.append(1) or GOLDEN['job_id'])
        self.key=self.record.intent.key

    def checkpoint(self):
        r=self.flow.ledger.read(self.key)
        return self.flow.checkpoint(self.key,OWNER,r.version,response())

    def ready(self):
        r=self.checkpoint()
        return self.flow.make_ready(self.key,OWNER,r.version)

    def initialize(self):
        r=self.ready()['record']
        return self.flow.reserve(self.key,OWNER,r.version)

    def restart(self):
        self.flow=OfflineCheckpointE2E.restore(self.flow.snapshot(),FLAGS_ON)
        return self.flow.ledger.read(self.key)

    def test_ten_step_full_flow_and_terminal_callback(self):
        self.assertEqual(self.record.state,'generating')
        self.assertEqual(len(self.mints),1)
        checkpoint=self.checkpoint()
        self.assertEqual(checkpoint.state,'generating')
        self.assertEqual(checkpoint.version,4)
        self.assertEqual(len(checkpoint.script_fingerprint),64)
        ready=self.flow.make_ready(self.key,OWNER,checkpoint.version)
        self.assertEqual(ready['record'].state,'ready')
        self.assertEqual(ready['record'].version,5)
        self.assertEqual(ready['render_payload'],GOLDEN['render_expected'])
        self.assertEqual(ready['pipeline_inputs'],GOLDEN['pipeline_inputs_expected'])
        init=self.flow.reserve(self.key,OWNER,ready['record'].version)
        restored=self.restart()
        self.assertEqual(init.version,6)
        self.assertEqual(init,restored)
        done=self.flow.accept_callback(mock_signed_callback(callback_body(restored)),NOW)
        self.assertEqual(done.state,'succeeded')
        self.assertEqual(done.version,7)
        self.assertTrue(self.flow.recovery(self.key,OWNER)['queue_done'])
        self.assertEqual(done.dispatch_reservations,1)
        self.assertTrue(all(ready['safety'].values()))
        self.assertFalse(ready['posting_permitted'])

    def test_pending_and_claimed_generation_versions(self):
        self.assertEqual(self.record.version,3)
        self.assertEqual(self.record.job_id,GOLDEN['job_id'])
        self.assertIsNone(self.record.script_checkpoint_json)

    def test_string_generation_fixture_accepted(self):
        r=self.flow.checkpoint(self.key,OWNER,self.record.version,json.dumps(response(),ensure_ascii=False))
        self.assertEqual(json.loads(r.script_checkpoint_json),response()['output'])

    def test_generation_response_missing(self):
        before=self.flow.snapshot()
        for value in (None,{},[],{'body':response()},{'output':None}):
            with self.subTest(kind=type(value).__name__),self.assertRaises(ValueError):
                self.flow.checkpoint(self.key,OWNER,self.record.version,value)
        self.assertEqual(self.flow.snapshot(),before)

    def test_malformed_json_rejected(self):
        before=self.flow.snapshot()
        for value in ('{','not JSON','```json\n{}\n```','{"output":'):
            with self.subTest(value_type='malformed'),self.assertRaises(ValueError):
                self.flow.checkpoint(self.key,OWNER,self.record.version,value)
        self.assertEqual(self.flow.snapshot(),before)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(ValueError):parse_generation_fixture('{"output":{},"output":{}}')

    def test_nonfinite_json_rejected(self):
        for value in ('NaN','Infinity','-Infinity'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                parse_generation_fixture('{"output":{"narration":'+value+'}}')

    def test_required_script_field_missing(self):
        for key in ('title','hook','narration','scenes','bgm'):
            value=response();del value['output'][key]
            with self.subTest(key=key),self.assertRaises(ValueError):
                self.flow.checkpoint(self.key,OWNER,self.record.version,value)
        self.assertIsNone(self.flow.ledger.read(self.key).script_fingerprint)

    def test_required_scene_field_missing(self):
        value=response();del value['output']['scenes'][0]['caption']
        with self.assertRaises(ValueError):self.flow.checkpoint(self.key,OWNER,self.record.version,value)

    def test_wrong_script_type_rejected(self):
        for key,value in (('title',7),('scenes',None),('bgm',[])):
            r=response();r['output'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.flow.checkpoint(self.key,OWNER,self.record.version,r)

    def test_extra_raw_response_not_persisted(self):
        value={**response(),'raw_response':{}}
        with self.assertRaises(ValueError):self.flow.checkpoint(self.key,OWNER,self.record.version,value)

    def test_script_sensitive_text_rejected_without_save(self):
        value=response();value['output']['narration']='access_token forbidden fixture'
        with self.assertRaises(ValueError):self.flow.checkpoint(self.key,OWNER,self.record.version,value)
        self.assertIsNone(self.flow.ledger.read(self.key).script_checkpoint_json)

    def test_checkpoint_before_crash_generation_reconciliation(self):
        # Fixture response exists only in caller memory; crash loses it.
        discarded=response()
        self.assertTrue(discarded)
        r=self.restart()
        self.assertEqual(r.state,'generating');self.assertIsNone(r.script_fingerprint)
        self.assertEqual(self.flow.recovery(self.key,OWNER)['action'],'reconcile_generation_only')
        with self.assertRaises(Conflict):self.flow.make_ready(self.key,OWNER,r.version)
        self.assertEqual(r.dispatch_reservations,0)

    def test_checkpoint_after_crash_converts_without_regeneration(self):
        cp=self.checkpoint();r=self.restart()
        self.assertEqual(cp,r)
        self.assertEqual(self.flow.recovery(self.key,OWNER)['action'],'convert_saved_checkpoint')
        ready=self.flow.make_ready(self.key,OWNER,r.version)
        self.assertEqual(ready['record'].state,'ready')
        self.assertEqual(ready['record'].script_fingerprint,cp.script_fingerprint)
        self.assertEqual(ready['pipeline_inputs'],GOLDEN['pipeline_inputs_expected'])

    def test_ready_crash_before_reservation(self):
        r=self.ready()['record'];r2=self.restart()
        self.assertEqual(r,r2)
        self.assertEqual(self.flow.reserve(self.key,OWNER,r2.version).dispatch_reservations,1)

    def test_initializing_crash_reconciliation_only(self):
        r=self.initialize();self.restart()
        self.assertEqual(self.flow.recovery(self.key,OWNER)['action'],'reconciliation_only')
        with self.assertRaises(Conflict):self.flow.reserve(self.key,OWNER,r.version)
        with self.assertRaises(Conflict):self.flow.make_ready(self.key,OWNER,r.version)

    def test_unknown_crash_no_automatic_resend(self):
        r=self.initialize();r=self.flow.ledger.advance(self.key,OWNER,r.version,'unknown');self.restart()
        before=self.flow.snapshot()
        self.assertFalse(self.flow.recovery(self.key,OWNER)['auto_resend'])
        with self.assertRaises(Conflict):self.flow.reserve(self.key,OWNER,r.version)
        with self.assertRaises(Conflict):self.flow.make_ready(self.key,OWNER,r.version)
        self.assertEqual(self.flow.snapshot(),before)

    def test_unknown_late_verified_mock_callback(self):
        r=self.initialize();r=self.flow.ledger.advance(self.key,OWNER,r.version,'unknown')
        done=self.flow.accept_callback(mock_signed_callback(callback_body(r)),NOW)
        self.assertEqual(done.state,'succeeded');self.assertEqual(done.dispatch_reservations,1)

    def test_different_script_same_job_rejected(self):
        r=self.checkpoint();different=response();different['output']['narration']+='変更。'
        before=self.flow.snapshot()
        with self.assertRaisesRegex(Conflict,'immutable_script_checkpoint'):
            self.flow.checkpoint(self.key,OWNER,r.version,different)
        self.assertEqual(self.flow.snapshot(),before)

    def test_same_checkpoint_replay_noop(self):
        r=self.checkpoint()
        self.assertEqual(self.flow.checkpoint(self.key,OWNER,r.version,response()),r)

    def test_checkpoint_stale_version_rejected(self):
        old=self.record.version;self.checkpoint()
        with self.assertRaises(Conflict):self.flow.checkpoint(self.key,OWNER,old,response())

    def test_checkpoint_stale_owner_rejected(self):
        with self.assertRaises(Conflict):self.flow.checkpoint(self.key,'old-worker',self.record.version,response())

    def test_checkpoint_does_not_alias_caller(self):
        value=response();r=self.flow.checkpoint(self.key,OWNER,self.record.version,value)
        value['output']['scenes'][0]['caption']='changed'
        self.assertEqual(json.loads(r.script_checkpoint_json),response()['output'])

    def test_checkpoint_script_and_payload_mismatch_rejected(self):
        r=self.checkpoint();payload=copy.deepcopy(GOLDEN['render_expected']);payload['narration']+='different'
        with self.assertRaisesRegex(Conflict,'checkpoint_payload_mismatch'):
            self.flow.ledger.bind_content(self.key,OWNER,r.version,payload)

    def test_conversion_matches_independent_n8n_oracle(self):
        r=self.ready()
        normalized=oracle([{'op':'normalize','input':response()}])[0]
        expected_payload=oracle([{'op':'render','input':normalized}])[0]
        expected_inputs=oracle([{'op':'dispatch','input':{**expected_payload,'job_id':self.record.job_id}}])[0]['inputs']
        self.assertEqual(r['render_payload'],expected_payload)
        self.assertEqual(r['pipeline_inputs'],expected_inputs)

    def test_duplicate_mock_callback_terminal_noop(self):
        r=self.initialize();envelope=mock_signed_callback(callback_body(r))
        first=self.flow.accept_callback(envelope,NOW)
        second=self.flow.accept_callback(envelope,NOW)
        self.assertEqual(first,second)

    def test_stale_version_mock_callback_rejected(self):
        r=self.initialize();envelope=mock_signed_callback(callback_body(r))
        self.flow.ledger.advance(self.key,OWNER,r.version,'unknown')
        with self.assertRaises(Conflict):self.flow.accept_callback(envelope,NOW)

    def test_stale_owner_signed_fixture_rejected(self):
        r=self.initialize();body=callback_body(r);body['owner']='stale-worker'
        with self.assertRaises(Conflict):self.flow.accept_callback(mock_signed_callback(body),NOW)

    def test_bad_signature_no_mutation(self):
        r=self.initialize();envelope=mock_signed_callback(callback_body(r));envelope['signature']='0'*64
        before=self.flow.snapshot()
        with self.assertRaisesRegex(ValueError,'invalid_mock_signature'):self.flow.accept_callback(envelope,NOW)
        self.assertEqual(self.flow.snapshot(),before)

    def test_tampered_signed_body_rejected(self):
        r=self.initialize();envelope=mock_signed_callback(callback_body(r))
        body=json.loads(envelope['body']);body['result_id']='other-video'
        envelope['body']=json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':'))
        with self.assertRaisesRegex(ValueError,'invalid_mock_signature'):self.flow.accept_callback(envelope,NOW)

    def test_mock_domain_required(self):
        r=self.initialize();envelope=mock_signed_callback(callback_body(r));envelope['mode']='PRODUCTION'
        with self.assertRaisesRegex(ValueError,'mock_only_required'):self.flow.accept_callback(envelope,NOW)

    def test_no_real_key_input_accepted(self):
        self.assertTrue(PUBLIC_FIXTURE_KEY.startswith(b'PLM-OFFLINE-PUBLIC'))
        with self.assertRaises(TypeError):mock_signed_callback({},real_key='not accepted')

    def test_expired_and_future_callback_rejected(self):
        r=self.initialize();env=mock_signed_callback(callback_body(r))
        for now in (NOW+301,NOW-31):
            with self.subTest(now=now),self.assertRaises(ValueError):self.flow.accept_callback(env,now)

    def test_wrong_job_signed_fixture_rejected(self):
        r=self.initialize();body=callback_body(r);body['job_id']='yt-900002-1790942400000'
        with self.assertRaisesRegex(Conflict,'callback_job_mismatch'):self.flow.accept_callback(mock_signed_callback(body),NOW)

    def test_callback_unknown_intent_rejected(self):
        r=self.initialize();body=callback_body(r);body['intent_id']='unknown-intent'
        with self.assertRaisesRegex(ValueError,'unknown_callback_intent'):self.flow.accept_callback(mock_signed_callback(body),NOW)

    def test_callback_extra_secret_field_rejected(self):
        r=self.initialize();body=callback_body(r);body['access_token']='forbidden fixture'
        with self.assertRaises(ValueError):mock_signed_callback(body)

    def test_callback_before_reservation_rejected(self):
        r=self.checkpoint()
        with self.assertRaises(Conflict):self.flow.accept_callback(mock_signed_callback(callback_body(r)),NOW)

    def test_succeeded_replay_no_new_job_or_send(self):
        r=self.initialize();done=self.flow.accept_callback(mock_signed_callback(callback_body(r)),NOW);self.restart()
        replay=self.flow.begin(entry('schedule'),OWNER,lambda:self.fail('mint on replay'))
        self.assertEqual(replay,done)
        self.assertEqual(self.flow.recovery(self.key,OWNER)['action'],'terminal_noop')
        with self.assertRaises(Conflict):self.flow.reserve(self.key,OWNER,replay.version)
        self.assertEqual(done.dispatch_reservations,1)

    def test_failed_terminal_never_done(self):
        r=self.initialize();failed=self.flow.accept_callback(mock_signed_callback(callback_body(r,'failed')),NOW)
        self.assertEqual(failed.state,'failed')
        self.assertFalse(self.flow.recovery(self.key,OWNER)['queue_done'])

    def test_manual_schedule_same_checkpoint_single_reservation(self):
        r=self.checkpoint();scheduled=self.flow.begin(entry('schedule'),OWNER,lambda:self.fail('second mint'))
        self.assertEqual(scheduled,r)
        ready=self.flow.make_ready(self.key,OWNER,r.version)['record']
        first=self.flow.reserve(self.key,OWNER,ready.version)
        with self.assertRaises(Conflict):self.flow.reserve(self.key,OWNER,first.version)
        self.assertEqual(first.dispatch_reservations,1)

    def test_concurrent_checkpoint_one_CAS_winner(self):
        barrier=Barrier(8)
        def save(i):
            barrier.wait()
            try:return self.flow.checkpoint(self.key,OWNER,self.record.version,response())
            except Conflict:return None
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(save,range(8)))
        self.assertEqual(sum(r is not None for r in results),1)
        self.assertEqual(self.flow.ledger.read(self.key).state,'generating')

    def test_snapshot_checkpoint_corruption_rejected(self):
        self.checkpoint();raw=json.loads(self.flow.snapshot())
        raw['ledger']['records'][0]['script_fingerprint']='0'*64
        with self.assertRaises(ValueError):OfflineCheckpointE2E.restore(json.dumps(raw),FLAGS_ON)

    def test_snapshot_checkpoint_and_payload_correspond(self):
        self.ready();raw=json.loads(self.flow.snapshot())
        script=json.loads(raw['ledger']['records'][0]['script_checkpoint_json']);script['narration']+='changed'
        import hashlib
        canon=json.dumps(script,ensure_ascii=False,sort_keys=True,separators=(',',':'))
        raw['ledger']['records'][0]['script_checkpoint_json']=canon
        raw['ledger']['records'][0]['script_fingerprint']=hashlib.sha256(canon.encode()).hexdigest()
        with self.assertRaisesRegex(ValueError,'checkpoint_payload_mismatch'):
            OfflineCheckpointE2E.restore(json.dumps(raw),FLAGS_ON)

    def test_snapshot_excludes_callback_signature_and_raw_response(self):
        r=self.initialize();self.flow.accept_callback(mock_signed_callback(callback_body(r)),NOW)
        snapshot=self.flow.snapshot()
        self.assertNotIn('signature',snapshot);self.assertNotIn('raw_response',snapshot)
        self.assertNotIn(PUBLIC_FIXTURE_KEY.decode(),snapshot)

    def test_legacy_snapshot_format1_restored_without_inventing_checkpoint(self):
        raw=json.loads(self.flow.ledger.snapshot());raw['format']=1
        for record in raw['records']:
            del record['script_checkpoint_json'];del record['script_fingerprint']
        legacy=Ledger.restore(json.dumps(raw),FLAGS_ON)
        r=legacy.read(self.key)
        self.assertIsNone(r.script_checkpoint_json)
        restored=OfflineCheckpointE2E(FLAGS_ON,legacy)
        with self.assertRaises(Conflict):restored.make_ready(self.key,OWNER,r.version)

    def test_other_account_refused_before_mint(self):
        with self.assertRaisesRegex(ValueError,'one_account_contract_required'):
            self.flow.begin({**entry(),'account_id':'youtube_other_001'},OWNER,lambda:self.fail('wrong account mint'))

    def test_unsafe_flags_rejected_on_restore(self):
        for key in FLAGS:
            with self.subTest(key=key),self.assertRaises(ValueError):
                OfflineCheckpointE2E.restore(self.flow.snapshot(),{**FLAGS_ON,key:False})

    def test_snapshot_unknown_fields_rejected(self):
        raw=json.loads(self.flow.snapshot());raw['raw_response']={}
        with self.assertRaises(ValueError):OfflineCheckpointE2E.restore(json.dumps(raw),FLAGS_ON)

    def test_claim_crash_then_begin_resumes_generation(self):
        flow=OfflineCheckpointE2E(FLAGS_ON)
        from intent_ledger import normalize_intent
        intent=normalize_intent(entry())
        r=flow.ledger.register(intent,lambda:GOLDEN['job_id'])
        self.assertEqual(r.state,'pending')
        r=flow.ledger.claim(intent.key,OWNER)
        self.assertEqual(r.state,'claimed')
        flow=OfflineCheckpointE2E.restore(flow.snapshot(),FLAGS_ON)
        resumed=flow.begin(entry('schedule'),OWNER,lambda:self.fail('mint after claim crash'))
        self.assertEqual(resumed.state,'generating')
        self.assertEqual(resumed.job_id,r.job_id)

    def test_key_order_replay_preserves_pipeline_serialization(self):
        original=self.checkpoint()
        changed=response()
        changed['output']={k:changed['output'][k] for k in reversed(list(changed['output']))}
        for i,scene in enumerate(changed['output']['scenes']):
            changed['output']['scenes'][i]={k:scene[k] for k in reversed(list(scene))}
        replay=self.flow.checkpoint(self.key,OWNER,original.version,changed)
        self.assertEqual(replay,original)
        self.assertEqual(self.flow.make_ready(self.key,OWNER,replay.version)['pipeline_inputs'],GOLDEN['pipeline_inputs_expected'])

    def test_different_script_after_succeeded_rejected(self):
        r=self.initialize();done=self.flow.accept_callback(mock_signed_callback(callback_body(r)),NOW)
        different=response();different['output']['title']='different title'
        with self.assertRaises(Conflict):self.flow.checkpoint(self.key,OWNER,done.version,different)
        self.assertEqual(self.flow.ledger.read(self.key),done)

    def test_mock_callback_boolean_version_rejected(self):
        r=self.initialize();body=callback_body(r);body['version']=True
        with self.assertRaises(ValueError):mock_signed_callback(body)

    def test_callback_path_traversal_identifier_rejected(self):
        r=self.initialize();body=callback_body(r);body['callback_id']='../callback'
        with self.assertRaises(ValueError):mock_signed_callback(body)

    def test_snapshot_checkpoint_pair_missing_rejected(self):
        self.checkpoint();raw=json.loads(self.flow.snapshot())
        raw['ledger']['records'][0]['script_fingerprint']=None
        with self.assertRaises(ValueError):OfflineCheckpointE2E.restore(json.dumps(raw),FLAGS_ON)
