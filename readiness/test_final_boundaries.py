"""Mandatory kernel guard; public fixed fixtures; NO clients or media work."""
from oracle_bridge import require_guard
require_guard()
import copy
import json
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from dataclasses import asdict
from generation_contract import *
from durable_reference import ReferenceAuthority,ReferenceClient,DurableStoreContract
from callback_boundary import sign_fixture,verify_fixture,accept_fixture
from final_readiness import *
from intent_ledger import Conflict
from checkpoint_e2e import OfflineCheckpointE2E

HERE=Path(__file__).parent
FIX=json.loads((HERE/'parity_fixture.json').read_text())
METRICS=json.loads((HERE/'metrics_loop_fixture.json').read_text())
SCRIPT=FIX['script_response']['output']
FLAGS_ON=dict.fromkeys(FLAGS,True)
JOB=FIX['job_id'];T=1790942400
ENTRY={'source':'manual','platform':'youtube','account_id':'youtube_game_001','intent_id':'final-fixture','theme':FIX['theme']}


def provider(script=None):
    return json.dumps({'candidates':[{'content':{'role':'model','parts':[{'text':canonical(script if script is not None else SCRIPT)}]},'finishReason':'STOP','index':0}],
                       'usageMetadata':{'totalTokenCount':100},'modelVersion':'public-fixture'},ensure_ascii=False)


class Setup(unittest.TestCase):
    def setUp(self):
        self.hub=ReferenceAuthority(FLAGS_ON);self.client=self.hub.client();self.other=self.hub.client()
        self.client.register(ENTRY,lambda:JOB);self.key=('youtube','youtube_game_001','final-fixture')
    def row(self):return self.client.read(self.key)
    def call(self,operation,*args):
        v=self.row();r=v['record'];return getattr(self.client,operation)(self.key,r.owner,v['owner_epoch'],r.version,*args)
    def claim(self):return self.client.claim(self.key,'owner-a',self.row()['record'].version)
    def generating(self):self.claim();return self.call('transition','generating')
    def checkpoint(self):self.generating();return self.call('checkpoint',copy.deepcopy(SCRIPT))
    def ready(self):self.checkpoint();return self.call('make_ready')
    def initializing(self):self.ready();return self.call('reserve')
    def body(self,**changes):
        v=self.row();r=v['record']
        return {'protocol':'plm-callback-v1','key_id':'fixture-current','platform':'youtube','account_id':'youtube_game_001','intent_id':'final-fixture','job_id':JOB,'owner':r.owner,'owner_epoch':v['owner_epoch'],'version':r.version,'issued_at':T,'delivery_id':'delivery-final','result_id':'result-final','outcome':'succeeded',**changes}
    def succeeded(self):self.initializing();return accept_fixture(self.client,sign_fixture(self.body()),T,T)
    def metric(self,slot='24h',**changes):
        v=copy.deepcopy(METRICS['one_hour_metrics' if slot=='1h' else 'day_metrics']);return {'platform':'youtube','account_id':'youtube_game_001','job_id':JOB,'result_id':'result-final','slot':slot,'evidence_id':'evidence-'+slot,'revision':1,'observed_at':T+(3600 if slot=='1h' else 86400),'status':'collected','metrics':v,**changes}
    def improve(self):return self.call('improvement',METRICS['improvement'],T+86400)
    def plan(self):return self.call('plan_next',METRICS['next_theme'],T+86400)
    def evidence(self):return {'mode':'OFFLINE_EVIDENCE','stopped_owner':'owner-a','epoch':1,'stop_evidence_id':'stop-1','side_effect_evidence_id':'settled-1','no_inflight':True,'supervisor_approval_id':'approval-fixture'}
    def restart(self):self.client=ReferenceClient.restore(self.client.snapshot(),FLAGS_ON);self.hub=self.client.a;self.other=self.hub.client()


