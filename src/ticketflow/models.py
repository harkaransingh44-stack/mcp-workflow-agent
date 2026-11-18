"""Shared types for the ticket store."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Priority = Literal["low", "medium", "high", "urgent"]
Status = Literal["open", "in_progress", "resolved", "closed"]
Category = Literal["access", "billing", "bug", "feature", "incident", "other"]

PRIORITIES: tuple[str, ...] = ("low", "medium", "high", "urgent")
STATUSES: tuple[str, ...] = ("open", "in_progress", "resolved", "closed")
CATEGORIES: tuple[str, ...] = (
    "access",
    "billing",
    "bug",
    "feature",
    "incident",
    "other",
)


class Ticket(BaseModel):
    id: int
    title: str
    body: str
    requester: str
    category: str
    priority: str
    status: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class TicketSummary(BaseModel):
    total: int
    open_or_in_progress: int
    by_status: dict[str, int] = Field(default_factory=dict)
    by_priority: dict[str, int] = Field(default_factory=dict)
    by_category: dict[str, int] = Field(default_factory=dict)
