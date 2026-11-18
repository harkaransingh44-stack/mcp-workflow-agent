"""Tests for the retry helper."""

from __future__ import annotations

import pytest

from ticketflow.retries import RetryError, backoff_seconds, retry_call


def test_backoff_without_jitter_is_exponential_and_capped():
    assert backoff_seconds(1, base=0.25, factor=2, cap=1.0, jitter=False) == 0.25
    assert backoff_seconds(2, base=0.25, factor=2, cap=1.0, jitter=False) == 0.5
    assert backoff_seconds(5, base=0.25, factor=2, cap=1.0, jitter=False) == 1.0


def test_retry_call_eventually_succeeds(monkeypatch):
    sleeps: list[float] = []
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("not yet")
        return "ok"

    result = retry_call(
        flaky,
        attempts=3,
        jitter=False,
        base=0.1,
        cap=1.0,
        sleeper=sleeps.append,
        retry_on=(TimeoutError,),
    )
    assert result == "ok"
    assert calls["n"] == 3
    assert sleeps == [0.1, 0.2]


def test_retry_call_raises_after_last_attempt():
    def always_fail():
        raise RuntimeError("nope")

    with pytest.raises(RetryError) as exc_info:
        retry_call(always_fail, attempts=2, jitter=False, sleeper=lambda _: None)
    assert exc_info.value.attempts == 2
    assert "nope" in str(exc_info.value)
