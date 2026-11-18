"""Unit tests for the SQLite ticket store."""

from __future__ import annotations

import pytest

from ticketflow.store import TicketStore


def test_create_and_get_ticket(store: TicketStore):
    ticket = store.create_ticket(
        title="Reset login",
        body="User is locked out",
        requester="alex@example.com",
        category="access",
        priority="high",
    )
    assert ticket.id == 1
    assert ticket.status == "open"
    assert ticket.created_at
    fetched = store.get_ticket(ticket.id)
    assert fetched is not None
    assert fetched.title == "Reset login"
    assert fetched.category == "access"


def test_create_ticket_requires_title(store: TicketStore):
    with pytest.raises(ValueError, match="title is required"):
        store.create_ticket(title="  ", body="empty")


def test_unknown_category_and_priority_fall_back(store: TicketStore):
    ticket = store.create_ticket(
        title="Hello", body="x", category="not-a-category", priority="super-high"
    )
    assert ticket.category == "other"
    assert ticket.priority == "medium"


def test_list_filters_and_update_status(store: TicketStore):
    first = store.create_ticket(title="A", body="a", category="bug", priority="high")
    store.create_ticket(title="B", body="b", category="billing", priority="low")
    store.update_status(first.id, "in_progress")

    open_bugs = store.list_tickets(category="bug", status="in_progress")
    assert [t.id for t in open_bugs] == [first.id]

    with pytest.raises(KeyError):
        store.update_status(999, "closed")
    with pytest.raises(ValueError, match="invalid status"):
        store.update_status(first.id, "done")


def test_summarize_counts(store: TicketStore):
    store.create_ticket(title="A", body="a", category="bug", priority="high")
    store.create_ticket(title="B", body="b", category="bug", priority="low")
    second = store.create_ticket(
        title="C", body="c", category="billing", priority="low"
    )
    store.update_status(second.id, "resolved")

    summary = store.summarize()
    assert summary.total == 3
    assert summary.open_or_in_progress == 2
    assert summary.by_category["bug"] == 2
    assert summary.by_status["resolved"] == 1
    assert summary.by_priority["low"] == 2
