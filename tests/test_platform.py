"""Common services stay portable even when no Windows libraries are installed."""
import subprocess
import sys


def test_common_services_do_not_import_win32():
    code = '''
import importlib.abc
import sys
class BlockWindows(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname.startswith(("win32", "kakao_mcp.controller", "kakao_mcp.backends.windows")):
            raise AssertionError("Unexpected Windows dependency: " + fullname)
sys.meta_path.insert(0, BlockWindows())
from kakao_mcp.board import BoardDrafts
from kakao_mcp.board_actions import BoardActions
from kakao_mcp.parser import parse_chat_text
'''
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_server_starts_and_reports_actual_platform_without_ui_actions():
    code = '''
from kakao_mcp.server import kakao_capabilities
import sys
result = kakao_capabilities()
assert result["native_automation"] == (sys.platform == "win32")
assert result["macos_native"] is False
'''
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