class GenerationTests(Setup):
    def test_model_request_no_client_or_credential(self):
        r=request_fixture(ENTRY,JOB,FLAGS_ON,METRICS['improvement']);self.assertFalse(r['live_permitted']);self.assertEqual(r['project_quota'],'UNVERIFIED')
        c=r['payload']['generationConfig'];self.assertEqual(c['responseFormat']['text']['mimeType'],'application/json');self.assertNotIn('tools',r['payload'])
    def test_schema_fields_exact_v2(self):self.assertEqual(set(output_schema()['required']),set(SCRIPT))
    def test_script_fixture_exact_parity(self):self.assertEqual(parse_script(canonical(SCRIPT),ENTRY['theme'],JOB,FLAGS_ON),SCRIPT)
    def test_provider_fixture_metadata_discarded(self):self.assertEqual(parse_provider_fixture(provider(),ENTRY['theme'],JOB,FLAGS_ON),SCRIPT)
    def test_provider_missing_candidate(self):
        with self.assertRaises(ValueError):parse_provider_fixture('{}',ENTRY['theme'],JOB,FLAGS_ON)
    def test_partial_finish_rejected(self):
        p=json.loads(provider());p['candidates'][0]['finishReason']='MAX_TOKENS'
        with self.assertRaises(ValueError):parse_provider_fixture(json.dumps(p),ENTRY['theme'],JOB,FLAGS_ON)
    def test_multiple_candidates_rejected(self):
        p=json.loads(provider());p['candidates']*=2
        with self.assertRaises(ValueError):parse_provider_fixture(json.dumps(p),ENTRY['theme'],JOB,FLAGS_ON)
    def test_thought_or_tool_part_rejected(self):
        p=json.loads(provider());p['candidates'][0]['content']['parts'][0]['thought']=True
        with self.assertRaises(ValueError):parse_provider_fixture(json.dumps(p),ENTRY['theme'],JOB,FLAGS_ON)
    def test_required_field_missing(self):
        for k in SCRIPT:
            s=copy.deepcopy(SCRIPT);del s[k]
            with self.subTest(k=k),self.assertRaises(ValueError):parse_script(canonical(s),ENTRY['theme'],JOB,FLAGS_ON)
    def test_invalid_types_rejected(self):
        for field,val in [('title',1),('narration',None),('scenes',{}),('bgm',[])]:
            s=copy.deepcopy(SCRIPT);s[field]=val
            with self.subTest(field=field),self.assertRaises(ValueError):parse_script(canonical(s),ENTRY['theme'],JOB,FLAGS_ON)
    def test_invalid_timeline_rejected(self):
        s=copy.deepcopy(SCRIPT);s['scenes'][0]['end']=0
        with self.assertRaises(ValueError):parse_script(canonical(s),ENTRY['theme'],JOB,FLAGS_ON)
    def test_feedback_exact_seven_items(self):
        o=copy.deepcopy(METRICS['improvement']);del o['improvement_actions']['hook']
        with self.assertRaises(ValueError):request_fixture(ENTRY,JOB,FLAGS_ON,o)
    def test_theme_limit_and_unicode(self):
        for theme in ['x'*241,'abc\n','\ud800','abc\u202e']:
            with self.subTest(theme=repr(theme)),self.assertRaises(ValueError):request_fixture({**ENTRY,'theme':theme},JOB,FLAGS_ON)
    def test_unknown_model_denied(self):
        with self.assertRaises(ValueError):request_fixture(ENTRY,JOB,FLAGS_ON,model='gemini-latest')
    def test_request_fingerprint_deterministic(self):self.assertEqual(request_fixture(ENTRY,JOB,FLAGS_ON),request_fixture(ENTRY,JOB,FLAGS_ON))
    def test_byte_limit_multibyte(self):
        with self.assertRaises(ValueError):strict_json(json.dumps('あ'*22000,ensure_ascii=False))
    def test_nested_duplicate_keys(self):
        with self.assertRaises(ValueError):strict_json('{"x":{"a":1,"a":2}}')
    def test_nonfinite_rejected(self):
        for raw in ['NaN','Infinity','1e999']:
            with self.subTest(raw=raw),self.assertRaises(ValueError):strict_json(raw)
    def test_depth_limit(self):
        with self.assertRaises(ValueError):strict_json('['*30+'0'+']'*30)
    def test_control_chars_rejected(self):
        for text in ['\n','\t','\x00','\x7f','\u0085','\u2028','\udfff']:
            with self.subTest(text=repr(text)),self.assertRaises(ValueError):strict_json(json.dumps({'a':text}))
    def test_valid_emoji_unicode(self):self.assertEqual(strict_json('"時計😀"'),'時計😀')
    def test_no_automatic_error_retry(self):
        for k in ['http_400','http_401','http_403','http_404','http_429','http_500','http_503','timeout','ambiguous','invalid_output','quota_unverified']:
            with self.subTest(kind=k):self.assertFalse(classify_error(k)['auto_retry'])
    def test_retry_candidate_bounded(self):
        self.assertEqual(classify_error('http_429')['category'],'retry_candidate_after_quota_review');self.assertEqual(classify_error('http_429',attempts=2)['category'],'non_retryable')
    def test_ambiguous_requires_reconciliation(self):self.assertEqual(classify_error('timeout')['category'],'reconciliation_required')
    def test_checkpoint_error_priority(self):self.assertEqual(classify_error('http_503',True)['category'],'checkpoint_first')
    def test_checkpoint_provider_raw_not_saved(self):
        e=OfflineCheckpointE2E(FLAGS_ON);r=e.begin(ENTRY,'owner-a',lambda:JOB);key=r.intent.key
        r=checkpoint_provider(e,key,'owner-a',r.version,provider());self.assertNotIn('usageMetadata',e.snapshot());self.assertEqual(generation_decision(r),'checkpoint_first_no_regeneration')
    def test_checkpoint_stops_provider_regeneration(self):
        e=OfflineCheckpointE2E(FLAGS_ON);r=e.begin(ENTRY,'owner-a',lambda:JOB);key=r.intent.key;r=checkpoint_provider(e,key,'owner-a',r.version,provider())
        with self.assertRaises(Conflict):checkpoint_provider(e,key,'owner-a',r.version,provider())
    def test_checkpoint_first_after_restart(self):
        self.checkpoint();self.restart();self.assertEqual(generation_decision(self.row()['record']),'checkpoint_first_no_regeneration')


