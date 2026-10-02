"""A prestarted guarded pure Node oracle. No process launch from test code."""
import json
_process = None
_guard_active = False


def require_guard():
    if not _guard_active:
        raise RuntimeError('guarded_tests_runner_required')


def oracle(requests):
    if _process is None:
        raise RuntimeError('guarded_oracle_required')
    _process.stdin.write(json.dumps(requests, ensure_ascii=True) + '\n')
    _process.stdin.flush()
    line = _process.stdout.readline()
    if not line:
        raise RuntimeError('oracle_stopped')
    result = json.loads(line)
    if not isinstance(result, list):
        raise RuntimeError('invalid_oracle_output')
    return result
