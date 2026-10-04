from oracle_bridge import require_guard
require_guard()
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import one_shot_executor as executor
import cloud_runtime_preflight as cloud

ROOT = Path(__file__).resolve().parents[1]
SHA = 'a' * 40


def context(**changes):
    values = dict(run_id=101, workflow_id=501, run_attempt=1, run_number=1,
                  identity=executor.RENDER_ID, path=executor.RENDER_WORKFLOW, head_sha=SHA)
    values.update(changes)
    return executor.RunContext(**values)


def record(ctx=None, **changes):
    ctx = ctx or context()
    value = dict(id=ctx.run_id, workflow_id=ctx.workflow_id, path=ctx.path,
                 run_attempt=ctx.run_attempt, run_number=ctx.run_number,
                 head_sha=ctx.head_sha, event=ctx.event, repository={'full_name': executor.REPO},
                 status='in_progress', conclusion=None)
    value.update(changes)
    return value


def current_page(ctx=None):
    return {'total_count': 1, 'workflow_runs': [record(ctx)]}


def observed():
    return {'runner': 'github-hosted', 'os': 'ubuntu-24.04', 'architecture': 'amd64',
            **executor.RUNTIME_VERSIONS, 'ffmpeg_version': '6.1.1', 'ffprobe_version': '6.1.1',
            'filters': sorted(executor.FILTERS), 'encoders': sorted(executor.ENCODERS),
            'font_family': 'Noto Sans CJK JP', 'font_verified': True, 'docker_available': True,
            'libav_candidate_versions_match': True,
            'codec_dependency_lock_verified': True, 'package_versions': {'ffmpeg': '7:6.1.1-3ubuntu5'}}


def quality():
    return {'mp4_exists': True, 'bytes': 20000, 'video_stream': True, 'audio_stream': True,
            'width': 1080, 'height': 1920, 'fps': '30/1', 'duration': 24,
            'captions_file_exists': True, 'captions': 'Dialogue: 0,in memory only',
            'max_yavg': 30, 'mean_volume_db': -20}


def speakers():
    return [{'name': 'ずんだもん', 'styles': [{'id': 1, 'name': 'あまあま'}]}]


def registry():
    return {'name': 'cpu-amd64-ubuntu24.04-0.25.2', 'digest': executor.INDEX_DIGEST,
            'images': [{'os': 'linux', 'architecture': 'amd64', 'digest': executor.IMAGE_DIGEST},
                       {'os': 'unknown', 'architecture': 'unknown', 'digest': 'sha256:' + 'b' * 64}]}


class FakeEffects:
    """Only reads existing text and returns in-memory observations. No media."""
    def __init__(self):
        source = json.loads((ROOT / 'readiness/one-shot-render-sources.json').read_text())['sources']
        self.data = {
            'history_page': current_page(),
            'billing_evidence': json.loads((ROOT / 'readiness/owner-billing-evidence-20261004.json').read_text()),
            'fixture_bytes': {name: (ROOT / 'readiness/manual_fixture' / name).read_bytes()
                              for name in executor.FIXTURE_HASHES},
            'production_checkout': (executor.PRODUCTION_SHA,
                                    {name: source[name].encode() for name in executor.SOURCE_HASHES}),
            'image_metadata': {'reference': executor.IMAGE, 'manifest_digest': executor.IMAGE_DIGEST,
                               'os': 'linux', 'architecture': 'amd64'},
            'runtime_binaries': observed(), 'container_start': True, 'version_get': '0.25.2',
            'speakers_get': speakers(), 'synthesis': True, 'encode': True, 'quality': quality(),
            'artifact_sizes': {'short.mp4': 20000, 'payload_snapshot.json': 2000, 'render-result.json': 1000},
            'upload': True,
        }
        self.calls = []
        self.fail = None

    def __call__(self, stage, *args):
        self.calls.append((stage, args))
        if stage == self.fail:
            raise TimeoutError('fake unknown; do not save arbitrary body')
        return copy.deepcopy(self.data[stage])


