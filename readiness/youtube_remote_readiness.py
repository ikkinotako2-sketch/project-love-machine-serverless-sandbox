"""Bounded read-only D1 schema preflight. No deployment, row read or mutation.

Only fixed public source hashes and fixed enums leave this boundary.
The transport is injectable for offline tests; live credentials stay in runner memory.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = 'ikkinotako2-sketch/project-love-machine-serverless-sandbox'
BRANCH = 'plm-offline-readiness-v1-20261002'
PARENT = '28df45cdfcd34b5f57f9e34a334704b593a8264d'
MESSAGE = 'PLM YouTube fresh readonly readiness once 20261006-r1'
ACCOUNT = '6c8ccd6aface937ab5dabef61cb64534'
DB = '18050cf6-934e-4f3a-a1cd-5041bac1c35e'
NAME = 'plm-serverless-sandbox-state'
FLAGS = ('TEST_ONLY', 'DRY_RUN', 'NO_PUBLISH', 'EMERGENCY_STOP')
SQL = "SELECT type, name, tbl_name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
TARGET = f'https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/d1/database/{DB}'
VERIFY = 'https://api.cloudflare.com/client/v4/user/tokens/verify'
MAX_BYTES = 262144


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def classify(schema, catalog):
    """No remote names/SQL are returned, including when unknown objects exist."""
    if not isinstance(schema, list) or len(schema) > 128:
        raise ValueError('SCHEMA_BOUND_REJECTED')
    seen = {}
    for row in schema:
        if not isinstance(row, dict) or set(row) != {'type', 'name', 'tbl_name', 'sql'}:
            raise ValueError('SCHEMA_SHAPE_REJECTED')
        if not all(isinstance(row[k], str) for k in row) or row['name'] in seen:
            raise ValueError('SCHEMA_SHAPE_REJECTED')
        seen[row['name']] = sha(json.dumps(row, sort_keys=True, separators=(',', ':')))
    allowed = set().union(*(set(v) for v in catalog.values()))
    result = {'protected_schema_exact': all(seen.get(k) == v for k, v in catalog['protected'].items()),
              'unknown_objects_count': len(set(seen) - allowed)}
    for label in ('provider_neutral', 'queue_result'):
        expected = catalog[label]
        present = set(expected) & set(seen)
        result[label] = ('NOT_APPLIED' if not present else
                         'FULL_APPLIED' if all(seen.get(k) == v for k, v in expected.items()) else
                         'PARTIAL_OR_DRIFT')
    return result


def pins_valid(plan):
    return all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h
               for p, h in plan['source_sha256'].items())


def audit(env, transport, plan, catalog):
    out = {'readiness': 'UNVERIFIED', 'failure_code': 'READ_CONTEXT_REJECTED',
           'read_only_calls': 0, 'd1_write': 0, 'deploy': 0, 'dispatch': 0,
           'youtube_upload': 0, 'retry': 0, 'raw_retention': 0,
           'live_ready': False, 'execution_approved': False,
           'oauth_current': 'UNVERIFIED', 'account_free_plan': 'UNVERIFIED',
           'account_usage': 'UNVERIFIED', 'worker_current': 'UNVERIFIED'}
    required = {'GITHUB_REPOSITORY': REPO, 'GITHUB_REF': 'refs/heads/' + BRANCH,
                'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_EVENT_NAME': 'push',
                'PLM_READ_BEFORE': PARENT, 'PLM_READ_MESSAGE': MESSAGE}
    if any(env.get(k) != v for k, v in required.items()) or any(env.get(k) != 'true' for k in FLAGS):
        return out
    if not env.get('PLM_CF_D1_READ_TOKEN'):
        out['failure_code'] = 'READ_CREDENTIAL_UNVERIFIED'
        return out
    if not pins_valid(plan):
        out['failure_code'] = 'SOURCE_PIN_DRIFT'
        return out
    # Ignore every other credential: it is never read or forwarded.
    def api(url, query=False):
        if url not in (VERIFY, TARGET, TARGET + '/query') or query != (url == TARGET + '/query'):
            raise ValueError('READ_ROUTE_REJECTED')
        if out['read_only_calls'] >= 3:
            raise ValueError('READ_BUDGET_REJECTED')
        out['read_only_calls'] += 1
        status, body = transport(url, 'POST' if query else 'GET',
                                 json.dumps({'sql': SQL, 'params': []}).encode() if query else None,
                                 env['PLM_CF_D1_READ_TOKEN'])
        if status != 200 or not isinstance(body, bytes) or len(body) > MAX_BYTES:
            raise ValueError('READ_RESPONSE_REJECTED')
        data = json.loads(body)
        if not isinstance(data, dict) or data.get('success') is not True:
            raise ValueError('READ_RESPONSE_REJECTED')
        return data.get('result')
    try:
        verify = api(VERIFY)
        if not isinstance(verify, dict) or verify.get('status') != 'active':
            raise ValueError('READ_TOKEN_UNVERIFIED')
        out['read_token_active'] = True
        meta = api(TARGET)
        if not isinstance(meta, dict) or meta.get('uuid') != DB or meta.get('name') != NAME:
            raise ValueError('READ_TARGET_REJECTED')
        size = meta.get('file_size')
        if type(size) is not int or not 0 <= size <= 5000000000:
            raise ValueError('READ_SIZE_REJECTED')
        out['database_size_bytes'] = size
        q = api(TARGET + '/query', True)
        if not isinstance(q, list) or len(q) != 1 or q[0].get('success') is not True:
            raise ValueError('READ_QUERY_REJECTED')
        qm = q[0].get('meta', {})
        if qm.get('changed_db') is not False or type(qm.get('rows_written')) is not int or qm['rows_written'] != 0:
            raise ValueError('READ_QUERY_REJECTED')
        if qm.get('served_by_primary') is not True:
            raise ValueError('PRIMARY_READ_UNVERIFIED')
        rr = qm.get('rows_read')
        if type(rr) is not int or rr < 0:
            raise ValueError('READ_USAGE_UNVERIFIED')
        out['query_rows_read'] = rr
        out.update(classify(q[0].get('results'), catalog))
        out['readiness'] = 'READ_ONLY_CONFIRMED'
        out['failure_code'] = ('CURRENT_SCHEMA_DRIFT_STOP' if not out['protected_schema_exact'] or out['unknown_objects_count'] or 'PARTIAL_OR_DRIFT' in (out['provider_neutral'], out['queue_result'])
                               else 'LIVE_GATES_UNVERIFIED_STOP')
    except Exception:
        # Exception text, responses and hashes of errors never leave this boundary.
        out['failure_code'] = 'READ_FAILED_UNKNOWN_NO_RETRY'
    return out


def main():
    import os
    import urllib.request
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    opener = urllib.request.build_opener(NoRedirect())
    def transport(url, method, body, token):
        req = urllib.request.Request(url, data=body, method=method,
                                     headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        with opener.open(req, timeout=15) as response:
            return response.status, response.read(MAX_BYTES + 1)
    plan = json.loads((ROOT/'readiness/youtube-live-connection-plan.json').read_text())
    catalog = json.loads((ROOT/'readiness/youtube-readonly-schema-catalog.json').read_text())
    env = {k: os.environ.get(k) for k in (*FLAGS, 'GITHUB_REPOSITORY', 'GITHUB_REF', 'GITHUB_RUN_ATTEMPT',
                                         'GITHUB_EVENT_NAME', 'PLM_READ_BEFORE', 'PLM_READ_MESSAGE', 'PLM_CF_D1_READ_TOKEN')}
    result = audit(env, transport, plan, catalog)
    # Always stop after diagnostics. UNVERIFIED does not authorize migration/deploy.
    print('YOUTUBE_REMOTE_READINESS ' + json.dumps(result, sort_keys=True))
    return 0 if result['readiness'] == 'READ_ONLY_CONFIRMED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
