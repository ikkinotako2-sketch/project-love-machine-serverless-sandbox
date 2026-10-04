"""Offline one-shot orchestration oracle; no runtime adapter or live renderer.

Effects are injected ONLY for guarded offline tests. The command-line entry
point always STOPs. GitHub history is mutable, not a permanent ledger.
"""
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

REPO = 'ikkinotako2-sketch/project-love-machine-serverless-sandbox'
PRODUCTION_REPO = 'ikkinotako2-sketch/project-love-machine'
PRODUCTION_SHA = '25f24bc4e6a20164c5549f746fc0eefcedf5d178'
RENDER_ID = 'manual-fixture-render-20261004-001'
PREFLIGHT_ID = 'manual-fixture-runtime-preflight-20261004-001'
RENDER_WORKFLOW = '.github/workflows/plm-manual-fixture-executor-candidate.yml'
PREFLIGHT_WORKFLOW = '.github/workflows/plm-cloud-runtime-preflight-once.yml'
IMAGE_DIGEST = 'sha256:ab700b3768d0a2e9230d53e054b321f60409fda34fe794a333ae7202ab1c87f4'
IMAGE = 'voicevox/voicevox_engine@' + IMAGE_DIGEST
INDEX_DIGEST = 'sha256:ece7d29fb87c754f795c044e13436d2181fccf8d50560bd45160c705b4f7e8d9'
FIXTURE_HASHES = {
    'script.canonical.json': '9077ccd4b61ff3bcdadcccaaea90219377acfd4abf19ebd414af36f7eb7c0b8b',
    'normalized-result.canonical.json': 'dbcc62dfe12ef550bb37987839c6cd3e30743ca9bc307d6f8131d42e7e0f555e',
    'render-payload.canonical.json': '2b92b1b2266da9be38e0cebdd061add724734049f08afc0bbffbe06b7aa53c40',
}
SOURCE_HASHES = {
    '.github/workflows/render-short.yml': 'd2a02202245c222a4b9a0622ba3c2f17c174e0ea478cf84b2180bb72b4e6a573',
    'render-worker/RENDER_QUALITY.md': '9ef585ab5530cac5d41808442ff0372ee42ea95455a5e1b208d6f4f9e2fa12ef',
    'render-worker/ffmpeg_builder.py': '8f542b06c2b98a7beb09a2798969fb4def8673efd73e673db6ebce176aedbccc',
    'render-worker/quality_gate.py': 'f3cbc58d62d0cfda41997fe8d420a3a630173effcbbfcbc397b0063cf14400ec',
    'render-worker/render.py': '993a89b8117b2cbb12be3409891a95beea22d9a64c56d93fe710f97ecd62640b',
    'render-worker/voicevox.py': 'd9811c6d49fdd312fd6a8f6d51514a8e0accfb46cc1cf2e07988d9c43cbfd858',
}
ARTIFACT_FILES = ('short.mp4', 'payload_snapshot.json', 'render-result.json')
ARTIFACT_CAP = 12 * 1024 * 1024
FILTERS = frozenset(('color', 'drawbox', 'crop', 'fade', 'trim', 'setpts',
                     'concat', 'subtitles', 'format', 'loudnorm', 'apad', 'atrim',
                     'fps', 'scale', 'signalstats', 'metadata', 'volumedetect'))
ENCODERS = frozenset(('libx264', 'aac'))
RUNTIME_VERSIONS = {'python': '3.12.15', 'ffmpeg_package': '7:6.1.1-3ubuntu5',
                    'font_package': '1:20230817+repack1-3'}


class Stop(ValueError):
    """A stable, non-secret stop code; never include provider bodies/tokens."""


def need(condition, code):
    if not condition:
        raise Stop(code)


def positive(value):
    return type(value) is int and value > 0


