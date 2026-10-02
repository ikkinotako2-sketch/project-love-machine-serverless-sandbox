"""Read-only final command view and fail-closed offline readiness evaluator."""
import copy
from offline_readiness import FLAGS, _identifier
from generation_contract import canonical
from intent_ledger import Record

OFFLINE_GATES=('offline_parity','generation_contract','durable_store_contract','duplicate_prevention','recovery','fencing','callback_auth_boundary','pipeline_contract','metrics_loop','improvement_loop','next_intent_uniqueness')
LIVE_GATES=('artifact_storage','ai_quota','backend_readiness','cloudflare_readiness','secrets_readiness','render_readiness','publish_readiness')
DESIGN_ONLY={'durable_store_contract','fencing','callback_auth_boundary'}


def evaluate_gate(evidence,flags):
    if not isinstance(flags,dict) or set(flags)!=set(FLAGS) or any(flags[k] is not True for k in FLAGS):raise ValueError('unsafe_flags')
    if not isinstance(evidence,dict) or set(evidence)-set(OFFLINE_GATES):raise ValueError('offline_evidence_only')
    rows={}
    for name in OFFLINE_GATES:
        item=evidence.get(name)
        if item is None:rows[name]={'status':'UNVERIFIED','evidence_id':None};continue
        if not isinstance(item,dict) or set(item)!={'mode','evidence_id','passed'} or item['mode']!='OFFLINE_TEST' or type(item['passed']) is not bool:raise ValueError('invalid_gate_evidence')
        _identifier(item['evidence_id'])
        rows[name]={'status':('DESIGN PASS' if name in DESIGN_ONLY else 'OFFLINE PASS') if item['passed'] else 'BLOCKED','evidence_id':item['evidence_id']}
    for name in LIVE_GATES:
        rows[name]={'status':'BLOCKED' if name in ('cloudflare_readiness','secrets_readiness','publish_readiness') else 'UNVERIFIED','evidence_id':None}
    return {'gates':rows,'offline_complete':all(rows[n]['status'] in ('OFFLINE PASS','DESIGN PASS') for n in OFFLINE_GATES),
            'live_ready':False,'posting_permitted':False,'claim_permitted':False,'auto_dispatch':False,
            'safety':copy.deepcopy(flags),'scope':'one_account_offline_reference'}


def command_view(read,now,loop=None,expectation=None,workflow_conclusion=None):
    if not isinstance(read,dict) or not isinstance(read.get('record'),Record):raise ValueError('record_required')
    if type(now) is not int or now<0:raise ValueError('virtual_time_required')
    r=read['record'];epoch=read.get('owner_epoch')
    if type(epoch) is not int or epoch<0:raise ValueError('epoch_required')
    for v in (r.job_id,r.intent.intent_id,r.intent.account_id):_identifier(v)
    slots={}
    if loop is not None:
        origin=loop.get('origin',{})
        if origin.get('job_id')!=r.job_id or origin.get('account_id')!=r.intent.account_id or origin.get('platform')!=r.intent.platform or origin.get('result_id')!=r.result_id:raise ValueError('monitor_identity_mismatch')
        if loop.get('now')!=now:raise ValueError('monitor_clock_mismatch')
        for slot in ('1h','24h'):
            s=loop['slots'][slot]
            slots[slot]={k:s[k] for k in ('state','observation_status','due','due_at','deadline_at','deadline_exceeded')}
    reconciliation=r.state in ('initializing','unknown') or any(s['observation_status']=='unknown' for s in slots.values())
    failed=r.state=='failed'
    checkpoint='terminal_result' if r.result_id else 'initialization_reservation' if r.dispatch_reservations else 'renderer_payload' if r.content_fingerprint else 'script_checkpoint' if r.script_fingerprint else 'claim' if r.owner else 'intent'
    next_event={'pending':'claim_review','claimed':'generation_fixture','generating':'checkpoint_recovery' if r.script_checkpoint_json else 'generation_reconciliation','ready':'dispatch_review','initializing':'side_effect_reconciliation','unknown':'manual_reconciliation','succeeded':'metrics_evidence','failed':'failure_review'}[r.state]
    deadline=None;expected=None
    # Derive the next event from observation/checkpoint evidence, not merely
    # the successful upload workflow. Explicit missed evidence remains missed.
    if slots and r.state=='succeeded':
        unresolved=[name for name in ('1h','24h') if slots[name]['observation_status']=='pending']
        if reconciliation:next_event='manual_reconciliation'
        elif unresolved:
            name=unresolved[0];next_event='metrics_'+name+'_evidence'
            expected=slots[name]['due_at'];deadline=slots[name]['deadline_at']
        elif loop.get('next_intent') is not None:next_event='next_intent_review'
        elif loop.get('improvement') is not None:next_event='next_intent_fixture'
        elif slots['24h']['observation_status']=='collected':next_event='improvement_fixture'
        else:next_event='metrics_missed_review'
        if loop.get('next_intent') is not None:checkpoint='next_intent_checkpoint'
        elif loop.get('improvement') is not None:checkpoint='improvement_checkpoint'
        elif any(s['observation_status']=='collected' for s in slots.values()):checkpoint='metrics_checkpoint'
    if expectation is not None:
        if not isinstance(expectation,dict) or set(expectation)!={'event','expected_at','deadline'} or expectation['event']!=next_event:raise ValueError('invalid_expectation')
        if any(type(expectation[k]) is not int or expectation[k]<0 for k in ('expected_at','deadline')) or expectation['deadline']<expectation['expected_at']:raise ValueError('invalid_deadline')
        expected=expectation['expected_at'];deadline=expectation['deadline']
    exceeded=(deadline is not None and now>deadline) or any(s['deadline_exceeded'] and s['observation_status'] in ('pending','unknown') for s in slots.values())
    healthy='UNVERIFIED' if not slots else 'observed' if all(s['observation_status']=='collected' for s in slots.values()) else 'incomplete'
    if failed:healthy='failed'
    elif reconciliation:healthy='reconciliation_required'
    elif exceeded:healthy='deadline_exceeded'
    elif any(s['observation_status']=='missed' for s in slots.values()):healthy='missed'
    return {'platform':r.intent.platform,'account_id':r.intent.account_id,'job_id':r.job_id,
        'current_stage':loop['phase'] if loop is not None and r.state=='succeeded' else r.state,
        'last_durable_checkpoint':checkpoint,'checkpoint_durability':'REFERENCE_ONLY_UNVERIFIED',
        'owner_epoch':epoch,'version':r.version,'next_expected_event':next_event,'expected_time':expected,
        'deadline':deadline,'deadline_exceeded':exceeded,'metrics':slots,'failed':failed,
        'manual_reconciliation_required':reconciliation,'health':healthy,
        'workflow_conclusion':workflow_conclusion if workflow_conclusion in ('success','failure','cancelled',None) else 'UNVERIFIED',
        'next_safe_action':'manual_reconciliation' if reconciliation else 'inspect_only' if failed or exceeded or healthy=='missed' else 'offline_fixture_only',
        'unsafe_automatic_action':['initialize','resend','timeout_takeover','generate_after_checkpoint','claim_next_intent','publish'],
        'live_permitted':False}


