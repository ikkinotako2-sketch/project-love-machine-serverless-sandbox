"""Harmless guard probes. Kernel must reject before path lookup/network IO."""
import ctypes
import errno
import importlib
import socket
import subprocess
from pathlib import Path


def verify(native):
    if native.plm_guard_active() != 1:
        raise RuntimeError('guard_missing')
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.socket(2, 1, 0) != -1 or ctypes.get_errno() != errno.EPERM:
        raise RuntimeError('native_socket_not_blocked')
    libc.execve.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_void_p]
    if libc.execve(b'/plm-never-execute-probe', None, None) != -1 or ctypes.get_errno() != errno.EPERM:
        raise RuntimeError('native_exec_not_blocked')
    for name in ('ffmpeg','ffprobe','docker','voicevox','renderer'):
        try:
            subprocess.run([name,'--offline-denied-probe'], check=True)
        except PermissionError:
            pass
        else:
            raise RuntimeError('process_not_blocked')
    try:
        socket.socket()
    except PermissionError:
        pass
    else:
        raise RuntimeError('network_not_blocked')
    for name in ('ffmpeg_builder','voicevox','docker','google.genai','googleapiclient'):
        try:
            importlib.import_module(name)
        except PermissionError:
            pass
        else:
            raise RuntimeError('import_not_blocked')
    try:
        Path('/tmp/plm-forbidden-probe.mp4').write_bytes(b'never written')
    except PermissionError:
        pass
    else:
        raise RuntimeError('media_write_not_blocked')
