"""Create shared services once per MCP server process."""
import sys
from .backends import ControllerProxy, create_desktop
from .board import BoardDrafts
from .board_actions import BoardActions

controller = ControllerProxy()
drafts = BoardDrafts(create_desktop())
board_actions = BoardActions(drafts.desktop, lock=drafts.lock)


def capabilities():
    return {"platform": sys.platform, "native_automation": sys.platform == "win32",
            "macos_native": False, "board_cache_ttl_seconds": 30,
            "max_search_posts": 50, "publish_requires_confirmation_token": True,
            "message": "Windows UI supported; macOS UI adapter not implemented"}
