"""Bounded board reading and separately confirmed one-shot publishing."""
import hashlib
import secrets
import threading
import time

from .common import normalize


class BoardActions:
    def __init__(self, desktop, clock=time.monotonic, lock=None):
        self.desktop = desktop
        self.clock = clock
        self.lock = lock or threading.RLock()
        self.tickets = {}
        self.cache = {}

    def invalidate_cache(self, room_name):
        self.cache = {k: v for k, v in self.cache.items() if k[0] != room_name}

    def prepare_publish(self, room_name):
        with self.lock:
            self.invalidate_cache(room_name)
            try:
                identity, body = self.desktop.draft_snapshot(room_name)
                if not body.strip():
                    raise ValueError("Draft is empty")
                # One pending ticket per room; no content persisted to disk.
                self.tickets = {t: v for t, v in self.tickets.items()
                                if v["room_name"] != room_name and v["expires"] > self.clock()}
                token = secrets.token_urlsafe(24)
                self.tickets[token] = dict(room_name=room_name, identity=identity,
                                          body=body, expires=self.clock() + 300)
                return {"success": True, "published": False, "room_name": room_name,
                        "body": body, "confirmation_token": token, "expires_in_seconds": 300,
                        "message": "Show this room and body to the user. Publish only on their explicit request."}
            except Exception as exc:
                return {"success": False, "published": False, "error": str(exc)}

    def _validate(self, token):
        ticket = self.tickets.get(token)
        if not ticket or ticket["expires"] <= self.clock():
            self.tickets.pop(token, None)
            raise ValueError("Unknown, used or expired confirmation token; prepare a fresh preview")
        identity, body = self.desktop.draft_snapshot(ticket["room_name"])
        if identity != ticket["identity"] or body != ticket["body"]:
            self.tickets.pop(token, None)
            raise ValueError("Draft window or body changed; prepare a fresh preview")
        return ticket

    def check_publish(self, token):
        with self.lock:
            try:
                ticket = self._validate(token)
                return {"success": True, "ready": True, "published": False,
                        "room_name": ticket["room_name"], "body": ticket["body"]}
            except Exception as exc:
                return {"success": False, "ready": False, "published": False, "error": str(exc)}

    def publish(self, token, confirm=False):
        with self.lock:
            if confirm is not True:
                return {"success": False, "published": False, "error": "Explicit confirm=true required"}
            try:
                ticket = self._validate(token)
            except Exception as exc:
                return {"success": False, "published": False, "error": str(exc)}
            # Consume BEFORE any external action: unknown results cannot be retried.
            del self.tickets[token]
            try:
                result = self.desktop.publish(ticket["room_name"], ticket["identity"], ticket["body"])
                return {"success": result.get("published") is True, **result}
            except Exception as exc:
                return {"success": False, "published": None, "state": "outcome_unknown",
                        "error": str(exc), "message": "Do not retry automatically. Inspect the board manually."}

    def read(self, room_name, index=0):
        with self.lock:
            try:
                if not room_name.strip() or not 0 <= index < 50:
                    raise ValueError("room_name and index 0..49 required")
                body = self.desktop.read_post(room_name, index)
                return {"success": True, "room_name": room_name, "index": index, "body": body,
                        "source": "KakaoTalk board text copy", "attachments_read": False,
                        "index_is_stable_id": False}
            except Exception as exc:
                return {"success": False, "error": str(exc)}

    def search(self, room_name, query, max_posts=10, refresh=False):
        with self.lock:
            if not room_name.strip() or not query.strip() or not 1 <= max_posts <= 50:
                return {"success": False, "error": "room_name, nonempty query and max_posts 1..50 required"}
            # Only text read results are cached; publish checks always use the UI.
            key = (room_name, max_posts)
            self.cache = {k: v for k, v in self.cache.items() if self.clock() - v[0] < 30}
            cached = self.cache.get(key)
            if cached and not refresh:
                timestamp, result = cached
                return {**result, "query": query, "cache_hit": True,
                        "cache_age_seconds": round(self.clock() - timestamp, 3),
                        "matches": [p.copy() for p in result["posts"] if query.casefold() in p["body"].casefold()],
                        "posts": None}
            self.cache.pop(key, None)
            posts, seen = [], set()
            scanned = 0
            stop_reason = "limit_reached"
            error = None
            for index in range(max_posts):
                try:
                    body = self.desktop.read_post(room_name, index)
                except Exception as exc:
                    stop_reason, error = "read_failed", str(exc)
                    break
                fingerprint = hashlib.sha256(body.encode("utf-8")).digest()
                if fingerprint in seen:
                    # Could be end-of-list OR two identical posts; never claim exhaustive.
                    stop_reason = "repeated_content"
                    break
                seen.add(fingerprint)
                scanned += 1
                posts.append({"index": index, "body": body})
            result = {"success": error is None, "room_name": room_name,
                    "posts": posts, "scanned": scanned, "complete": False,
                    "stop_reason": stop_reason, "error": error,
                    "scope": "Current board list from its first item; copied body text only, not attachments"}
            if error is None:
                # Bound memory to the latest eight scans, never write chat text to disk.
                if len(self.cache) >= 8:
                    oldest = min(self.cache, key=lambda k: self.cache[k][0])
                    del self.cache[oldest]
                self.cache[key] = (self.clock(), result)
            return {**result, "query": query, "posts": None, "cache_hit": False,
                    "cache_age_seconds": 0,
                    "matches": [p.copy() for p in posts if query.casefold() in p["body"].casefold()]}