class DurableTests(Setup):
    def test_register_mint_once_across_handles(self):
        def forbidden():raise AssertionError('remint')
        r=self.other.register({**ENTRY,'source':'schedule'},forbidden);self.assertEqual(r['record'].job_id,JOB)
    def test_same_intent_different_theme_rejected(self):
        with self.assertRaises(Conflict):self.other.register({**ENTRY,'theme':'changed'},lambda:JOB)
    def test_concurrent_independent_handles_one_owner(self):
        b=Barrier(8)
        def run(i):
            c=self.hub.client();b.wait()
            try:c.claim(self.key,'runner-'+str(i),1);return 'won'
            except Conflict:return 'lost'
        with ThreadPoolExecutor(max_workers=8) as p:out=list(p.map(run,range(8)))
        self.assertEqual(out.count('won'),1);self.assertEqual(out.count('lost'),7)
    def test_same_owner_claim_recovery(self):self.claim();self.assertEqual(self.other.claim(self.key,'owner-a',1),self.row())
    def test_stale_claim_version_rejected(self):
        with self.assertRaises(Conflict):self.client.claim(self.key,'owner-a',0)
    def test_checkpoint_cas_stale_rejected(self):
        self.generating();v=self.row();self.call('checkpoint',SCRIPT)
        with self.assertRaises(Conflict):self.other.checkpoint(self.key,'owner-a',1,v['record'].version,SCRIPT)
    def test_same_job_different_script_rejected(self):
        self.checkpoint();s=copy.deepcopy(SCRIPT);s['title']='changed'
        with self.assertRaises(Conflict):self.call('checkpoint',s)
    def test_checkpoint_same_content_no_op(self):self.checkpoint();before=self.client.snapshot();self.call('checkpoint',SCRIPT);self.assertEqual(self.client.snapshot(),before)
    def test_version_monotonic(self):
        self.claim();self.call('transition','generating');self.call('checkpoint',SCRIPT);self.call('make_ready')
        versions=[x['version'] for x in self.hub.audit];self.assertEqual(versions,list(range(1,6)))
    def test_initialization_reservation_once(self):
        self.initializing()
        with self.assertRaises(Conflict):self.call('reserve')
    def test_unknown_no_initialize(self):
        self.initializing();self.call('transition','unknown')
        with self.assertRaises(Conflict):self.call('reserve')
    def test_terminal_replay_atomic(self):
        self.initializing();b=self.body();self.client.complete_delivery(b,T);before=self.client.snapshot();self.other.complete_delivery(b,T);self.assertEqual(before,self.client.snapshot())
    def test_terminal_changed_outcome_rejected(self):
        self.succeeded();b=self.body(outcome='failed',delivery_id='delivery-other')
        with self.assertRaises(Conflict):self.client.complete_delivery(b,T)
    def test_delivery_payload_changed_rejected(self):
        self.succeeded();b=self.body(issued_at=T+1)
        with self.assertRaises(Conflict):self.client.complete_delivery(b,T)
    def test_metrics_slot_cas(self):
        self.succeeded();v=self.row();self.call('metrics',self.metric(),T+86400)
        with self.assertRaises(Conflict):self.other.metrics(self.key,'owner-a',1,v['record'].version,self.metric('1h'),T+86400)
    def test_metrics_invalid_atomic_rollback(self):
        self.succeeded();before=self.client.snapshot()
        with self.assertRaises(Conflict):self.call('metrics',self.metric(job_id='wrong'),T+86400)
        self.assertEqual(self.client.snapshot(),before)
    def test_improvement_checkpoint_immutable(self):
        self.succeeded();self.call('metrics',self.metric(),T+86400);self.improve();before=self.client.snapshot();self.improve();self.assertEqual(self.client.snapshot(),before)
    def test_next_intent_unique_without_register(self):
        self.succeeded();self.call('metrics',self.metric(),T+86400);self.improve();self.plan();before=self.client.snapshot();self.plan()
        self.assertEqual(before,self.client.snapshot());self.assertEqual(len(self.hub.ledger._records),1)
    def test_full_journal_restart(self):
        self.succeeded();self.call('metrics',self.metric(),T+86400);self.improve();self.plan();before=self.client.snapshot();audit=copy.deepcopy(self.hub.audit);self.restart();self.assertEqual(before,self.client.snapshot());self.assertEqual(audit,self.hub.audit)
    def test_restart_initializing_safe(self):
        self.initializing();self.restart()
        with self.assertRaises(Conflict):self.call('reserve')
    def test_restart_unknown_safe(self):
        self.initializing();self.call('transition','unknown');self.restart();self.assertEqual(self.row()['record'].state,'unknown')
    def test_snapshot_unsafe_operation_rejected(self):
        raw=json.loads(self.client.snapshot());raw['journal'].append({'op':'publish','args':[]})
        with self.assertRaises(ValueError):ReferenceClient.restore(canonical(raw),FLAGS_ON)
    def test_snapshot_duplicate_event_rejected(self):
        raw=json.loads(self.client.snapshot());raw['journal']*=2
        with self.assertRaises(ValueError):ReferenceClient.restore(canonical(raw),FLAGS_ON)
    def test_audit_no_payload_secret_or_provider_body(self):
        self.checkpoint();self.assertTrue(all(set(x)=={'sequence','operation','identity_hash','before_version','version','owner_epoch'} for x in self.hub.audit));self.assertNotIn('narration',canonical(self.hub.audit))
    def test_simulated_process_interleaving_stale_writer(self):
        self.generating();old=self.other.read(self.key);self.call('checkpoint',SCRIPT)
        with self.assertRaises(Conflict):self.other.checkpoint(self.key,'owner-a',old['owner_epoch'],old['record'].version,SCRIPT)
    def test_callback_invalid_completion_rollback(self):
        self.initializing();before=self.client.snapshot()
        with self.assertRaises(ValueError):self.client.complete_delivery(self.body(),-1)
        self.assertEqual(self.client.snapshot(),before);self.assertEqual(len(self.hub.deliveries),0)


