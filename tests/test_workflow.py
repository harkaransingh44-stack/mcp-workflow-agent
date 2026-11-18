"""Workflow tests with a mocked (or heuristic) LLM — no live API calls."""

from __future__ import annotations

from pathlib import Path

from ticketflow.llm import FlakyProvider, MockProvider, classify_text, get_provider
from ticketflow.store import TicketStore
from ticketflow.workflow import (
    IncomingRequest,
    load_requests,
    run_workflow,
    write_summary,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_mock_classifier_maps_keywords():
    result = classify_text(
        MockProvider(),
        "The customer portal is down and we cannot access dashboards. Outage.",
        requester="morgan@example.com",
    )
    assert result.category == "incident"
    assert result.priority == "urgent"
    assert result.provider == "mock"


def test_get_provider_defaults_to_mock_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("TICKETFLOW_PROVIDER", raising=False)
    assert get_provider().name == "mock"
    assert get_provider("mock").name == "mock"


def test_workflow_files_tickets_from_json(store: TicketStore):
    requests = load_requests(
        Path(__file__).resolve().parents[1] / "data" / "incoming_requests.json"
    )
    assert len(requests) == 8
    result = run_workflow(requests, store, MockProvider(), sleeper=lambda _: None)
    payload = result.to_dict()
    assert payload["failed"] == 0
    assert payload["filed"] == 8
    assert store.summarize().total == 8
    categories = {item["classification"]["category"] for item in payload["items"]}
    assert "incident" in categories
    assert "billing" in categories
    assert "access" in categories


def test_workflow_reads_csv_and_dry_run_does_not_write(store: TicketStore):
    requests = load_requests(
        Path(__file__).resolve().parents[1] / "data" / "incoming_requests.csv"
    )
    result = run_workflow(
        requests, store, MockProvider(), dry_run=True, sleeper=lambda _: None
    )
    assert result.to_dict()["filed"] == 0
    assert result.to_dict()["received"] == 2
    assert store.summarize().total == 0
    assert all(item["status"] == "classified" for item in result.to_dict()["items"])


def test_workflow_retries_flaky_provider(store: TicketStore):
    provider = FlakyProvider(MockProvider(), fail_times=2)
    requests = [
        IncomingRequest(
            id="req-retry",
            requester="a@example.com",
            message="Please reset my password.",
        )
    ]
    result = run_workflow(requests, store, provider, attempts=3, sleeper=lambda _: None)
    assert result.to_dict()["filed"] == 1
    assert provider.calls == 3
    assert store.list_tickets()[0].category == "access"


def test_workflow_records_failure_after_retries(store: TicketStore):
    provider = FlakyProvider(MockProvider(), fail_times=5)
    requests = [
        IncomingRequest(id="req-fail", requester="a@example.com", message="hello")
    ]
    result = run_workflow(requests, store, provider, attempts=2, sleeper=lambda _: None)
    assert result.to_dict()["failed"] == 1
    assert result.processed[0].ticket_id is None
    assert store.summarize().total == 0


def test_write_summary_markdown_and_json(store: TicketStore, tmp_path: Path):
    requests = [
        IncomingRequest(
            id="req-001",
            requester="alex@example.com",
            message="I was charged twice, please refund.",
        ),
    ]
    result = run_workflow(requests, store, MockProvider(), sleeper=lambda _: None)
    md_path = tmp_path / "summary.md"
    json_path = tmp_path / "summary.json"
    write_summary(result, md_path, store=store)
    write_summary(result, json_path, store=store)
    markdown = md_path.read_text(encoding="utf-8")
    assert "Ticket intake summary" in markdown
    assert "req-001" in markdown
    assert "billing" in markdown
    assert '"filed": 1' in json_path.read_text(encoding="utf-8")
