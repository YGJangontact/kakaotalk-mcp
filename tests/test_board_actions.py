import sys
import pytest
from kakao_mcp.board_actions import BoardActions


class Desktop:
    def __init__(self):
        self.body = "검토한 본문"
        self.identity = (1, 2, 3)
        self.clicks = 0
        self.posts = ["첫 공지", "MIT Mathematics", "마지막 공지"]

    def draft_snapshot(self, room):
        return self.identity, self.body

    def publish(self, room, identity, body):
        self.clicks += 1
        return {"published": True}

    def read_post(self, room, index):
        return self.posts[min(index, len(self.posts) - 1)]


def test_preview_never_publishes():
    desktop = Desktop()
    actions = BoardActions(desktop)
    token = actions.prepare_publish("테스트방")["confirmation_token"]
    assert actions.check_publish(token)["ready"]
    assert desktop.clicks == 0
    assert not actions.publish(token, False)["success"]
    assert desktop.clicks == 0


@pytest.mark.parametrize("change", ["body", "identity"])
def test_changed_draft_rejected(change):
    desktop = Desktop()
    actions = BoardActions(desktop)
    token = actions.prepare_publish("테스트방")["confirmation_token"]
    setattr(desktop, change, "변경됨" if change == "body" else (4, 5, 6))
    assert not actions.publish(token, True)["success"]
    assert desktop.clicks == 0


def test_token_cannot_publish_twice():
    desktop = Desktop()
    actions = BoardActions(desktop)
    token = actions.prepare_publish("테스트방")["confirmation_token"]
    assert actions.publish(token, True)["published"]
    assert not actions.publish(token, True)["success"]
    assert desktop.clicks == 1


def test_expiry_and_new_preview_revoke_old_token():
    desktop = Desktop()
    clock = [0]
    actions = BoardActions(desktop, clock=lambda: clock[0])
    old = actions.prepare_publish("테스트방")["confirmation_token"]
    new = actions.prepare_publish("테스트방")["confirmation_token"]
    assert not actions.check_publish(old)["success"]
    clock[0] = 301
    assert not actions.publish(new, True)["success"]
    assert desktop.clicks == 0


def test_unknown_submission_is_not_retryable():
    class Failed(Desktop):
        def publish(self, *args):
            self.clicks += 1
            raise RuntimeError("window disappeared")
    desktop = Failed()
    actions = BoardActions(desktop)
    token = actions.prepare_publish("테스트방")["confirmation_token"]
    result = actions.publish(token, True)
    assert result["state"] == "outcome_unknown"
    assert not actions.publish(token, True)["success"]
    assert desktop.clicks == 1


def test_search_is_bounded_and_does_not_claim_exhaustive():
    actions = BoardActions(Desktop())
    result = actions.search("테스트방", "mit", 3)
    assert result["matches"] == [{"index": 1, "body": "MIT Mathematics"}]
    assert result["scanned"] == 3
    assert result["complete"] is False


def test_search_repeated_content_stops_without_false_completeness():
    result = BoardActions(Desktop()).search("테스트방", "공지", 10)
    assert result["stop_reason"] == "repeated_content"
    assert result["complete"] is False


def test_invalid_search_does_not_navigate():
    class Unavailable:
        def read_post(self, *args):
            raise AssertionError("invalid request touched UI")
    actions = BoardActions(Unavailable())
    assert not actions.search("테스트방", "", 5)["success"]
    assert not actions.search("테스트방", "공지", 51)["success"]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native boundary")
@pytest.mark.parametrize("readback,expected", [("본문", True), ("다른 글", False)])
def test_native_publication_requires_editor_close_and_matching_readback(monkeypatch, readback, expected):
    """Exercise real native publish flow with only external UI boundaries replaced."""
    from types import SimpleNamespace
    from kakao_mcp.backends import windows_board as board
    desktop = board.Win32BoardDesktop()
    identity = (10, 20, 30)
    monkeypatch.setattr(board.controller, "_chat_monitor", SimpleNamespace(is_running=False))
    monkeypatch.setattr(board.controller, "bring_window_to_front", lambda _: None)
    monkeypatch.setattr(desktop, "draft_snapshot", lambda _: (identity, "본문"))
    monkeypatch.setattr(desktop, "registration_y", lambda _: 506)
    state = {"open": True, "clicks": []}
    def click(root, x, y, from_right):
        state["clicks"].append((root, x, y, from_right))
        state["open"] = False
    monkeypatch.setattr(desktop, "click", click)
    monkeypatch.setattr(desktop, "find_editor", lambda _: 20 if state["open"] else None)
    monkeypatch.setattr(desktop, "read_post", lambda *_: readback)
    if expected:
        assert desktop.publish("방", identity, "본문")["published"] is True
    else:
        with pytest.raises(RuntimeError, match="not verified"):
            desktop.publish("방", identity, "본문")
    assert state["clicks"] == [(10, 95, 506, True)]


def test_search_cache_reuses_scan_for_different_query_and_refreshes():
    class Counting(Desktop):
        def __init__(self):
            super().__init__()
            self.reads = 0
        def read_post(self, *args):
            self.reads += 1
            return super().read_post(*args)
    desktop = Counting()
    actions = BoardActions(desktop)
    first = actions.search("방", "MIT", 3)
    second = actions.search("방", "공지", 3)
    assert first["cache_hit"] is False and second["cache_hit"] is True
    assert len(second["matches"]) == 2 and desktop.reads == 3
    actions.search("방", "공지", 3, refresh=True)
    assert desktop.reads == 6


def test_cache_expiration_and_room_isolation():
    ticks = [0]
    actions = BoardActions(Desktop(), clock=lambda: ticks[0])
    actions.search("A", "MIT", 2)
    ticks[0] = 5
    assert actions.search("A", "MIT", 2)["cache_age_seconds"] == 5
    assert not actions.search("B", "MIT", 2)["cache_hit"]
    ticks[0] = 31
    assert not actions.search("A", "MIT", 2)["cache_hit"]


def test_failed_scan_is_not_cached():
    class Broken(Desktop):
        def read_post(self, room, index):
            if index == 1:
                raise RuntimeError("copy failed")
            return "first"
    actions = BoardActions(Broken())
    assert not actions.search("방", "first", 3)["success"]
    assert not actions.search("방", "first", 3)["cache_hit"]


def test_cache_never_used_to_approve_publication():
    desktop = Desktop()
    actions = BoardActions(desktop)
    actions.search("방", "MIT", 3)
    token = actions.prepare_publish("방")["confirmation_token"]
    desktop.body = "changed"
    assert not actions.check_publish(token)["ready"]
