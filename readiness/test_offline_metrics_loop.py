from oracle_bridge import require_guard
require_guard()
import copy
import json
from dataclasses import replace, asdict
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any
import unittest
from intent_ledger import Conflict, Record, normalize_intent
from offline_metrics_loop import OfflineMetricsLoop
from offline_readiness import FLAGS
from parity import CATEGORIES

HERE=Path(__file__).parent
GOLDEN=json.loads((HERE/'parity_fixture.json').read_text())
FIXTURE=json.loads((HERE/'metrics_loop_fixture.json').read_text())
SOURCE=json.loads((HERE/'parity_sources.json').read_text())
FLAGS_ON=dict.fromkeys(FLAGS,True)
T=1790942400


def terminal():
    # Frozen input fixture only. This loop never invokes claim/reservation APIs.
    import hashlib
    intent=normalize_intent({'source':'manual','platform':'youtube','account_id':'youtube_game_001',
        'intent_id':'loop-origin-001','theme':GOLDEN['theme']})
    script=GOLDEN['script_response']['output']
    canonical=lambda data:json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    content=canonical(GOLDEN['render_expected'])
    return Record(intent=intent,job_id=GOLDEN['job_id'],owner='worker-loop',version=7,state='succeeded',
        content_fingerprint=hashlib.sha256(content.encode()).hexdigest(),content_json=content,
        dispatch_reservations=1,callback_id='callback-loop',result_id='video-loop-fixture',
        script_checkpoint_json=json.dumps(script,ensure_ascii=False,separators=(',',':')),
        script_fingerprint=hashlib.sha256(canonical(script).encode()).hexdigest())