class HandoffTests(Setup):
    def test_claimed_handoff_advances_epoch(self):
        self.claim();r=self.call('handoff','owner-b',self.evidence());self.assertEqual(r['owner_epoch'],2);self.assertEqual(r['record'].owner,'owner-b')
    def test_ready_handoff_preserves_job_checkpoint(self):
        self.ready();old=self.row()['record'];r=self.call('handoff','owner-b',self.evidence())['record'];self.assertEqual(r.job_id,old.job_id);self.assertEqual(r.script_fingerprint,old.script_fingerprint)
    def test_generating_saved_checkpoint_handoff(self):self.checkpoint();self.assertEqual(self.call('handoff','owner-b',self.evidence())['owner_epoch'],2)
    def test_generating_no_checkpoint_handoff_denied(self):
        self.generating()
        with self.assertRaises(Conflict):self.call('handoff','owner-b',self.evidence())
    def test_timeout_only_handoff_denied(self):
        self.claim()
        with self.assertRaises(ValueError):self.call('handoff','owner-b',{'elapsed':999999})
    def test_missing_stopped_owner_evidence(self):
        self.claim();e=self.evidence();del e['stop_evidence_id']
        with self.assertRaises(ValueError):self.call('handoff','owner-b',e)
    def test_inflight_not_settled_denied(self):
        self.claim();e=self.evidence();e['no_inflight']=False
        with self.assertRaises(Conflict):self.call('handoff','owner-b',e)
    def test_initializing_handoff_denied(self):
        self.initializing()
        with self.assertRaises(Conflict):self.call('handoff','owner-b',self.evidence())
    def test_unknown_handoff_denied(self):
        self.initializing();self.call('transition','unknown')
        with self.assertRaises(Conflict):self.call('handoff','owner-b',self.evidence())
    def test_old_owner_fenced_after_handoff(self):
        self.claim();old=self.row();self.call('handoff','owner-b',self.evidence())
        with self.assertRaises(Conflict):self.other.transition(self.key,'owner-a',1,old['record'].version,'generating')
    def test_correct_owner_wrong_epoch_denied(self):
        self.claim();v=self.row()['record'].version
        with self.assertRaises(Conflict):self.client.transition(self.key,'owner-a',2,v,'generating')
    def test_handoff_restart_epoch_preserved(self):self.claim();self.call('handoff','owner-b',self.evidence());self.restart();self.assertEqual(self.row()['owner_epoch'],2)
    def test_callback_old_epoch_denied(self):
        self.ready();self.call('handoff','owner-b',self.evidence());self.call('reserve');b=self.body(owner_epoch=1)
        with self.assertRaises(Conflict):accept_fixture(self.client,sign_fixture(b),T,T)


