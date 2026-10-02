"""Evidence-scoped live gate overlay. Remote behavioral PASS is never inferred."""
import copy
from final_readiness import OFFLINE_GATES, DESIGN_ONLY
REMOTE_BEHAVIOR=('uniqueness','cas','version_monotonicity','immutable_fingerprint','concurrent_claim','stale_owner_rejection','fencing','checkpoint_durability','restart_recovery','duplicate_callback','replay','ambiguous_side_effect','unknown_no_automatic_resend')

def evaluate_post_migration(evidence,flags):
    if not isinstance(flags,dict) or set(flags)!=set(('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')) or any(v is not True for v in flags.values()):raise ValueError('unsafe_flags')
    d=evidence.get('d1',{})
    observed=evidence.get('receipt',{})
    if observed.get('run_id')!=37063527954 or observed.get('sql_sha256')!='ac01f6d9d7eac877b802688d4f1d3c4dd40e8940876ed3ce0dc441c10297d0e2':raise ValueError('receipt_mismatch')
    schema_pass=(evidence.get('d1_pass') is True and evidence.get('preexisting_schema_unchanged') is True and evidence.get('test_jobs_table_count')==1 and d.get('schema')=='PASS_EMPTY' and d.get('row_count')==0 and d.get('inventory')=='COMPLETE' and d.get('d1_count')==1 and d.get('other_d1_count')==0 and d.get('database')=='ID_AND_NAME_MATCHED' and d.get('time_travel')=='BOOKMARK_READ_CONFIRMED')
    gates={}
    # Offline accomplishments are identified as assertions backed by guarded CI,
    # never used as a remote execution proof.
    for k in OFFLINE_GATES:gates[k]={'status':'DESIGN PASS' if k in DESIGN_ONLY else 'OFFLINE PASS','scope':'guarded_reference_only'}
    gates['remote_d1_schema']={'status':'PASS' if schema_pass else 'BLOCKED','scope':'read_only_schema_and_empty_rows'}
    gates['remote_atomicity']={'status':'UNVERIFIED','scope':'remote_write_test_not_authorized'}
    gates['storage']={'status':'DESIGN PASS','scope':'artifact_plan_only_actual_GitHub_usage_unverified'}
    gates['ai_quota']={'status':'UNVERIFIED','scope':'actual_project_model_quota'}
    gates['cloudflare']={'status':'BLOCKED','scope':'D1_read_PASS_Free_owner_PASS_worker_unverified'}
    w=evidence.get('worker',{})
    confirmed=w.get('status')=='EXISTS' and w.get('account_wide_visibility_verified') is True
    gates['worker']={'status':'PASS' if confirmed else 'UNVERIFIED','scope':'existence_only_deploy_separately_blocked'}
    gates['worker_deploy']={'status':'BLOCKED','scope':'owner_existence_and_editor_and_deploy_approval_required'}
    gates['secrets']={'status':'BLOCKED','scope':'migration_Write_absent_test_only_secrets_not_registered'}
    gates['render']={'status':'UNVERIFIED','scope':'real_render_never_executed'}
    gates['publish']={'status':'BLOCKED','scope':'owner_authorization_OAuth_safety_gates_required'}
    backend={k:{'reference':'DESIGN PASS','remote':'UNVERIFIED'} for k in REMOTE_BEHAVIOR}
    return {'gates':gates,'backend':backend,'remote_schema_pass':schema_pass,'offline_complete':True,'live_ready':False,'posting_permitted':False,'auto_dispatch':False,'claim_permitted':False,'safety':copy.deepcopy(flags),'scope':'one_account_sandbox','multi_account':'BLOCKED_SEPARATE'}

if __name__=='__main__':
    import json,os
    from pathlib import Path
    evidence=json.loads((Path(__file__).parent/'POST_MIGRATION_READ_ONLY_EVIDENCE_2026_10_03.json').read_text())
    flags={k:os.environ.get(k)=='true' for k in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')}
    result=evaluate_post_migration(evidence,flags)
    result['evidence_run_id']=evidence['audit_run_id']
    result['evidence_checked_at']=evidence['d1']['checked_at']
    result['evidence_kind']='SANITIZED_READ_ONLY_SNAPSHOT_PLUS_GUARDED_REFERENCE'
    print('POST_MIGRATION_READINESS_GATE '+json.dumps(result,sort_keys=True))
