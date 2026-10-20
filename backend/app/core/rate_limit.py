"""Process-local sliding-window rate limiting for authentication endpoints."""

from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Iterable


class SlidingWindowRateLimiter:
    """A bounded in-memory limiter suitable for a single backend process.

    Multi-instance deployments need a shared store (for example Redis); this is
    documented as a limitation and revisited during deployment hardening.
    """

    def __init__(self, max_keys: int = 10_000) -> None:
        self._max_keys = max_keys
        self._events: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    def consume(
        self, keys: Iterable[str], limit: int, window_seconds: int
    ) -> int | None:
        """Record an attempt and return a retry delay when any key is limited."""

        now = time.monotonic()
        cutoff = now - window_seconds

        with self._lock:
            for key in keys:
                events = self._events.get(key)
                if not events:
                    continue
                self._prune(events, cutoff)
                if len(events) >= limit:
                    return max(1, math.ceil(events[0] + window_seconds - now))

            for key in keys:
                events = self._events.get(key)
                if events is None:
                    events = deque()
                    self._events[key] = events
                self._prune(events, cutoff)
                events.append(now)
                self._events.move_to_end(key)

            while len(self._events) > self._max_keys:
                self._events.popitem(last=False)

        return None

    def reset(self) -> None:
        with self._lock:
            self._events.clear()

    @staticmethod
    def _prune(events: deque[float], cutoff: float) -> None:
        while events and events[0] <= cutoff:
            events.popleft()


auth_rate_limiter = SlidingWindowRateLimiter()