class CallbackTests(Setup):
    def test_current_public_fixture_key(self):self.initializing();b=self.body();self.assertEqual(verify_fixture(sign_fixture(b),T),b)
    def test_previous_key_overlap(self):self.initializing();b=self.body(key_id='fixture-previous');self.assertEqual(verify_fixture(sign_fixture(b),T,T+300),b)
    def test_previous_key_expired(self):
        self.initializing()
        with self.assertRaises(ValueError):verify_fixture(sign_fixture(self.body(key_id='fixture-previous')),T,T-1)
    def test_previous_without_overlap_denied(self):
        self.initializing()
        with self.assertRaises(ValueError):verify_fixture(sign_fixture(self.body(key_id='fixture-previous')),T)
    def test_invalid_signature(self):
        self.initializing();e=sign_fixture(self.body());e['signature']='0'*64
        with self.assertRaises(ValueError):verify_fixture(e,T)
    def test_stale_signature(self):
        self.initializing()
        with self.assertRaises(ValueError):verify_fixture(sign_fixture(self.body()),T+301)
    def test_future_signature(self):
        self.initializing()
        with self.assertRaises(ValueError):verify_fixture(sign_fixture(self.body(issued_at=T+31)),T)
    def test_time_window_boundaries(self):self.initializing();verify_fixture(sign_fixture(self.body()),T+300);verify_fixture(sign_fixture(self.body(issued_at=T+30)),T)
    def test_reordered_json_refused(self):
        self.initializing();e=sign_fixture(self.body());d=json.loads(e['body']);e['body']=json.dumps(d,separators=(',',':'),sort_keys=False,indent=1)
        with self.assertRaises(ValueError):verify_fixture(e,T)
    def test_extra_field_refused(self):
        self.initializing()
        with self.assertRaises(ValueError):sign_fixture(self.body(extra='field'))
    def test_tampered_body(self):
        self.initializing();e=sign_fixture(self.body());d=json.loads(e['body']);d['outcome']='failed';e['body']=canonical(d)
        with self.assertRaises(ValueError):verify_fixture(e,T)
    def test_duplicate_key_refused(self):
        self.initializing();e=sign_fixture(self.body());e['body']=e['body'][:-1]+',"version":1}'
        with self.assertRaises(ValueError):verify_fixture(e,T)
    def test_account_binding(self):
        self.initializing()
        with self.assertRaises(ValueError):sign_fixture(self.body(account_id='youtube-other'))
    def test_job_binding(self):
        self.initializing()
        with self.assertRaises(Conflict):accept_fixture(self.client,sign_fixture(self.body(job_id='yt-other')),T,T)
    def test_owner_binding(self):
        self.initializing()
        with self.assertRaises(Conflict):accept_fixture(self.client,sign_fixture(self.body(owner='owner-b')),T,T)
    def test_version_binding(self):
        self.initializing()
        with self.assertRaises(Conflict):accept_fixture(self.client,sign_fixture(self.body(version=1)),T,T)
    def test_invalid_signature_never_mutates(self):
        self.initializing();before=self.client.snapshot();e=sign_fixture(self.body());e['signature']='1'*64
        with self.assertRaises(ValueError):accept_fixture(self.client,e,T,T)
        self.assertEqual(self.client.snapshot(),before)
    def test_duplicate_delivery_no_op(self):
        self.initializing();e=sign_fixture(self.body());accept_fixture(self.client,e,T,T);before=self.client.snapshot();accept_fixture(self.other,e,T+1,T);self.assertEqual(self.client.snapshot(),before)
    def test_replay_rotation_changed_key_denied(self):
        self.initializing();b=self.body();accept_fixture(self.client,sign_fixture(b),T,T)
        with self.assertRaises(Conflict):accept_fixture(self.client,sign_fixture({**b,'key_id':'fixture-previous'}),T,T,T+300)
    def test_restart_replay_protected(self):
        self.initializing();e=sign_fixture(self.body());accept_fixture(self.client,e,T,T);self.restart();before=self.client.snapshot();accept_fixture(self.client,e,T,T);self.assertEqual(self.client.snapshot(),before)
    def test_concurrent_callback_one_terminal_event(self):
        self.initializing();e=sign_fixture(self.body());b=Barrier(6)
        def run(i):b.wait();return accept_fixture(self.hub.client(),e,T,T)['record'].result_id
        with ThreadPoolExecutor(max_workers=6) as p:out=list(p.map(run,range(6)))
        self.assertEqual(len(set(out)),1);self.assertEqual(sum(x['operation']=='complete_delivery' for x in self.hub.audit),1)
    def test_path_traversal_delivery(self):
        self.initializing()
        with self.assertRaises(ValueError):sign_fixture(self.body(delivery_id='../escape'))
    def test_real_key_mode_denied(self):
        self.initializing();e=sign_fixture(self.body());e['mode']='production'
        with self.assertRaises(ValueError):verify_fixture(e,T)


