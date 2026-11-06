"""Lossless in-memory clipboard preservation for byte/string Win32 formats.

The API is injected so these contracts can be tested without a desktop.
"""
import time


class ClipboardTransaction:
    def __init__(self, api):
        self.api = api
        self.saved = {}
        self.owned_sequence = None

    def open(self):
        deadline = time.monotonic() + 1
        while True:
            try:
                self.api.OpenClipboard()
                return
            except Exception:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.02)

    def __enter__(self):
        self.open()
        try:
            formats = []
            current = self.api.EnumClipboardFormats(0)
            while current:
                formats.append(current)
                current = self.api.EnumClipboardFormats(current)
            total = 0
            for fmt in formats:
                # CF_BITMAP is a handle; DIB data can recreate this synthesized format.
                if fmt == 2 and (8 in formats or 17 in formats):
                    continue
                value = self.api.GetClipboardData(fmt)
                if not isinstance(value, (str, bytes)):
                    raise RuntimeError(f"Clipboard format {fmt}: cannot safely preserve native handle/file list")
                total += len(value) * (2 if isinstance(value, str) else 1)
                if total > 32 * 1024 * 1024:
                    raise RuntimeError("Clipboard exceeds 32 MiB preservation limit; unchanged")
                self.saved[fmt] = value
            self.sequence = self.api.GetClipboardSequenceNumber()
            return self
        finally:
            self.api.CloseClipboard()

    def put_text(self, text):
        self.open()
        try:
            if self.api.GetClipboardSequenceNumber() != self.sequence:
                raise RuntimeError("Clipboard changed before paste; unchanged")
            self.api.EmptyClipboard()
            try:
                self.api.SetClipboardData(13, text)  # CF_UNICODETEXT
            finally:
                self.owned_sequence = self.api.GetClipboardSequenceNumber()
        finally:
            self.api.CloseClipboard()

    def mark_copied(self):
        self.owned_sequence = self.api.GetClipboardSequenceNumber()

    def __exit__(self, *exception):
        if self.owned_sequence is None:
            return
        self.open()
        try:
            if self.api.GetClipboardSequenceNumber() == self.owned_sequence:
                self.api.EmptyClipboard()
                for fmt, value in self.saved.items():
                    self.api.SetClipboardData(fmt, value)
        finally:
            self.api.CloseClipboard()
