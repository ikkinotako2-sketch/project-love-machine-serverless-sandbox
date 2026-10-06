from oracle_bridge import require_guard
require_guard()
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import unittest
import youtube_remote_readiness as y

ROOT = Path(__file__).resolve().parents[1]
PLAN = json.loads((ROOT/'readiness/youtube-live-connection-plan.json').read_text())
CATALOG = json.loads((ROOT/'readiness/youtube-readonly-schema-catalog.json').read_text())
OLD = json.loads((ROOT/'audit-evidence/generalized-behavior-v3-schema-read-only-37170582256.json').read_text())['result']['post']['audit']['schema']
ENV = dict.fromkeys(y.FLAGS, 'true') | {'GITHUB_REPOSITORY': y.REPO, 'GITHUB_REF': 'refs/heads/'+y.BRANCH,
    'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_EVENT_NAME': 'push', 'PLM_READ_BEFORE': y.PARENT,
    'PLM_READ_MESSAGE': y.MESSAGE, 'PLM_CF_D1_READ_TOKEN': 'PUBLIC_FIXTURE_NOT_A_SECRET'}


class Transport:
    def __init__(self, schema=None, fault=None):
        self.calls=[]; self.schema=copy.deepcopy(OLD if schema is None else schema); self.fault=fault
    def __call__(self, url, method, body, token):
        self.calls.append((url,method,body))
        if self.fault=='timeout': raise TimeoutError('SECRET_LIKE_PAYLOAD_MUST_NOT_LEAK')
        if self.fault=='http': return 403,b'SECRET_LIKE_PAYLOAD_MUST_NOT_LEAK'
        if self.fault=='oversize': return 200,b'x'*(y.MAX_BYTES+1)
        if self.fault=='bad_json': return 200,b'SECRET_LIKE_PAYLOAD_MUST_NOT_LEAK'
        if url==y.VERIFY: result={'status':'expired' if self.fault=='expired' else 'active'}
        elif url==y.TARGET: result={'uuid':y.DB,'name':y.NAME,'file_size':196608}
        else:
            assert method=='POST' and json.loads(body)=={'sql':y.SQL,'params':[]}
            result=[{'success':True,'meta':{'changed_db':False,'rows_written':0,'served_by_primary':True,'rows_read':29},'results':self.schema}]
            if self.fault=='write':result[0]['meta']['rows_written']=1
            if self.fault=='replica':result[0]['meta']['served_by_primary']=False
            if self.fault=='missing_meta':result[0]['meta']={}
        return 200,json.dumps({'success':True,'result':result}).encode()


def candidates():
    db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
    for path in ('0008_provider_neutral_roundtrip_backend.sql','0009_youtube_queue_result_proposal.sql'):
        db.executescript((ROOT/'serverless/migrations'/path).read_text())
    return [dict(x) for x in db.execute(y.SQL)]


