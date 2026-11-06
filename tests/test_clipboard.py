import pytest
from kakao_mcp.backends.clipboard import ClipboardTransaction


class Clipboard:
    def __init__(self, data):
        self.data = data.copy()
        self.sequence = 1
    def OpenClipboard(self): pass
    def CloseClipboard(self): pass
    def EnumClipboardFormats(self, previous):
        keys = list(self.data)
        index = keys.index(previous) + 1 if previous else 0
        return keys[index] if index < len(keys) else 0
    def GetClipboardData(self, key): return self.data[key]
    def GetClipboardSequenceNumber(self): return self.sequence
    def EmptyClipboard(self):
        self.data.clear()
        self.sequence += 1
    def SetClipboardData(self, key, value):
        self.data[key] = value
        self.sequence += 1


def test_rich_text_and_binary_formats_restored_after_error():
    original = {13: "사용자 텍스트", 49386: b"<b>rich</b>", 49711: b"opaque"}
    api = Clipboard(original)
    with pytest.raises(RuntimeError):
        with ClipboardTransaction(api) as clipboard:
            clipboard.put_text("temporary")
            raise RuntimeError("paste failed")
    assert api.data == original


def test_concurrent_clipboard_change_is_not_overwritten():
    api = Clipboard({13: "original"})
    with ClipboardTransaction(api) as clipboard:
        clipboard.put_text("temporary")
        api.EmptyClipboard()
        api.SetClipboardData(13, "new user copy")
    assert api.data == {13: "new user copy"}


def test_unsupported_handle_keeps_original_untouched():
    api = Clipboard({3: 12345})
    with pytest.raises(RuntimeError, match="cannot safely preserve"):
        with ClipboardTransaction(api):
            pytest.fail("unsafe snapshot was accepted")
    assert api.data == {3: 12345}