class MonitorGateTests(Setup):
    def proofs(self):return {n:{'mode':'OFFLINE_TEST','evidence_id':'test-'+n.replace('_','-'),'passed':True} for n in OFFLINE_GATES}
    def test_all_offline_still_live_blocked(self):
        g=evaluate_gate(self.proofs(),FLAGS_ON);self.assertTrue(g['offline_complete']);self.assertFalse(g['live_ready']);self.assertFalse(g['posting_permitted'])
    def test_missing_evidence_not_pass(self):self.assertFalse(evaluate_gate({},FLAGS_ON)['offline_complete'])
    def test_failed_test_blocks_gate(self):p=self.proofs();p['recovery']['passed']=False;self.assertEqual(evaluate_gate(p,FLAGS_ON)['gates']['recovery']['status'],'BLOCKED')
    def test_cannot_inject_live_proof(self):
        with self.assertRaises(ValueError):evaluate_gate({**self.proofs(),'ai_quota':{'passed':True}},FLAGS_ON)
    def test_reference_fencing_design_only(self):self.assertEqual(evaluate_gate(self.proofs(),FLAGS_ON)['gates']['fencing']['status'],'DESIGN PASS')
    def test_unsafe_flags_denied(self):
        for k in FLAGS:
            with self.subTest(k=k),self.assertRaises(ValueError):evaluate_gate(self.proofs(),{**FLAGS_ON,k:False})
    def test_workflow_success_not_health(self):self.assertEqual(command_view(self.row(),T,workflow_conclusion='success')['health'],'UNVERIFIED')
    def test_unknown_monitor_manual(self):self.initializing();self.call('transition','unknown');v=command_view(self.row(),T);self.assertTrue(v['manual_reconciliation_required']);self.assertFalse(v['live_permitted'])
    def test_initializing_monitor_manual(self):self.initializing();self.assertTrue(command_view(self.row(),T)['manual_reconciliation_required'])
    def test_failed_monitor_not_done(self):self.claim();self.call('transition','failed');v=command_view(self.row(),T);self.assertTrue(v['failed']);self.assertEqual(v['health'],'failed')
    def test_checkpoint_monitor_priority(self):self.checkpoint();self.assertEqual(command_view(self.row(),T)['last_durable_checkpoint'],'script_checkpoint')
    def test_deadline_only_inspect(self):self.claim();v=command_view(self.row(),T+10,expectation={'event':'generation_fixture','expected_at':T,'deadline':T+1});self.assertEqual(v['next_safe_action'],'inspect_only')
    def test_metric_slots_command_independent(self):self.succeeded();v=self.call('metrics',self.metric('1h'),T+3600);m=command_view(self.row(),T+3600,loop=v['loop']);self.assertEqual(m['metrics']['1h']['state'],'collected');self.assertEqual(m['metrics']['24h']['state'],'pending')
    def test_monitor_identity_mismatch(self):
        self.succeeded();v=self.call('metrics',self.metric(),T+86400);v['loop']['origin']['job_id']='wrong'
        with self.assertRaises(ValueError):command_view(self.row(),T+86400,loop=v['loop'])
    def test_monitor_clock_mismatch(self):
        self.succeeded();v=self.call('metrics',self.metric(),T+86400)
        with self.assertRaises(ValueError):command_view(self.row(),T+86401,loop=v['loop'])
    def test_artifact_allowance_missing(self):self.assertEqual(media_budget(50*2**20,1000,1000)['capacity_status'],'UNVERIFIED')
    def test_artifact_bounded_capacity_formula(self):b=media_budget(50*2**20,1000,1000,allowance_bytes=500*2**20);self.assertEqual(b['capacity_status'],'WITHIN_ASSUMPTIONS');self.assertEqual(b['actual_billing_status'],'UNVERIFIED')
    def test_artifact_overage_blocked(self):self.assertEqual(media_budget(600*2**20,1000,1000,allowance_bytes=500*2**20)['capacity_status'],'BLOCKED')
    def test_artifact_not_claim_store(self):self.assertFalse(media_budget(1,1,1)['claim_backend_permitted'])
    def test_artifact_invalid_size(self):
        with self.assertRaises(ValueError):media_budget(-1,1,1)