@dataclass(frozen=True)
class RunContext:
    run_id: int
    workflow_id: int
    run_attempt: int
    run_number: int
    identity: str
    path: str
    head_sha: str
    repository: str = REPO
    event: str = 'workflow_dispatch'


def history_gate(context, fetch_page, *, identity=RENDER_ID, path=RENDER_WORKFLOW):
    """Unfiltered read-only pages. No retry; bound scan stops on ambiguity.

    Run number 1 also rejects a second run after a previous record is deleted.
    This is NOT proof against workflow deletion/recreation or administrator
    history mutation. The current record must already exist at run creation.
    """
    need(context.repository == REPO and context.identity == identity and
         context.path == path and context.event == 'workflow_dispatch', 'IDENTITY_MISMATCH')
    need(all(positive(v) for v in (context.run_id, context.workflow_id,
                                  context.run_attempt, context.run_number)), 'AMBIGUOUS_CONTEXT')
    need(context.run_attempt == 1, 'RERUN_REJECTED')
    need(context.run_number == 1, 'IDENTITY_CONSUMED_RUN_NUMBER')
    need(len(context.head_sha) == 40 and all(c in '0123456789abcdef' for c in context.head_sha),
         'AMBIGUOUS_CONTEXT')
    total = None
    records = []
    for page in range(1, 21):
        try:
            reply = fetch_page(page)
        except Exception:
            raise Stop('HISTORY_API_FAILURE') from None
        need(isinstance(reply, dict) and type(reply.get('total_count')) is int and
             reply['total_count'] >= 0 and isinstance(reply.get('workflow_runs'), list),
             'AMBIGUOUS_HISTORY')
        if total is None:
            total = reply['total_count']
        need(reply['total_count'] == total, 'HISTORY_CHANGED_DURING_SCAN')
        batch = reply['workflow_runs']
        need(len(batch) <= 100, 'AMBIGUOUS_HISTORY')
        records.extend(batch)
        need(len(records) <= total, 'AMBIGUOUS_HISTORY')
        if len(records) == total:
            break
        need(bool(batch), 'INCOMPLETE_HISTORY')
    else:
        raise Stop('HISTORY_PAGE_LIMIT')
    seen = set()
    for record in records:
        need(isinstance(record, dict) and positive(record.get('id')) and
             record.get('id') not in seen, 'AMBIGUOUS_HISTORY')
        seen.add(record['id'])
        need(record.get('workflow_id') == context.workflow_id and record.get('path') == path,
             'WORKFLOW_BINDING_MISMATCH')
    need(context.run_id in seen, 'CURRENT_RUN_MISSING')
    need(seen == {context.run_id}, 'IDENTITY_CONSUMED_PRIOR_RUN')
    current = records[0]
    need(type(current.get('run_attempt')) is int and type(current.get('run_number')) is int and
         current.get('run_attempt') == 1 and current.get('run_number') == 1 and
         current.get('head_sha') == context.head_sha and
         current.get('event') == context.event and
         current.get('repository', {}).get('full_name') == REPO, 'CURRENT_RUN_MISMATCH')
    return {'identity': identity, 'consumed': True, 'run_id': context.run_id,
            'workflow_id': context.workflow_id, 'scope': 'EXISTING_WORKFLOW_HISTORY_ONLY',
            'permanent_ledger_proven': False}


def verify_bytes(actual, expected, code):
    need(isinstance(actual, dict) and set(actual) == set(expected), code)
    for name, sha in expected.items():
        need(isinstance(actual[name], bytes) and hashlib.sha256(actual[name]).hexdigest() == sha, code)


def verify_fixture(files):
    verify_bytes(files, FIXTURE_HASHES, 'FIXTURE_HASH_MISMATCH')


def verify_source(commit, files):
    need(commit == PRODUCTION_SHA, 'SOURCE_COMMIT_MISMATCH')
    verify_bytes(files, SOURCE_HASHES, 'SOURCE_HASH_MISMATCH')