def media_budget(video_bytes,metadata_bytes,result_bytes,posts_per_day=1,existing_bytes=0,allowance_bytes=None,accrued_gib_hours=None,claim_bytes=128):
    """Current production retention: media1d; adapter7d; pipeline30d.

    Estimate counts FOUR bundled artifacts per successful job, not just mp4.
    Measured compressed artifact sizes/owner accrual remain required.
    """
    values=(video_bytes,metadata_bytes,result_bytes,posts_per_day,existing_bytes,claim_bytes)
    if any(type(x) is not int or x<0 for x in values) or video_bytes<1 or posts_per_day<1:raise ValueError('invalid_media_budget')
    if allowance_bytes is not None and (type(allowance_bytes) is not int or allowance_bytes<1):raise ValueError('invalid_allowance')
    if accrued_gib_hours is not None and (type(accrued_gib_hours) not in (int,float) or accrued_gib_hours<0):raise ValueError('invalid_accrual')
    required=existing_bytes+posts_per_day*(video_bytes+metadata_bytes+result_bytes*(7+30)+claim_bytes*30)
    return {'steady_state_bytes':required,'steady_state_gib_hours_per_30d':required/(2**30)*720,
        'capacity_status':'UNVERIFIED' if allowance_bytes is None else 'WITHIN_ASSUMPTIONS' if required<=allowance_bytes else 'BLOCKED',
        'actual_billing_status':'UNVERIFIED','current_accrual_supplied':accrued_gib_hours is not None,
        'claim_backend_permitted':False,'posting_permitted':False}

CI_GATE_TESTS={
 'offline_parity':'test_checkpoint_e2e.CheckpointE2ETests.test_conversion_matches_independent_n8n_oracle',
 'generation_contract':'test_final_boundaries.GenerationTests.test_provider_fixture_metadata_discarded',
 'durable_store_contract':'test_final_boundaries.DurableTests.test_full_journal_restart',
 'duplicate_prevention':'test_final_boundaries.DurableTests.test_concurrent_independent_handles_one_owner',
 'recovery':'test_final_boundaries.DurableTests.test_restart_unknown_safe',
 'fencing':'test_final_boundaries.HandoffTests.test_old_owner_fenced_after_handoff',
 'callback_auth_boundary':'test_final_boundaries.CallbackTests.test_invalid_signature_never_mutates',
 'pipeline_contract':'test_final_boundaries.FinalE2ETests.test_full_pipeline_inputs_equal_existing_fixture',
 'metrics_loop':'test_offline_metrics_loop.OfflineLoopTests.test_full_offline_loop',
 'improvement_loop':'test_offline_metrics_loop.OfflineLoopTests.test_improvement_validator_independent_source_contract',
 'next_intent_uniqueness':'test_final_boundaries.DurableTests.test_next_intent_unique_without_register'}


def evaluate_ci_gate(result,test_ids,flags):
    """CI-internal test evidence. Not authenticated external approval input."""
    all_ok=(result.wasSuccessful() and result.testsRun==len(test_ids) and not result.skipped and not result.expectedFailures)
    proofs={name:{'mode':'OFFLINE_TEST','evidence_id':'ci-'+name.replace('_','-'),
                  'passed':all_ok and test_id in test_ids} for name,test_id in CI_GATE_TESTS.items()}
    return {**evaluate_gate(proofs,flags),'python_tests_run':result.testsRun,'evidence_kind':'GUARDED_CI_TESTS_ONLY'}
