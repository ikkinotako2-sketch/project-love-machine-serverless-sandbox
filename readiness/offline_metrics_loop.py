"""Offline, virtual-time observation/hypothesis/planning reference.

No collectors, clients, timers, claim, dispatch or posting operations. Snapshot
journal replay is not a production durable backend or live metrics proof.
"""
import copy
import hashlib
import json
import math
from datetime import datetime, timezone
from threading import RLock
from dataclasses import asdict
from intent_ledger import Record, PublishIntent, normalize_intent, Conflict
from offline_readiness import FLAGS, _identifier
from monitor import observe_slot
from parity import validate_improvement

SLOTS = {'1h': (3600,10800), '24h': (86400,129600)}
COUNTS = {'views','likes','comments','subscribersGained','subscribersLost'}
NUMBERS = {'averageViewDuration','averageViewPercentage'}
METRIC_KEYS = COUNTS | NUMBERS | {'analytics_available'}
FIXTURE_KEYS = {'platform','account_id','job_id','result_id','slot','evidence_id',
                'revision','observed_at','status','metrics'}
ORIGIN_KEYS = {'platform','account_id','intent_id','job_id','result_id','callback_id',
               'completed_at','content_fingerprint','script_fingerprint','terminal_version','status'}


def _canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',', ':'),allow_nan=False)


def _epoch(value):
    if type(value) is not int or not 0 <= value <= 4102444800:
        raise ValueError('invalid_virtual_time')
    return value


def _iso(epoch):
    return datetime.fromtimestamp(epoch,timezone.utc).isoformat()


def _metrics(value):
    if not isinstance(value,dict) or set(value) - METRIC_KEYS:
        raise ValueError('malformed_metrics')
    for key,item in value.items():
        if item is None: continue
        if key in COUNTS and (type(item) is not int or item < 0):
            raise ValueError('invalid_count')
        if key in NUMBERS and (type(item) not in (int,float) or not math.isfinite(item) or not 0 <= item < 1e9):
            raise ValueError('invalid_metric_number')
        if key == 'analytics_available' and type(item) is not bool:
            raise ValueError('invalid_analytics_flag')
    # Absent values stay null, NEVER fabricate zero/False.
    return {key:value.get(key) for key in sorted(METRIC_KEYS)}


