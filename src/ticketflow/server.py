"""MCP server that exposes ticket-tracker tools over stdio.

The tools wrap :class:`ticketflow.store.TicketStore`. The workflow agent can
call the same store directly; Claude Desktop talks to this process over stdio.
"""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server import MCPServer

from ticketflow.models import Ticket, TicketSummary
from ticketflow.store import TicketStore

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "tickets.db"


def create_server(db_path: str | Path | None = None) -> MCPServer:
    """Build an MCP server bound to a specific SQLite file."""
    path = Path(db_path or os.getenv("TICKET_DB_PATH", str(DEFAULT_DB)))
    store = TicketStore(path)
    server = MCPServer("ticket-tracker")

    @server.tool()
    def create_ticket(
        title: str,
        body: str,
        requester: str = "",
        category: str = "other",
        priority: str = "medium",
    ) -> Ticket:
        """Create a support ticket and return its stored fields.

        category must be one of: access, billing, bug, feature, incident, other.
        priority must be one of: low, medium, high, urgent.
        """
        return store.create_ticket(
            title=title,
            body=body,
            requester=requester,
            category=category,
            priority=priority,
        )

    @server.tool()
    def list_tickets(
        status: str = "",
        category: str = "",
        priority: str = "",
        limit: int = 50,
    ) -> list[Ticket]:
        """List tickets, optionally filtered by status, category, or priority."""
        return store.list_tickets(
            status=status or None,
            category=category or None,
            priority=priority or None,
            limit=limit,
        )

    @server.tool()
    def update_status(ticket_id: int, status: str) -> Ticket:
        """Set a ticket's status to open, in_progress, resolved, or closed."""
        return store.update_status(ticket_id, status)

    @server.tool()
    def summarize() -> TicketSummary:
        """Return ticket counts by status, priority, and category."""
        return store.summarize()

    # Stash the store for tests and for the agent when it wants the same instance.
    server.ticket_store = store  # type: ignore[attr-defined]
    return server


# Module-level server so `mcp run` / `python -m ticketflow.server` can find it.
mcp = create_server()


def main() -> None:
    """Start the MCP server on stdio (the default transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
