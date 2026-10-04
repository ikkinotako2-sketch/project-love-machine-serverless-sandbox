"""Read-only launch guard. Git marker is primary; run history is secondary.

No writer, reset, retry, resume, media or runtime adapter in this module.
Owner approval is the out-of-band authorization to create the marker-only
commit on the exact reviewed parent, not a timestamp or a self-asserted flag.
"""
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from one_shot_executor import (REPO, PREFLIGHT_ID, RENDER_ID, PREFLIGHT_WORKFLOW,
    RENDER_WORKFLOW, FIXTURE_HASHES, Stop, need, verify_fixture)

BRANCH = 'plm-offline-readiness-v1-20261002'
BASELINE = '5b16c7f826e4db29b9112cbf5849a2c51d0b3120'
ROOT = Path(__file__).resolve().parents[1]
SPEC = {
    PREFLIGHT_ID: ('runtime-preflight', PREFLIGHT_WORKFLOW, 'readiness/cloud-runtime-preflight-policy.json'),
    RENDER_ID: ('actual-render', RENDER_WORKFLOW, 'readiness/one-shot-render-plan.json'),
}
FIELDS = {'identity','kind','approved_parent_sha','workflow_sha256','plan_sha256',
          'fixture_sha256','created_for_once_only','no_retry','no_resume'}
API = 'https://api.github.com/repos/' + REPO


def marker_path(identity):
    need(identity in SPEC, 'MARKER_IDENTITY_MISMATCH')
    return 'audit-evidence/consumed/' + identity + '.json'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def validate_marker(marker, identity, parent, workflow, plan, fixture):
    need(isinstance(marker, dict) and set(marker) == FIELDS, 'MARKER_SCHEMA_MISMATCH')
    kind, _, _ = SPEC[identity]
    expected = dict(identity=identity, kind=kind, approved_parent_sha=parent,
        workflow_sha256=digest(workflow), plan_sha256=digest(plan), fixture_sha256=digest(fixture),
        created_for_once_only=True, no_retry=True, no_resume=True)
    need(marker.get('identity') == identity and marker.get('kind') == kind, 'MARKER_IDENTITY_MISMATCH')
    need(marker.get('approved_parent_sha') == parent, 'APPROVED_PARENT_MISMATCH')
    for field in ('workflow_sha256','plan_sha256','fixture_sha256'):
        need(marker.get(field) == expected[field], field.upper() + '_MISMATCH')
    need(all(marker.get(k) is True for k in ('created_for_once_only','no_retry','no_resume')),
         'MARKER_ONCE_FLAGS_MISMATCH')
    return expected


def pages(fetch, label):
    """Require explicit empty terminal page, immutable sha query and unique SHAs."""
    records, seen = [], set()
    for number in range(1, 101):
        try:
            batch = fetch(number)
        except Exception:
            raise Stop('HISTORY_PAGINATION_FAILURE') from None
        need(isinstance(batch, list) and len(batch) <= 100, 'AMBIGUOUS_HISTORY')
        if not batch:
            return records
        for entry in batch:
            sha = entry.get('sha') if isinstance(entry, dict) else None
            need(isinstance(sha, str) and re.fullmatch('[0-9a-f]{40}', sha) and sha not in seen,
                 'AMBIGUOUS_HISTORY')
            seen.add(sha)
            records.append(entry)
    raise Stop('HISTORY_PAGINATION_LIMIT')


def continuity(records, parent):
    """Every ancestor edge must resolve, including merge parents, through root."""
    graph = {r['sha']: r for r in records}
    need(parent in graph and BASELINE in graph, 'BLOCKED_HISTORY_CONTINUITY_LOST')
    visited, active = set(), set()
    def walk(sha):
        need(sha in graph and sha not in active, 'BLOCKED_HISTORY_CONTINUITY_LOST')
        if sha in visited:
            return
        active.add(sha)
        parents = graph[sha].get('parents')
        need(isinstance(parents, list), 'BLOCKED_HISTORY_CONTINUITY_LOST')
        for p in parents:
            need(isinstance(p, dict) and isinstance(p.get('sha'), str), 'BLOCKED_HISTORY_CONTINUITY_LOST')
            walk(p['sha'])
        active.remove(sha)
        visited.add(sha)
    try:
        walk(parent)
    except RecursionError:
        raise Stop('BLOCKED_HISTORY_CONTINUITY_LOST') from None
    need(visited == set(graph) and BASELINE in visited, 'BLOCKED_HISTORY_CONTINUITY_LOST')
    return visited


