"""SQLite fixture only. No provider, worker, socket, render or production adapter."""
import hashlib,json,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
JOB='plm-durable-stage2-job-001';INTENT='plm-durable-stage2-20261003-r1';ACCOUNT='test_reference_001'
FP=hashlib.sha256(b'public-stage2-generation-input-fixture').hexdigest()
REQ=hashlib.sha256(b'public-model-request-contract-fixture').hexdigest()
OUTPUT=hashlib.sha256(b'public-normalized-output-fixture').hexdigest()
PAYLOAD=hashlib.sha256(b'public-canonical-callback-fixture').hexdigest()
PROOF=hashlib.sha256(b'public-old-owner-stopped-fixture-not-live-proof').hexdigest()
def db(path=':memory:'):
 c=sqlite3.connect(path,isolation_level=None);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');c.executescript((ROOT/'serverless/migrations/0003_durable_stage2_probe.sql').read_text());return c
INIT="INSERT INTO durable_stage2_job VALUES(?,?,?,?, 'owner_a',1,1,1,'CLAIMED','NONE',NULL,NULL,NULL,'create',?,?)"
HANDOFF="UPDATE durable_stage2_job SET owner='owner_b',owner_epoch=2,fencing_token=2,version=version+1,old_owner_stop_proof=?,last_operation='handoff',updated_at=? WHERE job_id=? AND owner='owner_a' AND owner_epoch=1 AND fencing_token=1 AND version=1 AND state='CLAIMED' AND effect_state='NONE'"
RESERVE="UPDATE durable_stage2_job SET state='RESERVED',effect_state='RESERVED',effect_id='stage2-effect-001',version=version+1,last_operation='reserve',updated_at=? WHERE job_id=? AND owner=? AND owner_epoch=? AND fencing_token=? AND version=2 AND state='CLAIMED'"
CK_CREATE="INSERT INTO durable_stage2_checkpoint VALUES('stage2-checkpoint-001',?,?,?,?,NULL,NULL,1,'STARTED',?,?) ON CONFLICT(checkpoint_id) DO NOTHING"
CK_COMPLETE="UPDATE durable_stage2_checkpoint SET output_fingerprint=?,output_ref='fixture://stage2/generation.json',version=version+1,state='COMPLETED',updated_at=? WHERE checkpoint_id='stage2-checkpoint-001' AND job_id=? AND generation_fingerprint=? AND request_contract_fingerprint=? AND version=1 AND state='STARTED' AND EXISTS(SELECT 1 FROM durable_stage2_job j WHERE j.job_id=durable_stage2_checkpoint.job_id AND j.owner=? AND j.owner_epoch=? AND j.fencing_token=?)"
MARK_SENT="UPDATE durable_stage2_job SET state='SENT',effect_state='SENT',version=version+1,last_operation='sent',updated_at=? WHERE job_id=? AND owner='owner_b' AND owner_epoch=2 AND fencing_token=2 AND version=3 AND state='RESERVED'"
MARK_UNKNOWN="UPDATE durable_stage2_job SET state='UNKNOWN',effect_state='UNKNOWN',version=version+1,last_operation='unknown',updated_at=? WHERE job_id=? AND owner='owner_b' AND owner_epoch=2 AND fencing_token=2 AND version=4 AND state='SENT'"
CALLBACK="INSERT INTO durable_stage2_callback SELECT 'stage2-delivery-001',job_id,account_id,owner_epoch,fencing_token,?,'stage2-result-001','SUCCEEDED',? FROM durable_stage2_job WHERE job_id=? AND account_id=? AND owner_epoch=? AND fencing_token=? AND state IN ('UNKNOWN','SUCCEEDED') ON CONFLICT(delivery_id) DO NOTHING"
def steps(t=100):
 return [
 ('01_create_job',INIT,[JOB,ACCOUNT,INTENT,FP,t,t],1),
 ('02_handoff',HANDOFF,[PROOF,t+1,JOB],1),
 ('03_stale_owner',RESERVE,[t+2,JOB,'owner_a',1,1],0),
 ('04_stale_fence',RESERVE,[t+2,JOB,'owner_b',2,1],0),
 ('05_duplicate_handoff',HANDOFF,[PROOF,t+1,JOB],0),
 ('06_checkpoint_started',CK_CREATE,[JOB,INTENT,FP,REQ,t+2,t+2],1),
 ('07_checkpoint_completed',CK_COMPLETE,[OUTPUT,t+3,JOB,FP,REQ,'owner_b',2,2],1),
 ('08_checkpoint_duplicate',CK_CREATE,[JOB,INTENT,FP,REQ,t+2,t+2],0),
 ('09_reservation',RESERVE,[t+4,JOB,'owner_b',2,2],1),
 ('10_sent_fixture',MARK_SENT,[t+5,JOB],1),
 ('11_unknown_fixture',MARK_UNKNOWN,[t+6,JOB],1),
 ('12_stale_callback',CALLBACK,[PAYLOAD,t+7,JOB,ACCOUNT,1,1],0),
 ('13_callback_terminal_atomic',CALLBACK,[PAYLOAD,t+7,JOB,ACCOUNT,2,2],2),
 ('14_callback_duplicate',CALLBACK,[PAYLOAD,t+7,JOB,ACCOUNT,2,2],0)]
def execute(c,step):
 before=c.total_changes;c.execute(step[1],step[2]);return c.total_changes-before
def rows(c):return {name:[dict(r) for r in c.execute('SELECT * FROM '+name)] for name in ('durable_stage2_job','durable_stage2_checkpoint','durable_stage2_callback')}
def checkpoint_resume(c,generation_fp=FP,request_fp=REQ,output_available=True,output_hash=OUTPUT):
 r=c.execute('SELECT * FROM durable_stage2_checkpoint').fetchone()
 if not r:return 'CREATE_RESERVATION_ONLY'
 if r['generation_fingerprint']!=generation_fp or r['request_contract_fingerprint']!=request_fp:return 'REJECT_FINGERPRINT'
 if r['state']!='COMPLETED':return 'STOP_NO_AUTOMATIC_GENERATION'
 if not output_available or r['output_fingerprint']!=output_hash:return 'STOP_MISSING_OR_CORRUPT_OUTPUT_NO_REGENERATION'
 return 'RESUME_FROM_COMPLETED_NO_GENERATION'
def handoff_authorized(*,old_owner_stopped=False,inflight='UNKNOWN',proof=None,timeout=False):
 return old_owner_stopped is True and inflight=='NONE' and proof==PROOF
class SideEffect:
 def __init__(self,state='RESERVED'):self.state=state;self.sends=0;self.reconciliations=0
 def send(self,lost=False):
  if self.state!='RESERVED':raise ValueError('SENT_UNKNOWN_NO_RESEND')
  self.state='SENT';self.sends+=1
  if lost:self.state='UNKNOWN'
 def restart(self):
  if self.state in ('SENT','UNKNOWN'):raise ValueError('NO_AUTOMATIC_RESUME')
 def reconcile(self,result):
  if self.state not in ('SENT','UNKNOWN') or self.reconciliations:raise ValueError('RECONCILIATION_LIMIT')
  if result not in ('COMMITTED','NOT_COMMITTED','STILL_UNKNOWN'):raise ValueError('INVALID_RECONCILIATION')
  self.reconciliations+=1
  if result=='COMMITTED':self.state='CONFIRMED'
  elif result=='NOT_COMMITTED':self.state='NOT_COMMITTED_MANUAL_APPROVAL_REQUIRED'
  else:self.state='UNKNOWN'
  return self.state
