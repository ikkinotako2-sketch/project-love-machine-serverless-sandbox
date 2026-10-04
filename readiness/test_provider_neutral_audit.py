from oracle_bridge import require_guard
require_guard()
import copy
import hashlib
import json
import sqlite3
import unittest
from pathlib import Path
from offline_readiness import FLAGS
from provider_neutral_generation import (REQUIRED,BUDGET,eligibility,require_eligible,
    checkpoint_fixture,render_input_fixture,uncertain_result)

ROOT=Path(__file__).resolve().parents[1]
def load(name):return json.loads((ROOT/name).read_text())
BEFORE=load('serverless/provider-neutral-backend-before.json')
AFTER=load('serverless/provider-neutral-backend-after.json')
PLAN=load('serverless/generalized-behavior-v3-test-plan.json')
ORACLE=load('serverless/generalized-behavior-v3-offline-oracle.json')
SQL=(ROOT/'serverless/migrations/0008_provider_neutral_roundtrip_backend.sql').read_text()
TABLES=list(AFTER['new']['rows'])

def seed(db,rows):
    for table,entries in rows.items():
        for row in entries:
            names=','.join('"'+k+'"' for k in row)
            db.execute('INSERT INTO '+table+' ('+names+') VALUES ('+','.join('?' for _ in row)+')',list(row.values()))

def fixture(rows=None,new=True):
    db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
    for obj in BEFORE['schema']:
        if obj['type']=='table':db.execute(obj['sql'])
    seed(db,BEFORE['protected_rows'])
    for obj in BEFORE['schema']:
        if obj['type']!='table' and obj['sql']:db.execute(obj['sql'])
    if new:
        # Oracle state hydration occurs before new guard installation, only offline.
        for obj in AFTER['new']['schema']:
            if obj['type']=='table':db.execute(obj['sql'])
        if rows:seed(db,rows)
        for obj in AFTER['new']['schema']:
            if obj['type']=='trigger':db.execute(obj['sql'])
    db.commit();db.execute('PRAGMA foreign_keys=ON')
    return db

def snap(db,tables):
    return {t:sorted([dict(row) for row in db.execute('SELECT * FROM '+t)],key=lambda x:json.dumps(x,sort_keys=True)) for t in tables}

def transform(value):
    if isinstance(value,str):
        return value.replace('plm_rt_v1_','plm_rt_v2_').replace('rt-behavior-20261004-003','rt-neutral-offline-20261004-001').replace('youtube_synthetic_rt_003','youtube_neutral_offline_001').replace('private-roundtrip-behavior-20261004-003','private-neutral-offline-001').replace('synthetic_video_rt_003','synthetic_video_neutral_offline_001') if value!='gemini' else 'offline_provider'
    if isinstance(value,list):return [transform(x) for x in value]
    if isinstance(value,dict):return {transform(k):transform(v) for k,v in value.items()}
    return value

def newrows(rows):
    # Old identities are never seeded into candidate namespace, even offline.
    return {transform(t):[transform(r) for r in rs if r.get('job_id')=='rt-behavior-20261004-003'] for t,rs in rows.items()}

def normalized(rows):return {t:sorted(rs,key=lambda x:json.dumps(x,sort_keys=True)) for t,rs in rows.items()}

