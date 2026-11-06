# Windows KakaoTalk board UI adapter.
import ctypes
import time
from contextlib import contextmanager
import win32api
import win32clipboard
import win32con
import win32gui
import win32process
from .. import controller
from ..common import EMPTY_HINT, unique, normalize
from .clipboard import ClipboardTransaction


class Win32BoardDesktop:
    @staticmethod
    def children(hwnd):
        result = []
        win32gui.EnumChildWindows(hwnd, lambda child, _: result.append(child), None)
        return result

    def named(self, hwnd, name, visible=True):
        return [child for child in self.children(hwnd)
                if win32gui.GetWindowText(child) == name
                and (not visible or win32gui.IsWindowVisible(child))]

    def windows(self, room_name=None, class_name="EVA_Window_Dblclk"):
        main = controller.is_kakaotalk_running()
        if not main["running"]:
            raise RuntimeError("KakaoTalk is not running")
        result = []
        def visit(hwnd, _):
            if (win32gui.IsWindowVisible(hwnd)
                    and win32gui.GetClassName(hwnd) == class_name
                    and win32process.GetWindowThreadProcessId(hwnd)[1] == main["pid"]
                    and (room_name is None or win32gui.GetWindowText(hwnd) == room_name)):
                result.append(hwnd)
        win32gui.EnumWindows(visit, None)
        return result

    def find_board(self, room_name):
        return unique([hwnd for hwnd in self.windows(room_name)
                       if self.named(hwnd, "MoimFeedView", visible=False)], "board")

    def find_editor(self, room_name):
        board = self.find_board(room_name)
        if not board or not self.named(board, "MoimPostEditWnd"):
            return None
        return unique([child for child in self.children(board)
                       if win32gui.IsWindowVisible(child)
                       and win32gui.GetClassName(child) == "RichEdit20W"
                       and win32gui.GetDlgCtrlID(child) == 1001], "board editor")

    @staticmethod
    def wait_for(find, label, timeout=4):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = find()
            if result:
                return result
            time.sleep(0.1)
        raise RuntimeError(f"Timed out waiting for {label}; inspect KakaoTalk layout")

    @staticmethod
    @contextmanager
    def dpi_context():
        user32 = ctypes.windll.user32
        user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        old = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        try:
            yield
        finally:
            if old:
                user32.SetThreadDpiAwarenessContext(old)

    def click(self, hwnd, x, y, from_right=False):
        # Coordinates are logical DIPs, scoped to a validated native window.
        with self.dpi_context():
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            scale = ctypes.windll.user32.GetDpiForWindow(hwnd) / 96
            if scale <= 0:
                raise RuntimeError("Cannot determine target DPI")
            px = right - round(x * scale) if from_right else left + round(x * scale)
            py = top + round(y * scale)
            if not (left < px < right and top < py < bottom):
                raise RuntimeError("Navigation target outside window")
            hit = win32gui.WindowFromPoint((px, py))
            if hit != hwnd and not win32gui.IsChild(hwnd, hit):
                raise RuntimeError("Target is obscured; no click sent")
            win32api.SetCursorPos((px, py))
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0)

    def open_editor(self, room_name):
        if controller._chat_monitor.is_running:
            raise RuntimeError("Stop chat monitoring before board editing")
        editor = self.find_editor(room_name)
        if editor:
            return self.focus_editor(editor)
        board = self.open_board(room_name)
        if self.named(board, "MoimPostWnd"):
            board, _ = self.feed(room_name)
        if not self.named(board, "MoimFeedView"):
            raise RuntimeError("Board is not on the feed; return to its list first")
        controller.bring_window_to_front(board)
        time.sleep(0.2)
        self.click(board, 45, 31, from_right=True)
        editor = self.wait_for(lambda: self.find_editor(room_name), "board editor")
        return self.focus_editor(editor)

    def open_board(self, room_name):
        board = self.find_board(room_name)
        if not board:
            # Require an already-open, uniquely identified conversation. Do not
            # use the upstream title-only finder: boards have the same title.
            rooms = [h for h in self.windows(room_name)
                     if any(win32gui.GetClassName(c) == "RICHEDIT50W"
                            and win32gui.GetDlgCtrlID(c) == 1006
                            for c in self.children(h))]
            chat = unique(rooms, "chat room")
            if not chat:
                raise RuntimeError("Open the exact chat room in KakaoTalk first")
            controller.bring_window_to_front(chat)
            time.sleep(0.2)
            if self.windows(class_name="EVA_Menu"):
                raise RuntimeError("Close the existing KakaoTalk popup menu first")
            self.click(chat, 15, 38, from_right=True)
            menu = self.wait_for(lambda: unique(self.windows(class_name="EVA_Menu"), "menu"), "chat menu")
            # Korean PC menu: second row is 톡게시판. No submission controls.
            self.click(menu, 42, 30)
            board = self.wait_for(lambda: self.find_board(room_name), "board")
        return board

    @staticmethod
    def focus_control(control):
        root = win32gui.GetAncestor(control, win32con.GA_ROOT)
        controller.bring_window_to_front(root)
        current = win32api.GetCurrentThreadId()
        target = win32process.GetWindowThreadProcessId(control)[0]
        attached = current != target
        if attached:
            win32process.AttachThreadInput(current, target, True)
        try:
            win32gui.SetFocus(control)
            if win32gui.GetFocus() != control:
                raise RuntimeError("Cannot focus board control")
        finally:
            if attached:
                win32process.AttachThreadInput(current, target, False)

    def feed(self, room_name):
        if controller._chat_monitor.is_running:
            raise RuntimeError("Stop chat monitoring before reading the board")
        board = self.open_board(room_name)
        if self.find_editor(room_name):
            raise RuntimeError("A draft editor is open; preserve it and close it manually before reading")
        controller.bring_window_to_front(board)
        if self.named(board, "MoimPostWnd"):
            self.click(board, 18, 30)
        feed = self.wait_for(lambda: unique(self.named(board, "MoimFeedView"), "feed"), "board feed")
        # Returning from detail refreshes the list asynchronously.
        time.sleep(0.5)
        return board, feed

    def read_post(self, room_name, index):
        board, feed = self.feed(room_name)
        self.focus_control(feed)
        # This custom view handles keys in its message loop (SendMessage does not
        # navigate). Recheck and focus the read-only list before each injected key.
        self.list_key(feed, win32con.VK_HOME)
        for _ in range(index):
            self.list_key(feed, win32con.VK_DOWN)
        self.list_key(feed, win32con.VK_RETURN)
        post = self.wait_for(lambda: unique(self.named(board, "MoimPostWnd"), "post"), "post detail")
        self.focus_control(post)
        # No click on body text: it may contain links or attachments.
        with ClipboardTransaction(win32clipboard) as clipboard:
            controller._send_ctrl_key_combo(0x41)
            controller._send_ctrl_key_combo(0x43)
            self.wait_for(lambda: win32clipboard.GetClipboardSequenceNumber() != clipboard.sequence, "post text copy", 2)
            clipboard.mark_copied()
            text = controller._read_clipboard_text()
            if not text:
                raise RuntimeError("No copyable post body; attachment-only posts are unsupported")
            # KakaoTalk's copy inserts CRCRLF for a single line break.
            return normalize(text.replace("\r\r\n", "\n")).rstrip("\n")

    def list_key(self, feed, key):
        if not win32gui.IsWindowVisible(feed) or win32gui.GetWindowText(feed) != "MoimFeedView":
            raise RuntimeError("Board list changed before navigation")
        self.focus_control(feed)
        controller._press_key(key)

    def draft_snapshot(self, room_name):
        editor = self.find_editor(room_name)
        if not editor:
            raise RuntimeError("No board draft editor open")
        root = win32gui.GetAncestor(editor, win32con.GA_ROOT)
        pid = win32process.GetWindowThreadProcessId(root)[1]
        return (root, editor, pid), normalize(self.read(editor))

    def publish(self, room_name, identity, body):
        if controller._chat_monitor.is_running:
            raise RuntimeError("Stop chat monitoring before publishing")
        current_identity, current_body = self.draft_snapshot(room_name)
        if current_identity != identity or current_body != body:
            raise RuntimeError("Draft changed before submission")
        root, editor, _ = identity
        controller.bring_window_to_front(root)
        time.sleep(0.2)
        # Same verified text editor layout used by prepare. No keyboard Enter.
        registration_y = self.registration_y(root)
        if self.draft_snapshot(room_name) != (identity, body):
            raise RuntimeError("Draft changed immediately before submission")
        self.click(root, 95, registration_y, from_right=True)
        # A click alone is not proof of publication. Read the resulting post.
        self.wait_for(lambda: not self.find_editor(room_name), "editor to close after submission")
        actual = self.read_post(room_name, 0)
        if normalize(actual).strip() != normalize(body).strip():
            raise RuntimeError("Submission outcome not verified; inspect board manually")
        return {"published": True, "state": "published_and_read_back", "room_name": room_name,
                "body": actual, "verification": "first post body matches; no stable post ID available"}

    def registration_y(self, root):
        with self.dpi_context():
            left, top, right, bottom = win32gui.GetWindowRect(root)
            scale = ctypes.windll.user32.GetDpiForWindow(root) / 96
            if scale <= 0:
                raise RuntimeError("Cannot determine registration button DPI")
            return (bottom - top) / scale - 27

    def focus_editor(self, editor):
        root = win32gui.GetAncestor(editor, win32con.GA_ROOT)
        controller.bring_window_to_front(root)
        time.sleep(0.2)
        self.click(editor, 6, 6)
        time.sleep(0.1)
        return editor

    @staticmethod
    def read(editor):
        if not win32gui.IsWindow(editor) or not win32gui.IsWindowVisible(editor):
            raise RuntimeError("Board editor closed")
        # GetWindowText does not retrieve another process's edit contents.
        length = win32gui.SendMessage(editor, win32con.WM_GETTEXTLENGTH, 0, 0)
        buffer = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.SendMessageW(editor, win32con.WM_GETTEXT, length + 1, buffer)
        # This KakaoTalk build returns its grey empty-editor hint via WM_GETTEXT.
        # The exact built-in hint is reserved, not a supported draft body.
        return "" if buffer.value == EMPTY_HINT else buffer.value

    def write(self, editor, body):
        if win32gui.GetClassName(editor) != "RichEdit20W" or self.read(editor):
            raise RuntimeError("Editor changed; refusing to overwrite")
        # Targeted paste avoids global Ctrl+V / Enter accidentally reaching chat.
        with ClipboardTransaction(win32clipboard) as clipboard:
            clipboard.put_text(body.replace("\n", "\r\n"))
            if self.read(editor):
                raise RuntimeError("Editor changed before paste")
            win32gui.SendMessage(editor, win32con.WM_PASTE, 0, 0)
