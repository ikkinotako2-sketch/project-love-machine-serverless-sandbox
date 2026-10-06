"""Data-only bridge from existing validated script/pipeline inputs to upload oracle.

No model/render/dispatch/client invocation. Receipts and readiness are test data;
trusted runtime/secret/quota observations and owner approval remain required live.
"""
from oracle_bridge import require_guard
from one_shot_executor import need
from offline_readiness import script_to_render
from parity import normalize_script, render_payload, pipeline_inputs
import youtube_pipeline_offline as y

def prepare_fixture(theme, script, job_id, flags, quality, files, readiness):
    require_guard()
    need(type(readiness) is dict and set(readiness) ==
         {'oauth_secret_exists','quota_verified','zero_cost_verified','runtime_verified'},
         'READINESS_FIELDS')
    converted=script_to_render(theme,script,'youtube_game_001',job_id,flags)
    payload=render_payload(normalize_script({'output':script}))
    need(payload == converted['render_payload'], 'RENDER_PARITY_MISMATCH')
    inputs=pipeline_inputs(payload,job_id)
    # Legacy parity defaults are fixtures, not audience/disclosure decisions.
    inputs.update(privacy_status='private', scheduled_for='', notify_subscribers=False,
                  made_for_kids=False, contains_synthetic_media=True)
    request={'job_id':job_id,'account_id':'youtube_game_001',
        'idempotency_key':y.digest({'account':'youtube_game_001','job':job_id,
                                   'content':converted['content_fingerprint']}),
        'media_sha256':quality.get('media_sha256'),'video_count':1,
        'privacy_status':'private','notify_subscribers':False,'scheduled_for':None,
        'made_for_kids':False,'contains_synthetic_media':True,
        'flags':dict(flags),**readiness}
    y.validate_contract(request,quality,files)
    return {'request':request,'render_payload':payload,'pipeline_inputs':inputs,
            'live_ready':False,'render_executed':False,'upload_executed':False,
            'mode':'OFFLINE_FIXTURE_ONLY'}
