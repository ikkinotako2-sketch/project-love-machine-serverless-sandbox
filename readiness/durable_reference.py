"""Backend-neutral contract/reference hub; NO production database selection.

Independent handles model runners sharing one atomic authority. RLock is NOT
proof of multi-process/remote DB atomicity. Snapshot is restart simulation only.
"""
import copy
import hashlib
import json
from dataclasses import replace, asdict
from threading import RLock
from typing import Protocol
from intent_ledger import Ledger, Conflict, normalize_intent
from checkpoint_e2e import OfflineCheckpointE2E
from offline_metrics_loop import OfflineMetricsLoop
from offline_readiness import FLAGS, _identifier
from generation_contract import canonical, strict_json, unicode_safe, checkpoint_inputs

class DurableStoreContract(Protocol):
    def register(self,entry,mint): ...
    def read(self,key): ...
    def claim(self,key,owner,version): ...
    def transition(self,key,owner,epoch,version,target): ...
    def checkpoint(self,key,owner,epoch,version,script): ...
    def make_ready(self,key,owner,epoch,version): ...
    def reserve(self,key,owner,epoch,version): ...
    def complete_delivery(self,body,completed_at): ...
    def metrics(self,key,owner,epoch,version,fixture,now): ...
    def improvement(self,key,owner,epoch,version,output,now): ...
    def plan_next(self,key,owner,epoch,version,theme,now): ...
    def handoff(self,key,owner,epoch,version,new_owner,evidence): ...
    def audit_trail(self): ...
    def snapshot(self): ...


class ReferenceAuthority:
    def __init__(self,flags):
        self.flags=dict(flags);self.ledger=Ledger(flags);self.loop=OfflineMetricsLoop(flags)
        self.epochs={};self.deliveries={};self.audit=[];self.lock=RLock();self.journal=[]

    def client(self):return ReferenceClient(self)