class FinalE2ETests(Setup):
    def test_generation_to_monitor_next_candidate_recovery(self):
        request_fixture(ENTRY,JOB,FLAGS_ON,METRICS['improvement']);script=parse_provider_fixture(provider(),ENTRY['theme'],JOB,FLAGS_ON)
        self.generating();self.call('checkpoint',script);self.restart();self.call('make_ready');self.call('reserve')
        e=sign_fixture(self.body());accept_fixture(self.client,e,T,T);self.call('metrics',self.metric('1h'),T+3600);self.call('metrics',self.metric(),T+86400);self.improve();planned=self.plan();self.restart()
        self.assertEqual(self.plan()['loop']['next_intent'],planned['loop']['next_intent']);self.assertEqual(len(self.hub.ledger._records),1);self.assertFalse(planned['loop']['dispatch_permitted'])
    def test_handoff_then_generation_checkpoint_and_callback(self):
        self.claim();self.call('handoff','owner-b',self.evidence());self.call('transition','generating');self.call('checkpoint',SCRIPT);self.call('make_ready');self.call('reserve');v=accept_fixture(self.client,sign_fixture(self.body()),T,T);self.assertEqual(v['owner_epoch'],2);self.assertEqual(v['record'].state,'succeeded')
    def test_full_pipeline_inputs_equal_existing_fixture(self):
        self.ready();r=self.row()['record'];from parity import pipeline_inputs
        self.assertEqual(checkpoint_inputs(r)['pipeline_inputs'],FIX['pipeline_inputs_expected'])
    def test_malformed_response_no_checkpoint_mutation(self):
        self.generating();before=self.client.snapshot()
        with self.assertRaises(ValueError):parse_provider_fixture('{broken',ENTRY['theme'],JOB,FLAGS_ON)
        self.assertEqual(before,self.client.snapshot())
    def test_24h_first_insufficient_sample_kept(self):
        self.succeeded();f=self.metric();f['metrics']['views']=2;self.call('metrics',f,T+86400);v=self.improve();self.assertEqual(v['loop']['improvement']['sample_status'],'insufficient_sample');self.assertIsNone(v['loop']['improvement']['evidence']['views_1h'])


