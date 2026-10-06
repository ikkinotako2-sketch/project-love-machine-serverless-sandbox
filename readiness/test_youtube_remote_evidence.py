from oracle_bridge import require_guard
require_guard()
import hashlib
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
E=json.loads((ROOT/'readiness/youtube-remote-readonly-37409541462.json').read_text())

class FreshEvidenceTests(unittest.TestCase):
    def test_current_schema_exact(self):
        self.assertEqual(E['run_id'],37409541462);self.assertEqual(E['attempt'],1)
        self.assertEqual(E['head'],'fa9890e4350c4bb97b50e2cef5ad0ab750c500ef')
        self.assertEqual(E['result']['readiness'],'READ_ONLY_CONFIRMED');self.assertTrue(E['result']['protected_schema_exact'])
    def test_not_applied_candidates(self):
        self.assertEqual(E['result']['provider_neutral'],'NOT_APPLIED');self.assertEqual(E['result']['queue_result'],'NOT_APPLIED')
        self.assertEqual(E['result']['unknown_objects_count'],0)
    def test_calls_and_write_proof(self):
        self.assertEqual(E['result']['read_only_calls'],3);self.assertEqual(E['result']['query_rows_read'],85)
        for k in ('d1_write','deploy','dispatch','youtube_upload','retry','raw_retention'):self.assertEqual(E['result'][k],0)
    def test_unknown_live_gates_preserved(self):
        for k in ('account_free_plan','account_usage','worker_current','oauth_current'):self.assertEqual(E['result'][k],'UNVERIFIED')
        self.assertEqual(E['scope']['protected_rows_current'],'UNVERIFIED');self.assertFalse(E['result']['live_ready']);self.assertFalse(E['deploy_launchable'])
    def test_bound_plan_exact(self):
        self.assertEqual(hashlib.sha256((ROOT/'readiness/youtube-live-connection-plan.json').read_bytes()).hexdigest(),E['plan_sha256'])
    def test_readonly_not_runtime_authorization(self):
        self.assertTrue(E['read_only_identity_consumed']);self.assertFalse(E['retry_permitted']);self.assertFalse(E['resume_permitted'])
        self.assertFalse(E['marker_created']);self.assertFalse(E['scope']['transaction_proof']);self.assertFalse(E['scope']['install_authorized'])

if __name__=='__main__':unittest.main()
