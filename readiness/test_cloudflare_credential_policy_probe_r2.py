from oracle_bridge import require_guard
require_guard()
import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import cloudflare_credential_policy_probe_r2 as p

ID='a'*32
FIXTURE='PUBLIC_FIXTURE_ONLY_NEVER_A_LIVE_CREDENTIAL'
def response(result):return json.dumps({'success':True,'result':result}).encode()
def details(name='Workers Scripts Read',account=p.ACCOUNT):
    return {'id':ID,'status':'active','value':FIXTURE,'policies':[{'effect':'allow','permission_groups':[{'id':'b'*32,'name':name,'secret':FIXTURE}],'resources':{'com.cloudflare.api.account.'+account:'*'}}]}
def transport(responses,calls):
    def get(method,path):calls.append((method,path));return responses[len(calls)-1]
    return get

class PolicyProbeR2Tests(unittest.TestCase):
    def test_account_two_get_exact_binding(self):
        calls=[];out=p.probe('ACCOUNT_OWNED',transport([(200,response({'id':ID,'status':'active','value':FIXTURE})),(200,response(details()))],calls))
        self.assertEqual(calls,[('GET','/accounts/'+p.ACCOUNT+'/tokens/verify'),('GET','/accounts/'+p.ACCOUNT+'/tokens/'+ID)])
        self.assertEqual(out['cloudflare_requests'],2);self.assertEqual(out['maximum_writes'],0)
    def test_user_root_only_no_account_fallback(self):
        calls=[];out=p.probe('USER',transport([],calls));self.assertEqual(calls,[]);self.assertEqual(out['result'],'TOKEN_TYPE_UNVERIFIED')
    def test_type_ambiguity_zero_requests(self):
        calls=[];out=p.probe('UNVERIFIED',transport([],calls));self.assertEqual(out['result'],'TOKEN_TYPE_UNVERIFIED');self.assertEqual(calls,[])
    def test_details_403_safe_result(self):
        calls=[];out=p.probe('ACCOUNT_OWNED',transport([(200,response({'id':ID,'status':'active'})),(403,b'raw secret '+FIXTURE.encode())],calls))
        self.assertEqual(out['result'],'TOKEN_POLICY_METADATA_NOT_READABLE_WITH_CURRENT_CREDENTIAL');self.assertEqual(len(calls),2)
        self.assertNotIn(FIXTURE,json.dumps(out))
    def test_details_404_no_fallback(self):
        calls=[];out=p.probe('ACCOUNT_OWNED',transport([(200,response({'id':ID,'status':'active'})),(404,b'')],calls));self.assertEqual(out['result'],'TOKEN_ENDPOINT_404_NO_FALLBACK');self.assertEqual(len(calls),2)
    def test_only_get(self):
        gate=p.TwoGet('ACCOUNT_OWNED',lambda *_:self.fail('transport reached'))
        for method in ('POST','PUT','PATCH','DELETE'):
            with self.assertRaises(p.Stop):gate.get(method,gate.root+'/verify')
        self.assertEqual(gate.count,0)
    def test_max_two_and_no_arbitrary_id(self):
        calls=[];gate=p.TwoGet('ACCOUNT_OWNED',transport([(200,response({'id':ID,'status':'active'})),(200,response(details()))],calls))
        gate.get('GET',gate.root+'/verify')
        with self.assertRaises(p.Stop):gate.get('GET',gate.root+'/'+'c'*32)
        gate.get('GET',gate.root+'/'+ID)
        with self.assertRaises(p.Stop):gate.get('GET',gate.root+'/'+ID)
        self.assertEqual(len(calls),2)
    def test_result_id_mismatch_stop(self):
        d=details();d['id']='c'*32
        with self.assertRaisesRegex(p.Stop,'TOKEN_ID_BINDING'):p.sanitize_details(d,ID)
    def test_secret_never_logged_or_retained(self):
        calls=[];buf=io.StringIO()
        with contextlib.redirect_stdout(buf):out=p.probe('ACCOUNT_OWNED',transport([(200,response({'id':ID,'status':'active','secret':FIXTURE})),(200,response(details()))],calls))
        encoded=json.dumps(out)
        self.assertEqual(buf.getvalue(),'');self.assertNotIn(FIXTURE,encoded);self.assertNotIn('secret',encoded);self.assertNotIn('value',encoded)
    def test_unmapped_group_name_only_hash_retained(self):
        result=p.sanitize_details(details(FIXTURE),ID);self.assertNotIn(FIXTURE,json.dumps(result));self.assertIn('unmapped_name_sha256',json.dumps(result))
    def test_permission_parser_worker_and_queue(self):
        out=p.evaluate(p.sanitize_details(details(),ID));self.assertEqual(out['worker_source'],'POLICY_READ_CAPABILITY_CONFIRMED');self.assertEqual(out['queues'],'POLICY_READ_CAPABILITY_CONFIRMED')
    def test_queue_read_does_not_grant_worker(self):
        out=p.evaluate(p.sanitize_details(details('Queues Read'),ID));self.assertEqual(out['queues'],'POLICY_READ_CAPABILITY_CONFIRMED');self.assertIn('UNVERIFIED',out['worker_source'])
    def test_exact_account_scope(self):
        out=p.evaluate(p.sanitize_details(details(account='c'*32),ID));self.assertIn('UNVERIFIED',out['worker_source'])
    def test_unknown_scope_and_deny_never_pass(self):
        for effect,scope in [('deny',{'com.cloudflare.api.account.'+p.ACCOUNT:'*'}),('allow',{'worker-secret-selector':FIXTURE})]:
            d=details();d['policies'][0].update(effect=effect,resources=scope)
            safe=p.sanitize_details(d,ID);self.assertNotIn(FIXTURE,json.dumps(safe));self.assertIn('UNVERIFIED',p.evaluate(safe)['worker_source'])
    def test_routes_no_zone_guess_and_d1_separate(self):
        out=p.evaluate(p.sanitize_details(details('Workers Routes Read'),ID));self.assertEqual(out['routes'],'UNVERIFIED_ZONE_ID_OR_PERMISSION');self.assertEqual(out['d1'],'SEPARATE_EXISTING_EVIDENCE_NOT_EVALUATED')
    def test_redirect_no_follow(self):
        calls=[];out=p.probe('ACCOUNT_OWNED',transport([(302,b'')],calls));self.assertEqual(out['result'],'HTTP_STATUS_STOP');self.assertEqual(len(calls),1)
    def test_timeout_unknown_no_retry(self):
        calls=[]
        def fail(method,path):calls.append(path);raise TimeoutError(FIXTURE)
        out=p.probe('ACCOUNT_OWNED',fail);self.assertEqual(len(calls),1);self.assertNotIn(FIXTURE,json.dumps(out));self.assertEqual(out['result'],'TRANSPORT_UNKNOWN_NO_RETRY')
    def test_response_limit(self):
        calls=[];out=p.probe('ACCOUNT_OWNED',transport([(200,b' '*262145)],calls));self.assertEqual(out['result'],'RESPONSE_LIMIT_STOP')
    def test_no_pagination(self):
        data={'success':True,'result':{'id':ID,'status':'active'},'result_info':{'page':1,'total_pages':2}}
        out=p.probe('ACCOUNT_OWNED',lambda *_:(200,json.dumps(data).encode()));self.assertEqual(out['result'],'UNEXPECTED_PAGINATION_STOP');self.assertEqual(out['cloudflare_requests'],1)
    def test_duplicate_json_stop(self):
        with self.assertRaises(p.Stop):p.decode(b'{"id":1,"id":2}')
    def test_marker_hash_and_schema_fail_closed(self):
        root=Path(__file__).resolve().parents[1]
        files={name:(root/name).read_bytes() for name in (p.PLAN,p.WORKFLOW,'readiness/cloudflare_credential_policy_probe_r2.py',p.SCHEMA)}
        plan=json.loads(files[p.PLAN]);before='d'*40
        marker={'identity':p.IDENTITY,'state':'CONSUMED_BEFORE_REMOTE','prepared_commit_sha':before,**{k:p.digest(files[n]) for k,n in [('plan_sha256',p.PLAN),('workflow_sha256',p.WORKFLOW),('helper_sha256','readiness/cloudflare_credential_policy_probe_r2.py')]}}
        p.validate_marker(marker,plan,before,files)
        bad=dict(marker,extra=FIXTURE)
        with self.assertRaises(p.Stop):p.validate_marker(bad,plan,before,files)
        bad=dict(marker,helper_sha256='0'*64)
        with self.assertRaises(p.Stop):p.validate_marker(bad,plan,before,files)
        if (root/p.MARKER).exists():
            consumed=json.loads((root/p.MARKER).read_bytes())
            self.assertEqual(consumed['identity'],p.IDENTITY)
            self.assertEqual(consumed['state'],'CONSUMED_BEFORE_REMOTE')
    def test_workflow_cannot_launch_on_preparation_push(self):
        root=Path(__file__).resolve().parents[1];text=(root/p.WORKFLOW).read_text()
        self.assertIn("paths: ['"+p.MARKER+"']",text);self.assertNotIn('workflow_dispatch:',text)
        self.assertIn('github.run_attempt == 1',text);self.assertIn("before+':'+MARKER",text)

    def test_exact_r2_identity_and_parent(self):
        self.assertEqual(p.IDENTITY,'youtube-cloudflare-credential-policy-readonly-20261006-r2')
        self.assertEqual(p.PARENT,'a998f9e5bff137dfe2e3843ff081b862fd24e484')
    def test_missing_credential_safe_reason_zero_network(self):
        with self.assertRaisesRegex(p.Stop,'CREDENTIAL_MISSING_STOP'):p.live_transport(None)
    def test_granular_scope_never_guessed(self):
        d=details('Content Read-Only');d['policies'][0]['resources']={'unrecognized-worker-resource':'*'}
        out=p.evaluate(p.sanitize_details(d,ID))
        self.assertIn('UNVERIFIED',out['worker_source'])
    def test_r1_marker_rejected_without_remote(self):
        root=Path(__file__).resolve().parents[1]
        files={n:(root/n).read_bytes() for n in (p.PLAN,p.WORKFLOW,'readiness/cloudflare_credential_policy_probe_r2.py',p.SCHEMA)}
        plan=json.loads(files[p.PLAN]);before='d'*40
        marker={'identity':'youtube-cloudflare-credential-policy-readonly-20261006-r1','state':'CONSUMED_BEFORE_REMOTE','prepared_commit_sha':before,'plan_sha256':'0'*64,'workflow_sha256':'0'*64,'helper_sha256':'0'*64}
        with self.assertRaisesRegex(p.Stop,'MARKER_BINDING_STOP'):p.validate_marker(marker,plan,before,files)
    def test_schema_pin_rejected_if_modified(self):
        root=Path(__file__).resolve().parents[1]
        files={n:(root/n).read_bytes() for n in (p.PLAN,p.WORKFLOW,'readiness/cloudflare_credential_policy_probe_r2.py',p.SCHEMA)}
        plan=json.loads(files[p.PLAN]);before='d'*40
        marker={'identity':p.IDENTITY,'state':'CONSUMED_BEFORE_REMOTE','prepared_commit_sha':before,**{k:p.digest(files[n]) for k,n in [('plan_sha256',p.PLAN),('workflow_sha256',p.WORKFLOW),('helper_sha256','readiness/cloudflare_credential_policy_probe_r2.py')]}}
        files[p.SCHEMA]+=b' '
        with self.assertRaisesRegex(p.Stop,'MARKER_SCHEMA_HASH_STOP'):p.validate_marker(marker,plan,before,files)

    def test_inactive_verify_stops_after_one(self):
        calls=[];out=p.probe('ACCOUNT_OWNED',transport([(200,response({'id':ID,'status':'disabled'}))],calls))
        self.assertEqual(out['result'],'TOKEN_NOT_ACTIVE_STOP');self.assertEqual(len(calls),1)
    def test_inactive_details_stops_without_retry(self):
        calls=[];d=details();d['status']='expired'
        out=p.probe('ACCOUNT_OWNED',transport([(200,response({'id':ID,'status':'active'})),(200,response(d))],calls))
        self.assertEqual(out['result'],'TOKEN_NOT_ACTIVE_STOP');self.assertEqual(len(calls),2)
    def test_plan_limit_drift_stops(self):
        root=Path(__file__).resolve().parents[1]
        files={n:(root/n).read_bytes() for n in (p.PLAN,p.WORKFLOW,'readiness/cloudflare_credential_policy_probe_r2.py',p.SCHEMA)}
        plan=json.loads(files[p.PLAN]);before='d'*40
        marker={'identity':p.IDENTITY,'state':'CONSUMED_BEFORE_REMOTE','prepared_commit_sha':before,**{k:p.digest(files[n]) for k,n in [('plan_sha256',p.PLAN),('workflow_sha256',p.WORKFLOW),('helper_sha256','readiness/cloudflare_credential_policy_probe_r2.py')]}}
        for key,value in [('maximum_requests',3),('maximum_writes',1),('retry',1),('resume',1),('redirect',1),('raw_retention',1),('pagination',True)]:
            bad=dict(plan);bad[key]=value
            with self.assertRaisesRegex(p.Stop,'PLAN_LIMITS_STOP'):p.validate_marker(marker,bad,before,files)

if __name__=='__main__':unittest.main()