def launch_gate(context, commit, marker, parent_marker, history_page, marker_history_page,
                workflow, plan, fixture, branch_tip, *, identity=PREFLIGHT_ID):
    need(context.get('repository') == REPO and context.get('event') == 'push' and
         context.get('branch') == BRANCH, 'UNEXPECTED_BRANCH_OR_EVENT')
    need(type(context.get('run_attempt')) is int and context['run_attempt'] == 1, 'RERUN_REJECTED')
    need(context.get('forced') is False and context.get('deleted') is False and
         context.get('created') is False, 'BLOCKED_HISTORY_CONTINUITY_LOST')
    sha, parent = context.get('sha'), context.get('approved_parent_sha')
    need(all(isinstance(v, str) and re.fullmatch('[0-9a-f]{40}', v) for v in (sha,parent)),
         'APPROVED_PARENT_MISMATCH')
    need(branch_tip == sha, 'BLOCKED_HISTORY_CONTINUITY_LOST')
    need(isinstance(commit, dict) and commit.get('sha') == sha and
         commit.get('parents') == [{'sha': parent}], 'APPROVED_PARENT_MISMATCH')
    files = commit.get('files')
    need(isinstance(files, list) and len(files) == 1 and
         files[0].get('filename') == marker_path(identity) and files[0].get('status') == 'added',
         'MARKER_ONLY_ADDITION_REQUIRED')
    need(parent_marker is None, 'IDENTITY_CONSUMED_PARENT')
    validate_marker(marker, identity, parent, workflow, plan, fixture)
    need(digest(fixture) == FIXTURE_HASHES['render-payload.canonical.json'], 'FIXTURE_HASH_MISMATCH')
    ancestors = continuity(pages(history_page, 'ancestry'), parent)
    prior = pages(marker_history_page, 'marker')
    need(all(r['sha'] in ancestors for r in prior), 'BLOCKED_HISTORY_CONTINUITY_LOST')
    need(not prior, 'IDENTITY_CONSUMED_HISTORY')
    return {'identity': identity, 'consumed': True, 'launch_sha': sha, 'approved_parent_sha': parent,
            'scope': 'AUTOMATION_MONOTONIC_CONSUMPTION', 'allow': True, 'execution_approved': True,
            'no_retry': True, 'no_resume': True, 'admin_immutable': False}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Stop('HISTORY_REDIRECT_STOP')


