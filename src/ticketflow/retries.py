"""Exponential backoff with a cap and optional jitter."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class RetryError(Exception):
    """Raised when a function still fails after the last attempt."""

    def __init__(self, attempts: int, last_error: BaseException) -> None:
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(f"failed after {attempts} attempts: {last_error}")


def backoff_seconds(
    attempt: int,
    base: float = 0.25,
    factor: float = 2.0,
    cap: float = 4.0,
    jitter: bool = True,
) -> float:
    """Return the sleep time before the next attempt. *attempt* is 1-based."""
    delay = min(cap, base * (factor ** (attempt - 1)))
    if jitter:
        delay = delay * (0.5 + random.random())
    return delay


def retry_call(
    func: Callable[[], T],
    *,
    attempts: int = 3,
    base: float = 0.25,
    factor: float = 2.0,
    cap: float = 4.0,
    jitter: bool = True,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    on_retry: Callable[[int, BaseException, float], None] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> T:
    """Call *func* up to *attempts* times. Retry on *retry_on* exceptions."""
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except retry_on as exc:
            last_error = exc
            if attempt >= attempts:
                break
            delay = backoff_seconds(
                attempt, base=base, factor=factor, cap=cap, jitter=jitter
            )
            if on_retry:
                on_retry(attempt, exc, delay)
            sleeper(delay)
    assert last_error is not None
    raise RetryError(attempts, last_error) from last_error
