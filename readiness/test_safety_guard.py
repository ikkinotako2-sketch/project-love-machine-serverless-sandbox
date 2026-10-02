from oracle_bridge import require_guard
require_guard()
import ctypes
import errno
import importlib
from pathlib import Path
import socket
import subprocess
import unittest


class GuardTests(unittest.TestCase):
    def test_native_execve_denied_before_path_lookup(self):
        libc=ctypes.CDLL(None,use_errno=True)
        libc.execve.argtypes=[ctypes.c_char_p,ctypes.c_void_p,ctypes.c_void_p]
        self.assertEqual(libc.execve(b'/plm-never-execute-probe',None,None),-1)
        self.assertEqual(ctypes.get_errno(),errno.EPERM)

    def test_native_socket_denied(self):
        libc=ctypes.CDLL(None,use_errno=True)
        self.assertEqual(libc.socket(2,1,0),-1)
        self.assertEqual(ctypes.get_errno(),errno.EPERM)

    def test_ffmpeg_ffprobe_docker_voicevox_render_processes_denied(self):
        for command in ('ffmpeg','ffprobe','docker','voicevox','renderer'):
            with self.subTest(command=command),self.assertRaises(PermissionError):
                subprocess.run([command,'--offline-denied-probe'],check=True)

    def test_render_and_ai_imports_denied(self):
        for module in ('ffmpeg_builder','voicevox','docker','google.genai','googleapiclient'):
            with self.subTest(module=module),self.assertRaises(PermissionError):
                importlib.import_module(module)

    def test_socket_api_denied(self):
        with self.assertRaises(PermissionError):socket.socket()

    def test_media_write_denied(self):
        for suffix in ('.mp4','.wav','.mp3','.ass'):
            with self.subTest(suffix=suffix),self.assertRaises(PermissionError):
                Path('/tmp/plm-forbidden-probe'+suffix).write_bytes(b'not written')

    def test_safe_source_read_allowed(self):
        self.assertIn('native_exec',Path(__file__).read_text())