class OfflineMetricsLoop:
    def __init__(self,flags):
        if not isinstance(flags,dict) or set(flags) != set(FLAGS) or any(flags[k] is not True for k in FLAGS):
            raise ValueError('unsafe_flags')
        self._records = {}
        self._lock = RLock()

    def start(self, terminal, completed_at):
        if not isinstance(terminal,Record) or terminal.state != 'succeeded' or terminal.dispatch_reservations != 1:
            raise ValueError('succeeded_terminal_required')
        return self._start_origin({'platform':terminal.intent.platform,'account_id':terminal.intent.account_id,
            'intent_id':terminal.intent.intent_id,'job_id':terminal.job_id,'result_id':terminal.result_id,
            'callback_id':terminal.callback_id,'completed_at':completed_at,'status':'succeeded',
            'content_fingerprint':terminal.content_fingerprint,'script_fingerprint':terminal.script_fingerprint,
            'terminal_version':terminal.version})

    def _start_origin(self,origin):
        if not isinstance(origin,dict) or set(origin) != ORIGIN_KEYS or origin['status'] != 'succeeded':
            raise ValueError('invalid_origin')
        if origin['platform'] != 'youtube' or origin['account_id'] != 'youtube_game_001':
            raise ValueError('one_account_origin_required')
        for key in ('account_id','intent_id','job_id','result_id','callback_id'):
            _identifier(origin[key])
        for key in ('content_fingerprint','script_fingerprint'):
            if not isinstance(origin[key],str) or len(origin[key]) != 64 or any(c not in '0123456789abcdef' for c in origin[key]):
                raise ValueError('invalid_origin_fingerprint')
        if type(origin['terminal_version']) is not int or origin['terminal_version'] < 1:
            raise ValueError('invalid_terminal_version')
        _epoch(origin['completed_at'])
        key = (origin['platform'],origin['account_id'],origin['job_id'])
        with self._lock:
            if key in self._records:
                if self._records[key]['origin'] != origin:
                    raise Conflict('terminal_identity_changed')
                return self._view(self._records[key])
            record = {'origin':copy.deepcopy(origin),'now':origin['completed_at'],
                      'slots':{'1h':None,'24h':None},'history':[],
                      'improvement':None,'candidate':None,'journal':[]}
            self._records[key]=record
            return self._view(record)

    def _clock(self,record,now):
        _epoch(now)
        if now < record['now']:
            raise ValueError('virtual_clock_backwards')

    def tick(self,key,now):
        with self._lock:
            record=self._records[key];self._clock(record,now)
            if now != record['now']:
                record['now']=now;record['journal'].append({'op':'tick','now':now})
            return self._view(record)

    def _view(self,record):
        origin=record['origin'];slots={}
        for slot,(delay,window) in SLOTS.items():
            fixture=record['slots'][slot]
            observation={'status':fixture['status'],'evidence_id':fixture['evidence_id']} if fixture else {}
            due=origin['completed_at']+delay;deadline=origin['completed_at']+window
            state=observe_slot(observation,_iso(deadline),_iso(record['now']))
            slots[slot]={**state,'observation_status':fixture['status'] if fixture else 'pending','due':record['now']>=due,'due_at':due,'deadline_at':deadline,
                         'metrics':_metrics(fixture['metrics']) if fixture and fixture['status']=='collected' else None}
        phase='next_intent_planned' if record['candidate'] else 'improvement_ready' if record['improvement'] else 'metrics_pending'
        return copy.deepcopy({'phase':phase,'origin':origin,'now':record['now'],'slots':slots,
            'improvement':record['improvement'],'next_intent':record['candidate'],
            'claim_permitted':False,'dispatch_permitted':False,'posting_permitted':False})

    def ingest(self,key,fixture,now):
        if not isinstance(fixture,dict) or set(fixture) != FIXTURE_KEYS:
            raise ValueError('invalid_metrics_fixture_fields')
        if not isinstance(fixture['slot'],str) or fixture['slot'] not in SLOTS or fixture['status'] not in ('pending','collected','missed','unknown'):
            raise ValueError('invalid_metrics_state')
        _identifier(fixture['evidence_id'])
        if type(fixture['revision']) is not int or fixture['revision'] < 1:
            raise ValueError('invalid_metrics_revision')
        observed=_epoch(fixture['observed_at'])
        if fixture['status']=='collected': _metrics(fixture['metrics'])
        elif fixture['metrics'] is not None: raise ValueError('metrics_without_collection')
        with self._lock:
            record=self._records[key];self._clock(record,now);origin=record['origin']
            if any(fixture[field] != origin[field] for field in ('platform','account_id','job_id','result_id')):
                raise Conflict('metrics_identity_mismatch')
            if observed > now or observed < origin['completed_at']:
                raise ValueError('invalid_observation_time')
            due,window=SLOTS[fixture['slot']]
            if fixture['status']!='pending' and observed < origin['completed_at']+due:
                raise ValueError('premature_observation')
            if fixture['status']=='missed' and observed <= origin['completed_at']+window:
                raise ValueError('premature_missed_evidence')
            for accepted in record['history']:
                if accepted['evidence_id']==fixture['evidence_id']:
                    if _canonical(accepted)!=_canonical(fixture): raise Conflict('evidence_identity_changed')
                    return self._view(record) # exact replay, no mutation/journal addition
            previous=record['slots'][fixture['slot']]
            if previous:
                if fixture['revision'] <= previous['revision'] or observed < previous['observed_at']:
                    raise Conflict('stale_metrics_fixture')
                if previous['status'] in ('collected','unknown','missed'):
                    raise Conflict('immutable_slot_observation')
            saved=copy.deepcopy(fixture)
            record['slots'][fixture['slot']]=saved;record['history'].append(saved)
            record['now']=now;record['journal'].append({'op':'metrics','now':now,'fixture':saved})
            return self._view(record)

    def improve(self,key,output,now):
        checked=validate_improvement(output) # SAME production 7-item contract
        if checked is None: raise ValueError('invalid_seven_item_improvement')
        safe={'analysis':checked['analysis'],'improvement_actions':checked['improvement_actions']}
        with self._lock:
            record=self._records[key];self._clock(record,now)
            if record['improvement']:
                if record['improvement']['validated_output'] != safe: raise Conflict('immutable_improvement')
                return self._view(record)
            day=record['slots']['24h'];hour=record['slots']['1h']
            if not day or day['status']!='collected': raise Conflict('explicit_24h_evidence_required')
            metrics=_metrics(day['metrics']);earlier=_metrics(hour['metrics']) if hour and hour['status']=='collected' else {}
            views=metrics['views'];enough=type(views) is int and views>=30 # existing rules threshold
            record['improvement']={'method':'offline_fixture','validated_output':copy.deepcopy(safe),
                'hypothesis_only':True,'effect_proven':False,
                'sample_status':'sufficient_for_hypothesis' if enough else 'insufficient_sample',
                'evidence':{'views_24h':views,'views_1h':earlier.get('views'),'sample_sufficient':enough,
                            '1h_evidence_id':hour['evidence_id'] if hour and hour['status']=='collected' else None,
                            '24h_evidence_id':day['evidence_id']}}
            record['now']=now;record['journal'].append({'op':'improve','now':now,'output':copy.deepcopy(safe)})
            return self._view(record)

    def plan_next(self,key,theme,now):
        with self._lock:
            record=self._records[key];self._clock(record,now)
            if not record['improvement']:raise Conflict('improvement_required')
            origin=record['origin']
            identity='next-'+hashlib.sha256(_canonical({k:origin[k] for k in ('platform','account_id','job_id','result_id')}).encode()).hexdigest()[:40]
            candidate=normalize_intent({'source':'schedule','platform':origin['platform'],
                'account_id':origin['account_id'],'intent_id':identity,'theme':theme})
            planned={**asdict(candidate),'status':'planned_only','job_id':None,
                     'basis_job_id':origin['job_id'],
                     'hypothesis_fingerprint':hashlib.sha256(_canonical(record['improvement']).encode()).hexdigest()}
            if record['candidate']:
                if record['candidate'] != planned: raise Conflict('immutable_next_intent')
                return self._view(record)
            record['candidate']=planned;record['now']=now
            record['journal'].append({'op':'plan','now':now,'theme':candidate.theme})
            return self._view(record)

    def snapshot(self):
        with self._lock:
            return _canonical({'format':'offline_metrics_loop_v1','records':[
                {'origin':record['origin'],'journal':record['journal']} for record in self._records.values()]})

    @classmethod
    def restore(cls,snapshot,flags):
        def unique(pairs):
            result={}
            for k,v in pairs:
                if k in result:raise ValueError('duplicate_snapshot_key')
                result[k]=v
            return result
        if not isinstance(snapshot,str) or len(snapshot)>1048576:raise ValueError('invalid_snapshot')
        raw=json.loads(snapshot,object_pairs_hook=unique)
        if not isinstance(raw,dict) or set(raw)!={'format','records'} or raw['format']!='offline_metrics_loop_v1' or not isinstance(raw['records'],list):raise ValueError('invalid_snapshot')
        loop=cls(flags);seen=set()
        for data in raw['records']:
            if not isinstance(data,dict) or set(data)!={'origin','journal'} or not isinstance(data['journal'],list):raise ValueError('invalid_snapshot_record')
            view=loop._start_origin(data['origin']);origin=view['origin']
            key=(origin['platform'],origin['account_id'],origin['job_id'])
            if key in seen:raise ValueError('duplicate_snapshot_origin')
            seen.add(key)
            for op in data['journal']:
                if not isinstance(op,dict):raise ValueError('invalid_journal')
                kind=op.get('op');allowed={'tick':{'op','now'},'metrics':{'op','now','fixture'},'improve':{'op','now','output'},'plan':{'op','now','theme'}}
                if not isinstance(kind,str) or kind not in allowed or set(op)!=allowed[kind]:raise ValueError('invalid_journal')
                if kind=='tick':loop.tick(key,op['now'])
                elif kind=='metrics':loop.ingest(key,op['fixture'],op['now'])
                elif kind=='improve':loop.improve(key,op['output'],op['now'])
                else:loop.plan_next(key,op['theme'],op['now'])
            if _canonical(loop._records[key]['journal']) != _canonical(data['journal']):raise ValueError('noncanonical_replay_journal')
        return loop
