"""心跳校验的宽限策略（纯逻辑，不依赖 Qt，便于单元测试）。"""

from __future__ import annotations

import time


class HeartbeatPolicy:
    def __init__(self, interval_seconds: int = 1800, grace_seconds: int = 600):
        self.interval_seconds = interval_seconds
        self.grace_seconds = grace_seconds
        self._consecutive_failures = 0
        self._first_failure_at: float | None = None

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._first_failure_at = None

    def record_failure(self, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        self._consecutive_failures += 1
        if self._first_failure_at is None:
            self._first_failure_at = now

    def should_lock(self, now: float | None = None) -> bool:
        if self._first_failure_at is None:
            return False
        now = now if now is not None else time.time()
        return now - self._first_failure_at >= self.grace_seconds
