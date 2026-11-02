"""PR D2b tests: DecisionLog writes and reads decisions.tsv safely. Local files only."""
from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

from pyx.decisions import COLUMNS, DecisionLog, DecisionRow, DecisionRowError

ROW = DecisionRow(lesson_id="", step="grade", result="pass", reason_code="", criteria_fixed="",
                  criteria_broken="", judge_a="T1.C8=PASS", judge_b="T1.C8=PASS", seed="0", run_id="r1",
                  flags="", task_id="T1")
ROW2 = replace(ROW, result="fail", criteria_broken="T1.C1", task_id="T2")


def test_new_file_gets_one_header_then_rows(tmp_path: Path) -> None:
    path = tmp_path / "decisions.tsv"
    DecisionLog(path).append([ROW])
    DecisionLog(path).append([ROW2])
    lines = path.read_text().split("\n")
    assert lines[0] == "\t".join(COLUMNS)
    assert lines[1:] == ["\t".join(ROW.values()), "\t".join(ROW2.values()), ""]


def test_a_different_header_is_refused_and_the_file_is_untouched(tmp_path: Path) -> None:
    path = tmp_path / "decisions.tsv"
    path.write_text("lesson_id\tstep\tresult\n")
    before = path.read_bytes()
    with pytest.raises(DecisionRowError, match="header"):
        DecisionLog(path).append([ROW])
    assert path.read_bytes() == before


def test_identical_rows_are_written_once(tmp_path: Path) -> None:
    path = tmp_path / "decisions.tsv"
    DecisionLog(path).append([ROW, ROW])
    DecisionLog(path).append([ROW, replace(ROW, seed="1")])
    assert DecisionLog(path).read() == [ROW, replace(ROW, seed="1")]


def test_crash_before_rename_keeps_the_old_file_and_no_temp(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "decisions.tsv"
    DecisionLog(path).append([ROW])
    before = path.read_bytes()

    def boom(src, dst):
        raise OSError("simulated crash")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        DecisionLog(path).append([ROW2])
    monkeypatch.undo()
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir() if not p.name.endswith(".lock")) == ["decisions.tsv"]


def test_read_validates_rows_and_names_the_line(tmp_path: Path) -> None:
    path = tmp_path / "decisions.tsv"
    DecisionLog(path).append([ROW])
    bad = "\t".join(replace(ROW, task_id="T9").values()).replace("\tpass\t\t", "\tpass\tMADE_UP\t")
    with path.open("a") as fh:
        fh.write(bad + "\n")
    with pytest.raises(DecisionRowError, match="line 3"):
        DecisionLog(path).read()


def test_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "decisions.tsv"
    rows = [ROW, ROW2, replace(ROW, result="inconclusive", flags="JUDGE_UNAVAILABLE", judge_b="T1.C8=MALFORMED")]
    DecisionLog(path).append(rows)
    assert DecisionLog(path).read() == rows
