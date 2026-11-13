"""Held out transfer run (ticket 4, ADR 0004). Not built yet: the tests come first."""
from __future__ import annotations


class RefuseToStart(RuntimeError):
    pass


class FallbackRefused(RuntimeError):
    pass


class TransferAbort(RuntimeError):
    pass


def committed_rubric_sha256():
    raise NotImplementedError


def verify_rubric(path, expected_sha256=None):
    raise NotImplementedError


def require_live_keys(env):
    raise NotImplementedError


class NoFallback:
    def __init__(self, inner):
        raise NotImplementedError


def earned_context():
    raise NotImplementedError


def run_transfer(out, rubric_path, paper_path, live, ledger, env=None, src_log=None, expected_sha256=None,
                 caps=None, hard_stop_usd=None):
    raise NotImplementedError