class CIGateTests(unittest.TestCase):
    def result(self,n,failed=False,skip=False):
        r=unittest.TestResult();r.testsRun=n
        if failed:r.errors=[(None,'failure fixture')]
        if skip:r.skipped=[(None,'skipped fixture')]
        return r
    def test_ci_gate_complete_still_not_live(self):
        ids=list(CI_GATE_TESTS.values());g=evaluate_ci_gate(self.result(len(ids)),ids,FLAGS_ON);self.assertTrue(g['offline_complete']);self.assertFalse(g['live_ready'])
    def test_ci_failure_blocks(self):
        ids=list(CI_GATE_TESTS.values());self.assertFalse(evaluate_ci_gate(self.result(len(ids),failed=True),ids,FLAGS_ON)['offline_complete'])
    def test_ci_missing_required_test_blocks(self):
        ids=list(CI_GATE_TESTS.values())[1:];self.assertFalse(evaluate_ci_gate(self.result(len(ids)),ids,FLAGS_ON)['offline_complete'])
    def test_ci_skipped_blocks(self):
        ids=list(CI_GATE_TESTS.values());self.assertFalse(evaluate_ci_gate(self.result(len(ids),skip=True),ids,FLAGS_ON)['offline_complete'])
    def test_ci_mismatched_count_blocks(self):
        ids=list(CI_GATE_TESTS.values());self.assertFalse(evaluate_ci_gate(self.result(1),ids,FLAGS_ON)['offline_complete'])
    def test_restart_pipeline_bytes_unchanged(self):
        c=ReferenceAuthority(FLAGS_ON).client();c.register(ENTRY,lambda:JOB);key=('youtube','youtube_game_001','final-fixture');c.claim(key,'owner-a',1);v=c.read(key)['record'].version;c.transition(key,'owner-a',1,v,'generating');v=c.read(key)['record'].version;c.checkpoint(key,'owner-a',1,v,SCRIPT);c=ReferenceClient.restore(c.snapshot(),FLAGS_ON)
        self.assertEqual(checkpoint_inputs(c.read(key)['record'])['pipeline_inputs'],FIX['pipeline_inputs_expected'])


class ExtraBoundaryTests(unittest.TestCase):
    def test_unicode_noncharacters_denied(self):
        for v in ('\ufdd0','\ufffe','\U0001ffff'):
            with self.subTest(v=repr(v)),self.assertRaises(ValueError):strict_json(json.dumps(v))
    def test_quota_unknown_cannot_pass(self):self.assertEqual(quota_plan()['status'],'UNVERIFIED')
    def test_quota_low_rpd_blocks(self):self.assertEqual(quota_plan({'rpm':1,'rpd':5,'tpm':10000},100)['status'],'BLOCKED')
    def test_quota_fixture_not_entitlement(self):self.assertFalse(quota_plan({'rpm':1,'rpd':6,'tpm':10000},100)['live_permitted'])
    def test_quota_uses_output_headroom(self):self.assertEqual(quota_plan({'rpm':1,'rpd':6,'tpm':4195},100)['status'],'BLOCKED')
    def test_audit_view_detached(self):
        c=ReferenceAuthority(FLAGS_ON).client();c.register(ENTRY,lambda:JOB);v=c.audit_trail();v[0]['version']=999;self.assertEqual(c.audit_trail()[0]['version'],1)

class SourceAndMonitorTests(Setup):
    def test_final_source_export_hash_matches_parity(self):
        s=json.loads((HERE/'final_sources.json').read_text());p=json.loads((HERE/'parity_sources.json').read_text());self.assertEqual(s['n8n_export_sha256'],p['export_sha256'])
    def test_final_source_pipeline_hash_matches_parity(self):
        s=json.loads((HERE/'final_sources.json').read_text());p=json.loads((HERE/'parity_sources.json').read_text());w=next(x for x in s['workflows'] if x['path'].endswith('/youtube-pipeline.yml'));self.assertEqual(w['sha256'],p['pipeline_sha256'])
    def test_final_protected_pr_heads_match(self):
        s=json.loads((HERE/'final_sources.json').read_text());p=json.loads((HERE/'parity_sources.json').read_text())
        for n in ('15','16'):
            self.assertEqual(s['protected_prs'][n]['head'],p['pr'+n+'_sha']);self.assertTrue(s['protected_prs'][n]['draft']);self.assertFalse(s['protected_prs'][n]['merged'])
    def test_collected_slots_not_falsely_pending_overdue(self):
        self.succeeded();self.call('metrics',self.metric('1h'),T+3600);self.call('metrics',self.metric(),T+86400)
        r=self.row()['record'];loop=self.hub.loop.tick((r.intent.platform,r.intent.account_id,r.job_id),T+200000)
        v=command_view(self.row(),T+200000,loop=loop);self.assertEqual(v['health'],'observed');self.assertFalse(v['deadline_exceeded']);self.assertEqual(v['metrics']['24h']['observation_status'],'collected')
    def test_final_runbook_has_all_stage_stop_columns(self):
        text=(HERE/'LIVE_MIGRATION_RUNBOOK_JA.md').read_text();self.assertIn('STOP条件',text);self.assertIn('EMERGENCY_STOP=false',text)
        for stage in range(17):self.assertIn('| '+str(stage)+' |',text)