class ReferenceClient:
    def __init__(self,authority):
        if not isinstance(authority,ReferenceAuthority):raise ValueError('reference_authority_required')
        self.a=authority

    def read(self,key):
        with self.a.lock:
            r=self.a.ledger.read(key)
            return {'record':r,'owner_epoch':self.a.epochs.get(key,0),'backend':'IN_MEMORY_REFERENCE','live_permitted':False}

    def _cas(self,key,owner,epoch,version):
        r=self.a.ledger.read(key)
        if type(epoch) is not int or epoch<1 or self.a.epochs.get(key)!=epoch:raise Conflict('stale_fencing_epoch')
        if r.owner!=owner or type(version) is not int or r.version!=version:raise Conflict('stale_owner_version')
        return r

    def _event(self,key,op,args,before,after):
        # Atomic journal with mutation under the same authority lock.
        self.a.audit.append({'sequence':len(self.a.audit)+1,'operation':op,
            'identity_hash':hashlib.sha256(canonical(list(key)).encode()).hexdigest(),
            'before_version':before,'version':after,'owner_epoch':self.a.epochs.get(key,0)})
        self.a.journal.append({'op':op,'args':copy.deepcopy(args)})

    def register(self,entry,mint):
        unicode_safe(entry);intent=normalize_intent(entry)
        if intent.account_id!='youtube_game_001':raise ValueError('one_account_only')
        with self.a.lock:
            before=len(self.a.ledger._records)
            r=self.a.ledger.register(intent,mint)
            if len(self.a.ledger._records)!=before:
                self.a.epochs[intent.key]=0
                self._event(intent.key,'register',[entry,r.job_id],0,r.version)
            return self.read(intent.key)

    def claim(self,key,owner,version):
        _identifier(owner)
        with self.a.lock:
            r=self.a.ledger.read(key)
            if r.owner==owner:return self.read(key)
            if type(version) is not int or r.version!=version:raise Conflict('stale_version')
            updated=self.a.ledger.claim(key,owner)
            self.a.epochs[key]=1
            self._event(key,'claim',[list(key),owner,version],r.version,updated.version)
            return self.read(key)

    def _core(self,op,key,owner,epoch,version,arg=None):
        with self.a.lock:
            r=self._cas(key,owner,epoch,version)
            e2e=OfflineCheckpointE2E(self.a.flags,self.a.ledger)
            if op=='transition':updated=self.a.ledger.advance(key,owner,version,arg)
            elif op=='checkpoint':
                unicode_safe(arg);updated=e2e.checkpoint(key,owner,version,{'output':arg})
            elif op=='make_ready':
                mapped=checkpoint_inputs(r);updated=self.a.ledger.bind_content(key,owner,version,mapped['render_payload'])
            elif op=='reserve':updated=e2e.reserve(key,owner,version)
            else:raise ValueError('invalid_operation')
            if updated!=r:
                args=[list(key),owner,epoch,version]+([arg] if op in ('transition','checkpoint') else [])
                self._event(key,op,args,r.version,updated.version)
            return self.read(key)

    def transition(self,key,owner,epoch,version,target):return self._core('transition',key,owner,epoch,version,target)
    def checkpoint(self,key,owner,epoch,version,script):return self._core('checkpoint',key,owner,epoch,version,script)
    def make_ready(self,key,owner,epoch,version):return self._core('make_ready',key,owner,epoch,version)
    def reserve(self,key,owner,epoch,version):return self._core('reserve',key,owner,epoch,version)

    def handoff(self,key,owner,epoch,version,new_owner,evidence):
        _identifier(new_owner)
        fields={'mode','stopped_owner','epoch','stop_evidence_id','side_effect_evidence_id','no_inflight','supervisor_approval_id'}
        if not isinstance(evidence,dict) or set(evidence)!=fields or evidence['mode']!='OFFLINE_EVIDENCE':raise ValueError('mock_handoff_evidence_required')
        for name in ('stop_evidence_id','side_effect_evidence_id','supervisor_approval_id'):_identifier(evidence[name])
        with self.a.lock:
            r=self._cas(key,owner,epoch,version)
            if (new_owner==owner or evidence['stopped_owner']!=owner or type(evidence['epoch']) is not int or evidence['epoch']!=epoch or evidence['no_inflight'] is not True):raise Conflict('unsafe_handoff_evidence')
            if r.state not in ('claimed','generating','ready') or r.dispatch_reservations or (r.state=='generating' and not r.script_checkpoint_json):raise Conflict('inflight_or_unknown_handoff_forbidden')
            updated=replace(r,owner=new_owner,version=r.version+1)
            self.a.ledger._records[key]=updated;self.a.epochs[key]=epoch+1
            self._event(key,'handoff',[list(key),owner,epoch,version,new_owner,evidence],r.version,updated.version)
            return self.read(key)

    def complete_delivery(self,body,completed_at):
        """Verified MOCK envelope body only; replay+terminal+audit atomic in hub.

        NOT a public endpoint. Production must commit replay and result in ONE
        backend transaction and verify fencing at every side-effect boundary.
        """
        from callback_boundary import validate_body
        validate_body(body)
        key=(body['platform'],body['account_id'],body['intent_id'])
        with self.a.lock:
            r=self.a.ledger.read(key)
            if r.job_id!=body['job_id'] or r.owner!=body['owner'] or self.a.epochs[key]!=body['owner_epoch']:raise Conflict('callback_identity_or_epoch')
            delivery_key=(body['platform'],body['account_id'],body['delivery_id'])
            digest=hashlib.sha256(canonical(body).encode()).hexdigest()
            prior=self.a.deliveries.get(delivery_key)
            if prior is not None:
                if prior!=digest:raise Conflict('delivery_replay_changed')
                return self.read(key)
            # Validate time and origin before any mutation using a cloned loop.
            updated=self.a.ledger.callback(key,body['owner'],body['version'],body['delivery_id'],body['result_id'],body['outcome'])
            try:
                loop=OfflineMetricsLoop.restore(self.a.loop.snapshot(),self.a.flags)
                if updated.state=='succeeded':loop.start(updated,completed_at)
            except Exception:
                self.a.ledger._records[key]=r
                raise
            self.a.loop=loop;self.a.deliveries[delivery_key]=digest
            self._event(key,'complete_delivery',[body,completed_at],r.version,updated.version)
            return self.read(key)

    def _loop_update(self,op,key,owner,epoch,version,arg,now):
        with self.a.lock:
            unicode_safe(arg)
            r=self._cas(key,owner,epoch,version)
            if r.state!='succeeded':raise Conflict('successful_terminal_required')
            loop=OfflineMetricsLoop.restore(self.a.loop.snapshot(),self.a.flags)
            before=loop.snapshot();loopkey=(r.intent.platform,r.intent.account_id,r.job_id)
            fn={'metrics':loop.ingest,'improvement':loop.improve,'plan_next':loop.plan_next}[op]
            view=fn(loopkey,arg,now)
            if loop.snapshot()!=before:
                updated=replace(r,version=r.version+1)
                self.a.ledger._records[key]=updated;self.a.loop=loop
                self._event(key,op,[list(key),owner,epoch,version,arg,now],r.version,updated.version)
            return {**self.read(key),'loop':view}

    def metrics(self,key,owner,epoch,version,fixture,now):return self._loop_update('metrics',key,owner,epoch,version,fixture,now)
    def improvement(self,key,owner,epoch,version,output,now):return self._loop_update('improvement',key,owner,epoch,version,output,now)
    def plan_next(self,key,owner,epoch,version,theme,now):return self._loop_update('plan_next',key,owner,epoch,version,theme,now)

    def audit_trail(self):
        with self.a.lock:return copy.deepcopy(self.a.audit)

    def snapshot(self):
        with self.a.lock:return canonical({'format':'neutral_reference_v1','journal':self.a.journal})

    @classmethod
    def restore(cls,snapshot,flags):
        raw=strict_json(snapshot,1048576)
        if not isinstance(raw,dict) or set(raw)!={'format','journal'} or raw['format']!='neutral_reference_v1' or not isinstance(raw['journal'],list):raise ValueError('invalid_store_snapshot')
        client=ReferenceAuthority(flags).client()
        for event in raw['journal']:
            if not isinstance(event,dict) or set(event)!={'op','args'} or not isinstance(event['args'],list):raise ValueError('invalid_store_journal')
            op=event['op'];args=copy.deepcopy(event['args'])
            if op=='register':
                if len(args)!=2:raise ValueError('invalid_register_journal')
                client.register(args[0],lambda:args[1])
            elif op in ('claim','transition','checkpoint','make_ready','reserve','handoff','metrics','improvement','plan_next'):
                args[0]=tuple(args[0]);getattr(client,op)(*args)
            elif op=='complete_delivery':client.complete_delivery(*args)
            else:raise ValueError('unsafe_journal_operation')
        if client.snapshot()!=canonical(raw):raise ValueError('noncanonical_store_journal')
        return client
