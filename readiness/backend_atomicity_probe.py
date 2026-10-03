"""SQLite/offline probe only. Never calls Cloudflare or starts an external client.

The nine-step REST plan is inert. SQLite passing does not prove D1 concurrency.
"""
from pathlib import Path
import copy
import hashlib
import json
import sqlite3

SQL_PATH=Path(__file__).resolve().parents[1]/'serverless/migrations/0002_backend_probe_v1.sql'
SQL_SHA='ca2ee1a2c618c5f71b43ade4620d9ded3eb105282be9a610c492632fec59fdc3'
PLATFORM='test'; ACCOUNT='test_reference_001'
INTENT='plm-d1-atomicity-20261003-r1'; JOB='plm-d1-atomicity-job-001'
FP='5bb172915fd10aac8565814c5157a28ded8001e0c8cc5a85317f2d0e2a7feb6b'
IDENTITY=(PLATFORM,ACCOUNT,INTENT)
DB_ID='18050cf6-934e-4f3a-a1cd-5041bac1c35e'
CF_ACCOUNT='6c8ccd6aface937ab5dabef61cb64534'
INSERT="INSERT INTO backend_probe_v1(platform,account_id,intent_id,job_id,content_fingerprint,owner,owner_epoch,fencing_token,state,version,last_request_id,created_at,updated_at) VALUES(?,?,?,?,?,NULL,0,0,'ready',1,'init',?,?) ON CONFLICT(platform,account_id,intent_id) DO NOTHING"
CLAIM="UPDATE backend_probe_v1 SET owner=?,owner_epoch=1,fencing_token=1,state='claimed',version=version+1,last_request_id=?,updated_at=? WHERE platform=? AND account_id=? AND intent_id=? AND content_fingerprint=? AND version=1 AND state='ready' AND owner IS NULL AND owner_epoch=0 AND fencing_token=0"
TERMINAL="UPDATE backend_probe_v1 SET state=?,version=version+1,last_request_id='terminal',delivery_id='delivery_001',result_id='result_001',updated_at=? WHERE platform=? AND account_id=? AND intent_id=? AND content_fingerprint=? AND version=? AND state='claimed' AND owner=? AND owner_epoch=1 AND fencing_token=1"
READ="SELECT * FROM backend_probe_v1 WHERE platform=? AND account_id=? AND intent_id=?"

def migration_contract(raw=None):
    raw=SQL_PATH.read_bytes() if raw is None else raw
    if hashlib.sha256(raw).hexdigest()!=SQL_SHA:raise ValueError('SQL_HASH_MISMATCH')
    text=raw.decode('utf-8','strict'); statements=[]; buffer=''
    for line in text.splitlines(True):
        buffer+=line
        if sqlite3.complete_statement(buffer):
            statements.append(buffer); buffer=''
    if buffer.strip() or len(statements)!=2:raise ValueError('MIGRATION_STATEMENTS_MISMATCH')
    if 'CREATE TABLE backend_probe_v1' not in statements[0] or not statements[1].startswith('CREATE TRIGGER backend_probe_v1_guard'):raise ValueError('MIGRATION_NOT_ADDITIVE')
    # Guard BEGIN/SELECT/END is part of CREATE TRIGGER, not a standalone mutation.
    return {'sha256':SQL_SHA,'create_table':1,'create_trigger':1,'alter':0,'destructive_statements':0,'standalone_data_mutations':0,'statements':2,'execution_permitted':False}

def sql_plan(now=1790998200,winner='contender_a',outcome='succeeded'):
    if type(now) is not int or now<=0 or winner not in ('contender_a','contender_b') or outcome not in ('succeeded','failed'):raise ValueError('PLAN_INPUT_REJECTED')
    loser='contender_b' if winner=='contender_a' else 'contender_a'
    init=[PLATFORM,ACCOUNT,INTENT,JOB,FP,now,now]
    def term(owner,version=2,fp=FP):return [outcome,now+2,*IDENTITY,fp,version,owner]
    return [
      {'id':'01_init','sql':INSERT,'params':init,'expected_changes':1},
      {'id':'02_identity_replay','sql':INSERT,'params':init,'expected_changes':0},
      {'id':'03_claim_a','sql':CLAIM,'params':['contender_a','claim_a',now+1,*IDENTITY,FP],'group':'concurrent_claim','expected_changes':None},
      {'id':'04_claim_b','sql':CLAIM,'params':['contender_b','claim_b',now+1,*IDENTITY,FP],'group':'concurrent_claim','expected_changes':None},
      {'id':'05_stale_version','sql':TERMINAL,'params':term(winner,1),'expected_changes':0},
      {'id':'06_stale_owner','sql':TERMINAL,'params':term(loser),'expected_changes':0},
      {'id':'07_wrong_fingerprint','sql':TERMINAL,'params':term(winner,2,'0'*64),'expected_changes':0},
      {'id':'08_terminal','sql':TERMINAL,'params':term(winner),'expected_changes':1},
      {'id':'09_terminal_replay','sql':TERMINAL,'params':term(winner),'expected_changes':0},
    ]

def validate_payload(step,now,winner='contender_a',outcome='succeeded'):
    matches=[x for x in sql_plan(now,winner,outcome) if x['id']==step.get('id')]
    if len(matches)!=1 or step!=matches[0]:raise ValueError('FIXED_PLAN_MISMATCH')
    for value in step['params']:
        if type(value) not in (str,int):raise ValueError('PARAM_TYPE_REJECTED')
    return {'sql':step['sql'],'params':copy.deepcopy(step['params'])}