def verify_image(metadata):
    need(isinstance(metadata, dict) and metadata.get('reference') == IMAGE and
         metadata.get('manifest_digest') == IMAGE_DIGEST and metadata.get('os') == 'linux' and
         metadata.get('architecture') == 'amd64', 'DIGEST_OR_PLATFORM_MISMATCH')


def verify_speakers(version, speakers):
    need(version == '0.25.2', 'ENGINE_VERSION_MISMATCH')
    need(isinstance(speakers, list), 'SPEAKER_METADATA_INVALID')
    matches = []
    for speaker in speakers:
        need(isinstance(speaker, dict) and isinstance(speaker.get('styles'), list),
             'SPEAKER_METADATA_INVALID')
        for style in speaker['styles']:
            need(isinstance(style, dict), 'SPEAKER_METADATA_INVALID')
            if type(style.get('id')) is int and style['id'] == 1:
                matches.append((speaker.get('name'), style.get('name')))
    need(matches == [('ずんだもん', 'あまあま')], 'SPEAKER_MISMATCH')


def verify_runtime(observed, *, require_codec_lock=True):
    need(isinstance(observed, dict) and observed.get('runner') == 'github-hosted' and
         observed.get('os') == 'ubuntu-24.04' and observed.get('architecture') == 'amd64',
         'CLOUD_RUNNER_REQUIRED')
    need(all(observed.get(k) == v for k, v in RUNTIME_VERSIONS.items()), 'RUNTIME_VERSION_MISMATCH')
    need(observed.get('ffmpeg_version') == '6.1.1' and observed.get('ffprobe_version') == '6.1.1',
         'RUNTIME_VERSION_MISMATCH')
    need(observed.get('font_family') == 'Noto Sans CJK JP' and observed.get('font_verified') is True,
         'FONT_MISMATCH')
    need(FILTERS.issubset(set(observed.get('filters', []))) and
         ENCODERS.issubset(set(observed.get('encoders', []))), 'CODEC_OR_FILTER_MISSING')
    need(observed.get('libav_candidate_versions_match') is True, 'LIBAV_VERSION_MISMATCH')
    if require_codec_lock:
        need(observed.get('codec_dependency_lock_verified') is True, 'CODEC_DEPENDENCIES_UNPINNED')
    need(observed.get('docker_available') is True, 'DOCKER_UNAVAILABLE')


def quality_gate(report):
    need(isinstance(report, dict), 'QUALITY_INVALID')
    need(report.get('mp4_exists') is True and type(report.get('bytes')) is int and
         report['bytes'] > 10000, 'QUALITY_FILE_SIZE')
    need(report.get('video_stream') is True and report.get('audio_stream') is True, 'QUALITY_STREAMS')
    need((report.get('width'), report.get('height')) == (1080, 1920), 'QUALITY_RESOLUTION')
    try:
        fps = Fraction(report['fps'])
        duration, luma, volume = (float(report[k]) for k in ('duration', 'max_yavg', 'mean_volume_db'))
    except (ValueError, TypeError, KeyError, ZeroDivisionError):
        raise Stop('QUALITY_INVALID') from None
    need(all(math.isfinite(x) for x in (duration, luma, volume)), 'QUALITY_INVALID')
    need(fps == 30 and 0.5 <= duration <= 180.5, 'QUALITY_TIMING')
    need(report.get('captions_file_exists') is True and
         isinstance(report.get('captions'), str) and 'Dialogue:' in report['captions'], 'QUALITY_CAPTIONS')
    need(luma >= 25 and volume >= -38, 'QUALITY_SIGNAL')


def artifact_gate(files):
    need(isinstance(files, dict) and set(files) == set(ARTIFACT_FILES), 'ARTIFACT_INVENTORY')
    need(all(type(v) is int and v > 0 for v in files.values()), 'ARTIFACT_SIZE_UNKNOWN')
    need(files['short.mp4'] > 10000, 'QUALITY_FILE_SIZE')
    need(sum(files.values()) <= ARTIFACT_CAP, 'ARTIFACT_OVER_CAP')
    return {'files': list(ARTIFACT_FILES), 'max_total_bytes': ARTIFACT_CAP,
            'retention_days': 1, 'retry': 0, 'upload_max': 1}