class ProviderNeutralMigrationTests(unittest.TestCase):
    def test_exact_raw_pins_and_source_receipt(self):
        for path,sha in load('serverless/provider-neutral-backend-sha256.json').items():
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),sha)
        self.assertEqual(hashlib.sha256((ROOT/BEFORE['source_execution_receipt']).read_bytes()).hexdigest(),BEFORE['source_execution_receipt_sha256'])
        self.assertEqual(AFTER['preserved_before'],BEFORE)
        self.assertTrue(BEFORE['fresh_remote_preflight_required_before_any_future_approval'])

    def test_apply_exact_after_schema_columns_indexes_empty_protected(self):
        db=fixture(new=False);old=snap(db,BEFORE['protected_rows']);db.executescript(SQL)
        schema=[dict(r) for r in db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name")]
        self.assertEqual(schema,AFTER['schema']);self.assertEqual(snap(db,BEFORE['protected_rows']),old)
        self.assertEqual(snap(db,TABLES),AFTER['new']['rows'])
        for t in TABLES:
            self.assertEqual([dict(r) for r in db.execute('PRAGMA table_info('+t+')')],AFTER['new']['columns'][t])
            self.assertEqual([dict(r) for r in db.execute('PRAGMA index_list('+t+')')],AFTER['new']['indexes'][t])
        # Reserved KV content is never queried.
        self.assertEqual(BEFORE['kv_content_status'],'NOT_APPLICABLE_RESERVED_UNQUERYABLE')

    def test_second_apply_fails_without_resume_or_cleanup(self):
        db=fixture();old=snap(db,BEFORE['protected_rows']);schema=list(db.execute('SELECT name,sql FROM sqlite_master'))
        with self.assertRaises(sqlite3.OperationalError):db.executescript(SQL)
        self.assertEqual(snap(db,BEFORE['protected_rows']),old);self.assertEqual(list(db.execute('SELECT name,sql FROM sqlite_master')),schema)

    def test_replay_all_33_candidate_transitions_preserves_all_evidence(self):
        db=fixture();old=snap(db,BEFORE['protected_rows']);logical=applied=noop=0
        for step in PLAN['steps']:
            with self.subTest(step=step['id']):
                self.assertEqual(snap(db,TABLES),normalized(newrows(step['before_rows'])))
                start=db.total_changes
                db.execute(transform(step['sql']),transform(step['params']))
                changed=db.total_changes-start
                self.assertEqual(changed,step['expected']['logical_changes']);logical+=changed
                applied+=changed>0;noop+=changed==0
                self.assertEqual(snap(db,TABLES),normalized(newrows(step['after_rows'])))
                self.assertEqual(snap(db,BEFORE['protected_rows']),old)
        self.assertEqual((applied,noop,logical),(16,17,18));self.assertEqual(sum(map(len,snap(db,TABLES).values())),7)

    def test_provider_identifier_grammar_rejects_bad_values_without_row_change(self):
        step=next(s for s in PLAN['steps'] if s['sql'].startswith('INSERT INTO plm_rt_v1_script'))
        for provider in ('','A','1provider','UPPER','has space','with.dot','bad/route','a'*33,'ab\\n'):
            with self.subTest(provider=provider):
                db=fixture(newrows(step['before_rows']));before=snap(db,TABLES)
                params=transform(step['params']);params[params.index('offline_provider')]=provider
                with self.assertRaises(sqlite3.IntegrityError):db.execute(transform(step['sql']),params)
                self.assertEqual(snap(db,TABLES),before)

    def test_provider_model_and_request_are_immutable_after_start(self):
        step=next(s for s in PLAN['steps'] if any(r.get('state')=='STARTED' for r in s['after_rows']['plm_rt_v1_script']))
        for field,value in [('provider','other_provider'),('model','other-model'),('request_sha256','f'*64)]:
            with self.subTest(field=field):
                db=fixture(newrows(step['after_rows']));before=snap(db,TABLES)
                with self.assertRaisesRegex(sqlite3.IntegrityError,'rt_script_immutable_or_unsent'):
                    db.execute('UPDATE plm_rt_v2_script SET '+field+'=?,version=2,state=\'UNKNOWN\',updated_at=updated_at+1',[value])
                self.assertEqual(snap(db,TABLES),before)

# Candidate exact-SQL oracle: distinct from remote v1 migrated-schema proof.
def oracle_test(case):
    def run(self):
        db=fixture(newrows(case['before_rows']));before=snap(db,TABLES);protected=snap(db,BEFORE['protected_rows'])
        with self.assertRaises(sqlite3.IntegrityError) as error:db.execute(transform(case['sql']),transform(case['params']))
        self.assertEqual(str(error.exception),case['expected_token']);self.assertEqual(snap(db,TABLES),before)
        self.assertEqual(snap(db,BEFORE['protected_rows']),protected)
    return run
for case in ORACLE['cases']:
    setattr(ProviderNeutralMigrationTests,'test_candidate_oracle_'+case['id'],oracle_test(case))

class ProviderEligibilityTests(unittest.TestCase):
    def test_public_audit_has_no_full_pass_or_chosen_provider(self):
        a=load('readiness/AI_PROVIDER_ELIGIBILITY_20261004.json');self.assertEqual(a['decision'],'BLOCKED_NO_COMPLIANT_ZERO_COST_PROVIDER')
        self.assertIsNone(a['primary']);self.assertIsNone(a['fallback']);self.assertFalse(a['credentials_requested'])
        self.assertEqual(len(a['providers']),13)
        for p in a['providers']:self.assertEqual(p['status'],'EXCLUDED_FROM_EXECUTABLE_CANDIDATES')
        self.assertTrue(all(x==0 for x in a['operations'].values()))
        self.assertEqual(a['safety_flags'],dict.fromkeys(FLAGS,True))

    def test_all_mandatory_evidence_must_be_exact_true(self):
        good={**dict.fromkeys(REQUIRED,True),'current_official_evidence':True};self.assertTrue(eligibility(good))
        for k in (*REQUIRED,'current_official_evidence'):
            for value in (None,False,1,'true'):
                with self.subTest(key=k,value=value):bad={**good,k:value};self.assertFalse(eligibility(bad))
        for provider in ('gemini','github_models'):
            with self.assertRaises(ValueError):require_eligible(provider,good)
        for p in ('cloudflare','mistral','huggingface'):
            with self.assertRaises(ValueError):require_eligible(p,{})

    def test_budget_is_six_distinct_calls_not_retry_allowance(self):
        self.assertEqual(BUDGET['distinct_generations_per_day'],6);self.assertEqual(BUDGET['attempts_per_generation'],1)
        for key in BUDGET:
            if key.startswith('automatic_'):self.assertEqual(BUDGET[key],0)

    def test_owner_cleanup_is_only_owner_evidence(self):
        e=load('audit-evidence/generalized-behavior-v3-owner-cleanup-20261004.json')
        self.assertFalse(e['independently_verified']);self.assertTrue(e['read_token_maintained']);self.assertTrue(e['all_three_behavior_identities_permanently_consumed'])

class NeutralCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.fixture=load('readiness/parity_fixture.json');self.flags=dict.fromkeys(FLAGS,True)
        self.script=self.fixture['script_response']['output'];self.raw=json.dumps(self.script,ensure_ascii=False)
    def save(self,**kw):
        return checkpoint_fixture('offline_provider','synthetic-model','a'*64,self.raw,self.fixture['theme'],self.fixture['job_id'],self.flags,**kw)
    def test_json_sha_checkpoint_precedes_render_input(self):
        cp=self.save();r=render_input_fixture(cp,'offline_provider','synthetic-model','a'*64)
        self.assertEqual(r['script'],self.script);self.assertFalse(r['render_executed']);self.assertFalse(cp['live_permitted'])
    def test_saved_checkpoint_never_regenerated(self):
        with self.assertRaises(ValueError):self.save(existing=self.save())
    def test_incomplete_and_ambiguous_never_checkpointed(self):
        for reason in ('length','timeout','ambiguous','filtered',None):
            with self.subTest(reason=reason),self.assertRaises(ValueError):self.save(finish=reason)
    def test_identity_and_sha_drift_prevent_render_input(self):
        cp=self.save()
        for p,m,h in [('other','synthetic-model','a'*64),('offline_provider','other','a'*64),('offline_provider','synthetic-model','b'*64)]:
            with self.assertRaises(ValueError):render_input_fixture(cp,p,m,h)
        cp['script_json']+=' '
        with self.assertRaises(ValueError):render_input_fixture(cp,'offline_provider','synthetic-model','a'*64)
    def test_bad_json_rejected(self):
        bad=['{"title":"a","title":"b"}','NaN','Infinity','1e999','{"x":"\\u0000"}','['*26+'0'+']'*26,'x'*65537,'{"extra":true}']
        for raw in bad:
            with self.subTest(kind=raw[:15]),self.assertRaises((ValueError,KeyError)):
                checkpoint_fixture('offline_provider','synthetic-model','a'*64,raw,self.fixture['theme'],self.fixture['job_id'],self.flags)
    def test_reloaded_checkpoint_schema_is_revalidated_even_with_matching_sha(self):
        cp=self.save();cp['script_json']='{"extra":true}'
        cp['script_sha256']=hashlib.sha256(cp['script_json'].encode()).hexdigest()
        with self.assertRaises(ValueError):render_input_fixture(cp,'offline_provider','synthetic-model','a'*64)
    def test_error_classification_has_no_retry_or_fallback(self):
        for kind in ('timeout','ambiguous','http_error','invalid_json','quota','model_drift'):
            r=uncertain_result(kind);self.assertTrue(all(r[k]==0 for k in ('retry','regenerate','render','upload','fallback')))