class SQLiteReference:
    def __init__(self,filename=':memory:',initialize=True):
        self.db=sqlite3.connect(filename,isolation_level=None,timeout=5)
        self.db.row_factory=sqlite3.Row
        if initialize:
            migration_contract();self.db.executescript(SQL_PATH.read_text())
    def mutate(self,step):
        before=self.db.total_changes
        self.db.execute(step['sql'],step['params'])
        return self.db.total_changes-before
    def read(self):
        rows=self.db.execute(READ,IDENTITY).fetchall()
        if len(rows)>1:raise ValueError('MULTIPLE_IDENTITIES')
        return dict(rows[0]) if rows else None
    def close(self):self.db.close()

class OnceAttemptLedger:
    """Durable fixture snapshot, record intent before mock transport; never real API."""
    def __init__(self,snapshot=None):
        self.events=copy.deepcopy(snapshot or [])
        if type(self.events) is not list or len(self.events)>9:raise ValueError('BAD_JOURNAL')
        if any(type(e) is not dict or set(e)!={'id','status'} or type(e['id']) is not str or e['status'] not in ('SENT','ACK','UNKNOWN') for e in self.events):raise ValueError('BAD_JOURNAL')
        if len({e['id'] for e in self.events})!=len(self.events):raise ValueError('BAD_JOURNAL')
        if snapshot is not None:self.resume()
    def reserve(self,step):
        if any(e['status']=='UNKNOWN' for e in self.events):raise ValueError('UNKNOWN_STOP')
        if any(e['id']==step['id'] for e in self.events):raise ValueError('NO_RESEND')
        if len(self.events)>=9:raise ValueError('BUDGET_EXHAUSTED')
        self.events.append({'id':step['id'],'status':'SENT'})
    def finish(self,id,status):
        next(e for e in self.events if e['id']==id)['status']=status
    def snapshot(self):return copy.deepcopy(self.events)
    def send(self,step,transport):
        self.reserve(step)
        try:
            response=transport(step)
            if type(response) is not dict or response.get('http_status')!=200 or response.get('success') is not True or type(response.get('changes')) is not int or response['changes'] not in (0,1):raise ValueError('AMBIGUOUS_RESPONSE')
            self.finish(step['id'],'ACK');return response
        except Exception:
            self.finish(step['id'],'UNKNOWN')
            return {'status':'UNKNOWN','automatic_resend':False,'next':'READ_ONLY_RECONCILIATION_THEN_STOP'}
    def resume(self):
        # A persisted SENT entry after restart is ambiguous; never reset a slot.
        for e in self.events:
            if e['status']=='SENT':e['status']='UNKNOWN'
        return self

def reconcile(step,row,*,primary_confirmed=False,authoritative_not_committed=False):
    if authoritative_not_committed is True:return {'verdict':'NOT_COMMITTED','resend_permitted':False}
    if primary_confirmed is not True:return {'verdict':'STILL_UNKNOWN','resend_permitted':False}
    committed=False
    if row and tuple(row.get(k) for k in ('platform','account_id','intent_id'))==IDENTITY and row.get('job_id')==JOB and row.get('content_fingerprint')==FP:
        if step['id']=='01_init':committed=row.get('version')==1 and row.get('last_request_id')=='init'
        elif step['id'] in ('03_claim_a','04_claim_b'):committed=row.get('version')==2 and row.get('last_request_id')==step['params'][1] and row.get('owner')==step['params'][0]
        elif step['id']=='08_terminal':committed=row.get('version')==3 and row.get('last_request_id')=='terminal' and row.get('state')==step['params'][0] and row.get('owner')==step['params'][-1] and row.get('delivery_id')=='delivery_001' and row.get('result_id')=='result_001'
    # Absence/old row is NOT proof of no commit: a request may still be in flight.
    return {'verdict':'COMMITTED' if committed else 'STILL_UNKNOWN','resend_permitted':False}

def remote_readiness(schema_added=False,write_token=False,execution_approved=False):
    return {'offline_contract':'DESIGN PASS','remote_schema':'UNVERIFIED' if not schema_added else 'REQUIRES_FRESH_READBACK','remote_atomicity':'UNVERIFIED','remote_fencing':'UNVERIFIED','callback_replay_ledger':'UNVERIFIED','schema_migration_required':True,'write_token_present':write_token,'execution_permitted':False,'manual_approval_required':not execution_approved,'live_ready':False,'posting_permitted':False}

def validate_remote_preconditions(evidence):
    """Inert future gate, not a live executor or permission to send SQL."""
    required={'account':CF_ACCOUNT,'database':DB_ID,'database_name':'plm-serverless-sandbox-state',
      'inventory_complete':True,'inventory_count':1,'other_d1_count':0,'probe_table_absent':True,
      'existing_schema_unchanged':True,'test_jobs_rows':0,'bookmark_fresh':True,
      'token_kind':'ACCOUNT_TOKEN','token_active':True,'token_unexpired':True,
      'token_scope_owner_confirmed_d1_write_only':True,'free_owner_confirmed':True,
      'TEST_ONLY':True,'DRY_RUN':True,'NO_PUBLISH':True,'EMERGENCY_STOP':True,
      'run_attempt':1,'exact_commit_pinned':True,'migration_history_absent':True,
      'sql_sha256':SQL_SHA,'destructive_statements':0,'separate_final_migration_approval':True}
    failed=[k for k,v in required.items() if type(evidence.get(k)) is not type(v) or evidence.get(k)!=v]
    return {'preconditions_pass':not failed,'failed_gates':failed,'execution_permitted':False,
      'reason':'NO_LIVE_MIGRATION_EXECUTOR_IN_THIS_PREPARATION','token_scope_api_verified':False,
      'account_isolation':'unverified','d1_isolation':'TARGET_ONLY_IN_LATEST_INVENTORY' if not failed else 'UNVERIFIED'}
