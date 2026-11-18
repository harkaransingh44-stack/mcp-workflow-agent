"""LLM providers used to classify incoming requests.

Mock mode is the default when ANTHROPIC_API_KEY is unset, so the workflow
runs offline. The Anthropic provider is used when a key is present (or when
the caller asks for it explicitly).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Protocol

from ticketflow.models import CATEGORIES, PRIORITIES

CLASSIFY_SYSTEM_PROMPT = """You classify incoming support requests for a ticket tracker.

Return a single JSON object with exactly these keys:
- title: a short ticket title, max 80 characters
- category: one of access, billing, bug, feature, incident, other
- priority: one of low, medium, high, urgent
- summary: one or two sentences describing the request

Do not include markdown or any text outside the JSON object.
"""


@dataclass
class Classification:
    title: str
    category: str
    priority: str
    summary: str
    raw: str
    provider: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "category": self.category,
            "priority": self.priority,
            "summary": self.summary,
            "provider": self.provider,
        }


class LLMProvider(Protocol):
    name: str

    def complete(self, system: str, user: str) -> str: ...


class MockProvider:
    """Deterministic, keyword-based classifier. No network, no API key."""

    name = "mock"

    def __init__(self, scripted: dict[str, str] | None = None) -> None:
        self.scripted = scripted or {}

    def complete(self, system: str, user: str) -> str:
        if user in self.scripted:
            return self.scripted[user]
        return json.dumps(_heuristic_classify(user))


class FlakyProvider:
    """Fails the first *fail_times* calls, then delegates to *inner*. Used in tests."""

    name = "flaky"

    def __init__(self, inner: LLMProvider, fail_times: int = 2) -> None:
        self.inner = inner
        self.fail_times = fail_times
        self.calls = 0

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise TimeoutError(f"simulated LLM timeout on attempt {self.calls}")
        return self.inner.complete(system, user)


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "the anthropic package is required for the Anthropic provider"
            ) from exc
        key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        self._client = anthropic.Anthropic(api_key=key)
        self.model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")

    def complete(self, system: str, user: str) -> str:
        message = self._client.messages.create(
            model=self.model,
            max_tokens=512,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts = [
            block.text
            for block in message.content
            if getattr(block, "type", "") == "text"
        ]
        return "\n".join(parts).strip()


def get_provider(name: str | None = None) -> LLMProvider:
    """Return a provider. Default is mock when no API key is set, else anthropic."""
    requested = (name or os.getenv("TICKETFLOW_PROVIDER") or "").strip().lower()
    if requested in {"mock", "dry-run", "dry_run"}:
        return MockProvider()
    if requested == "anthropic":
        return AnthropicProvider()
    if requested:
        raise ValueError(f"unknown provider {name!r}")
    if os.getenv("ANTHROPIC_API_KEY"):
        return AnthropicProvider()
    return MockProvider()


def classify_text(
    provider: LLMProvider, request_text: str, requester: str = ""
) -> Classification:
    user = _build_user_prompt(request_text, requester)
    raw = provider.complete(CLASSIFY_SYSTEM_PROMPT, user)
    data = _parse_classification_json(raw)
    title = str(data.get("title") or _fallback_title(request_text)).strip()[:80]
    category = _one_of(str(data.get("category", "")), CATEGORIES, "other")
    priority = _one_of(str(data.get("priority", "")), PRIORITIES, "medium")
    summary = str(data.get("summary") or request_text[:200]).strip()
    return Classification(
        title=title or "Untitled request",
        category=category,
        priority=priority,
        summary=summary,
        raw=raw,
        provider=provider.name,
    )


def _build_user_prompt(request_text: str, requester: str) -> str:
    who = f"Requester: {requester}\n" if requester else ""
    return f"{who}Incoming request:\n{request_text.strip()}"


def _parse_classification_json(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if match:
        data = json.loads(match.group(0))
        if isinstance(data, dict):
            return data
    raise ValueError(f"classifier did not return JSON: {raw[:200]!r}")


def _one_of(value: str, allowed: tuple[str, ...], default: str) -> str:
    cleaned = value.strip().lower().replace(" ", "_").replace("-", "_")
    return cleaned if cleaned in allowed else default


def _fallback_title(text: str) -> str:
    first = text.strip().splitlines()[0] if text.strip() else "Untitled request"
    return first[:80]


def _heuristic_classify(user: str) -> dict[str, str]:
    text = user.lower()
    category = "other"
    priority = "medium"
    if any(
        word in text
        for word in (
            "down",
            "outage",
            "cannot access",
            "can't access",
            "offline",
            "p0",
            "sev-1",
            "sev1",
        )
    ):
        category, priority = "incident", "urgent"
    elif any(
        word in text for word in ("password", "login", "locked out", "mfa", "reset my")
    ):
        category, priority = "access", "high"
    elif any(
        word in text for word in ("invoice", "charged", "refund", "billing", "payment")
    ):
        category, priority = "billing", "medium"
    elif any(
        word in text for word in ("traceback", "error", "bug", "broken", "500", "crash")
    ):
        category, priority = "bug", "high"
    elif any(
        word in text
        for word in ("feature", "would be nice", "please add", "enhancement")
    ):
        category, priority = "feature", "low"

    title_source = user
    if "incoming request:" in text:
        title_source = user.split("Incoming request:", 1)[-1]
    title = _fallback_title(title_source)
    if title.lower().startswith("requester"):
        title = _fallback_title(title_source.split("\n", 1)[-1])
    return {
        "title": title[:80],
        "category": category,
        "priority": priority,
        "summary": " ".join(title_source.split())[:240],
    }
