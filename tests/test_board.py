"""Board draft contracts; never operate the real desktop from unit tests."""
import pytest
from kakao_mcp import board


class Desktop:
    def __init__(self, text=""):
        self.text = text
        self.writes = 0

    def open_editor(self, room):
        return 123

    def read(self, editor):
        return self.text

    def write(self, editor, text):
        self.writes += 1
        self.text = text


def test_preserves_existing_draft():
    desktop = Desktop("사용자가 작성하던 글")
    result = board.BoardDrafts(desktop).prepare("테스트방", "새 글")
    assert result["success"] is False
    assert desktop.text == "사용자가 작성하던 글"
    assert desktop.writes == 0


def test_retry_does_not_append_or_publish():
    desktop = Desktop()
    service = board.BoardDrafts(desktop)
    first = service.prepare("테스트방", "한글\n둘째 줄")
    again = service.prepare("테스트방", "한글\n둘째 줄")
    assert first["success"] and again["success"]
    assert first["published"] is False
    assert first["body"] == "한글\n둘째 줄"
    assert desktop.text == "한글\n둘째 줄"
    assert desktop.writes == 1


@pytest.mark.parametrize("room,body", [("", "본문"), ("방", "  "), ("방", "a\x00b"),
                                     ("방", "멤버들과 공유하고 싶은 소식을 남겨보세요.")])
def test_invalid_input_does_not_touch_desktop(room, body):
    class NoAccess:
        def open_editor(self, room):
            raise AssertionError("invalid request reached desktop")
    assert board.BoardDrafts(NoAccess()).prepare(room, body)["success"] is False


def test_does_not_report_success_on_truncated_input():
    class Truncated(Desktop):
        def write(self, editor, text):
            self.text = text[:2]
    result = board.BoardDrafts(Truncated()).prepare("방", "긴 본문입니다")
    assert result["success"] is False
    assert result["published"] is False


def test_ambiguous_windows_fail_closed():
    with pytest.raises(RuntimeError, match="ambiguous"):
        board.unique([10, 20], "board")


def test_status_is_read_only():
    class ReadOnly(Desktop):
        def find_editor(self, room):
            return 123
        def open_editor(self, room):
            raise AssertionError("status must not navigate")
    desktop = ReadOnly("작성 중")
    result = board.BoardDrafts(desktop).status("방")
    assert result["body"] == "작성 중"
    assert desktop.writes == 0
