"""uma4a_fetch — reading a document a peer, or a stranger, names.

An agent's request names URLs this server then reads: its client metadata,
its operator's key directory, the issuer of its agent token. Those reads
happen before anything about the agent is believed, so every one is bounded
the same way — https only, no redirects, one deadline for the whole exchange
rather than for each read, and a cap on the bytes taken — and a caller on an
event loop runs it in a thread, so one slow origin holds up one request and
not the server.

`FailureFloor` is the other half: an origin that has just failed is not asked
again until a minute has passed, whoever asks, so a requester cannot make
this server fetch a failing URL once per request.
"""

from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict

DEADLINE_S = 5.0
MAX_BYTES = 256 * 1024
FAILURE_FLOOR_S = 60.0


def get_json(url: str, *, verify=True, deadline_s: float = DEADLINE_S,
             max_bytes: int = MAX_BYTES) -> dict:
    """GET `url` and return its JSON object, or raise naming what was wrong."""
    import httpx

    if not url.startswith("https://"):
        raise ValueError(f"{url} is not https")
    started = time.monotonic()
    body = bytearray()
    with httpx.Client(verify=verify, timeout=deadline_s,
                      follow_redirects=False) as client:
        with client.stream("GET", url) as r:
            r.raise_for_status()
            for chunk in r.iter_bytes():
                body += chunk
                if len(body) > max_bytes:
                    raise ValueError(f"{url} returned more than {max_bytes} bytes")
                if time.monotonic() - started > deadline_s:
                    raise TimeoutError(f"{url} took longer than {deadline_s:g}s")
    doc = json.loads(body)
    if not isinstance(doc, dict):
        raise ValueError(f"{url} did not return a JSON object")
    return doc


class FailureFloor:
    """Remembers which keys failed recently, boundedly.

    `check(key)` raises with the original reason while the floor holds;
    `failed(key, reason)` starts it; `cleared(key)` ends it on a success.
    """

    def __init__(self, floor_s: float = FAILURE_FLOOR_S, max_entries: int = 1024,
                 clock=time.time):
        self.floor_s, self.max_entries, self._clock = floor_s, max_entries, clock
        self._failed: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        with self._lock:
            hit = self._failed.get(key)
        if hit and self._clock() - hit[0] < self.floor_s:
            raise RuntimeError(f"{hit[1]} (not retried for "
                               f"{self.floor_s - (self._clock() - hit[0]):.0f}s)")

    def failed(self, key: str, reason: str) -> None:
        with self._lock:
            self._failed.pop(key, None)
            self._failed[key] = (self._clock(), reason)
            while len(self._failed) > self.max_entries:
                self._failed.popitem(last=False)

    def cleared(self, key: str) -> None:
        with self._lock:
            self._failed.pop(key, None)


class BoundedCache(OrderedDict):
    """A dict that forgets its oldest entry past `max_entries`."""

    def __init__(self, max_entries: int = 1024):
        super().__init__()
        self.max_entries = max_entries

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.move_to_end(key)
        while len(self) > self.max_entries:
            self.popitem(last=False)