class HistoryTests(unittest.TestCase):
    def test_first_run_accepted_as_offline_history_candidate(self):
        r = executor.history_gate(context(), lambda p: current_page())
        self.assertTrue(r['consumed'])
        self.assertFalse(r['permanent_ledger_proven'])

    def test_current_run_only_history_accepted(self):
        self.assertEqual(executor.history_gate(context(), lambda p: current_page())['run_id'], 101)

    def test_second_independent_run_rejected_even_deleted_history(self):
        ctx = context(run_id=102, run_number=2)
        with self.assertRaisesRegex(executor.Stop, 'CONSUMED_RUN_NUMBER'):
            executor.history_gate(ctx, lambda p: current_page(ctx))

    def test_rerun_attempt_rejected_before_api(self):
        calls = []
        with self.assertRaisesRegex(executor.Stop, 'RERUN_REJECTED'):
            executor.history_gate(context(run_attempt=2), lambda p: calls.append(p))
        self.assertEqual(calls, [])

    def test_pagination_reads_all_pages_and_prior_consumes(self):
        calls = []
        pages = {1: {'total_count': 2, 'workflow_runs': [record()]},
                 2: {'total_count': 2, 'workflow_runs': [record(id=99)]}}
        def fetch(page):
            calls.append(page)
            return pages[page]
        with self.assertRaisesRegex(executor.Stop, 'CONSUMED_PRIOR_RUN'):
            executor.history_gate(context(), fetch)
        self.assertEqual(calls, [1, 2])

    def test_history_api_failure_no_retry(self):
        calls = []
        def fetch(page):
            calls.append(page)
            raise RuntimeError('fake network failure')
        with self.assertRaisesRegex(executor.Stop, 'HISTORY_API_FAILURE'):
            executor.history_gate(context(), fetch)
        self.assertEqual(calls, [1])

    def test_history_page_limit_stops_bounded(self):
        calls = []
        def fetch(page):
            calls.append(page)
            return {'total_count': 21, 'workflow_runs': [record(id=page)]}
        with self.assertRaisesRegex(executor.Stop, 'HISTORY_PAGE_LIMIT'):
            executor.history_gate(context(), fetch)
        self.assertEqual(len(calls), 20)

    def test_mutable_history_never_proves_permanent_consumption(self):
        with self.assertRaisesRegex(executor.Stop, 'RENDER_NOT_APPROVED_RUNTIME_METADATA_REQUIRED'):
            executor.live_render_gate()

    def test_history_total_changes_between_pages_stop(self):
        pages = {1: {'total_count': 2, 'workflow_runs': [record()]},
                 2: {'total_count': 1, 'workflow_runs': [record(id=99)]}}
        with self.assertRaisesRegex(executor.Stop, 'HISTORY_CHANGED_DURING_SCAN'):
            executor.history_gate(context(), lambda page: pages[page])


def prior_test(conclusion):
    def test(self):
        prior = record(id=99, status='completed', conclusion=conclusion)
        with self.assertRaisesRegex(executor.Stop, 'CONSUMED_PRIOR_RUN'):
            executor.history_gate(context(), lambda p: {'total_count': 2, 'workflow_runs': [record(), prior]})
    return test


for name in ('cancelled', 'failure', 'success', 'timed_out', 'skipped', None):
    setattr(HistoryTests, 'test_prior_' + str(name) + '_consumes', prior_test(name))


def bad_history_test(value):
    def test(self):
        with self.assertRaises(executor.Stop):
            executor.history_gate(context(), lambda p: copy.deepcopy(value))
    return test


for name, value in {
    'empty': {'total_count': 0, 'workflow_runs': []},
    'missing_fields': {},
    'duplicate': {'total_count': 2, 'workflow_runs': [record(), record()]},
    'unknown_current': {'total_count': 1, 'workflow_runs': [record(id=77)]},
    'wrong_workflow': {'total_count': 1, 'workflow_runs': [record(workflow_id=9)]},
    'wrong_path': {'total_count': 1, 'workflow_runs': [record(path='other.yml')]},
    'wrong_sha': {'total_count': 1, 'workflow_runs': [record(head_sha='b' * 40)]},
    'missing_attempt': {'total_count': 1, 'workflow_runs': [record(run_attempt=None)]},
    'total_overflow': {'total_count': 0, 'workflow_runs': [record()]},
    'incomplete': {'total_count': 2, 'workflow_runs': []},
}.items():
    setattr(HistoryTests, 'test_ambiguous_history_' + name + '_stop', bad_history_test(value))


