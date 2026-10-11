"""Offline contract only. No HTTP client, credentials, environment or live entrypoint."""
ID='provider-neutral-runtime-remote-readonly-inspection-20261011-r1'
ACCOUNT='6c8ccd6aface937ab5dabef61cb64534'
WORKER='plm-serverless-sandbox-control'
DB='18050cf6-934e-4f3a-a1cd-5041bac1c35e'
BUNDLE_SHA='8a6615fd020ca6590ba8f5e2c73a3844473d9e6ecd3babb19ea836d604d4a8a9'
PREFIX='/accounts/'+ACCOUNT+'/workers/scripts/'+WORKER
ENDPOINTS=(PREFIX+'/content/v2',PREFIX+'/settings',PREFIX+'/schedules','/accounts/'+ACCOUNT+'/queues')
def allowed_request(method,path,number):
    return method=='GET' and path in ENDPOINTS and type(number) is int and 1<=number<=4

def metadata_only_bindings(bindings):
    """Never inspect/retain material. Names/type and exact target boolean only."""
    out={'db_binding_exact':False,'secret_names':[],'secret_values_accessed':False}
    for b in bindings:
        if b.get('type')=='d1' and b.get('name')=='DB':out['db_binding_exact']=b.get('id')==DB
        elif b.get('type')=='secret_text' and b.get('name') in ('PLM_YOUTUBE_CHECKPOINT_KEY','PLM_YOUTUBE_RESULT_CALLBACK_KEY','PLM_GITHUB_DISPATCH_TOKEN'):out['secret_names'].append(b['name'])
    out['secret_names']=sorted(set(out['secret_names']))
    return out

def source_comparison(response_sha,bundle_sha,representation_proven):
    # Raw multipart response hashes are not hashes of a bundled JS module.
    if not representation_proven:return 'UNVERIFIED_SOURCE_REPRESENTATION'
    return 'YES' if response_sha==bundle_sha==BUNDLE_SHA else 'NO'

def classify(e):
    if e.get('active') is True:return 'STOP_UNEXPECTED_ACTIVE_RUNTIME'
    required=('exists','source_representation_proven','routes_complete','cron_complete','consumers_complete','binding_exact','parked_proven')
    if not all(e.get(k) is True for k in required):return 'BLOCKED_REMOTE_VISIBILITY'
    if e.get('cron_count')!=0 or e.get('consumer_count')!=0 or e.get('route_count')!=0:return 'STOP_UNEXPECTED_ACTIVE_RUNTIME'
    if e.get('candidate_equal')=='YES':return 'REMOTE_EXACT_PARKED'
    if e.get('candidate_equal')=='NO' and e.get('known_old_parked_source') is True:return 'REMOTE_PARKED_OLD_SOURCE_DEPLOY_PREPARATION_REQUIRED'
    return 'BLOCKED_REMOTE_VISIBILITY'
