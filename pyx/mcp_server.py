"""The read only MCP server over one run's earned lessons bank (Amendment 1).

Two tools, no write surface: query_earned_lessons and get_lesson_provenance,
served over streamable HTTP by the official mcp Python SDK (the optional mcp
extra). The SDK import is lazy so the core pipeline never requires it.

Run: python -m pyx.mcp_server --run-dir runs/<run_id> [--host H] [--port N]
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from pyx.bank import LessonBank


def build_server(bank: LessonBank):
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("pyx-bank")

    @server.tool()
    def query_earned_lessons(task_id: Optional[str] = None,
                             criterion_id: Optional[str] = None) -> list:
        """List the bank's earned lessons, optionally filtered by task family
        (for example T1) or by the exact criterion a lesson fixes (for
        example T1.C1). Each entry carries the lesson text and its sha256."""
        return bank.earned_lessons(task_id=task_id, criterion_id=criterion_id)

    @server.tool()
    def get_lesson_provenance(lesson_id: str) -> dict:
        """Fetch one lesson's full record: its text and provenance (distiller,
        source, sha256, approver) plus every verdict row recorded for it.
        Works for any candidate in the run, earned or not."""
        return bank.provenance(lesson_id)

    return server


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Serve one run's earned lessons bank over MCP (read only).")
    parser.add_argument("--run-dir", required=True, help="a run directory holding decisions.tsv and candidates files")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8377)
    args = parser.parse_args(argv)
    bank = LessonBank.load(Path(args.run_dir))
    server = build_server(bank)
    server.settings.host = args.host
    server.settings.port = args.port
    server.run(transport="streamable-http")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