class ExecutorTests(unittest.TestCase):
    def test_offline_order_all_bounds_and_safe_receipt(self):
        fake = FakeEffects()
        runner = executor.OfflineExecutor(context(), fake)
        receipt = runner.execute()
        self.assertEqual([x[0] for x in fake.calls], [
            'history_page', 'billing_evidence', 'fixture_bytes', 'production_checkout', 'image_metadata',
            'runtime_binaries', 'container_start', 'version_get', 'speakers_get', 'synthesis', 'encode',
            'quality', 'artifact_sizes', 'upload'])
        self.assertEqual(runner.attempts, {'synthesis': 1, 'encode': 1, 'upload': 1})
        self.assertEqual(receipt['actual_operations'], 0)
        self.assertIn('NOT_LIVE_READY', receipt['status'])
        bounds = fake.calls[-1][1][0]
        self.assertEqual(bounds['retention_days'], 1)
        self.assertEqual(bounds['retry'], 0)
        self.assertNotIn('narration', json.dumps(receipt))

    def test_same_executor_cannot_resume_after_failure(self):
        fake = FakeEffects(); fake.fail = 'synthesis'
        runner = executor.OfflineExecutor(context(), fake)
        with self.assertRaises(executor.Stop): runner.execute()
        count = len(fake.calls)
        with self.assertRaisesRegex(executor.Stop, 'ALREADY_CONSUMED'): runner.execute()
        self.assertEqual(len(fake.calls), count)
        self.assertEqual(runner.attempts, {'synthesis': 1, 'encode': 0, 'upload': 0})

    def test_identity_mismatch_stops_all_effects(self):
        fake = FakeEffects()
        with self.assertRaisesRegex(executor.Stop, 'IDENTITY_MISMATCH'):
            executor.OfflineExecutor(context(identity='other'), fake).execute()
        self.assertEqual(fake.calls, [])

    def test_fixture_hash_mismatch_before_checkout(self):
        fake = FakeEffects(); fake.data['fixture_bytes']['script.canonical.json'] += b' '
        with self.assertRaisesRegex(executor.Stop, 'FIXTURE_HASH_MISMATCH'):
            executor.OfflineExecutor(context(), fake).execute()
        self.assertEqual(fake.calls[-1][0], 'fixture_bytes')

    def test_source_hash_mismatch_before_image(self):
        fake = FakeEffects(); fake.data['production_checkout'][1]['render-worker/render.py'] += b' '
        with self.assertRaisesRegex(executor.Stop, 'SOURCE_HASH_MISMATCH'):
            executor.OfflineExecutor(context(), fake).execute()
        self.assertEqual(fake.calls[-1][0], 'production_checkout')

    def test_digest_mismatch_before_container(self):
        fake = FakeEffects(); fake.data['image_metadata']['manifest_digest'] = executor.INDEX_DIGEST
        with self.assertRaisesRegex(executor.Stop, 'DIGEST_OR_PLATFORM_MISMATCH'):
            executor.OfflineExecutor(context(), fake).execute()
        self.assertNotIn('container_start', [x[0] for x in fake.calls])

    def test_arm64_digest_is_never_substituted(self):
        fake = FakeEffects()
        fake.data['image_metadata'].update(architecture='arm64', manifest_digest='sha256:52bfd61345fe6896a3d0014e0efd1931f6d2f91f501f3c27181e7bce05b47d68')
        with self.assertRaises(executor.Stop): executor.OfflineExecutor(context(), fake).execute()

    def test_speaker_mismatch_before_synthesis(self):
        fake = FakeEffects(); fake.data['speakers_get'][0]['styles'][0]['name'] = 'ノーマル'
        with self.assertRaisesRegex(executor.Stop, 'SPEAKER_MISMATCH'):
            executor.OfflineExecutor(context(), fake).execute()
        self.assertNotIn('synthesis', [x[0] for x in fake.calls])

    def test_duplicate_speaker_id_is_ambiguous(self):
        with self.assertRaisesRegex(executor.Stop, 'SPEAKER_MISMATCH'):
            executor.verify_speakers('0.25.2', speakers() + speakers())

    def test_artifact_over_cap_never_uploads(self):
        fake = FakeEffects(); fake.data['artifact_sizes']['short.mp4'] = executor.ARTIFACT_CAP
        with self.assertRaisesRegex(executor.Stop, 'ARTIFACT_OVER_CAP'):
            executor.OfflineExecutor(context(), fake).execute()
        self.assertNotIn('upload', [x[0] for x in fake.calls])

    def test_artifact_exact_cap_accepted(self):
        r = executor.artifact_gate({'short.mp4': executor.ARTIFACT_CAP - 2,
                                   'payload_snapshot.json': 1, 'render-result.json': 1})
        self.assertEqual(r['upload_max'], 1)

    def test_unexpected_file_and_unknown_size_rejected(self):
        for sizes in ({'short.mp4': 20000}, {'short.mp4': 20000, 'payload_snapshot.json': 1,
                      'render-result.json': 1, 'audio.wav': 1}, dict.fromkeys(executor.ARTIFACT_FILES, None)):
            with self.assertRaises(executor.Stop): executor.artifact_gate(sizes)

    def test_artifact_upload_false_or_timeout_never_retries(self):
        for timeout in (False, True):
            fake = FakeEffects(); fake.data['upload'] = False
            if timeout: fake.fail = 'upload'
            runner = executor.OfflineExecutor(context(), fake)
            with self.assertRaises(executor.Stop): runner.execute()
            self.assertEqual([x[0] for x in fake.calls].count('upload'), 1)
            self.assertEqual(runner.attempts['upload'], 1)

    def test_owner_evidence_never_infers_reserved_capacity(self):
        fake = FakeEffects()
        executor.billing_gate(fake.data['billing_evidence'])
        self.assertIn('NOT_RESERVED_STORAGE_CAPACITY', fake.data['billing_evidence']['evaluation'])
        fake.data['billing_evidence']['budgets']['Actions']['stop_usage'] = False
        with self.assertRaisesRegex(executor.Stop, 'BILLING_NOT_FAIL_CLOSED'):
            executor.billing_gate(fake.data['billing_evidence'])