def read_api(route, *, absent_ok=False):
    # GET only, repository-fixed routes. Never log tokens or response errors.
    need(isinstance(route,str) and route.startswith('/') and not any(c in route for c in ('\n','\r','#')),
         'API_ROUTE_INVALID')
    need(route.startswith(('/commits?', '/commits/', '/git/ref/heads/', '/contents/', '/actions/runs/')),
         'API_ROUTE_INVALID')
    request = urllib.request.Request(API + route, method='GET', headers={
        'Accept':'application/vnd.github+json', 'Authorization':'Bearer ' + os.environ.get('GH_TOKEN',''),
        'User-Agent':'plm-marker-read-only'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
            need(response.status == 200, 'HISTORY_API_FAILURE')
            raw = response.read(8 * 1024 * 1024 + 1)
        need(len(raw) <= 8 * 1024 * 1024, 'HISTORY_API_TOO_LARGE')
        return json.loads(raw)
    except urllib.error.HTTPError as error:
        if absent_ok and error.code == 404:
            return None
        raise Stop('HISTORY_API_FAILURE') from None
    except Exception:
        raise Stop('HISTORY_API_FAILURE') from None


def cloud_launch_guard(env, identity=PREFLIGHT_ID, read=read_api):
    need(env.get('GITHUB_ACTIONS') == 'true' and env.get('RUNNER_ENVIRONMENT') == 'github-hosted' and
         env.get('RUNNER_OS') == 'Linux' and env.get('RUNNER_ARCH') == 'X64', 'CLOUD_RUNNER_REQUIRED')
    try:
        event = json.loads(Path(env['GITHUB_EVENT_PATH']).read_text())
        context = dict(repository=env['GITHUB_REPOSITORY'], event=env['GITHUB_EVENT_NAME'],
            branch=env['GITHUB_REF'].removeprefix('refs/heads/'), sha=env['GITHUB_SHA'],
            approved_parent_sha=event['before'], run_attempt=int(env['GITHUB_RUN_ATTEMPT']),
            forced=event['forced'], deleted=event['deleted'], created=event['created'])
        need(event['after'] == context['sha'] and event['ref'] == env['GITHUB_REF'], 'PUSH_EVENT_MISMATCH')
        # Reject wrong event/branch before any API read.
        need(context['repository'] == REPO and context['event'] == 'push' and context['branch'] == BRANCH,
             'UNEXPECTED_BRANCH_OR_EVENT')
        need(context['run_attempt'] == 1, 'RERUN_REJECTED')
        sha, parent = context['sha'], context['approved_parent_sha']
        need(re.fullmatch('[0-9a-f]{40}',sha) and re.fullmatch('[0-9a-f]{40}',parent), 'PUSH_EVENT_MISMATCH')
        full = read('/commits/' + sha + '?per_page=100&page=1')
        extra = read('/commits/' + sha + '?per_page=100&page=2')
        need(isinstance(extra,dict) and extra.get('files') == [], 'MARKER_ONLY_ADDITION_REQUIRED')
        commit = dict(sha=full['sha'], parents=[{'sha':p['sha']} for p in full['parents']], files=full['files'])
        path = marker_path(identity)
        parent_marker = read('/contents/' + path + '?ref=' + parent, absent_ok=True)
        marker_file = ROOT/path
        need(marker_file.is_file() and not marker_file.is_symlink(), 'MARKER_MISSING')
        marker = json.loads(marker_file.read_text())
        _, wf, plan = SPEC[identity]
        fixture = {name:(ROOT/'readiness/manual_fixture'/name).read_bytes() for name in FIXTURE_HASHES}
        verify_fixture(fixture)
        tip = read('/git/ref/heads/' + BRANCH)['object']['sha']
        receipt = launch_gate(context,commit,marker,parent_marker,
            lambda page:read('/commits?sha='+parent+'&per_page=100&page='+str(page)),
            lambda page:read('/commits?sha='+parent+'&path='+urllib.parse.quote(path,safe='')+
                             '&per_page=100&page='+str(page)),
            (ROOT/wf).read_bytes(),(ROOT/plan).read_bytes(),fixture['render-payload.canonical.json'],tip,
            identity=identity)
        run = read('/actions/runs/' + env['GITHUB_RUN_ID'])
        need(run.get('head_sha') == sha and run.get('event') == 'push' and run.get('run_attempt') == 1 and
             run.get('path') == wf and run.get('head_branch') == BRANCH and
             str(run.get('id')) == env['GITHUB_RUN_ID'] and
             run.get('repository',{}).get('full_name') == REPO, 'SECONDARY_RUN_AUDIT_MISMATCH')
        receipt['run_id'] = int(env['GITHUB_RUN_ID'])
        # Tip must still match after all history/API reads.
        need(read('/git/ref/heads/'+BRANCH)['object']['sha'] == sha, 'BLOCKED_HISTORY_CONTINUITY_LOST')
        return receipt
    except Stop:
        raise
    except Exception:
        raise Stop('AMBIGUOUS_LAUNCH_EVIDENCE') from None


def main():
    try:
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('--identity', choices=tuple(SPEC), default=PREFLIGHT_ID)
        receipt = cloud_launch_guard(os.environ, parser.parse_args().identity)
        print(json.dumps(receipt,sort_keys=True))
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'],'a') as output:
                output.write('allow=true\nexecution_approved=true\n')
    except Stop as error:
        print(str(error))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
