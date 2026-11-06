import sys
import pytest
from kakao_mcp.backends.macos import MacBoardDesktop
from kakao_mcp.board import BoardDrafts
from kakao_mcp.board_actions import BoardActions


def node(role, ident, **extra):
    return dict(AXRole=role, AXIdentifier=ident, **extra)


class FakeAX:
    pid = 42
    def __init__(self):
        self.editor = node("AXTextArea", "editor", AXValue="")
        self.button = node("AXButton", "publish")
        self.board = node("AXGroup", "board", AXChildren=[self.editor, self.button])
        self.window = node("AXWindow", "window", AXTitle="test", AXChildren=[self.board])
        self.root = dict(AXWindows=[self.window])
        self.pressed = []
    def get(self, element, attribute):
        return element.get(attribute)
    def set(self, element, attribute, value):
        element[attribute] = value
    def press(self, element):
        self.pressed.append(element)


@pytest.fixture
def desktop():
    selectors = {name: dict(AXRole=role, AXIdentifier=name) for name, role in
                 [("board", "AXGroup"), ("editor", "AXTextArea"), ("publish", "AXButton"),
                  ("compose", "AXButton"), ("post_list", "AXTable"), ("post_body", "AXStaticText")]}
    selectors["room_window"] = dict(AXRole="AXWindow", AXTitle="{room}")
    return MacBoardDesktop(FakeAX(), dict(selectors=selectors))


def test_draft_preserves_existing_text_and_never_presses(desktop):
    drafts = BoardDrafts(desktop)
    assert drafts.prepare("test", "hello")["success"]
    assert drafts.prepare("test", "hello")["success"]
    assert not drafts.prepare("test", "different")["success"]
    assert desktop.ax.editor["AXValue"] == "hello"
    assert desktop.ax.pressed == []


def test_duplicate_room_or_editor_fails_closed(desktop):
    desktop.ax.root["AXWindows"].append(desktop.ax.window.copy())
    assert not BoardDrafts(desktop).prepare("test", "hello")["success"]
    desktop.ax.root["AXWindows"].pop()
    desktop.ax.board["AXChildren"].append(desktop.ax.editor.copy())
    assert not BoardDrafts(desktop).prepare("test", "hello")["success"]
    assert not desktop.ax.pressed


def test_compose_waits_for_editor_without_pressing_publish(desktop):
    desktop.ax.board["AXChildren"].remove(desktop.ax.editor)
    compose = node("AXButton", "compose")
    desktop.ax.board["AXChildren"].append(compose)
    def press(element):
        assert element is compose
        desktop.ax.pressed.append(element)
        desktop.ax.board["AXChildren"].append(desktop.ax.editor)
    desktop.ax.press = press
    assert BoardDrafts(desktop).prepare("test", "한글\nsecond line")["success"]
    assert desktop.ax.pressed == [compose]


def test_draft_blocks_reading_and_wrong_room(desktop):
    with pytest.raises(RuntimeError, match="Close the draft"):
        desktop.read_post("test", 0)
    with pytest.raises(RuntimeError, match="exact room"):
        desktop.window("another room")


def test_publish_token_invalidated_by_body_change(desktop):
    desktop.write(desktop.ax.editor, "hello")
    service = BoardActions(desktop)
    token = service.prepare_publish("test")["confirmation_token"]
    desktop.write(desktop.ax.editor, "changed")
    assert not service.publish(token, confirm=True)["success"]
    assert not desktop.ax.pressed


def test_publish_is_once_and_outcome_unknown(desktop):
    desktop.write(desktop.ax.editor, "hello")
    service = BoardActions(desktop)
    token = service.prepare_publish("test")["confirmation_token"]
    assert not service.publish(token)["success"]
    assert service.publish(token, confirm=True)["published"] is None
    assert not service.publish(token, confirm=True)["success"]
    assert len(desktop.ax.pressed) == 1


def test_read_search_and_diagnostics(desktop):
    desktop.ax.board["AXChildren"].remove(desktop.ax.editor)
    row = node("AXRow", "row", AXChildren=[node("AXStaticText", "post_body", AXValue="Full body")])
    desktop.ax.board["AXChildren"].append(node("AXTable", "post_list", AXRows=[row]))
    assert desktop.read_post("test", 0) == "Full body"
    assert BoardActions(desktop).search("test", "BODY", 1)["scanned"] == 1
    with pytest.raises(RuntimeError):
        desktop.read_post("test", 1)
    assert all("AXValue" not in n and "AXTitle" not in n for n in desktop.diagnose("test")["nodes"])


def test_profile_required_and_unbound_window_rejected(desktop, monkeypatch):
    monkeypatch.delenv("KAKAO_MAC_PROFILE", raising=False)
    with pytest.raises(RuntimeError, match="KAKAO_MAC_PROFILE"):
        MacBoardDesktop().profile
    desktop.profile["selectors"]["room_window"]["AXTitle"] = "test"
    with pytest.raises(ValueError):
        desktop.window("other")


@pytest.mark.skipif(sys.platform != "darwin", reason="Native macOS framework import")
def test_native_framework_exports():
    import ApplicationServices as ax
    from AppKit import NSRunningApplication
    assert callable(ax.AXUIElementCopyAttributeValue)
    assert callable(ax.AXUIElementIsAttributeSettable)
    assert callable(ax.AXUIElementPerformAction)
    assert NSRunningApplication is not None
