"""Offline reference ledger; no database/backend or dispatch/API client.

Restart is an explicit JSON snapshot/reload simulation, not crash-safe storage.
Every record mutation is lock-protected with owner/version compare-and-swap.
"""
from dataclasses import dataclass, replace, asdict
import hashlib
import json
import re
from threading import RLock
from offline_readiness import FLAGS, _identifier, _text

STATES = {'pending','claimed','generating','ready','initializing','unknown','succeeded','failed'}
_FINGERPRINT = re.compile(r'[a-f0-9]{64}\Z')
_EDGES = {'claimed': {'generating','failed'}, 'generating': {'failed'},
          'ready': {'failed'}, 'initializing': {'unknown'}, 'unknown': set(),
          'succeeded': set(), 'failed': set(), 'pending': set()}


@dataclass(frozen=True)
class PublishIntent:
    platform: str
    account_id: str
    intent_id: str
    theme: str

    @property
    def key(self):
        return (self.platform, self.account_id, self.intent_id)


def normalize_intent(entry):
    if not isinstance(entry,dict) or set(entry) != {'source','platform','account_id','intent_id','theme'}:
        raise ValueError('invalid_intent_fields')
    if entry['source'] not in ('manual','schedule') or entry['platform'] != 'youtube':
        raise ValueError('invalid_entry')
    for k in ('account_id','intent_id'):
        _identifier(entry[k])
    if not entry['account_id'].startswith(('youtube_', 'youtube-')):
        raise ValueError('platform_mismatch')
    _text(entry['theme'],240)
    # JS/NFKC/content-based identity is intentionally not invented here.
    # Both callers supply the SAME persisted intent_id to mean the same intent.
    return PublishIntent('youtube',entry['account_id'],entry['intent_id'],entry['theme'].strip())


def _canonical(payload):
    if not isinstance(payload,dict):
        raise ValueError('invalid_content')
    # Content must pass the existing offline script/render validators first.
    # No arbitrary raw response, token/header/URL-bearing fields are accepted.
    allowed = {'title','hook','narration','scenes','captions','bgm','speaker','output'}
    if set(payload) != allowed:
        raise ValueError('invalid_content_fields')
    from offline_readiness import script_to_render
    script = {k:payload[k] for k in ('title','hook','narration','scenes','bgm')}
    checked = script_to_render('offline ledger fixture', script, 'youtube_game_001',
                               'yt-900001-1790942400000', dict.fromkeys(FLAGS,True))
    if checked['render_payload'] != payload:
        raise ValueError('invalid_render_payload')
    value = json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',', ':'),allow_nan=False)
    from offline_readiness import SENSITIVE
    if SENSITIVE.search(value) or 'https://' in value or 'http://' in value:
        raise ValueError('unsafe_content')
    return value


@dataclass(frozen=True)
class Record:
    intent: PublishIntent
    job_id: str
    owner: str | None = None
    version: int = 1
    state: str = 'pending'
    content_fingerprint: str | None = None
    content_json: str | None = None
    dispatch_reservations: int = 0
    callback_id: str | None = None
    result_id: str | None = None


class Conflict(ValueError):
    pass


