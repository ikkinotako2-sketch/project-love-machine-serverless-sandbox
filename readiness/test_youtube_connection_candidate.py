from oracle_bridge import require_guard
require_guard()
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'readiness/production-candidate/source/plm/entrypoints/yt_serverless_candidate.py'
spec=importlib.util.spec_from_file_location('proposed_sender',SOURCE)
sender=importlib.util.module_from_spec(spec);spec.loader.exec_module(sender)

class SenderTests(unittest.TestCase):
    def setUp(self):
        self.fixture=json.loads((ROOT/'readiness/production-candidate/sender-cross-language-fixture.json').read_text())
    def test_callback_exact_node_python_signed_bytes(self):
        f=self.fixture
        raw,sig=sender.sign(f['callback_body'],f['callback_fixture_key'].encode(),'plm-youtube-result-v2')
        self.assertEqual(raw,f['callback_raw']);self.assertEqual(sig,f['callback_signature'])
    def test_stage_exact_node_python_signed_bytes(self):
        f=self.fixture
        raw,sig=sender.sign(f['stage_body'],f['stage_fixture_key'].encode(),'plm-youtube-checkpoint-v1')
        self.assertEqual(raw,f['stage_raw']);self.assertEqual(sig,f['stage_signature'])
    def test_event_boolean_restore_and_exact_payload_hash(self):
        f=self.fixture
        inputs=dict(f['dispatch_payload']['inputs'])
        for k in ('made_for_kids','contains_synthetic_media','notify_subscribers'):inputs[k]=str(inputs[k]).lower()
        b=sender.context({'inputs':inputs},'123','1',f['dispatch_payload']['ref'],(ROOT/'readiness/production-candidate/source/.github/workflows/youtube-pipeline.yml').read_bytes(),108,'checkpoint-fixture')
        self.assertEqual(b['dispatch_payload_sha256'],f['stage_body']['dispatch_payload_sha256'])
        self.assertEqual(b,f['stage_body'])
    def test_rerun_context_rejected(self):
        f=self.fixture
        with self.assertRaisesRegex(ValueError,'EXACT_RUN_REF'):sender.context({'inputs':f['dispatch_payload']['inputs']},'123','2',f['dispatch_payload']['ref'],b'wrong',108,'fixture')
    def test_wrong_workflow_ref_rejected(self):
        f=self.fixture
        with self.assertRaisesRegex(ValueError,'EXACT_RUN_REF'):sender.context({'inputs':f['dispatch_payload']['inputs']},'123','1','f'*40,b'wrong',108,'fixture')
    def test_quality_gate_failure_rejected(self):
        with self.assertRaisesRegex(ValueError,'QUALITY_GATE'):sender.render_checkpoint(self.fixture['stage_body'],{'ok':False},b'FAKE_MEDIA_ONLY','rendered-short-job',110)
    def test_media_hash_from_bytes_and_run_mapping(self):
        b=sender.render_checkpoint(self.fixture['stage_body'],{'ok':True,'quality_gate':{'ok':True},'stages':{'quality_gate':'succeeded'}},b'FAKE_MEDIA_ONLY','rendered-short-job',110)
        self.assertEqual(b['media_sha256'],hashlib.sha256(b'FAKE_MEDIA_ONLY').hexdigest());self.assertEqual(b['render_run_id'],b['run_id'])
    def test_processed_status_required(self):
        f=self.fixture
        with self.assertRaisesRegex(ValueError,'PROCESSING_NOT_COMPLETE'):sender.result_payload(f['stage_body'],f['render_checkpoint'],f['adapter_result'],{'id':'offline0001','status':{'privacyStatus':'private','uploadStatus':'uploaded'}},114,'callback-fixture')
    def test_callback_payload_matches_node_builder(self):
        f=self.fixture
        self.assertEqual(sender.result_payload(f['stage_body'],f['render_checkpoint'],f['adapter_result'],f['video_status'],114,'callback-fixture'),f['callback_body'])
    def test_http_one_send_sentinel_and_close_on_unknown(self):
        calls=[]
        class C:
            def __init__(self,origin,timeout):calls.append(('open',origin,timeout))
            def request(self,*args,**kw):calls.append(('request',args[0]))
            def getresponse(self):raise TimeoutError('PUBLIC_FIXTURE_ONLY')
            def close(self):calls.append(('close',))
        with tempfile.TemporaryDirectory() as d:
            marker=Path(d)/'consumed'
            with self.assertRaisesRegex(ValueError,'UNKNOWN'):sender.send_once('https://offline.test/youtube/result','{}','0'*64,marker,C,'offline.test','/youtube/result')
            with self.assertRaises(FileExistsError):sender.send_once('https://offline.test/youtube/result','{}','0'*64,marker,C,'offline.test','/youtube/result')
        self.assertEqual(sum(c[0]=='request' for c in calls),1);self.assertEqual(calls[-1],('close',))
    def test_wrong_origin_no_send(self):
        with self.assertRaisesRegex(ValueError,'EXACT_CALLBACK_URL'):sender.send_once('https://other.test/youtube/result','{}','0'*64,'unused',None,'offline.test','/youtube/result')
    def test_patch_scope_and_legacy_inputs(self):
        patch=(ROOT/'readiness/production-candidate/production.patch').read_text()
        self.assertEqual(patch.count('+++ '),3)
        self.assertIn('b/.github/workflows/youtube-pipeline.yml',patch)
        self.assertIn('b/.github/workflows/youtube-adapter.yml',patch)
        self.assertIn('b/plm/entrypoints/yt_serverless_candidate.py',patch)
        self.assertNotIn('b/.github/workflows/render-short.yml',patch)

if __name__=='__main__':unittest.main()
