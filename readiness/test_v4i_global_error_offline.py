from oracle_bridge import require_guard
require_guard()
import json
from pathlib import Path
import unittest
import apt_safe_fingerprint_v4h as h

ROOT=Path(__file__).resolve().parents[1]

def trusted():
    return h.context({'noble':{('root','1','amd64'):{'Depends':'dep (>= 2)'},('dep','2','amd64'):{},('other','2','amd64'):{}}},{})

class GlobalErrorOfflineAuditTests(unittest.TestCase):
    def report(self):
        return json.loads((ROOT/'readiness/runtime-preflight-v4i-global-error-offline-audit.json').read_text())

    def test_frozen_source_scope(self):
        r=self.report();e=json.loads((ROOT/r['source_evidence']).read_text())
        self.assertEqual(r['mode'],'OFFLINE_ONLY')
        self.assertEqual(e['implementation'],'Ubuntu Noble APT 2.8.3')
        self.assertEqual(e['source_commit'],r['source_commit'])
        self.assertFalse(e['source_fetch_in_runtime']);self.assertFalse(e['source_fetch_in_offline_CI'])

    def test_global_error_e_candidates_exactly_six(self):
        r=self.report();f=json.loads((ROOT/r['source_fixtures']).read_text())['fixtures']
        self.assertEqual(len(f),17)
        c=[x for x in f if x['stream']=='stderr' and x['template_instance'].startswith('E:')]
        self.assertEqual(len(c),6);self.assertEqual(r['scope']['global_error_e_stderr_candidates'],6)

    def test_observed_fingerprint_matches_no_frozen_template(self):
        r=self.report();target=r['observed_safe_fingerprint']
        fixtures=json.loads((ROOT/r['source_fixtures']).read_text())['fixtures']
        candidates=[x for x in fixtures if x['stream']=='stderr' and x['template_instance'].startswith('E:')]
        actual=[];exact=0
        for item in candidates:
            shape=h.fingerprint(item['template_instance'],trusted(),'STDERR')
            diff=sorted(k for k,v in target.items() if shape[k]!=v)
            if not diff:exact+=1
            actual.append(dict(source_file=item['source_file'],source_line=item['source_line'],family=item['family'],mismatch_fields=diff))
        expected=[dict(x,mismatch_fields=sorted(x['mismatch_fields'])) for x in r['candidate_mismatches']]
        self.assertEqual(sorted(actual,key=lambda x:(x['source_file'],x['source_line'])),sorted(expected,key=lambda x:(x['source_file'],x['source_line'])))
        self.assertEqual(exact,0);self.assertEqual(r['scope']['exact_source_template_matches'],0)

    def test_no_root_cause_or_authorization_claim(self):
        r=self.report();s=r['scope']
        self.assertFalse(s['inference_allowed']);self.assertFalse(s['root_cause_proven'])
        self.assertFalse(s['transaction_proof']);self.assertFalse(s['install_authorized'])
        self.assertEqual(r['conclusion'],'NO_EXACT_MATCH_IN_FROZEN_SOURCE_CONFIRMED_GLOBALERROR_E_TEMPLATES')

    def test_004h_consumed_and_no_004i_runtime_surface(self):
        marker=ROOT/'audit-evidence/consumed/manual-fixture-runtime-preflight-20261005-004h.json'
        self.assertTrue(marker.is_file())
        self.assertFalse((ROOT/'audit-evidence/consumed/manual-fixture-runtime-preflight-20261006-004i.json').exists())
        self.assertFalse(list((ROOT/'.github/workflows').glob('*v4i*')))

    def test_audit_contains_no_raw_runtime_capture_fields(self):
        raw=json.dumps(self.report(),sort_keys=True)
        for field in ('raw_stdout','raw_stderr','raw_line','runtime_output','captured_line'):
            self.assertNotIn(field,raw)
