from oracle_bridge import require_guard
require_guard()
import copy
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import unittest
from intent_ledger import Ledger, Conflict, normalize_intent, recovery, STATES
from offline_readiness import FLAGS

FLAGS_ON = dict.fromkeys(FLAGS,True)
JOB = 'yt-900001-1790942400000'
PAYLOAD = json.loads(Path(__file__).with_name('parity_fixture.json').read_text())['render_expected']


def entry(source='manual', intent_id='intent-fixture-001'):
    return {'source':source,'platform':'youtube','account_id':'youtube_game_001',
            'intent_id':intent_id,'theme':' 時計fixture '}


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.store = Ledger(FLAGS_ON)
        self.intent = normalize_intent(entry())
        self.record = self.store.register(self.intent,lambda:JOB)
        self.key = self.intent.key

    def state(self, target):
        r = self.record
        if target == 'pending': return r
        r = self.store.claim(self.key,'worker-a')
        if target == 'claimed': return r
        r = self.store.advance(self.key,'worker-a',r.version,'generating')
        if target == 'generating': return r
        r = self.store.bind_content(self.key,'worker-a',r.version,copy.deepcopy(PAYLOAD))
        if target == 'ready': return r
        r = self.store.reserve_mock_dispatch(self.key,'worker-a',r.version)
        if target == 'initializing': return r
        if target == 'unknown': return self.store.advance(self.key,'worker-a',r.version,'unknown')
        return self.store.callback(self.key,'worker-a',r.version,'callback-fixture','video-fixture',target)

    def restart(self):
        return Ledger.restore(self.store.snapshot(),FLAGS_ON)

    def test_manual_schedule_same_intent(self):
        self.assertEqual(normalize_intent(entry()),normalize_intent(entry('schedule')))

    def test_unique_ledger_and_mint_once(self):
        count=[]
        factory=lambda:count.append(1) or 'yt-900002-1790942400000'
        intent=normalize_intent(entry('schedule','intent-fixture-002'))
        first=self.store.register(intent,factory)
        second=self.store.register(normalize_intent(entry('manual','intent-fixture-002')),factory)
        self.assertEqual(first,second);self.assertEqual(len(count),1)

    def test_retry_and_restart_job_id_stable(self):
        store=self.restart()
        r=store.register(self.intent,lambda:self.fail('mint called on retry'))
        self.assertEqual(r.job_id,JOB)

    def test_same_intent_different_theme_rejected(self):
        other=normalize_intent({**entry(),'theme':'別のテーマ'})
        with self.assertRaises(Conflict): self.store.register(other,lambda:JOB)

    def test_other_intent_same_job_rejected(self):
        with self.assertRaises(Conflict):self.store.register(normalize_intent(entry(intent_id='other-intent')),lambda:JOB)

    def test_first_claim_same_owner_replay(self):
        r=self.state('claimed')
        self.assertEqual(self.store.claim(self.key,'worker-a'),r)

    def test_competing_owner_rejected(self):
        self.state('claimed')
        with self.assertRaises(Conflict):self.store.claim(self.key,'worker-b')

    def test_owner_timeout_not_takeover(self):
        r=self.state('claimed');before=self.store.snapshot()
        self.assertFalse(recovery(r,'worker-b')['takeover_permitted'])
        self.assertEqual(recovery(r,'worker-b')['action'],'blocked_owner')
        with self.assertRaises(Conflict):self.store.claim(self.key,'worker-b')
        self.assertEqual(self.store.snapshot(),before)

    def test_stale_version_rejected(self):
        r=self.state('claimed')
        self.store.advance(self.key,'worker-a',r.version,'generating')
        with self.assertRaises(Conflict):self.store.advance(self.key,'worker-a',r.version,'failed')

    def test_stale_owner_update_rejected(self):
        r=self.state('claimed')
        with self.assertRaises(Conflict):self.store.advance(self.key,'old-worker',r.version,'generating')

    def test_invalid_transition_rejected(self):
        r=self.state('claimed')
        for state in ('succeeded','initializing','pending','unknown','ready','invalid'):
            with self.subTest(state=state),self.assertRaises(Conflict):self.store.advance(self.key,'worker-a',r.version,state)

    def test_fingerprint_immutable_same_bind_noop(self):
        r=self.state('ready')
        self.assertEqual(self.store.bind_content(self.key,'worker-a',r.version,copy.deepcopy(PAYLOAD)),r)

    def test_same_job_different_fingerprint_rejected(self):
        r=self.state('ready');changed=copy.deepcopy(PAYLOAD);changed['narration']+='変更'
        with self.assertRaisesRegex(Conflict,'immutable_content'):self.store.bind_content(self.key,'worker-a',r.version,changed)
        self.assertEqual(self.store.read(self.key),r)

    def test_content_detached_from_caller(self):
        r=self.state('generating');payload=copy.deepcopy(PAYLOAD)
        stored=self.store.bind_content(self.key,'worker-a',r.version,payload)
        payload['scenes'][0]['caption']='modified'
        self.assertEqual(json.loads(stored.content_json),PAYLOAD)

    def test_manual_schedule_no_second_mock_dispatch(self):
        r=self.state('ready')
        scheduled=self.store.register(normalize_intent(entry('schedule')),lambda:self.fail('new job'))
        first=self.store.reserve_mock_dispatch(self.key,'worker-a',scheduled.version)
        with self.assertRaises(Conflict):self.store.reserve_mock_dispatch(self.key,'worker-a',first.version)
        self.assertEqual(self.store.read(self.key).dispatch_reservations,1)

    def test_crash_after_claim_restart_resume(self):
        r=self.state('claimed');store=self.restart()
        self.assertEqual(store.read(self.key),r)
        self.assertEqual(recovery(r,'worker-a')['action'],'resume_generation_fixture')
        self.assertEqual(r.dispatch_reservations,0)

    def test_script_generated_not_saved_crash_reconcile(self):
        r=self.state('generating');store=self.restart()
        self.assertEqual(recovery(store.read(self.key),'worker-a')['action'],'reconcile_saved_script')
        self.assertIsNone(r.content_fingerprint)
        self.assertEqual(r.dispatch_reservations,0)

    def test_script_saved_crash_restart_ready(self):
        r=self.state('ready');store=self.restart()
        self.assertEqual(store.read(self.key),r)
        self.assertEqual(recovery(r,'worker-a')['action'],'reserve_mock_dispatch_only')

    def test_crash_before_reservation_zero_dispatch(self):
        r=self.state('ready');store=self.restart()
        self.assertEqual(store.read(self.key).dispatch_reservations,0)
        self.assertEqual(store.reserve_mock_dispatch(self.key,'worker-a',r.version).dispatch_reservations,1)

    def test_crash_after_reservation_before_send_no_resend(self):
        r=self.state('initializing');store=self.restart()
        self.assertEqual(recovery(r,'worker-a')['action'],'reconciliation_only')
        with self.assertRaises(Conflict):store.reserve_mock_dispatch(self.key,'worker-a',r.version)
        self.assertEqual(store.read(self.key).dispatch_reservations,1)

    def test_external_response_unknown_no_reinitialize(self):
        r=self.state('unknown');store=self.restart()
        hint=recovery(r,'worker-a')
        self.assertFalse(hint['auto_resend']);self.assertFalse(hint['initialize_permitted'])
        with self.assertRaises(Conflict):store.reserve_mock_dispatch(self.key,'worker-a',r.version)
        self.assertEqual(store.read(self.key),r)

    def test_duplicate_callback_noop(self):
        r=self.state('initializing')
        first=self.store.callback(self.key,'worker-a',r.version,'callback-fixture','video-fixture','succeeded')
        again=self.store.callback(self.key,'worker-a',r.version,'callback-fixture','video-fixture','succeeded')
        self.assertEqual(first,again)

    def test_stale_owner_callback_rejected(self):
        r=self.state('initializing')
        with self.assertRaises(Conflict):self.store.callback(self.key,'old-worker',r.version,'callback-fixture','video-fixture','succeeded')

    def test_stale_version_callback_rejected(self):
        r=self.state('initializing')
        self.store.advance(self.key,'worker-a',r.version,'unknown')
        with self.assertRaises(Conflict):self.store.callback(self.key,'worker-a',r.version,'callback-fixture','video-fixture','succeeded')

    def test_unknown_resolution_fixture_callback(self):
        r=self.state('unknown')
        r=self.store.callback(self.key,'worker-a',r.version,'late-callback','video-fixture','succeeded')
        self.assertEqual(r.state,'succeeded');self.assertEqual(r.dispatch_reservations,1)

    def test_succeeded_replay_terminal_restart(self):
        r=self.state('succeeded');store=self.restart()
        self.assertEqual(store.claim(self.key,'worker-a'),r)
        self.assertEqual(recovery(r,'worker-a')['action'],'terminal_noop')
        self.assertTrue(recovery(r,'worker-a')['queue_done'])
        with self.assertRaises(Conflict):store.reserve_mock_dispatch(self.key,'worker-a',r.version)

    def test_failed_never_done(self):
        r=self.state('failed')
        self.assertFalse(recovery(r,'worker-a')['queue_done'])
        self.assertEqual(recovery(r,'worker-a')['action'],'terminal_failed')

    def test_wrong_owner_cannot_mark_done(self):
        r=self.state('succeeded')
        self.assertFalse(recovery(r,'stale-worker')['queue_done'])

    def test_conflicting_terminal_callback_rejected(self):
        r=self.state('succeeded')
        with self.assertRaises(Conflict):self.store.callback(self.key,'worker-a',r.version,'other-callback','other-result','failed')

    def test_all_state_restart_roundtrip(self):
        for state in sorted(STATES):
            with self.subTest(state=state):
                self.setUp();r=self.state(state)
                self.assertEqual(self.restart().read(self.key),r)

    def test_concurrent_claim_one_owner(self):
        barrier=Barrier(8)
        def contender(i):
            barrier.wait()
            try:return self.store.claim(self.key,f'worker-{i}').owner
            except Conflict:return None
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(contender,range(8)))
        winners=[r for r in results if r]
        self.assertEqual(len(winners),1);self.assertEqual(self.store.read(self.key).version,2)

    def test_concurrent_registration_mints_once(self):
        barrier=Barrier(8);count=[]
        intent=normalize_intent(entry(intent_id='race-intent'))
        def contender(i):
            barrier.wait()
            return self.store.register(intent,lambda:count.append(1) or 'yt-900002-1790942400000')
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(contender,range(8)))
        self.assertEqual(len(count),1);self.assertTrue(all(r==results[0] for r in results))

    def test_snapshot_tamper_fingerprint_rejected(self):
        self.state('ready');raw=json.loads(self.store.snapshot())
        raw['records'][0]['content_fingerprint']='0'*64
        with self.assertRaises(ValueError):Ledger.restore(json.dumps(raw),FLAGS_ON)

    def test_snapshot_duplicate_identity_rejected(self):
        raw=json.loads(self.store.snapshot());raw['records'].append(raw['records'][0])
        with self.assertRaises(ValueError):Ledger.restore(json.dumps(raw),FLAGS_ON)

    def test_snapshot_secret_field_rejected(self):
        raw=json.loads(self.store.snapshot());raw['records'][0]['access_token']='fixture-forbidden'
        with self.assertRaises(ValueError):Ledger.restore(json.dumps(raw),FLAGS_ON)

    def test_secret_or_traversal_identifier_rejected(self):
        for value in ('../intent','access_token','bearer value'):
            with self.subTest(value=value),self.assertRaises(ValueError):normalize_intent({**entry(),'intent_id':value})

    def test_unsafe_flags_rejected(self):
        for key in FLAGS:
            flags={**FLAGS_ON,key:False}
            with self.assertRaises(ValueError):Ledger(flags)

    def test_content_extra_raw_response_rejected(self):
        r=self.state('generating')
        with self.assertRaises(ValueError):self.store.bind_content(self.key,'worker-a',r.version,{**PAYLOAD,'raw_response':{}})

    def test_content_bad_caption_or_secret_rejected(self):
        r=self.state('generating')
        for key,value in (('title','access_token fixture'),('captions',[])):
            payload={**PAYLOAD,key:value}
            with self.assertRaises(ValueError):self.store.bind_content(self.key,'worker-a',r.version,payload)

    def test_concurrent_same_owner_dispatch_reservation_one_winner(self):
        r=self.state('ready');barrier=Barrier(8)
        def contender(i):
            barrier.wait()
            try:return self.store.reserve_mock_dispatch(self.key,'worker-a',r.version).dispatch_reservations
            except Conflict:return None
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(contender,range(8)))
        self.assertEqual(results.count(1),1)
        self.assertEqual(self.store.read(self.key).dispatch_reservations,1)

    def test_generation_failure_not_queue_done(self):
        r=self.state('generating')
        r=self.store.advance(self.key,'worker-a',r.version,'failed')
        self.assertFalse(recovery(r,'worker-a')['queue_done'])
        self.assertIsNone(r.content_fingerprint)
        self.assertEqual(r.dispatch_reservations,0)

    def test_unknown_cannot_transition_back_to_ready(self):
        r=self.state('unknown')
        for state in ('claimed','generating','ready','initializing','failed'):
            with self.subTest(state=state),self.assertRaises(Conflict):self.store.advance(self.key,'worker-a',r.version,state)

    def test_snapshot_corrupt_version_rejected(self):
        raw=json.loads(self.store.snapshot());raw['records'][0]['version']=True
        with self.assertRaises(ValueError):Ledger.restore(json.dumps(raw),FLAGS_ON)
