"""Offline private-upload boundary over a reference SQL ledger; never a live adapter.

Reuse existing render Quality Gate/artifact checks and the production result shape.
The reference ledger survives new oracle objects on the same connection, not
runner loss. A deployed durable ledger and authenticated evidence are still gates.
"""
from oracle_bridge import require_guard
import hashlib
import json
import re
import sqlite3
from one_shot_executor import Stop, need, quality_gate, artifact_gate
from youtube_pipeline_production_result_snapshot import build_pipeline_result

FLAGS = ('TEST_ONLY', 'DRY_RUN', 'NO_PUBLISH', 'EMERGENCY_STOP')
FIELDS = frozenset(('job_id', 'account_id', 'idempotency_key', 'media_sha256',
                    'privacy_status', 'notify_subscribers', 'scheduled_for',
                    'made_for_kids', 'contains_synthetic_media', 'video_count',
                    'oauth_secret_exists', 'quota_verified', 'zero_cost_verified',
                    'runtime_verified', 'flags'))
HEX = re.compile(r'[0-9a-f]{64}')
VIDEO = re.compile(r'[A-Za-z0-9_-]{11}')
RESULT_KEYS = frozenset(('post_id', 'privacy_status', 'upload_status', 'media_sha256'))

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()

def validate_contract(request, quality, files):
    require_guard()
    need(type(request) is dict and set(request) == FIELDS, 'UPLOAD_CONTRACT_FIELDS')
    need(type(request['flags']) is dict and set(request['flags']) == set(FLAGS)
         and all(request['flags'][k] is True for k in FLAGS), 'UNSAFE_FLAGS')
    need(request['account_id'] == 'youtube_game_001' and
         isinstance(request['job_id'], str) and
         re.fullmatch(r'yt-[0-9]+-[0-9]{13}', request['job_id']), 'UPLOAD_IDENTITY')
    need(all(isinstance(request[k], str) and HEX.fullmatch(request[k])
             for k in ('idempotency_key', 'media_sha256')), 'UPLOAD_BINDING')
    need(type(request['video_count']) is int and request['video_count'] == 1, 'ONE_VIDEO_REQUIRED')
    need(request['privacy_status'] == 'private' and request['notify_subscribers'] is False
         and request['scheduled_for'] is None, 'PRIVATE_NO_SCHEDULE_REQUIRED')
    need(all(type(request[k]) is bool for k in ('made_for_kids', 'contains_synthetic_media')),
         'EXPLICIT_DISCLOSURE_REQUIRED')
    for field, code in (('oauth_secret_exists', 'OAUTH_SECRET_MISSING'),
                        ('quota_verified', 'QUOTA_NOT_VERIFIED'),
                        ('zero_cost_verified', 'ZERO_COST_NOT_VERIFIED'),
                        ('runtime_verified', 'RUNTIME_NOT_VERIFIED')):
        need(request[field] is True, code)
    quality_fields = {'mp4_exists','bytes','video_stream','audio_stream','width','height',
                      'fps','duration','captions_file_exists','captions','max_yavg',
                      'mean_volume_db','media_sha256'}
    need(type(quality) is dict and set(quality) == quality_fields, 'QUALITY_FIELDS')
    from offline_readiness import SENSITIVE
    need(isinstance(quality['captions'], str) and len(quality['captions']) <= 65536
         and not SENSITIVE.search(quality['captions']), 'QUALITY_CAPTIONS_UNSAFE')
    need(quality.get('media_sha256') == request['media_sha256'],
         'QUALITY_MEDIA_BINDING')
    quality_gate(quality)
    bounds = artifact_gate(files)
    need(files['short.mp4'] == quality['bytes'], 'QUALITY_SIZE_BINDING')
    return bounds

