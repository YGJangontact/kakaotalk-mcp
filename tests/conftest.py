"""Unit tests must never inject input into a real KakaoTalk session."""
from unittest.mock import MagicMock
import pytest


@pytest.fixture(autouse=True)
def isolate_legacy_controller_tests(request, monkeypatch):
    if request.node.path.name == "test_controller.py":
        from kakao_mcp import controller
        # Legacy tests mock only some calls; sending now also uses foreground,
        # clipboard and keybd_event. Replace all native boundaries by default.
        for name in ("win32api", "win32gui", "win32clipboard", "win32process", "_user32"):
            monkeypatch.setattr(controller, name, MagicMock())
        monkeypatch.setattr(controller, "bring_window_to_front", MagicMock())
