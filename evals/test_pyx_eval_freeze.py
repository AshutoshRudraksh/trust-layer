"""PR H7 tests: the committed EVAL.md is frozen at its pinned hash, and a draft copy still refuses."""
from __future__ import annotations

import hashlib
from io import StringIO

import pytest

from pyx.run import EVAL_PATH, EvalNotFrozenError, check_frozen, main

PINNED = "73583998bfccc2dbb3831b5f2425e196a8505fe740bd0dac4e17dcb957c27ddb"


def test_committed_eval_is_frozen_and_accepted_at_its_pinned_hash() -> None:
    data = EVAL_PATH.read_bytes()
    assert data.decode("utf-8").splitlines()[2].startswith("Status: FROZEN. Frozen by Ashutosh on Nov 2, 2026, with amendments A1 to A11.")
    assert hashlib.sha256(data).hexdigest() == PINNED
    assert check_frozen(EVAL_PATH, PINNED) == PINNED
    assert main(["check-eval", "--eval", str(EVAL_PATH), "--eval-sha256", PINNED], StringIO(), StringIO()) == 0


@pytest.mark.parametrize("status", ["Status: DRAFT. Not approved.", "Status: FROZENISH", "Note: Status: FROZEN."])
def test_a_draft_copy_still_refuses_with_exit_2(tmp_path, status) -> None:
    draft = tmp_path / "EVAL.md"
    draft.write_text(f"# Pyx EVAL.md\n\n{status}\n")
    h = hashlib.sha256(draft.read_bytes()).hexdigest()
    with pytest.raises(EvalNotFrozenError):
        check_frozen(draft, h)
    assert main(["check-eval", "--eval", str(draft), "--eval-sha256", h], StringIO(), StringIO()) == 2