class ReferenceLedger:
    """SQL reference only, with atomic unique claims. No external storage writes.

    Connection must be in-memory. Production D1/GitHub persistence is NOT wired.
    CLAIMED is already consumed: crash before upload does not permit another claim.
    Different keys cannot resend the same job or bytes. Ambiguity requires human
    reconciliation; neither failed states nor process restarts release the claim.
    """
    def __init__(self, connection):
        require_guard()
        self.db = connection
        need(all(not row[2] for row in self.db.execute('PRAGMA database_list')),
             'OFFLINE_MEMORY_LEDGER_REQUIRED')
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS youtube_claim (
            key TEXT PRIMARY KEY, job TEXT UNIQUE NOT NULL,
            media TEXT UNIQUE NOT NULL, binding TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN
              ('CLAIMED','ATTEMPTED','UNKNOWN','CONFIRMED','RESULT_SAVED')),
            result TEXT
          );
          CREATE TRIGGER IF NOT EXISTS youtube_no_delete
            BEFORE DELETE ON youtube_claim BEGIN SELECT RAISE(ABORT,'consumed'); END;
          CREATE TRIGGER IF NOT EXISTS youtube_identity_immutable
            BEFORE UPDATE OF key,job,media,binding ON youtube_claim
            BEGIN SELECT RAISE(ABORT,'consumed'); END;
          CREATE TRIGGER IF NOT EXISTS youtube_monotonic
            BEFORE UPDATE OF state ON youtube_claim
            WHEN NOT ((OLD.state='CLAIMED' AND NEW.state='ATTEMPTED') OR
                      (OLD.state='ATTEMPTED' AND NEW.state IN ('UNKNOWN','CONFIRMED')) OR
                      (OLD.state='CONFIRMED' AND NEW.state IN ('UNKNOWN','RESULT_SAVED')))
            BEGIN SELECT RAISE(ABORT,'invalid_transition'); END;
          CREATE TRIGGER IF NOT EXISTS youtube_result_immutable
            BEFORE UPDATE OF result ON youtube_claim WHEN OLD.result IS NOT NULL
            BEGIN SELECT RAISE(ABORT,'result_immutable'); END;
        """)

    def claim(self, request, quality, files):
        binding = digest({'request': request, 'quality': quality, 'files': files})
        try:
            with self.db:
                count = self.db.execute(
                  """INSERT INTO youtube_claim
                     SELECT ?,?,?,?,'CLAIMED',NULL
                     WHERE NOT EXISTS
                       (SELECT 1 FROM youtube_claim WHERE state <> 'RESULT_SAVED')""",
                  (request['idempotency_key'], request['job_id'],
                   request['media_sha256'], binding)).rowcount
                if count != 1:
                    duplicate = self.db.execute(
                        'SELECT 1 FROM youtube_claim WHERE key=? OR job=? OR media=?',
                        (request['idempotency_key'], request['job_id'],
                         request['media_sha256'])).fetchone()
                    raise Stop('DUPLICATE_OR_CONSUMED' if duplicate else 'PRIOR_JOB_UNRESOLVED')
        except sqlite3.IntegrityError:
            raise Stop('DUPLICATE_OR_CONSUMED') from None
        return binding

    def transition(self, key, old, new):
        with self.db:
            count = self.db.execute('UPDATE youtube_claim SET state=? WHERE key=? AND state=?',
                                    (new, key, old)).rowcount
            need(count == 1, 'LEDGER_TRANSITION_REJECTED')

    def save(self, key, payload):
        encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        with self.db:
            count = self.db.execute(
                "UPDATE youtube_claim SET state='RESULT_SAVED',result=? WHERE key=? AND state='CONFIRMED'",
                (encoded, key)).rowcount
            need(count == 1, 'RESULT_SAVE_REJECTED')

    def state(self, key):
        row = self.db.execute('SELECT state FROM youtube_claim WHERE key=?', (key,)).fetchone()
        return row[0] if row else None

    def result(self, key):
        row = self.db.execute('SELECT result FROM youtube_claim WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row and row[0] else None

def confirmed_result(reply, request):
    # Strict projection: never persist an external body, URL, message or exception.
    need(type(reply) is dict and set(reply) == RESULT_KEYS, 'UPLOAD_RESULT_UNSAFE_OR_UNKNOWN')
    need(isinstance(reply['post_id'], str) and VIDEO.fullmatch(reply['post_id']),
         'UPLOAD_RESULT_UNSAFE_OR_UNKNOWN')
    need(reply['privacy_status'] == 'private' and reply['upload_status'] == 'processed'
         and reply['media_sha256'] == request['media_sha256'], 'UPLOAD_RESULT_UNSAFE_OR_UNKNOWN')
    payload = build_pipeline_result(
        job_id=request['job_id'], render_job_status='success', youtube_job_status='success',
        render_result={'ok': True, 'quality_gate': 'PASS'},
        youtube_result={'ok': True, 'result': {
            'post_id': reply['post_id'], 'state': 'published',
            'url': 'https://www.youtube.com/watch?v=' + reply['post_id']}})
    payload.update(privacy_status='private', notify_subscribers=False,
                   next_job_ready=True, actual_operations=0, live_ready=False)
    return payload

class OfflinePrivatePipeline:
    """Injected fake upload only. Guarded tests; live entry always denied."""
    def __init__(self, ledger):
        require_guard()
        self.ledger = ledger
        self.fake_upload_attempts = 0

    def execute(self, request, quality, files, fake_upload):
        validate_contract(request, quality, files)
        self.ledger.claim(request, quality, files)
        key = request['idempotency_key']
        self.ledger.transition(key, 'CLAIMED', 'ATTEMPTED')
        self.fake_upload_attempts += 1
        try:
            payload = confirmed_result(fake_upload(), request)
        except Exception:
            self.ledger.transition(key, 'ATTEMPTED', 'UNKNOWN')
            raise Stop('UPLOAD_UNKNOWN_PERMANENTLY_CONSUMED') from None
        self.ledger.transition(key, 'ATTEMPTED', 'CONFIRMED')
        try:
            self.ledger.save(key, payload)
            need(self.ledger.result(key) == payload, 'RESULT_READBACK_MISMATCH')
        except Exception:
            # Save could have succeeded before a timeout. Never resend; no reset.
            if self.ledger.state(key) == 'CONFIRMED':
                self.ledger.transition(key, 'CONFIRMED', 'UNKNOWN')
            raise Stop('RESULT_PERSISTENCE_UNKNOWN_NO_RESEND') from None
        return payload

def live_upload_gate():
    raise Stop('BLOCKED_RUNTIME_DURABLE_LEDGER_AND_UPLOAD_APPROVAL_REQUIRED')
