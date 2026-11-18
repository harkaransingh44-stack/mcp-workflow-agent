"""Read incoming requests, classify them, file tickets, and write a summary."""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ticketflow.llm import Classification, LLMProvider, classify_text
from ticketflow.logging_config import log
from ticketflow.retries import RetryError, retry_call
from ticketflow.store import TicketStore

logger = logging.getLogger("ticketflow")


@dataclass
class IncomingRequest:
    id: str
    requester: str
    message: str


@dataclass
class ProcessedRequest:
    request_id: str
    requester: str
    classification: Classification | None
    ticket_id: int | None
    status: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "requester": self.requester,
            "classification": self.classification.to_dict()
            if self.classification
            else None,
            "ticket_id": self.ticket_id,
            "status": self.status,
            "error": self.error,
        }


@dataclass
class WorkflowResult:
    processed: list[ProcessedRequest] = field(default_factory=list)
    dry_run: bool = False
    provider: str = "mock"

    def to_dict(self) -> dict[str, Any]:
        filed = sum(1 for item in self.processed if item.ticket_id is not None)
        failed = sum(1 for item in self.processed if item.status == "failed")
        return {
            "provider": self.provider,
            "dry_run": self.dry_run,
            "received": len(self.processed),
            "filed": filed,
            "failed": failed,
            "items": [item.to_dict() for item in self.processed],
        }


def load_requests(path: str | Path) -> list[IncomingRequest]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _load_csv(path)
    if suffix in {".json", ".jsonl"}:
        return _load_json(path)
    raise ValueError(f"unsupported input format: {path.suffix}")


def run_workflow(
    requests: list[IncomingRequest],
    store: TicketStore,
    provider: LLMProvider,
    *,
    dry_run: bool = False,
    attempts: int = 3,
    sleeper=None,
) -> WorkflowResult:
    """Classify each request and optionally file a ticket.

    When *dry_run* is true, tickets are not written to the store.
    Classification still runs (against the mock or the live provider).
    """
    result = WorkflowResult(dry_run=dry_run, provider=provider.name)
    retry_kwargs: dict[str, Any] = {
        "attempts": attempts,
        "jitter": False,
        "base": 0.05,
        "cap": 0.4,
    }
    if sleeper is not None:
        retry_kwargs["sleeper"] = sleeper

    for request in requests:
        log(
            logger,
            logging.INFO,
            "processing request",
            request_id=request.id,
            requester=request.requester,
            provider=provider.name,
        )
        try:
            classification = retry_call(
                lambda req=request: classify_text(provider, req.message, req.requester),
                on_retry=lambda attempt, exc, delay, req_id=request.id: log(
                    logger,
                    logging.WARNING,
                    "classifier retry",
                    request_id=req_id,
                    attempt=attempt,
                    error=str(exc),
                    sleep=delay,
                ),
                **retry_kwargs,
            )
        except (RetryError, ValueError) as exc:
            log(
                logger,
                logging.ERROR,
                "classification failed",
                request_id=request.id,
                error=str(exc),
            )
            result.processed.append(
                ProcessedRequest(
                    request_id=request.id,
                    requester=request.requester,
                    classification=None,
                    ticket_id=None,
                    status="failed",
                    error=str(exc),
                )
            )
            continue

        ticket_id = None
        if not dry_run:
            ticket = store.create_ticket(
                title=classification.title,
                body=_ticket_body(request, classification),
                requester=request.requester,
                category=classification.category,
                priority=classification.priority,
            )
            ticket_id = ticket.id
            log(
                logger,
                logging.INFO,
                "filed ticket",
                request_id=request.id,
                ticket_id=ticket_id,
                category=classification.category,
                priority=classification.priority,
            )

        result.processed.append(
            ProcessedRequest(
                request_id=request.id,
                requester=request.requester,
                classification=classification,
                ticket_id=ticket_id,
                status="classified" if dry_run else "filed",
            )
        )
    return result


def write_summary(
    result: WorkflowResult, path: str | Path, store: TicketStore | None = None
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = result.to_dict()
    if store is not None and not result.dry_run:
        payload["tracker"] = store.summarize().model_dump()
    if path.suffix.lower() == ".json":
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return
    path.write_text(_to_markdown(payload), encoding="utf-8")


def _to_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Ticket intake summary",
        "",
        f"- Provider: `{payload['provider']}`",
        f"- Dry run: {payload['dry_run']}",
        f"- Received: {payload['received']}",
        f"- Filed: {payload['filed']}",
        f"- Failed: {payload['failed']}",
        "",
        "| Request | Requester | Title | Category | Priority | Ticket | Status |",
        "|---------|-----------|-------|----------|----------|--------|--------|",
    ]
    for item in payload["items"]:
        classification = item.get("classification") or {}
        lines.append(
            "| {request_id} | {requester} | {title} | {category} "
            "| {priority} | {ticket} | {status} |".format(
                request_id=item["request_id"],
                requester=item.get("requester") or "",
                title=(classification.get("title") or "").replace("|", "/"),
                category=classification.get("category") or "",
                priority=classification.get("priority") or "",
                ticket=item.get("ticket_id")
                if item.get("ticket_id") is not None
                else "—",
                status=item["status"],
            )
        )
    tracker = payload.get("tracker")
    if tracker:
        lines.extend(
            ["", "## Tracker totals", "", f"- Total tickets: {tracker['total']}"]
        )
        for label, counts in (
            ("By status", tracker.get("by_status", {})),
            ("By priority", tracker.get("by_priority", {})),
            ("By category", tracker.get("by_category", {})),
        ):
            pretty = ", ".join(f"{k}={v}" for k, v in counts.items()) or "none"
            lines.append(f"- {label}: {pretty}")
    lines.append("")
    return "\n".join(lines)


def _ticket_body(request: IncomingRequest, classification: Classification) -> str:
    return (
        f"{classification.summary}\n\n"
        f"---\nOriginal request ({request.id}):\n{request.message.strip()}\n"
    )


def _load_json(path: Path) -> list[IncomingRequest]:
    text = path.read_text(encoding="utf-8").strip()
    if path.suffix.lower() == ".jsonl":
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        data = json.loads(text)
        if isinstance(data, dict) and "requests" in data:
            rows = data["requests"]
        elif isinstance(data, list):
            rows = data
        else:
            raise ValueError(
                "JSON input must be a list or an object with a 'requests' array"
            )
    return [_row_to_request(row, index) for index, row in enumerate(rows, start=1)]


def _load_csv(path: Path) -> list[IncomingRequest]:
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        return [
            _row_to_request(row, index) for index, row in enumerate(reader, start=1)
        ]


def _row_to_request(row: dict[str, Any], index: int) -> IncomingRequest:
    return IncomingRequest(
        id=str(row.get("id") or f"req-{index:03d}"),
        requester=str(row.get("requester") or row.get("from") or "").strip(),
        message=str(
            row.get("message") or row.get("body") or row.get("text") or ""
        ).strip(),
    )
