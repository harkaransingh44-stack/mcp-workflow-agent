"""Shared fixtures for the ticketflow tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from ticketflow.store import TicketStore


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "tickets.db"


@pytest.fixture
def store(db_path: Path) -> TicketStore:
    return TicketStore(db_path)


def pytest_configure(config: pytest.Config) -> None:
    Path("reports").mkdir(exist_ok=True)