class Ledger:
    """Reference only. RLock atomicity applies to THIS in-memory instance."""
    def __init__(self, flags):
        if not isinstance(flags,dict) or set(flags) != set(FLAGS) or any(flags[k] is not True for k in FLAGS):
            raise ValueError('unsafe_flags')
        self._records = {}
        self._jobs = set()
        self._lock = RLock()

    def register(self, intent, mint_job_id):
        # Only call the pure fixture mint factory for the FIRST registration.
        # The real caller must persist intent identity before its first request.
        if not isinstance(intent,PublishIntent) or normalize_intent({'source':'manual',**asdict(intent)}) != intent:
            raise ValueError('invalid_intent')
        if not callable(mint_job_id):
            raise ValueError('mint_factory_required')
        with self._lock:
            current = self._records.get(intent.key)
            if current:
                if current.intent != intent:
                    raise Conflict('intent_content_changed')
                return current
            minted_job_id = mint_job_id()
            _identifier(minted_job_id)
            if not re.fullmatch(r'yt-[0-9]+-[0-9]{13}', minted_job_id):
                raise ValueError('invalid_job_id')
            if minted_job_id in self._jobs:
                raise Conflict('job_id_collision')
            record = Record(intent,minted_job_id)
            self._records[intent.key] = record
            self._jobs.add(minted_job_id)
            return record

    def read(self, key):
        with self._lock:
            return self._records[key]

    def _cas(self, key, owner, version):
        _identifier(owner)
        record = self._records[key]
        if type(version) is not int or record.owner != owner or record.version != version:
            raise Conflict('stale_owner_or_version')
        return record

    def _save(self, record, **fields):
        updated = replace(record, version=record.version+1, **fields)
        self._records[record.intent.key] = updated
        return updated

    def claim(self, key, owner):
        _identifier(owner)
        with self._lock:
            record = self._records[key]
            if record.owner is not None:
                if record.owner != owner:
                    raise Conflict('competing_owner')
                return record # safe same-owner replay, including terminal state
            if record.state != 'pending':
                raise Conflict('invalid_claim_state')
            return self._save(record,owner=owner,state='claimed')

    def advance(self, key, owner, version, target):
        with self._lock:
            record = self._cas(key,owner,version)
            if not isinstance(target,str) or target not in _EDGES[record.state]:
                raise Conflict('invalid_transition')
            return self._save(record,state=target)

    def bind_content(self, key, owner, version, payload):
        canonical = _canonical(payload)
        fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
        with self._lock:
            record = self._cas(key,owner,version)
            if record.content_fingerprint is not None:
                if record.content_fingerprint != fingerprint or record.content_json != canonical:
                    raise Conflict('immutable_content')
                return record
            if record.state != 'generating':
                raise Conflict('invalid_content_state')
            return self._save(record,state='ready',content_fingerprint=fingerprint,content_json=canonical)

    def reserve_mock_dispatch(self, key, owner, version):
        """Save initializing BEFORE any future send; never actually sends.

        A crash here, including before a send, is conservatively ambiguous.
        Exactly-once external execution is NOT claimed.
        """
        with self._lock:
            record = self._cas(key,owner,version)
            if record.state != 'ready' or not record.content_fingerprint or record.dispatch_reservations:
                raise Conflict('initialize_forbidden')
            return self._save(record,state='initializing',dispatch_reservations=1)

    def callback(self, key, owner, version, callback_id, result_id, outcome):
        """Fixture callback; owner matching is not real authentication/signature."""
        _identifier(owner); _identifier(callback_id); _identifier(result_id)
        if outcome not in ('succeeded','failed'):
            raise ValueError('invalid_callback')
        with self._lock:
            record = self._records[key]
            if record.owner != owner:
                raise Conflict('stale_owner_or_version')
            if record.state in ('succeeded','failed'):
                if (record.callback_id,record.result_id,record.state) == (callback_id,result_id,outcome):
                    return record # exact callback replay is a no-op, old version OK
                raise Conflict('terminal_record')
            record = self._cas(key,owner,version)
            if record.state not in ('initializing','unknown') or record.dispatch_reservations != 1:
                raise Conflict('invalid_callback_state')
            return self._save(record,state=outcome,callback_id=callback_id,result_id=result_id)

    def snapshot(self):
        with self._lock:
            return json.dumps({'format':1,'records':[asdict(r) for r in self._records.values()]},
                              ensure_ascii=False,sort_keys=True,allow_nan=False)

    @classmethod
    def restore(cls, snapshot, flags):
        raw = json.loads(snapshot)
        if not isinstance(raw,dict) or set(raw) != {'format','records'} or type(raw['format']) is not int or raw['format'] != 1 or not isinstance(raw['records'],list):
            raise ValueError('invalid_snapshot')
        store = cls(flags)
        fields = set(Record.__dataclass_fields__)
        for data in raw['records']:
            if not isinstance(data,dict) or set(data) != fields or not isinstance(data['intent'],dict):
                raise ValueError('invalid_snapshot_record')
            intent = normalize_intent({'source':'manual',**data['intent']})
            if asdict(intent) != data['intent']:
                raise ValueError('noncanonical_intent')
            record = Record(**{**data,'intent':intent})
            _identifier(record.job_id)
            if not re.fullmatch(r'yt-[0-9]+-[0-9]{13}',record.job_id):
                raise ValueError('invalid_job_id')
            if type(record.version) is not int or record.version < 1 or not isinstance(record.state,str) or record.state not in STATES:
                raise ValueError('invalid_snapshot_state')
            if record.owner is not None: _identifier(record.owner)
            if (record.state == 'pending') != (record.owner is None):
                raise ValueError('invalid_owner_state')
            if type(record.dispatch_reservations) is not int or record.dispatch_reservations not in (0,1):
                raise ValueError('invalid_reservation')
            if (record.content_json is None) != (record.content_fingerprint is None):
                raise ValueError('invalid_content_record')
            if record.content_fingerprint is not None:
                if not isinstance(record.content_fingerprint,str) or not _FINGERPRINT.fullmatch(record.content_fingerprint):
                    raise ValueError('invalid_fingerprint')
                if _canonical(json.loads(record.content_json)) != record.content_json or hashlib.sha256(record.content_json.encode()).hexdigest() != record.content_fingerprint:
                    raise ValueError('content_integrity')
            if record.state in ('pending','claimed','generating') and record.content_fingerprint is not None:
                raise ValueError('premature_content')
            if record.state in ('ready','initializing','unknown','succeeded') and not record.content_fingerprint:
                raise ValueError('missing_content')
            if record.state in ('initializing','unknown','succeeded') and record.dispatch_reservations != 1:
                raise ValueError('missing_reservation')
            if record.dispatch_reservations and record.state not in ('initializing','unknown','succeeded','failed'):
                raise ValueError('invalid_reservation_state')
            if (record.callback_id is None) != (record.result_id is None):
                raise ValueError('invalid_callback_record')
            if record.callback_id is not None:
                _identifier(record.callback_id); _identifier(record.result_id)
                if record.state not in ('succeeded','failed') or record.dispatch_reservations != 1:
                    raise ValueError('invalid_callback_record')
            if record.state == 'succeeded' and record.callback_id is None:
                raise ValueError('missing_callback')
            if intent.key in store._records or record.job_id in store._jobs:
                raise ValueError('duplicate_snapshot_identity')
            store._records[intent.key] = record
            store._jobs.add(record.job_id)
        return store


def recovery(record, owner):
    """Read-only decision. Elapsed time is deliberately not an input."""
    _identifier(owner)
    if record.owner not in (None,owner):
        action = 'blocked_owner'
    else:
        action = {'pending':'claim_only','claimed':'resume_generation_fixture',
                  'generating':'reconcile_saved_script','ready':'reserve_mock_dispatch_only',
                  'initializing':'reconciliation_only','unknown':'reconciliation_only',
                  'succeeded':'terminal_noop','failed':'terminal_failed'}[record.state]
    return {'action':action,'initialize_permitted':False,'auto_resend':False,
            'takeover_permitted':False,'posting_permitted':False,
            'queue_done':record.state=='succeeded' and record.owner==owner}
