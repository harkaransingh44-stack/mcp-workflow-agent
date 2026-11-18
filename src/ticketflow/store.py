"""SQLite-backed ticket store used by both the MCP server and the workflow agent."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from ticketflow.models import CATEGORIES, PRIORITIES, STATUSES, Ticket, TicketSummary

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    requester TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'other',
    priority TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _normalize(value: str, allowed: tuple[str, ...], default: str) -> str:
    cleaned = (value or "").strip().lower().replace(" ", "_").replace("-", "_")
    return cleaned if cleaned in allowed else default


class TicketStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        if self.db_path.parent != Path("."):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def create_ticket(
        self,
        title: str,
        body: str,
        requester: str = "",
        category: str = "other",
        priority: str = "medium",
        status: str = "open",
    ) -> Ticket:
        title = (title or "").strip()
        if not title:
            raise ValueError("title is required")
        now = _now()
        values = (
            title,
            body or "",
            requester or "",
            _normalize(category, CATEGORIES, "other"),
            _normalize(priority, PRIORITIES, "medium"),
            _normalize(status, STATUSES, "open"),
            now,
            now,
        )
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO tickets (
                    title, body, requester, category, priority,
                    status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            ticket_id = int(cur.lastrowid)
        ticket = self.get_ticket(ticket_id)
        assert ticket is not None
        return ticket

    def get_ticket(self, ticket_id: int) -> Ticket | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM tickets WHERE id = ?", (ticket_id,)
            ).fetchone()
        return _row_to_ticket(row) if row else None

    def list_tickets(
        self,
        status: str | None = None,
        category: str | None = None,
        priority: str | None = None,
        limit: int = 50,
    ) -> list[Ticket]:
        clauses: list[str] = []
        params: list[object] = []
        if status:
            clauses.append("status = ?")
            params.append(_normalize(status, STATUSES, status))
        if category:
            clauses.append("category = ?")
            params.append(_normalize(category, CATEGORIES, category))
        if priority:
            clauses.append("priority = ?")
            params.append(_normalize(priority, PRIORITIES, priority))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit = max(1, min(int(limit), 500))
        sql = f"SELECT * FROM tickets {where} ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_ticket(row) for row in rows]

    def update_status(self, ticket_id: int, status: str) -> Ticket:
        ticket = self.get_ticket(ticket_id)
        if ticket is None:
            raise KeyError(f"ticket {ticket_id} not found")
        new_status = _normalize(status, STATUSES, "")
        if new_status not in STATUSES:
            raise ValueError(f"invalid status {status!r}; expected one of {STATUSES}")
        with self._connect() as conn:
            conn.execute(
                "UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?",
                (new_status, _now(), ticket_id),
            )
        updated = self.get_ticket(ticket_id)
        assert updated is not None
        return updated

    def summarize(self) -> TicketSummary:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) AS n FROM tickets").fetchone()["n"]
            by_status = {
                row["status"]: row["n"]
                for row in conn.execute(
                    "SELECT status, COUNT(*) AS n FROM tickets GROUP BY status"
                )
            }
            by_priority = {
                row["priority"]: row["n"]
                for row in conn.execute(
                    "SELECT priority, COUNT(*) AS n FROM tickets GROUP BY priority"
                )
            }
            by_category = {
                row["category"]: row["n"]
                for row in conn.execute(
                    "SELECT category, COUNT(*) AS n FROM tickets GROUP BY category"
                )
            }
        open_like = sum(by_status.get(s, 0) for s in ("open", "in_progress"))
        return TicketSummary(
            total=int(total),
            open_or_in_progress=int(open_like),
            by_status=by_status,
            by_priority=by_priority,
            by_category=by_category,
        )


def _row_to_ticket(row: sqlite3.Row) -> Ticket:
    return Ticket(
        id=int(row["id"]),
        title=row["title"],
        body=row["body"],
        requester=row["requester"],
        category=row["category"],
        priority=row["priority"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
