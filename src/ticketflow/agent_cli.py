"""Command-line entry point for the intake workflow."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from ticketflow.llm import get_provider
from ticketflow.logging_config import configure_logging
from ticketflow.store import TicketStore
from ticketflow.workflow import load_requests, run_workflow, write_summary

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "data" / "incoming_requests.json"
DEFAULT_DB = ROOT / "data" / "tickets.db"
DEFAULT_OUT = ROOT / "reports" / "summary.md"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Classify incoming requests and file tickets in the local tracker."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="JSON, JSONL, or CSV of incoming requests",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite path (default: data/tickets.db or TICKET_DB_PATH)",
    )
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help="Markdown or JSON summary path"
    )
    parser.add_argument(
        "--provider",
        choices=["auto", "mock", "anthropic"],
        default="auto",
        help="auto uses mock when ANTHROPIC_API_KEY is unset",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Classify only; do not write tickets"
    )
    parser.add_argument(
        "--attempts", type=int, default=3, help="Classifier retries on failure"
    )
    parser.add_argument("--log-level", default="INFO")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(args.log_level)

    provider_name = None if args.provider == "auto" else args.provider
    provider = get_provider(provider_name)
    store = TicketStore(args.db or DEFAULT_DB)
    requests = load_requests(args.input)
    logging.getLogger("ticketflow").info(
        "starting workflow",
        extra={
            "fields": {
                "count": len(requests),
                "provider": provider.name,
                "dry_run": args.dry_run,
            }
        },
    )
    result = run_workflow(
        requests,
        store,
        provider,
        dry_run=args.dry_run,
        attempts=args.attempts,
    )
    write_summary(result, args.out, store=store)
    summary = result.to_dict()
    print(f"Wrote {args.out} ({summary['filed']} filed, {summary['failed']} failed)")
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
