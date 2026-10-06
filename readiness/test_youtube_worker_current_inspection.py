import contextlib
import copy
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from oracle_bridge import require_guard
require_guard()
import youtube_worker_current_inspection as p

ROOT=Path(__file__).resolve().parents[1]
def envelope(result,info=None):
    d={'success':True,'result':result,'unwanted_secret':'never-retain-fixture'}
    if info is not None:d['result_info']=info
    return json.dumps(d).encode()
def queues(rows=None):
    rows=[] if rows is None else rows
    return envelope(rows,{'count':len(rows),'page':1,'per_page':20,'total_count':len(rows),'total_pages':1})
def transport():
    replies=[(200,b'private worker fixture code',{'content_type':'application/javascript'}),(200,envelope({'schedules':[]}),{}),(200,queues(),{})]
    calls=[]
    def get(method,path):calls.append((method,path));return replies[len(calls)-1]
    return get,calls

class WorkerInspectionTests(unittest.TestCase):
    def test_exact_observed_mapping(self):
        self.assertEqual(p.digest(p.KNOWN_PERMISSION.encode()),p.OBSERVED_NAME_HASH)
        self.assertEqual(p.map_worker_permission({'id':p.OBSERVED_GROUP_ID,'name':p.KNOWN_PERMISSION}),p.KNOWN_PERMISSION)
    def test_sanitized_hash_mapping(self):
        self.assertEqual(p.map_worker_permission({'id':p.OBSERVED_GROUP_ID,'unmapped_name_sha256':p.OBSERVED_NAME_HASH}),p.KNOWN_PERMISSION)
    def test_unknown_permission(self):
        for group in ({'id':p.OBSERVED_GROUP_ID,'name':'Workers Unknown Read'},{'id':'other','name':p.KNOWN_PERMISSION},{'id':p.OBSERVED_GROUP_ID,'unmapped_name_sha256':'0'*64}):
            self.assertIsNone(p.map_worker_permission(group))
    def test_candidate_not_endpoint_success(self):
        d={'status':'active','policies':[{'effect':'allow','resource_scope_complete':True,'resources':{'com.cloudflare.api.account.'+p.ACCOUNT:'*'},'permission_groups':[{'id':p.OBSERVED_GROUP_ID,'name':p.KNOWN_PERMISSION}]}]}
        out=p.policy_candidate(d)
        self.assertEqual(out['worker_source'],'READ_CANDIDATE');self.assertEqual(out['endpoint_success'],'UNVERIFIED')
        d['policies'][0]['resources']={'other':'*'}
        self.assertEqual(p.policy_candidate(d)['worker_source'],'UNVERIFIED')
    def test_exact_endpoints(self):
        prefix='/accounts/'+p.ACCOUNT
        self.assertEqual(p.ENDPOINTS,(prefix+'/workers/scripts/'+p.WORKER+'/content/v2',prefix+'/workers/scripts/'+p.WORKER+'/schedules',prefix+'/queues'))
    def test_success_three_gets(self):
        get,calls=transport();out=p.inspect(get)
        self.assertEqual(calls,[('GET',x) for x in p.ENDPOINTS]);self.assertEqual(out['cloudflare_requests'],3)
        self.assertEqual(out['result'],'WORKER_CURRENT_READONLY_INSPECTION_SUCCESS_STOP')
    def test_raw_source_never_logged_or_retained(self):
        get,_=transport();stdout=io.StringIO()
        with contextlib.redirect_stdout(stdout):out=p.inspect(get)
        text=json.dumps(out)
        self.assertEqual(stdout.getvalue(),'');self.assertNotIn('private worker fixture code',text);self.assertNotIn('never-retain-fixture',text)
        self.assertEqual(out['source']['sha256'],p.digest(b'private worker fixture code'))
    def test_source_mime_sanitized(self):
        out=p.source_evidence(b'x',{'content_type':'multipart/form-data; boundary=sensitive-fixture'})
        self.assertEqual(out['content_type'],'multipart/form-data');self.assertNotIn('sensitive-fixture',json.dumps(out))
    def test_max_three(self):
        get,calls=transport();gate=p.ThreeGet(get)
        for path in p.ENDPOINTS:gate.get('GET',path)
        with self.assertRaises(p.Stop):gate.get('GET',p.ENDPOINTS[0])
        self.assertEqual(len(calls),3)
    def test_write_methods_rejected(self):
        for method in ('POST','PUT','PATCH','DELETE'):
            get,calls=transport()
            with self.assertRaises(p.Stop):p.ThreeGet(get).get(method,p.ENDPOINTS[0])
            self.assertEqual(calls,[])
    def test_routes_and_d1_rejected(self):
        for path in ('/zones/fixture/workers/routes','/accounts/'+p.ACCOUNT+'/d1/database'):
            get,calls=transport()
            with self.assertRaises(p.Stop):p.ThreeGet(get).get('GET',path)
            self.assertEqual(calls,[])
    def test_old_content_rejected(self):
        get,calls=transport()
        with self.assertRaises(p.Stop):p.ThreeGet(get).get('GET',p.ENDPOINTS[0].removesuffix('/v2'))
        self.assertEqual(calls,[])
    def test_http_stop_no_retry(self):
        for status in (403,404,301,302,307,308,500):
            calls=[]
            def get(m,path):calls.append(path);return status,b'never-retain-fixture',{}
            out=p.inspect(get);self.assertEqual(len(calls),1);self.assertNotIn('never-retain-fixture',json.dumps(out))
    def test_timeout_latched(self):
        calls=[]
        def get(m,path):calls.append(path);raise TimeoutError('secret-fixture')
        gate=p.ThreeGet(get)
        with self.assertRaisesRegex(p.Stop,'TRANSPORT_UNKNOWN_NO_RETRY'):gate.get('GET',p.ENDPOINTS[0])
        with self.assertRaises(p.Stop):gate.get('GET',p.ENDPOINTS[1])
        self.assertEqual(len(calls),1)
    def test_pagination_incomplete(self):
        for info in (None,{'count':0,'page':1,'per_page':20,'total_count':2,'total_pages':2},{'count':False,'page':1,'per_page':20,'total_count':0,'total_pages':1}):
            with self.assertRaisesRegex(p.Stop,'UNVERIFIED_INCOMPLETE_PAGINATION'):p.queues_evidence(envelope([],info))
    def test_complete_empty_inventory(self):
        out=p.queues_evidence(queues());self.assertEqual(out['queue_count'],0);self.assertEqual(out['consumer_association'],'CONFIRMED_ABSENT')
    def test_consumer_sanitizer(self):
        q={'queue_id':'a'*32,'queue_name':'never-retain-fixture','consumers_total_count':1,'consumers':[{'consumer_id':'b'*32,'type':'worker','script_name':p.WORKER,'settings':{'token':'never-retain-fixture'}}]}
        out=p.queues_evidence(queues([q]));self.assertEqual(out['consumer_association'],'CONFIRMED_PRESENT');self.assertNotIn('never-retain-fixture',json.dumps(out))
    def test_consumer_unknown_not_absent(self):
        out=p.queues_evidence(queues([{'queue_id':'a'*32}]))
        self.assertEqual(out['consumer_association'],'UNVERIFIED')
    def test_schedules_sanitizer(self):
        out=p.schedules_evidence(envelope({'schedules':[{'cron':'*/5 * * * *','token':'never-retain-fixture'}]}))
        self.assertEqual(out['cron_count'],1);self.assertNotIn('never-retain-fixture',json.dumps(out))
    def test_schedules_pagination_stop(self):
        with self.assertRaises(p.Stop):p.schedules_evidence(envelope({'schedules':[]},{}))
    def test_response_bound(self):
        with self.assertRaises(p.Stop):p.source_evidence(b'x'*(p.MAX_BYTES+1),{'content_type':'text/plain'})
        with self.assertRaises(p.Stop):p.decode(b'x'*(p.MAX_BYTES+1))
    def test_duplicate_json_stop(self):
        with self.assertRaises(p.Stop):p.decode(b'{"success":true,"success":true}')
    def test_credential_missing(self):
        for token in (None,'','\r\n'):
            with self.assertRaises(p.Stop):p.live_transport(token)
    def test_transport_redirect_no_follow(self):
        import http.client
        with patch.object(http.client,'HTTPSConnection') as connection:
            response=connection.return_value.getresponse.return_value;response.status=302
            t=p.live_transport('offline-fixture-not-live');out=p.inspect(t)
            self.assertEqual(out['cloudflare_requests'],1);self.assertEqual(connection.call_count,1)
            connection.return_value.close.assert_called_once();response.read.assert_not_called()
    def test_transport_read_bounded(self):
        import http.client
        with patch.object(http.client,'HTTPSConnection') as connection:
            response=connection.return_value.getresponse.return_value;response.status=200
            response.getheader.side_effect=lambda k:'text/plain' if k=='Content-Type' else None
            response.read.return_value=b'x'
            p.live_transport('offline-fixture-not-live')('GET',p.ENDPOINTS[0])
            response.read.assert_called_once_with(p.MAX_BYTES+1)
            args=connection.return_value.request.call_args.args
            self.assertEqual(args,('GET','/client/v4'+p.ENDPOINTS[0]))
    def test_marker_binding(self):
        files={x:(ROOT/x).read_bytes() for x in (p.PLAN,p.WORKFLOW,p.HELPER,p.SCHEMA)}
        plan=json.loads(files[p.PLAN]);before='1'*40
        marker={'identity':p.IDENTITY,'state':'CONSUMED_BEFORE_REMOTE','prepared_commit_sha':before,'plan_sha256':p.digest(files[p.PLAN]),'workflow_sha256':p.digest(files[p.WORKFLOW]),'helper_sha256':p.digest(files[p.HELPER])}
        p.validate_marker(marker,plan,before,files)
        for identity in plan['consumed_identities']:
            bad=dict(marker,identity=identity)
            with self.assertRaises(p.Stop):p.validate_marker(bad,plan,before,files)
        for key in ('prepared_commit_sha','plan_sha256','workflow_sha256','helper_sha256'):
            bad=dict(marker);bad[key]='0'*len(bad[key])
            with self.assertRaises(p.Stop):p.validate_marker(bad,plan,before,files)
    def test_plan_and_marker_absent(self):
        plan=json.loads((ROOT/p.PLAN).read_bytes())
        if (ROOT/p.MARKER).exists():
            consumed=json.loads((ROOT/p.MARKER).read_bytes())
            self.assertEqual(consumed['identity'],p.IDENTITY)
            self.assertEqual(consumed['state'],'CONSUMED_BEFORE_REMOTE')
            self.assertEqual(consumed['prepared_commit_sha'],'95090e18396888e9ee74ec6f46bc431f5ea565cc')
        for k in ('maximum_writes','retry','resume','redirect','pagination_fallback','raw_retention'):self.assertEqual(plan[k],0)
        self.assertEqual(plan['maximum_requests'],3);self.assertEqual(plan['run_attempt'],1)
    def test_workflow_static(self):
        raw=(ROOT/p.WORKFLOW).read_text()
        self.assertIn("on:\n  push:\n",raw)
        self.assertIn("    paths: ['"+p.MARKER+"']",raw)
        self.assertIn("permissions:\n  contents: read\n",raw)
        self.assertIn('github.run_attempt == 1',raw)
        # Workflow uses only this restricted YAML structure; full YAML parse is
        # also performed during local preparation, without adding CI dependencies.
        self.assertIn('    branches: [plm-offline-readiness-v1-20261002]',raw)
        import ast
        for line in raw.splitlines():
            if line.strip().startswith('paths:'):
                self.assertIsInstance(ast.literal_eval(line.split(':',1)[1].strip()),list)
        for text in ('contents: write','pull_request:','schedule:','workflow_call:'):
            self.assertNotIn(text,raw)
        self.assertNotIn('upload-artifact',raw);self.assertNotIn('workflow_dispatch',raw)
        self.assertIn("git('diff','--name-only',before,'HEAD')==MARKER",raw)
        self.assertIn("before+':'+MARKER",raw)

if __name__=='__main__':unittest.main()
