"""Experimental, profile-driven macOS Accessibility board adapter.

No coordinate/keyboard fallback: absent or ambiguous AX elements fail closed.
Native imports and permission checks occur only when a UI operation is requested.
"""
import json
import os
import time
from pathlib import Path

from ..common import normalize


class Accessibility:
    def __init__(self, bundle_id):
        import ApplicationServices as ax
        from AppKit import NSRunningApplication
        self.ax = ax
        if not ax.AXIsProcessTrusted():
            raise RuntimeError("Grant Accessibility permission to the MCP host/Python in System Settings, then restart it")
        apps = NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle_id)
        if len(apps) != 1:
            raise RuntimeError("Expected one running KakaoTalk application; check bundle_id")
        self.pid = apps[0].processIdentifier()
        self.root = ax.AXUIElementCreateApplication(self.pid)
        ax.AXUIElementSetMessagingTimeout(self.root, 2.0)

    def get(self, element, attribute):
        error, value = self.ax.AXUIElementCopyAttributeValue(element, attribute, None)
        if error in (self.ax.kAXErrorAttributeUnsupported, self.ax.kAXErrorNoValue):
            return None
        if error:
            raise RuntimeError(f"Accessibility read {attribute} failed: {error}")
        return value

    def set(self, element, attribute, value):
        error, writable = self.ax.AXUIElementIsAttributeSettable(element, attribute, None)
        if error or not writable:
            raise RuntimeError(f"Accessibility attribute {attribute} is not writable")
        error = self.ax.AXUIElementSetAttributeValue(element, attribute, value)
        if error:
            raise RuntimeError(f"Accessibility write failed: {error}")

    def press(self, element):
        if self.get(element, "AXEnabled") is False:
            raise RuntimeError("Accessibility control is disabled")
        error = self.ax.AXUIElementPerformAction(element, "AXPress")
        if error:
            raise RuntimeError(f"Accessibility AXPress failed: {error}")


class MacBoardDesktop:
    def __init__(self, bridge=None, profile=None):
        self._bridge = bridge
        self._profile = profile

    @property
    def profile(self):
        if self._profile is None:
            path = os.environ.get("KAKAO_MAC_PROFILE")
            if not path:
                raise RuntimeError("Set KAKAO_MAC_PROFILE to a calibrated AX selector JSON; see docs/macos.md")
            self._profile = json.loads(Path(path).read_text(encoding="utf-8"))
        return self._profile

    @property
    def ax(self):
        if self._bridge is None:
            self._bridge = Accessibility(self.profile["bundle_id"])
        return self._bridge

    def walk(self, root):
        pending = [(root, 0)]
        count = 0
        while pending:
            node, depth = pending.pop()
            count += 1
            if count > 2000 or depth > 40:
                raise RuntimeError("AX tree limit exceeded; narrow the selector scope")
            yield node
            pending.extend((child, depth + 1) for child in reversed(self.ax.get(node, "AXChildren") or []))

    def matches(self, node, selector, room):
        allowed = {"AXRole", "AXIdentifier", "AXTitle", "AXDescription"}
        if not selector or not set(selector) <= allowed or "AXRole" not in selector or len(selector) < 2:
            raise ValueError("Selectors require AXRole and an exact identifier/title/description")
        return all(self.ax.get(node, key) == value.replace("{room}", room)
                   for key, value in selector.items())

    def find(self, root, name, room, optional=False):
        selector = self.profile["selectors"][name]
        nodes = [n for n in self.walk(root) if self.matches(n, selector, room)]
        if not nodes and optional:
            return None
        if len(nodes) != 1:
            raise RuntimeError(f"Expected exactly one {name}, found {len(nodes)}; calibrate Mac profile")
        return nodes[0]

    def window(self, room):
        if not room.strip():
            raise ValueError("Exact room name required")
        selector = self.profile["selectors"]["room_window"]
        if selector.get("AXTitle") != "{room}":
            raise ValueError("room_window must bind AXTitle exactly to {room}")
        windows = self.ax.get(self.ax.root, "AXWindows") or []
        matches = [w for w in windows if self.matches(w, selector, room)]
        if len(matches) != 1:
            raise RuntimeError("Open the exact room/board window manually; absent or duplicate room windows")
        return matches[0]

    def board(self, room):
        return self.find(self.window(room), "board", room)

    def find_editor(self, room):
        return self.find(self.board(room), "editor", room, optional=True)

    def wait_for(self, operation):
        deadline = time.monotonic() + 4
        while True:
            result = operation()
            if result is not None:
                return result
            if time.monotonic() >= deadline:
                raise RuntimeError("Timed out waiting for AX UI transition; inspect KakaoTalk manually")
            time.sleep(0.1)

    def open_editor(self, room):
        editor = self.find_editor(room)
        if editor is not None:
            return editor
        self.ax.press(self.find(self.board(room), "compose", room))
        return self.wait_for(lambda: self.find_editor(room))

    def read(self, editor):
        value = self.ax.get(editor, "AXValue")
        if not isinstance(value, str):
            raise RuntimeError("Editor AXValue is not exposed as text")
        return normalize(value)

    def write(self, editor, body):
        self.ax.set(editor, "AXValue", body)

    def draft_snapshot(self, room):
        window = self.window(room)
        editor = self.find_editor(room)
        if editor is None:
            raise RuntimeError("No board draft editor open")
        return (self.ax.pid, window, editor), self.read(editor)

    def read_post(self, room, index):
        if not 0 <= index < 50:
            raise ValueError("index must be 0..49")
        board = self.board(room)
        if self.find(board, "editor", room, optional=True) is not None:
            raise RuntimeError("Close the draft manually before reading posts")
        listing = self.find(board, "post_list", room)
        rows = self.ax.get(listing, "AXRows")
        if rows is None or index >= len(rows):
            raise RuntimeError("Post not exposed in AXRows; load the list manually (no scrolling fallback)")
        # Read full body from each exposed row. Never mistake a preview for full text:
        # the profile must identify the verified full-body field, not a snippet.
        body = self.find(rows[index], "post_body", room)
        value = self.ax.get(body, "AXValue")
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError("Full post body is not exposed as AXValue")
        return normalize(value)

    def publish(self, room, identity, body):
        if self.draft_snapshot(room) != (identity, body):
            raise RuntimeError("Draft changed before publication")
        button = self.find(self.board(room), "publish", room)
        # Recheck after resolving the button. Never retry this external action.
        if self.draft_snapshot(room) != (identity, body):
            raise RuntimeError("Draft changed before publication")
        self.ax.press(button)
        return {"published": None, "state": "outcome_unknown",
                "message": "AXPress dispatched once; verify registration manually. Do not retry automatically."}

    def diagnose(self, room, include_labels=False):
        nodes = []
        for node in self.walk(self.window(room)):
            row = {key: self.ax.get(node, key) for key in ("AXRole", "AXIdentifier")}
            if include_labels:
                row.update({key: self.ax.get(node, key) for key in ("AXTitle", "AXDescription")})
            nodes.append(row)
        return {"pid": self.ax.pid, "nodes": nodes, "values_included": False}
