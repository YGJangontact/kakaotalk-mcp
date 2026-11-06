# Platform-independent board draft service.
import threading
from .common import EMPTY_HINT, unique, normalize


class BoardDrafts:
    def __init__(self, desktop):
        self.desktop = desktop
        self.lock = threading.RLock()

    def prepare(self, room_name, body):
        with self.lock:
            try:
                if not room_name.strip() or not body.strip() or "\x00" in body:
                    raise ValueError("room_name and nonempty body without NUL are required")
                if body == EMPTY_HINT:
                    raise ValueError("The built-in empty-editor hint is reserved")
                editor = self.desktop.open_editor(room_name)
                existing = normalize(self.desktop.read(editor))
                desired = normalize(body)
                if existing and existing != desired:
                    raise RuntimeError("Existing draft preserved; clear it manually before preparing another")
                if not existing:
                    self.desktop.write(editor, desired)
                actual = normalize(self.desktop.read(editor))
                if actual != desired:
                    raise RuntimeError("Draft readback mismatch; inspect the editor before retrying")
                return {"success": True, "published": False, "state": "draft_ready",
                        "room_name": room_name, "body": actual,
                        "message": "Draft verified. Registration has NOT been clicked."}
            except Exception as exc:
                return {"success": False, "published": False, "error": str(exc)}

    def status(self, room_name):
        with self.lock:
            try:
                editor = self.desktop.find_editor(room_name)
                if not editor:
                    return {"success": True, "state": "editor_not_open", "room_name": room_name}
                return {"success": True, "state": "editor_open", "room_name": room_name,
                        "body": normalize(self.desktop.read(editor))}
            except Exception as exc:
                return {"success": False, "error": str(exc)}
