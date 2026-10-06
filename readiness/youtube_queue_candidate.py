"""Guarded offline SQLite implementation of proposed serverless Queue/claim/result.

Uses the unchanged 0008 job/script/render/effect/callback schema. No HTTP client,
credentials, deployed Worker, real workflow dispatch, upload, or live approval.
Disk-backed tests prove SQLite commit/reopen behavior, not remote D1 deployment.
"""
from oracle_bridge import require_guard
import hashlib
import json
import re
import sqlite3

FLAGS = ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')
PRODUCTION = 'ikkinotako2-sketch/project-love-machine'
PRODUCTION_SHA = 'b0c7f429a1f58726c4a75f4fb090928cf567b585'


class QueueStop(ValueError):
    """Fixed code only; never external exception text or provider responses."""


def need(condition, code):
    if not condition:
        raise QueueStop(code)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',', ':'),
                                   allow_nan=False).encode()).hexdigest()


def identifier(value):
    return isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,64}',value)


def sha(value):
    return isinstance(value,str) and re.fullmatch(r'[0-9a-f]{64}',value)


class SQLiteQueueCandidate:
    def __init__(self, connection, flags):
        require_guard()
        need(type(flags) is dict and set(flags)==set(FLAGS) and
             all(flags[k] is True for k in FLAGS), 'UNSAFE_FLAGS')
        need(connection.execute('PRAGMA foreign_keys').fetchone()[0]==1,
             'FOREIGN_KEYS_REQUIRED')
        self.db=connection
        self.flags=dict(flags)
        self.fake_dispatch_calls=0
        self._owned_reservations=set()

    def _write(self, effect):
        require_guard()
        need(not self.db.in_transaction, 'TRANSACTION_BOUNDARY_REQUIRED')
        try:
            self.db.execute('BEGIN IMMEDIATE')
            value=effect()
            self.db.commit()
            return value
        except QueueStop:
            if self.db.in_transaction:self.db.rollback()
            raise
        except Exception:
            if self.db.in_transaction:self.db.rollback()
            raise QueueStop('SQL_CONFLICT_OR_UNKNOWN') from None

    def _row(self,job):
        row=self.db.execute('SELECT * FROM plm_ytq_v1_queue WHERE job_id=?',(job,)).fetchone()
        need(row is not None,'QUEUE_JOB_MISSING')
        return dict(row)

    def enqueue(self, entry, now):
        fields={'job_id','account_id','intent_id','script_sha256','owner',
                'owner_epoch','fencing_token','not_before'}
        need(type(entry) is dict and set(entry)==fields, 'QUEUE_FIELDS')
        need(entry['account_id']=='youtube_game_001' and
             all(identifier(entry[k]) for k in ('job_id','intent_id','owner')) and
             sha(entry['script_sha256']), 'QUEUE_IDENTITY')
        need(all(type(entry[k]) is int and entry[k]>0
                 for k in ('owner_epoch','fencing_token','not_before')) and
             type(now) is int and now>0,'QUEUE_TIME_OR_FENCE')
        def write():
            prior=self.db.execute('SELECT * FROM plm_ytq_v1_queue WHERE job_id=?',
                                  (entry['job_id'],)).fetchone()
            if prior:
                need(all(prior[k]==v for k,v in entry.items()),'QUEUE_REPLAY_CHANGED')
                return dict(prior)
            self.db.execute('''INSERT INTO plm_ytq_v1_queue
              (job_id,account_id,intent_id,script_sha256,owner,owner_epoch,fencing_token,
               not_before,state,version,created_at,updated_at)
              VALUES (?,?,?,?,?,?,?,?,'QUEUED',1,?,?)''',
              tuple(entry[k] for k in ('job_id','account_id','intent_id','script_sha256',
                                      'owner','owner_epoch','fencing_token','not_before'))+(now,now))
            return self._row(entry['job_id'])
        return self._write(write)

    def eligible(self,now):
        require_guard()
        need(type(now) is int and now>0,'QUEUE_TIME_OR_FENCE')
        row=self.db.execute('''SELECT job_id FROM plm_ytq_v1_queue q
          WHERE q.state='QUEUED' AND q.not_before<=? AND NOT EXISTS
            (SELECT 1 FROM plm_ytq_v1_queue a WHERE a.account_id=q.account_id
             AND a.state IN ('CLAIMED','DISPATCHED','UNKNOWN'))
          ORDER BY q.not_before,q.created_at,q.job_id LIMIT 1''',(now,)).fetchone()
        return row[0] if row else None

    def claim(self,job,owner,epoch,fence,version,now):
        need(identifier(job) and identifier(owner) and all(type(x) is int and x>0
             for x in (epoch,fence,version,now)),'QUEUE_TIME_OR_FENCE')
        def write():
            count=self.db.execute('''UPDATE plm_ytq_v1_queue
              SET state='CLAIMED',version=version+1,updated_at=?
              WHERE job_id=? AND state='QUEUED' AND owner=? AND owner_epoch=?
                AND fencing_token=? AND version=?''',
              (now,job,owner,epoch,fence,version)).rowcount
            need(count==1,'CLAIM_ALREADY_CONSUMED_OR_STALE')
            return self._row(job)
        return self._write(write)

    def reserve_dispatch(self,job,version,now):
        need(type(version) is int and version>0 and type(now) is int and now>0,
             'QUEUE_TIME_OR_FENCE')
        def write():
            row=self._row(job)
            need(row['state']=='CLAIMED' and row['version']==version,
                 'DISPATCH_ALREADY_CONSUMED_OR_STALE')
            dispatch_id=digest({'account_id':row['account_id'],'job_id':job,
                                'script_sha256':row['script_sha256']})
            proposal={'repository':PRODUCTION,'ref':PRODUCTION_SHA,
              'workflow':'.github/workflows/youtube-pipeline.yml','job_id':job,
              'script_sha256':row['script_sha256'],'privacy_status':'private',
              'notify_subscribers':False,'scheduled_for':None,'video_count':1,
              'flags':self.flags,'no_retry':True,'no_resume':True,'live_ready':False}
            self.db.execute('''INSERT INTO plm_ytq_v1_outbox
              VALUES (?,?,?,'RESERVED',0)''',(dispatch_id,job,digest(proposal)))
            count=self.db.execute('''UPDATE plm_ytq_v1_queue
              SET state='DISPATCHED',version=version+1,updated_at=?
              WHERE job_id=? AND state='CLAIMED' AND version=?''',(now,job,version)).rowcount
            need(count==1,'DISPATCH_RESERVATION_UNKNOWN')
            return {'dispatch_id':dispatch_id,'proposal':proposal,'actual_operations':0}
        receipt=self._write(write)
        self._owned_reservations.add(receipt['dispatch_id'])
        return receipt

    def fake_send(self,dispatch_id,fake_transport,now):
        """One fake send only, after durable intent; every actual live call denied."""
        need(sha(dispatch_id) and type(now) is int and now>0,'DISPATCH_IDENTITY')
        # Process-local capability is granted only after THIS instance commits
        # the reservation. Reopening a durable RESERVED row never grants resume.
        need(dispatch_id in self._owned_reservations,'DISPATCH_NO_RESUME_CAPABILITY')
        self._owned_reservations.remove(dispatch_id)
        def attempted():
            count=self.db.execute('''UPDATE plm_ytq_v1_outbox
              SET state='SENT',send_attempts=1 WHERE dispatch_id=? AND state='RESERVED'
              AND send_attempts=0''',(dispatch_id,)).rowcount
            need(count==1,'DISPATCH_ALREADY_CONSUMED_OR_STALE')
        self._write(attempted)
        self.fake_dispatch_calls+=1
        try:
            status=fake_transport()
            need(type(status) is int and status==204,'DISPATCH_NOT_CONFIRMED')
        except Exception:
            def unknown():
                out=self.db.execute('SELECT job_id FROM plm_ytq_v1_outbox WHERE dispatch_id=?',
                                    (dispatch_id,)).fetchone()
                self.db.execute("UPDATE plm_ytq_v1_outbox SET state='UNKNOWN' WHERE dispatch_id=? AND state='SENT'",(dispatch_id,))
                self.db.execute("UPDATE plm_ytq_v1_queue SET state='UNKNOWN',version=version+1,updated_at=? WHERE job_id=? AND state='DISPATCHED'",(now,out[0]))
            self._write(unknown)
            raise QueueStop('DISPATCH_UNKNOWN_NO_RETRY_OR_RESUME') from None
        return {'dispatch_acknowledged':True,'result_saved':False,'next_job_ready':False,
                'actual_operations':0,'live_ready':False}

    def save_result(self,job,body,now):
        # This is an OFFLINE verified-callback fixture, not public ingress/auth.
        fields={'result_id','video_id','media_sha256','privacy_status',
                'notify_subscribers','upload_status'}
        need(type(body) is dict and set(body)==fields,'RESULT_FIELDS')
        need(identifier(body['result_id']) and isinstance(body['video_id'],str) and
             re.fullmatch(r'[A-Za-z0-9_-]{11}',body['video_id']) and sha(body['media_sha256']),
             'RESULT_IDENTITY')
        need(body['privacy_status']=='private' and body['notify_subscribers'] is False
             and body['upload_status']=='processed','PRIVATE_PROCESSED_RESULT_REQUIRED')
        need(type(now) is int and now>0,'QUEUE_TIME_OR_FENCE')
        def write():
            prior=self.db.execute('SELECT * FROM plm_ytq_v1_result WHERE job_id=?',(job,)).fetchone()
            if prior:
                need(all(prior[k]==(0 if k=='notify_subscribers' else v)
                         for k,v in body.items()),'RESULT_REPLAY_CHANGED')
                return {'result_saved':True,'next_job_ready':True,'replay':True,
                        'actual_operations':0,'live_ready':False}
            self.db.execute('''INSERT INTO plm_ytq_v1_result
              (job_id,result_id,video_id,media_sha256,privacy_status,notify_subscribers,upload_status,saved_at)
              VALUES (?,?,?,?,?,0,?,?)''',(job,body['result_id'],body['video_id'],
              body['media_sha256'],body['privacy_status'],body['upload_status'],now))
            need(self._row(job)['state']=='COMPLETE','RESULT_READBACK_FAILED')
            return {'result_saved':True,'next_job_ready':True,'replay':False,
                    'actual_operations':0,'live_ready':False}
        return self._write(write)


def live_dispatch_gate():
    raise QueueStop('BLOCKED_CLOUDFLARE_DEPLOY_RUNTIME_AND_UPLOAD_APPROVAL_REQUIRED')
