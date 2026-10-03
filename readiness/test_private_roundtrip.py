import hashlib
import sqlite3
import unittest
from pathlib import Path
from types import SimpleNamespace
from private_roundtrip import ai_preconditions, generation_recovery, render_inputs

class PrivateRoundtripTests(unittest.TestCase):
    def test_missing_free_backend_and_approval_blocks(self):
        self.assertEqual(ai_preconditions({})['status'],'BLOCKED')
        self.assertIn('billing_unlinked',ai_preconditions({})['missing'])
        self.assertIn('durable_backend_verified',ai_preconditions({})['missing'])

    def test_unknown_never_regenerates(self):
        for state in ('SENT','STARTED','UNKNOWN','TIMEOUT','AMBIGUOUS'):
            self.assertEqual(generation_recovery(state,False),'STOP_MANUAL_RECONCILIATION_NO_RESEND')
            self.assertEqual(generation_recovery(state,True),'READ_SAVED_CHECKPOINT_NO_REGENERATION')

    def test_local_checkpoint_cannot_unlock_render(self):
        r=SimpleNamespace(script_checkpoint_json='{}',job_id='job')
        for readback in ({},{'state':'COMPLETED','job_id':'job','script_json':'{}','script_sha256':'0'*64}):
            with self.assertRaises(ValueError):render_inputs(r,readback)

    def test_saved_checkpoint_maps_existing_render_inputs_private_only(self):
        from checkpoint_e2e import OfflineCheckpointE2E
        from offline_readiness import FLAGS
        import json
        golden=json.loads(Path(__file__).with_name('parity_fixture.json').read_text())
        flow=OfflineCheckpointE2E(dict.fromkeys(FLAGS,True))
        r=flow.begin({'source':'manual','platform':'youtube','account_id':'youtube_game_001','intent_id':'private-one','theme':golden['theme']},'fixture-owner',lambda:golden['job_id'])
        r=flow.checkpoint(r.intent.key,'fixture-owner',r.version,golden['script_response'])
        readback={'state':'COMPLETED','job_id':r.job_id,'script_json':r.script_checkpoint_json,'script_sha256':hashlib.sha256(r.script_checkpoint_json.encode()).hexdigest()}
        result=render_inputs(r,readback)
        self.assertEqual(result['inputs']['privacy_status'],'private')
        self.assertIs(result['inputs']['notify_subscribers'],False)
        self.assertEqual(result['inputs']['scheduled_for'],'')
        self.assertIs(result['allow'],False)
        self.assertEqual(result['inputs']['job_id'],r.job_id)

    def test_proposal_persists_script_and_blocks_overwrite(self):
        db=sqlite3.connect(':memory:')
        db.executescript((Path(__file__).resolve().parents[1]/'serverless/migrations/0006_youtube_checkpoint_proposal.sql').read_text())
        db.execute('INSERT INTO youtube_roundtrip_checkpoint VALUES (?,?,?,?,?,?,?,?,?)',('real-job-01','youtube_game_001','intent-01','a'*64,'gemini-3.8-flash','STARTED',None,None,1))
        script='{"title":"fixture"}';sha=hashlib.sha256(script.encode()).hexdigest()
        db.execute("UPDATE youtube_roundtrip_checkpoint SET state='COMPLETED',script_json=?,script_sha256=?,version=2 WHERE job_id=? AND version=1",(script,sha,'real-job-01'));db.commit()
        self.assertEqual(db.execute('SELECT script_json,script_sha256 FROM youtube_roundtrip_checkpoint').fetchone(),(script,sha))
        with self.assertRaises(sqlite3.IntegrityError):db.execute("UPDATE youtube_roundtrip_checkpoint SET script_json='{}' WHERE job_id='real-job-01'")
        with self.assertRaises(sqlite3.IntegrityError):db.execute('INSERT INTO youtube_roundtrip_checkpoint SELECT * FROM youtube_roundtrip_checkpoint')

    def test_unknown_checkpoint_terminal(self):
        db=sqlite3.connect(':memory:');db.executescript((Path(__file__).resolve().parents[1]/'serverless/migrations/0006_youtube_checkpoint_proposal.sql').read_text())
        db.execute('INSERT INTO youtube_roundtrip_checkpoint VALUES (?,?,?,?,?,?,?,?,?)',('job','youtube_game_001','intent','a'*64,'gemini-3.8-flash','STARTED',None,None,1))
        db.execute("UPDATE youtube_roundtrip_checkpoint SET state='UNKNOWN',version=2")
        with self.assertRaises(sqlite3.IntegrityError):db.execute("UPDATE youtube_roundtrip_checkpoint SET state='STARTED',version=1")