class OfflineLoopTests(unittest.TestCase):
    def setUp(self):
        self.done=terminal();self.loop=OfflineMetricsLoop(FLAGS_ON)
        self.view=self.loop.start(self.done,T);self.key=('youtube','youtube_game_001',self.done.job_id)

    def fixture(self,slot='1h',status='collected',revision=1,observed=None,evidence=None):
        return {'platform':'youtube','account_id':'youtube_game_001','job_id':self.done.job_id,
            'result_id':self.done.result_id,'slot':slot,'evidence_id':evidence or 'evidence-'+slot.replace('h','hour')+'-'+str(revision),
            'revision':revision,'observed_at':observed if observed is not None else T+(3600 if slot=='1h' else 86400),
            'status':status,'metrics':copy.deepcopy(FIXTURE['one_hour_metrics' if slot=='1h' else 'day_metrics']) if status=='collected' else None}

    def collect_day(self):return self.loop.ingest(self.key,self.fixture('24h'),T+86400)
    def improve(self):return self.loop.improve(self.key,copy.deepcopy(FIXTURE['improvement']),T+86400)
    def plan(self):return self.loop.plan_next(self.key,FIXTURE['next_theme'],T+86400)
    def restart(self):self.loop=OfflineMetricsLoop.restore(self.loop.snapshot(),FLAGS_ON)

    def test_full_offline_loop(self):
        self.assertEqual(self.view['phase'],'metrics_pending')
        view=self.loop.tick(self.key,T+3600);self.assertTrue(view['slots']['1h']['due'])
        view=self.loop.ingest(self.key,self.fixture(),T+3600)
        self.assertEqual(view['slots']['1h']['state'],'collected');self.assertEqual(view['slots']['24h']['state'],'pending')
        view=self.collect_day();self.assertEqual(view['slots']['24h']['state'],'collected')
        view=self.improve();self.assertEqual(view['phase'],'improvement_ready')
        view=self.plan();self.assertEqual(view['phase'],'next_intent_planned')
        self.assertIsNone(view['next_intent']['job_id'])
        self.assertFalse(view['claim_permitted']);self.assertFalse(view['dispatch_permitted']);self.assertFalse(view['posting_permitted'])
        self.assertTrue(view['improvement']['hypothesis_only']);self.assertFalse(view['improvement']['effect_proven'])

    def test_terminal_failed_start_refused(self):
        with self.assertRaises(ValueError):self.loop.start(replace(self.done,state='failed'),T)

    def test_terminal_unknown_start_refused(self):
        with self.assertRaises(ValueError):self.loop.start(replace(self.done,state='unknown'),T)

    def test_terminal_without_explicit_result_refused(self):
        with self.assertRaises(ValueError):self.loop.start(replace(self.done,result_id=None),T)

    def test_initial_slots_independent_pending(self):
        for slot in ('1h','24h'):
            self.assertEqual(self.view['slots'][slot]['state'],'pending');self.assertFalse(self.view['slots'][slot]['due'])
            self.assertIsNone(self.view['slots'][slot]['metrics'])

    def test_due_before_at_and_after_one_hour(self):
        for seconds,expected in ((3599,False),(3600,True),(3601,True)):
            self.assertEqual(self.loop.tick(self.key,T+seconds)['slots']['1h']['due'],expected)

    def test_24h_due_independent(self):
        view=self.loop.tick(self.key,T+86400)
        self.assertTrue(view['slots']['24h']['due']);self.assertEqual(view['slots']['24h']['state'],'pending')
        self.assertEqual(view['slots']['1h']['state'],'deadline_exceeded')
        self.assertEqual(view['slots']['1h']['observation_status'],'pending')

    def test_deadline_at_boundary_not_exceeded(self):
        self.assertEqual(self.loop.tick(self.key,T+10800)['slots']['1h']['state'],'pending')

    def test_deadline_exceeded_not_missed(self):
        view=self.loop.tick(self.key,T+10801)
        self.assertEqual(view['slots']['1h']['state'],'deadline_exceeded')
        self.assertEqual(view['slots']['1h']['observation_status'],'pending')
        self.assertIsNone(view['slots']['1h']['metrics'])

    def test_missing_evidence_refused(self):
        f=self.fixture();f['evidence_id']=''
        with self.assertRaises(ValueError):self.loop.ingest(self.key,f,T+3600)

    def test_only_1h_collection_no_improvement(self):
        self.loop.ingest(self.key,self.fixture(),T+3600)
        with self.assertRaises(Conflict):self.improve()

    def test_24h_first_and_1h_late_delivery(self):
        view=self.collect_day();self.assertEqual(view['slots']['1h']['observation_status'],'pending')
        view=self.loop.ingest(self.key,self.fixture('1h'),T+86401)
        self.assertEqual(view['slots']['1h']['state'],'collected');self.assertEqual(view['slots']['24h']['state'],'collected')

    def test_24h_premature_observation_rejected(self):
        f=self.fixture('24h',observed=T+3600)
        with self.assertRaises(ValueError):self.loop.ingest(self.key,f,T+86400)

    def test_collected_after_deadline(self):
        view=self.loop.tick(self.key,T+10801)
        self.assertEqual(view['slots']['1h']['state'],'deadline_exceeded')
        view=self.loop.ingest(self.key,self.fixture(observed=T+10801),T+10801)
        self.assertEqual(view['slots']['1h']['state'],'collected');self.assertTrue(view['slots']['1h']['deadline_exceeded'])

    def test_day_collected_after_deadline(self):
        view=self.loop.ingest(self.key,self.fixture('24h',observed=T+129601),T+129601)
        self.assertEqual(view['slots']['24h']['state'],'collected');self.assertTrue(view['slots']['24h']['deadline_exceeded'])

    def test_explicit_missed_fixture(self):
        view=self.loop.ingest(self.key,self.fixture(status='missed',observed=T+10801),T+10801)
        self.assertEqual(view['slots']['1h']['state'],'missed');self.assertIsNone(view['slots']['1h']['metrics'])

    def test_missed_before_deadline_refused(self):
        with self.assertRaises(ValueError):self.loop.ingest(self.key,self.fixture(status='missed'),T+3600)

    def test_unknown_retained_after_deadline(self):
        self.loop.ingest(self.key,self.fixture(status='unknown'),T+3600)
        view=self.loop.tick(self.key,T+200000)
        self.assertEqual(view['slots']['1h']['state'],'unknown');self.assertFalse(view['slots']['1h']['auto_resend'])

    def test_unknown_cannot_be_automatically_overwritten(self):
        self.loop.ingest(self.key,self.fixture(status='unknown'),T+3600)
        with self.assertRaises(Conflict):self.loop.ingest(self.key,self.fixture(revision=2),T+3600)

    def test_24h_unknown_blocks_improvement(self):
        self.loop.ingest(self.key,self.fixture('24h',status='unknown'),T+86400)
        with self.assertRaises(Conflict):self.improve()

    def test_1h_unknown_does_not_fabricate_evidence_for_improvement(self):
        self.loop.ingest(self.key,self.fixture(status='unknown'),T+3600);self.collect_day()
        view=self.improve();self.assertIsNone(view['improvement']['evidence']['views_1h'])
        self.assertEqual(view['slots']['1h']['state'],'unknown')

    def test_missing_values_remain_null_not_zero(self):
        f=self.fixture('24h');f['metrics']={}
        view=self.loop.ingest(self.key,f,T+86400)
        self.assertTrue(all(v is None for v in view['slots']['24h']['metrics'].values()))
        view=self.improve();self.assertIsNone(view['improvement']['evidence']['views_24h'])
        self.assertEqual(view['improvement']['sample_status'],'insufficient_sample')

    def test_explicit_zero_preserved(self):
        f=self.fixture('24h');f['metrics']={'views':0,'comments':0}
        view=self.loop.ingest(self.key,f,T+86400)
        self.assertEqual(view['slots']['24h']['metrics']['views'],0)
        self.assertIsNone(view['slots']['24h']['metrics']['likes'])

    def test_small_sample_status_retained(self):
        f=self.fixture('24h');f['metrics']['views']=2
        self.loop.ingest(self.key,f,T+86400);view=self.improve()
        self.assertFalse(view['improvement']['evidence']['sample_sufficient'])
        self.assertEqual(view['improvement']['sample_status'],'insufficient_sample')
        self.assertFalse(self.plan()['improvement']['effect_proven'])

    def test_sample_threshold_matches_existing_rules(self):
        for count,enough in ((29,False),(30,True)):
            self.setUp();f=self.fixture('24h');f['metrics']['views']=count
            self.loop.ingest(self.key,f,T+86400)
            self.assertEqual(self.improve()['improvement']['evidence']['sample_sufficient'],enough)

    def test_metrics_identity_mismatch(self):
        for field,value in (('platform','tiktok'),('account_id','youtube_other_001'),('job_id','other-job'),('result_id','other-result')):
            f=self.fixture();f[field]=value
            with self.subTest(field=field),self.assertRaises(Conflict):self.loop.ingest(self.key,f,T+3600)

    def test_duplicate_fixture_noop(self):
        f=self.fixture();self.loop.ingest(self.key,f,T+3600);before=self.loop.snapshot()
        self.loop.ingest(self.key,f,T+3600);self.assertEqual(self.loop.snapshot(),before)

    def test_changed_evidence_identity_refused(self):
        f=self.fixture();self.loop.ingest(self.key,f,T+3600);f['metrics']['views']=99
        with self.assertRaises(Conflict):self.loop.ingest(self.key,f,T+3600)

    def test_same_slot_double_collection_refused(self):
        self.loop.ingest(self.key,self.fixture(),T+3600)
        with self.assertRaises(Conflict):self.loop.ingest(self.key,self.fixture(revision=2),T+3601)

    def test_collected_overwrite_refused(self):
        self.collect_day()
        with self.assertRaises(Conflict):self.loop.ingest(self.key,self.fixture('24h',status='unknown',revision=2),T+86401)

    def test_stale_revision_refused(self):
        self.loop.ingest(self.key,self.fixture(status='pending',revision=2),T+3600)
        with self.assertRaises(Conflict):self.loop.ingest(self.key,self.fixture(revision=1),T+3600)

    def test_stale_observation_time_refused(self):
        self.loop.ingest(self.key,self.fixture(status='pending',observed=T+4000),T+4000)
        with self.assertRaises(Conflict):self.loop.ingest(self.key,self.fixture(revision=2,observed=T+3600),T+4001)

    def test_pending_then_explicit_collection(self):
        self.loop.ingest(self.key,self.fixture(status='pending'),T+3600)
        view=self.loop.ingest(self.key,self.fixture(revision=2,observed=T+3700),T+3700)
        self.assertEqual(view['slots']['1h']['state'],'collected')

    def test_future_observation_refused(self):
        with self.assertRaises(ValueError):self.loop.ingest(self.key,self.fixture(observed=T+3700),T+3600)

    def test_virtual_time_backwards_refused(self):
        self.loop.tick(self.key,T+3600)
        with self.assertRaises(ValueError):self.loop.tick(self.key,T)

    def test_malformed_metrics_refused(self):
        for metrics in ([],None,{'views':'12'},{'views':True},{'views':-1},{'averageViewDuration':float('nan')},{'analytics_available':1},{'raw_response':{}}):
            f=self.fixture();f['metrics']=metrics
            with self.subTest(kind=type(metrics).__name__),self.assertRaises(ValueError):self.loop.ingest(self.key,f,T+3600)

    def test_metrics_not_collected_cannot_carry_counts(self):
        f=self.fixture(status='unknown');f['metrics']={'views':1}
        with self.assertRaises(ValueError):self.loop.ingest(self.key,f,T+3600)

    def test_invalid_fixture_fields_refused(self):
        for field,value in (('access_token','forbidden'),('raw_response',{})):
            f=self.fixture();f[field]=value
            with self.assertRaises(ValueError):self.loop.ingest(self.key,f,T+3600)

    def test_improvement_missing_each_required_category(self):
        self.collect_day()
        for key in CATEGORIES:
            output=copy.deepcopy(FIXTURE['improvement']);del output['improvement_actions'][key]
            with self.subTest(key=key),self.assertRaises(ValueError):self.loop.improve(self.key,output,T+86400)

    def test_improvement_validator_independent_source_contract(self):
        self.collect_day();ns={'Any':Any,'CATEGORIES':CATEGORIES};exec(SOURCE['producer_validator'],ns)
        for value in ('x'*180,'x'*181,'',7):
            output=copy.deepcopy(FIXTURE['improvement']);output['improvement_actions']['hook']=value
            expected=ns['validate_ai'](output)
            loop=OfflineMetricsLoop.restore(self.loop.snapshot(),FLAGS_ON)
            if expected is None:
                with self.assertRaises(ValueError):loop.improve(self.key,output,T+86400)
            else:
                view=loop.improve(self.key,output,T+86400)
                self.assertEqual(view['improvement']['validated_output']['improvement_actions'],expected['improvement_actions'])

    def test_improvement_repeat_no_duplicate_next_intent(self):
        self.collect_day();self.improve();first=self.plan();before=self.loop.snapshot()
        self.improve();second=self.plan()
        self.assertEqual(first['next_intent'],second['next_intent']);self.assertEqual(self.loop.snapshot(),before)

    def test_different_improvement_after_ready_refused(self):
        self.collect_day();self.improve();other=copy.deepcopy(FIXTURE['improvement']);other['analysis']='different'
        with self.assertRaises(Conflict):self.loop.improve(self.key,other,T+86400)

    def test_plan_without_improvement_refused(self):
        self.collect_day()
        with self.assertRaises(Conflict):self.plan()

    def test_next_candidate_immutable(self):
        self.collect_day();self.improve();self.plan()
        with self.assertRaises(Conflict):self.loop.plan_next(self.key,'changed theme',T+86400)

    def test_terminal_replay_does_not_create_second_candidate(self):
        self.collect_day();self.improve();first=self.plan();before=self.loop.snapshot()
        view=self.loop.start(self.done,T)
        self.assertEqual(view['next_intent'],first['next_intent']);self.assertEqual(self.loop.snapshot(),before)

    def test_terminal_changed_completion_refused(self):
        with self.assertRaises(Conflict):self.loop.start(self.done,T+1)

    def test_next_intent_does_not_enter_posting_ledger(self):
        before=asdict(self.done);self.collect_day();self.improve();candidate=self.plan()['next_intent']
        self.assertEqual(candidate['status'],'planned_only');self.assertIsNone(candidate['job_id'])
        self.assertEqual(asdict(self.done),before)

    def test_snapshot_restart_pending(self):
        before=self.loop.snapshot();self.restart();self.assertEqual(self.loop.snapshot(),before)

    def test_snapshot_restart_planned_no_duplicate(self):
        self.collect_day();self.improve();first=self.plan();before=self.loop.snapshot();self.restart()
        self.assertEqual(self.loop.snapshot(),before)
        self.assertEqual(self.plan()['next_intent'],first['next_intent'])

    def test_snapshot_restart_unknown_preserves_state(self):
        self.loop.ingest(self.key,self.fixture(status='unknown'),T+3600);self.restart()
        self.assertEqual(self.loop.tick(self.key,T+200000)['slots']['1h']['state'],'unknown')

    def test_late_1h_keeps_original_hypothesis_evidence_after_replay(self):
        self.collect_day();original=self.improve()['improvement'];self.plan()
        self.loop.ingest(self.key,self.fixture(),T+86401);self.restart()
        view=self.loop.tick(self.key,T+86401)
        self.assertEqual(view['improvement'],original)
        self.assertIsNone(view['improvement']['evidence']['views_1h'])
        self.assertEqual(view['slots']['1h']['state'],'collected')

    def test_snapshot_invalid_journal_refused(self):
        raw=json.loads(self.loop.snapshot());raw['records'][0]['journal']=[{'op':'dispatch','now':T}]
        with self.assertRaises(ValueError):OfflineMetricsLoop.restore(json.dumps(raw),FLAGS_ON)

    def test_snapshot_duplicate_origin_refused(self):
        raw=json.loads(self.loop.snapshot());raw['records'].append(copy.deepcopy(raw['records'][0]))
        with self.assertRaises(ValueError):OfflineMetricsLoop.restore(json.dumps(raw),FLAGS_ON)

    def test_unsafe_flags_refused(self):
        for key in FLAGS:
            with self.assertRaises(ValueError):OfflineMetricsLoop.restore(self.loop.snapshot(),{**FLAGS_ON,key:False})

    def test_concurrent_plan_one_candidate(self):
        self.collect_day();self.improve();barrier=Barrier(8)
        def plan(i):barrier.wait();return self.plan()['next_intent']['intent_id']
        with ThreadPoolExecutor(max_workers=8) as pool:ids=list(pool.map(plan,range(8)))
        self.assertEqual(len(set(ids)),1)
        journal=json.loads(self.loop.snapshot())['records'][0]['journal']
        self.assertEqual(sum(op['op']=='plan' for op in journal),1)

    def test_evidence_path_traversal_refused(self):
        f=self.fixture();f['evidence_id']='../evidence'
        with self.assertRaises(ValueError):self.loop.ingest(self.key,f,T+3600)

    def test_missed_not_overwritten_automatically(self):
        self.loop.ingest(self.key,self.fixture(status='missed',observed=T+10801),T+10801)
        with self.assertRaises(Conflict):self.loop.ingest(self.key,self.fixture(revision=2,observed=T+10802),T+10802)

    def test_snapshot_return_values_are_detached(self):
        self.collect_day();view=self.improve();view['improvement']['evidence']['views_24h']=999
        self.assertEqual(self.loop.tick(self.key,T+86400)['improvement']['evidence']['views_24h'],45)

    def test_next_candidate_links_improvement_hypothesis(self):
        self.collect_day();view=self.improve();planned=self.plan()['next_intent']
        import hashlib
        fingerprint=hashlib.sha256(json.dumps(view['improvement'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(planned['hypothesis_fingerprint'],fingerprint)
        self.assertEqual(planned['basis_job_id'],self.done.job_id)

    def test_rejected_metrics_does_not_advance_clock_or_state(self):
        before=self.loop.snapshot();f=self.fixture();f['result_id']='wrong-result'
        with self.assertRaises(Conflict):self.loop.ingest(self.key,f,T+86400)
        self.assertEqual(self.loop.snapshot(),before)