def stage_failure(stage):
    def test(self):
        fake = FakeEffects(); fake.fail = stage
        runner = executor.OfflineExecutor(context(), fake)
        with self.assertRaises(executor.Stop): runner.execute()
        self.assertEqual(fake.calls[-1][0], stage)
        self.assertEqual([x[0] for x in fake.calls].count(stage), 1)
    return test


for stage in ('production_checkout', 'runtime_binaries', 'container_start', 'version_get',
              'speakers_get', 'synthesis', 'encode', 'quality', 'artifact_sizes'):
    setattr(ExecutorTests, 'test_' + stage + '_unknown_stops_next_effect', stage_failure(stage))


def quality_rejection(key, value):
    def test(self):
        report = quality(); report[key] = value
        with self.assertRaises(executor.Stop): executor.quality_gate(report)
    return test


for name, key, value in (
    ('size_10000', 'bytes', 10000), ('missing_mp4','mp4_exists',False),
    ('missing_video','video_stream',False), ('missing_audio','audio_stream',False),
    ('width','width',720), ('height','height',1080), ('fps','fps','2997/100'),
    ('duration_under','duration',0.49), ('duration_over','duration',180.51),
    ('no_captions_file','captions_file_exists',False), ('no_dialogue','captions',''),
    ('dark','max_yavg',24.99), ('quiet','mean_volume_db',-38.01), ('nan','duration',float('nan'))):
    setattr(ExecutorTests, 'test_quality_reject_' + name, quality_rejection(key, value))


