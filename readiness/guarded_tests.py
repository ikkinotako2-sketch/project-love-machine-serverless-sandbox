"""Trusted bootstrap. Tests cannot start without native execution/network guard.

Compile native_guard.c OUTSIDE this runner; no compiler invoked by this file.
One pure Node oracle is started with LD_PRELOAD before installing the same
seccomp filter on Python. All tests then inherit no-exec/no-socket policy.
"""
import ctypes
import json
import importlib.abc
import os
from pathlib import Path
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parent
BLOCKED_MODULES = ('ffmpeg_builder', 'render', 'renderer', 'voicevox', 'docker',
                   'requests', 'httpx', 'google', 'google.generativeai', 'google.genai',
                   'googleapiclient', 'yt_dlp')
MEDIA_SUFFIXES = ('.mp4', '.mkv', '.mov', '.avi', '.webm', '.wav', '.mp3', '.m4a', '.ass')
COUNTS = {'blocked_exec': 0, 'blocked_network': 0, 'blocked_media_write': 0, 'blocked_import': 0}


def audit(event, args):
    if event in ('subprocess.Popen', 'os.system', 'os.exec', 'os.posix_spawn'):
        COUNTS['blocked_exec'] += 1
        raise PermissionError('offline_exec_denied')
    if event.startswith('socket.'):
        COUNTS['blocked_network'] += 1
        raise PermissionError('offline_network_denied')
    if event == 'import' and any(args[0] == name or args[0].startswith(name + '.') for name in BLOCKED_MODULES):
        COUNTS['blocked_import'] += 1
        raise PermissionError('offline_import_denied')
    if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
        path = os.fsdecode(args[0]).lower()
        mode = args[1] or ''
        flags = args[2] or 0
        write = any(c in mode for c in 'wax+') or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)
        if write and path.endswith(MEDIA_SUFFIXES):
            COUNTS['blocked_media_write'] += 1
            raise PermissionError('offline_media_write_denied')


class BlockImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + '.') for name in BLOCKED_MODULES):
            COUNTS['blocked_import'] += 1
            raise PermissionError('offline_import_denied')
        return None


def main():
    if any(os.environ.get(k) != 'true' for k in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')):
        raise SystemExit('unsafe_flags')
    library = Path(os.environ.get('PLM_GUARD_LIBRARY', '')).resolve()
    if not library.is_file() or library.suffix != '.so':
        raise SystemExit('native_guard_required')
    import oracle_bridge
    env = {'PATH': os.environ['PATH'], 'LD_PRELOAD': str(library),
           **{k:'true' for k in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')}}
    process = subprocess.Popen(['node', '--import', str(HERE/'guard/node_guard.mjs'),
                                str(HERE/'n8n_parity_oracle.mjs'), '--lines'],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, env=env)
    oracle_bridge._process = process
    # Ping verifies that guarded Node really started before test discovery.
    if oracle_bridge.oracle([]) != []:
        raise SystemExit('oracle_guard_failed')
    native = ctypes.CDLL(str(library))  # constructor installs irreversible TSYNC seccomp
    if native.plm_guard_active() != 1:
        raise SystemExit('guard_not_active')
    oracle_bridge._guard_active = True
    sys.addaudithook(audit)
    sys.meta_path.insert(0, BlockImports())
    import safety_probe
    safety_probe.verify(native)
    suite = unittest.defaultTestLoader.discover(str(HERE), pattern='test_*.py')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    try:
        process.stdin.close()
    except BrokenPipeError:
        pass
    process.wait(timeout=5)
    if process.returncode:
        raise SystemExit('oracle_guard_failed')
    print('OFFLINE_GUARD_EVIDENCE ' + json.dumps({'native_seccomp_active': True,
          'socket_syscalls_denied': True, 'exec_syscalls_denied': True,
          'render_executions': 0, 'external_api_calls': 0,
          'blocked_probe_attempts': COUNTS}, sort_keys=True))
    raise SystemExit(not result.wasSuccessful())


if __name__ == '__main__':
    main()
