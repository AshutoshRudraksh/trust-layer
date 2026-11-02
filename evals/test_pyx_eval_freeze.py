"""PR H5 test: the committed EVAL.md is a draft until Ashutosh freezes it, so a counted run refuses."""
from __future__ import annotations

import hashlib

import pytest

from pyx.run import EVAL_PATH, EvalNotFrozenError, check_frozen


def test_committed_eval_is_draft_and_counted_runs_refuse_it() -> None:
    data = EVAL_PATH.read_bytes()
    assert "Status: DRAFT" in data.decode("utf-8")
    with pytest.raises(EvalNotFrozenError):
        check_frozen(EVAL_PATH, hashlib.sha256(data).hexdigest())