class CloudTests(unittest.TestCase):
    def setup_fake(self):
        policy = json.loads(cloud.POLICY_PATH.read_text())
        policy.update(allow=True, execution_approved=True, hard_disabled=False)
        env = {'PLM_ALLOW': 'true', 'PLM_EXECUTION_APPROVED': 'true',
               'PLM_APPROVED_HEAD_SHA': SHA, 'PLM_ORIGINAL_WORKFLOW_ID': '501',
               'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': executor.REPO,
               'RUNNER_ENVIRONMENT': 'github-hosted', 'RUNNER_OS': 'Linux', 'RUNNER_ARCH': 'X64',
               'GITHUB_RUN_ID': '101', 'GITHUB_RUN_NUMBER': '1', 'GITHUB_RUN_ATTEMPT': '1',
               'GITHUB_SHA': SHA, 'GITHUB_EVENT_NAME': 'workflow_dispatch'}
        ctx = context(identity=executor.PREFLIGHT_ID, path=executor.PREFLIGHT_WORKFLOW)
        calls = []; reads = []
        data = {f'https://api.github.com/repos/{executor.REPO}/actions/runs/101': record(ctx),
                f'https://api.github.com/repos/{executor.REPO}/actions/workflows/501/runs?per_page=100&page=1': current_page(ctx),
                cloud.REGISTRY_URL: registry(), cloud.VOICE_URLS['version']: '0.25.2',
                cloud.VOICE_URLS['speakers']: speakers()}
        def read(url): reads.append(url); return copy.deepcopy(data[url])
        def run(command, timeout=30):
            calls.append(command)
            if command[:3] == ['docker', 'image', 'inspect']:
                return json.dumps([{'Os': 'linux', 'Architecture': 'amd64', 'RepoDigests': [executor.IMAGE]}])
            return 'fake'
        return policy, env, calls, reads, data, run, read

    def test_checked_in_policy_refuses_before_network_or_process(self):
        policy, env, calls, reads, _, run, read = self.setup_fake()
        with self.assertRaisesRegex(executor.Stop, 'DISABLED_NOT_APPROVED'):
            cloud.runtime_preflight(json.loads(cloud.POLICY_PATH.read_text()), env, run, read)
        self.assertEqual(calls, []); self.assertEqual(reads, [])

    def test_preflight_only_two_voice_gets_zero_generation(self):
        p,e,c,r,d,run,read = self.setup_fake()
        result = cloud.runtime_preflight(p,e,run,read,lambda env,cmd: observed())
        self.assertEqual([u for u in r if u.startswith('http://')], list(cloud.VOICE_URLS.values()))
        self.assertEqual(result['synthesis'], 0); self.assertEqual(result['encode'], 0)
        self.assertEqual(result['mp4'], 0); self.assertEqual(result['artifact_upload'], 0)
        self.assertEqual(sum(cmd[:2] == ['docker','pull'] for cmd in c), 1)
        self.assertEqual(sum(cmd[:2] == ['docker','run'] for cmd in c), 1)
        self.assertEqual(c[-1][:3], ['docker','rm','-f'])
        self.assertFalse(any('ffmpeg' in cmd or 'apt-get' in cmd for cmd in c))

    def test_wrong_version_stops_before_speakers_and_cleans_up(self):
        p,e,c,r,d,run,read = self.setup_fake(); d[cloud.VOICE_URLS['version']] = '0.25.1'
        with self.assertRaisesRegex(executor.Stop, 'ENGINE_VERSION_MISMATCH'):
            cloud.runtime_preflight(p,e,run,read,lambda env,cmd: observed())
        self.assertNotIn(cloud.VOICE_URLS['speakers'], r)
        self.assertEqual(c[-1][:3], ['docker','rm','-f'])

    def test_speakers_mismatch_never_synthesizes(self):
        p,e,c,r,d,run,read = self.setup_fake(); d[cloud.VOICE_URLS['speakers']][0]['name'] = 'other'
        with self.assertRaisesRegex(executor.Stop, 'SPEAKER_MISMATCH'):
            cloud.runtime_preflight(p,e,run,read,lambda env,cmd: observed())
        self.assertEqual(c[-1][:3], ['docker','rm','-f'])

    def test_self_hosted_and_user_pc_refuse_before_effects(self):
        p,e,c,r,d,run,read = self.setup_fake(); e['RUNNER_ENVIRONMENT'] = 'self-hosted'
        with self.assertRaisesRegex(executor.Stop, 'CLOUD_RUNNER_REQUIRED'):
            cloud.runtime_preflight(p,e,run,read)
        self.assertEqual(c, []); self.assertEqual(r, [])

    def test_approved_head_and_original_workflow_binding_required(self):
        for field in ('PLM_APPROVED_HEAD_SHA','PLM_ORIGINAL_WORKFLOW_ID'):
            p,e,c,r,d,run,read = self.setup_fake(); e[field] = ''
            with self.assertRaises(executor.Stop): cloud.runtime_preflight(p,e,run,read)
            self.assertEqual(c, []); self.assertEqual(r, [])

    def test_generation_endpoint_rejected_before_http(self):
        for path in ('synthesis','audio_query','initialize_speaker','sing_frame_audio_query'):
            with self.assertRaisesRegex(executor.Stop, 'HTTP_ROUTE_NOT_ALLOWED'):
                cloud.get_json('http://127.0.0.1:50021/' + path)

    def test_registry_index_is_not_manifest(self):
        reply = registry(); reply['images'][0]['digest'] = executor.INDEX_DIGEST
        with self.assertRaises(executor.Stop): cloud.registry_metadata(reply)

    def test_registry_arm64_rejected(self):
        reply = registry(); reply['images'][0]['architecture'] = 'arm64'
        with self.assertRaises(executor.Stop): cloud.registry_metadata(reply)

    def test_http_unknown_after_start_no_metadata_retry_and_cleanup_once(self):
        p,e,c,r,d,run,read = self.setup_fake()
        def unknown(url):
            if url == cloud.VOICE_URLS['version']:
                r.append(url)
                raise TimeoutError('fake timeout')
            return read(url)
        with self.assertRaises(TimeoutError):
            cloud.runtime_preflight(p,e,run,unknown,lambda env,cmd: observed())
        self.assertEqual(r.count(cloud.VOICE_URLS['version']),1)
        self.assertNotIn(cloud.VOICE_URLS['speakers'],r)
        self.assertEqual(sum(cmd[:3] == ['docker','rm','-f'] for cmd in c),1)

    def test_preflight_missing_binary_stops_before_pull(self):
        p,e,c,r,d,run,read = self.setup_fake()
        def missing(env,cmd): raise executor.Stop('RUNTIME_COMMAND_FAILURE_OR_UNKNOWN')
        with self.assertRaises(executor.Stop): cloud.runtime_preflight(p,e,run,read,missing)
        self.assertEqual(c,[])

    def test_preflight_does_not_claim_external_codec_lock(self):
        p,e,c,r,d,run,read = self.setup_fake()
        obs=observed();obs['codec_dependency_lock_verified']=False
        receipt=cloud.runtime_preflight(p,e,run,read,lambda env,cmd: obs)
        self.assertFalse(receipt['codec_dependency_lock_verified'])
        with self.assertRaisesRegex(executor.Stop,'CODEC_DEPENDENCIES_UNPINNED'):
            executor.verify_runtime(obs)

    def test_runtime_version_or_filter_or_font_drift_stop(self):
        for key, value in [('python','3.12.14'), ('ffmpeg_package','latest'), ('filters',[]),
                           ('encoders',[]), ('font_family','fallback'), ('codec_dependency_lock_verified',False)]:
            obs=observed(); obs[key]=value
            with self.assertRaises(executor.Stop): executor.verify_runtime(obs)

    def test_both_workflows_marker_scoped_no_inputs_and_no_upload(self):
        for filename, identity in [(executor.RENDER_WORKFLOW,executor.RENDER_ID),
                                   (executor.PREFLIGHT_WORKFLOW,executor.PREFLIGHT_ID)]:
            text=(ROOT/filename).read_text()
            if identity == executor.RENDER_ID: self.assertIn('if: false',text)
            else: self.assertIn('steps.marker.outputs.allow',text)
            self.assertIn("allow: 'false'",text)
            self.assertIn("execution_approved: 'false'",text)
            self.assertIn('runs-on: ubuntu-24.04',text)
            self.assertIn('group: '+identity,text)
            self.assertIn('cancel-in-progress: false',text)
            self.assertNotIn('on: workflow_dispatch',text)
            self.assertIn('audit-evidence/consumed/'+identity+'.json',text)
            self.assertIn("branches: ['plm-offline-readiness-v1-20261002']",text)
            self.assertNotIn('inputs:',text)
            self.assertNotIn('upload-artifact@',text)
            self.assertNotIn('self-hosted',text)

    def test_quality_inclusive_signal_and_duration_boundaries_unchanged(self):
        for duration in (0.5,180.5):
            report=quality(); report.update(duration=duration,max_yavg=25,mean_volume_db=-38,bytes=10001)
            executor.quality_gate(report)
