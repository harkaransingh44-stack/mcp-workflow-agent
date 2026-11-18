"""In-memory MCP client tests against the ticket-tracker server."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from mcp import Client
from mcp.types import TextContent

from ticketflow.server import create_server


def payload(result) -> Any:
    """Prefer structured_content; fall back to JSON in the text block."""
    if result.structured_content is not None:
        data = result.structured_content
        if isinstance(data, dict) and set(data.keys()) == {"result"}:
            return data["result"]
        return data
    for block in result.content or []:
        if isinstance(block, TextContent):
            return json.loads(block.text)
    raise AssertionError(f"no payload in tool result: {result!r}")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client(tmp_path: Path):
    server = create_server(tmp_path / "tickets.db")
    async with Client(server, raise_exceptions=True) as connected:
        yield connected


@pytest.mark.anyio
async def test_list_tools_includes_expected_names(client: Client):
    result = await client.list_tools()
    names = sorted(tool.name for tool in result.tools)
    assert names == ["create_ticket", "list_tickets", "summarize", "update_status"]


@pytest.mark.anyio
async def test_create_list_update_and_summarize(client: Client):
    created = await client.call_tool(
        "create_ticket",
        {
            "title": "Portal outage",
            "body": "Dashboards are down",
            "requester": "morgan@example.com",
            "category": "incident",
            "priority": "urgent",
        },
    )
    assert created.is_error is False
    ticket = payload(created)
    assert ticket["title"] == "Portal outage"
    assert ticket["status"] == "open"
    ticket_id = ticket["id"]

    updated = await client.call_tool(
        "update_status", {"ticket_id": ticket_id, "status": "in_progress"}
    )
    assert payload(updated)["status"] == "in_progress"

    listed = await client.call_tool("list_tickets", {"status": "in_progress"})
    ids = [item["id"] for item in payload(listed)]
    assert ticket_id in ids

    summary = payload(await client.call_tool("summarize", {}))
    assert summary["total"] == 1
    assert summary["by_priority"]["urgent"] == 1
    assert summary["by_status"]["in_progress"] == 1