class ReadinessTests(unittest.TestCase):
    def run_audit(self, fault=None, schema=None, env=None):
        t=Transport(schema,fault);r=y.audit(ENV if env is None else env,t,PLAN,CATALOG)
        self.assertEqual(r['d1_write'],0);self.assertEqual(r['deploy'],0);self.assertEqual(r['dispatch'],0)
        self.assertEqual(r['youtube_upload'],0);self.assertFalse(r['live_ready']);self.assertFalse(r['execution_approved'])
        self.assertLessEqual(len(t.calls),3);return r,t
    def test_source_pins(self):self.assertTrue(y.pins_valid(PLAN))
    def test_historical_not_current(self):self.assertEqual(PLAN['current_remote_schema'],'UNVERIFIED')
    def test_absent_extensions(self):
        r,t=self.run_audit();self.assertEqual(r['readiness'],'READ_ONLY_CONFIRMED');self.assertEqual(r['provider_neutral'],'NOT_APPLIED');self.assertEqual(r['queue_result'],'NOT_APPLIED');self.assertEqual(len(t.calls),3)
    def test_full_extensions(self):
        r,_=self.run_audit(schema=OLD+candidates());self.assertEqual(r['provider_neutral'],'FULL_APPLIED');self.assertEqual(r['queue_result'],'FULL_APPLIED');self.assertFalse(r['live_ready'])
    def test_partial_extension(self):
        r,_=self.run_audit(schema=OLD+candidates()[:1]);self.assertEqual(r['provider_neutral'],'PARTIAL_OR_DRIFT');self.assertEqual(r['failure_code'],'CURRENT_SCHEMA_DRIFT_STOP')
    def test_protected_missing(self):
        r,_=self.run_audit(schema=OLD[1:]);self.assertFalse(r['protected_schema_exact'])
    def test_protected_drift(self):
        rows=copy.deepcopy(OLD);rows[0]['sql']+=' ';r,_=self.run_audit(schema=rows);self.assertFalse(r['protected_schema_exact'])
    def test_unknown_name_not_emitted(self):
        rows=OLD+[{'type':'table','name':'SECRET_LIKE_PAYLOAD','tbl_name':'PRIVATE_PATH','sql':'SECRET_LIKE_PAYLOAD'}];r,_=self.run_audit(schema=rows);self.assertEqual(r['unknown_objects_count'],1);self.assertNotIn('SECRET_LIKE_PAYLOAD',json.dumps(r));self.assertNotIn('PRIVATE_PATH',json.dumps(r))
    def test_duplicate_schema_rejected(self):
        r,_=self.run_audit(schema=OLD+OLD[:1]);self.assertEqual(r['readiness'],'UNVERIFIED')
    def test_schema_bounds(self):
        r,_=self.run_audit(schema=OLD*5);self.assertEqual(r['readiness'],'UNVERIFIED')
    def test_wrong_shape(self):
        r,_=self.run_audit(schema=[{'sql':'secret'}]);self.assertEqual(r['readiness'],'UNVERIFIED')
    def test_no_retry_timeout(self):
        r,t=self.run_audit('timeout');self.assertEqual(len(t.calls),1);self.assertNotIn('SECRET_LIKE_PAYLOAD',json.dumps(r));self.assertNotIn(hashlib.sha256(b'SECRET_LIKE_PAYLOAD_MUST_NOT_LEAK').hexdigest(),json.dumps(r))
    def test_http_error_redacted(self):
        r,t=self.run_audit('http');self.assertEqual(len(t.calls),1);self.assertNotIn('SECRET_LIKE_PAYLOAD',json.dumps(r))
    def test_invalid_json_redacted(self):
        r,_=self.run_audit('bad_json');self.assertEqual(r['readiness'],'UNVERIFIED')
    def test_oversize(self):
        r,_=self.run_audit('oversize');self.assertEqual(r['readiness'],'UNVERIFIED')
    def test_expired_token_stops(self):
        r,t=self.run_audit('expired');self.assertEqual(len(t.calls),1);self.assertEqual(r['readiness'],'UNVERIFIED')
    def test_query_write_meta_rejected(self):self.assertEqual(self.run_audit('write')[0]['readiness'],'UNVERIFIED')
    def test_replica_unverified(self):self.assertEqual(self.run_audit('replica')[0]['readiness'],'UNVERIFIED')
    def test_missing_meta_unverified(self):self.assertEqual(self.run_audit('missing_meta')[0]['readiness'],'UNVERIFIED')
    def test_context_rejections_before_network(self):
        for k in ('GITHUB_RUN_ATTEMPT','GITHUB_REPOSITORY','GITHUB_REF','PLM_READ_BEFORE','PLM_READ_MESSAGE',*y.FLAGS):
            with self.subTest(key=k):
                r,t=self.run_audit(env=ENV|{k:'wrong'});self.assertEqual(t.calls,[])
    def test_missing_secret_not_absence_claim(self):
        env=ENV.copy();env.pop('PLM_CF_D1_READ_TOKEN');r,t=self.run_audit(env=env);self.assertEqual(t.calls,[]);self.assertEqual(r['oauth_current'],'UNVERIFIED')
    def test_other_secret_never_used(self):
        r,t=self.run_audit(env=ENV|{'OAUTH_VALUE':'SECRET_LIKE_PAYLOAD','PLM_CF_WRITE_TOKEN':'SECRET_LIKE_PAYLOAD'});self.assertNotIn('SECRET_LIKE_PAYLOAD',json.dumps(r));self.assertEqual(len(t.calls),3)
    def test_fixed_select_no_rows(self):self.assertNotIn('SELECT *',y.SQL);self.assertEqual(PLAN['read_only']['maximum_requests'],3)
    def test_current_usage_not_inferred_from_size(self):
        r,_=self.run_audit();self.assertEqual(r['account_usage'],'UNVERIFIED');self.assertEqual(r['account_free_plan'],'UNVERIFIED')
    def test_historical_production_e2e_separate(self):self.assertEqual(PLAN['progress'],{'existing_youtube_percent':98,'hardened_live_e2e':'0/1'})
    def test_no_deploy_authorization(self):self.assertFalse(PLAN['execution_approved']);self.assertFalse(PLAN['one_shot_deployment']['launchable'])
    def test_live_worker_is_not_existing_test_worker(self):self.assertFalse(PLAN['worker']['youtube_live_implementation_ready'])
    def test_callback_no_fixture_key_live(self):self.assertEqual(PLAN['callback']['fixture_keys_live_allowed'],False)
    def test_callback_bound_fields(self):
        self.assertTrue({'owner_epoch','fencing_token','dispatch_id','run_id','media_sha256','privacy_status','notify_subscribers','processing_status'}<=set(PLAN['callback']['signed_fields']))
    def test_trigger_stop(self):self.assertEqual(PLAN['trigger']['enabled'],False);self.assertEqual(PLAN['trigger']['unknown_policy'],'STOP_NO_RETRY_NO_NEXT_JOB')
    def test_004h_consumed_independent(self):self.assertEqual(PLAN['runtime']['004h'],'PERMANENTLY_CONSUMED');self.assertEqual(PLAN['runtime']['same_conditions_retry'],0)
    def test_render_marker_absent(self):
        self.assertFalse((ROOT/'audit-evidence/consumed/manual-fixture-runtime-preflight-20261005-004j.json').exists());self.assertFalse(PLAN['runtime']['new_marker_created'])


if __name__=='__main__':unittest.main()