def billing_gate(evidence):
    need(evidence.get('provenance') == 'OWNER_REPORTED_SCREENSHOTS_2026_10_04' and
         evidence.get('card_addition_permitted') is False and
         evidence.get('billing_changes_permitted') is False, 'BILLING_EVIDENCE_MISMATCH')
    need(all(evidence.get('budgets', {}).get(k) == {'usd': 0, 'stop_usage': True}
             for k in ('Actions', 'Packages', 'Codespaces', 'Git LFS', 'All AI Credit SKUs')),
         'BILLING_NOT_FAIL_CLOSED')


class OfflineExecutor:
    """Single-use state machine over in-memory fake effects, never live-ready."""
    def __init__(self, context, effects, consumption_gate=None):
        self.context, self.effects = context, effects
        self.consumption_gate = consumption_gate
        self.started = False
        self.stage = 'not_started'
        self.trace = []
        self.attempts = dict.fromkeys(('synthesis', 'encode', 'upload'), 0)

    def call(self, stage, *args):
        self.stage = stage
        self.trace.append(stage)
        if stage in self.attempts:
            self.attempts[stage] += 1  # count BEFORE effect; timeout still consumes it
            need(self.attempts[stage] == 1, 'SIDE_EFFECT_ALREADY_ATTEMPTED')
        return self.effects(stage, *args)

    def execute(self):
        need(not self.started, 'EXECUTOR_ALREADY_CONSUMED')
        self.started = True
        try:
            # Legacy oracle tests retain mutable history only as a historical model.
            # New marker candidate supplies the read-only primary consumption gate.
            history = self.consumption_gate() if self.consumption_gate is not None else history_gate(
                self.context, lambda page: self.call('history_page', page))
            billing_gate(self.call('billing_evidence'))
            verify_fixture(self.call('fixture_bytes'))
            commit, source = self.call('production_checkout', PRODUCTION_REPO, PRODUCTION_SHA)
            verify_source(commit, source)
            verify_image(self.call('image_metadata', IMAGE))
            verify_runtime(self.call('runtime_binaries'))
            need(self.call('container_start', IMAGE) is True, 'CONTAINER_START_UNKNOWN')
            version = self.call('version_get')
            speakers = self.call('speakers_get')
            verify_speakers(version, speakers)
            need(self.call('synthesis') is True, 'SYNTHESIS_UNKNOWN')
            need(self.call('encode') is True, 'ENCODE_UNKNOWN')
            quality_gate(self.call('quality'))
            bounds = artifact_gate(self.call('artifact_sizes'))
            need(self.call('upload', bounds) is True, 'UPLOAD_FAILURE_OR_QUOTA_STOP')
            return {'status': 'OFFLINE_SIMULATION_PASS_NOT_LIVE_READY',
                    'identity': RENDER_ID, 'run_id': self.context.run_id,
                    'history': history, 'simulated_attempts': dict(self.attempts),
                    'actual_operations': 0, 'credit': 'VOICEVOX:ずんだもん'}
        except Exception as error:
            # Do not retain exception text from adapters or external response bodies.
            raise Stop(str(error) if isinstance(error, Stop) else 'SIDE_EFFECT_FAILURE_OR_UNKNOWN') from None


def live_render_gate():
    # Deliberately cannot be unlocked by plan flags or caller-supplied history.
    raise Stop('BLOCKED_RENDER_NOT_APPROVED_RUNTIME_METADATA_REQUIRED')


if __name__ == '__main__':
    try:
        live_render_gate()
    except Stop as error:
        print(str(error))
        raise SystemExit(1)
