"""Append only JSONL log of every judge, checker and distill call in a run.

One line per judge call attempt (retries and errors included) and one line per
checker pass. A keyless rerun serves judge replies from these lines by their
replay key. Lines are written with a fixed set of fields, appended, flushed and
fsynced. A torn line is reported on read and blocks further appends. Before any
write the line is screened for live key values and key shaped patterns; a hit
raises and nothing is written. For held out tasks only the prompt hash is kept.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Sequence, Union

KEY_ENV_NAMES = ("MODEL_API_KEY", "BASETEN_API_KEY", "GITHUB_TOKEN")
KEY_PATTERNS = re.compile(
    r"sk-[A-Za-z0-9]{16,}|bearer\s+[A-Za-z0-9._-]{20,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN",
    re.I,
)
CHECKER_SOURCE = Path(__file__).resolve().parent / "checker.py"


class TornLogError(RuntimeError):
    """A line in the log is not complete JSON, usually from a crash mid write."""


class KeyLeakError(RuntimeError):
    """A line about to be written contains a live key value or a key shaped string."""


def _sha256(text: Union[str, bytes]) -> str:
    return hashlib.sha256(text.encode("utf-8") if isinstance(text, str) else text).hexdigest()


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def replay_key(judge: str, model: str, endpoint: str, prompt: str, params: Dict[str, Any]) -> str:
    return _sha256(_canonical({"judge": judge, "model": model, "endpoint": endpoint,
                               "prompt": prompt, "params": params}))


def _screen(line: str) -> None:
    for name in KEY_ENV_NAMES:
        value = os.getenv(name, "")
        if len(value) >= 8 and value in line:
            raise KeyLeakError(f"refused to write: line contains the value of {name}")
    if KEY_PATTERNS.search(line):
        raise KeyLeakError("refused to write: line contains a key shaped string")


class CallLog:
    def __init__(self, path: Union[str, Path], run_id: str) -> None:
        self.path = Path(path)
        self.run_id = run_id

    def read(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        raw = self.path.read_text(encoding="utf-8")
        lines = raw.split("\n")
        if lines[-1] != "":
            raise TornLogError(f"{self.path}: line {len(lines)} has no newline (torn write)")
        out = []
        for number, line in enumerate(lines[:-1], start=1):
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise TornLogError(f"{self.path}: line {number} is not valid JSON") from exc
        return out

    def _append(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        entry = {"run_id": self.run_id, "seq": len(self.read()), **entry}
        line = _canonical(entry)
        _screen(line)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return entry

    def append_judge(self, *, judge: str, model: str, endpoint: str, params: Dict[str, Any], prompt: str,
                     reply: str, outcome: str, input_tokens: int, output_tokens: int, reasoning_tokens: int,
                     cost_usd: float, latency_s: float, error: str = "", held_out: bool = False,
                     kind: str = "judge") -> Dict[str, Any]:
        return self._append({
            "kind": kind, "judge": judge, "model": model, "endpoint": endpoint, "params": params,
            "key": replay_key(judge, model, endpoint, prompt, params), "prompt_sha256": _sha256(prompt),
            "prompt": None if held_out else prompt, "held_out": held_out, "reply": reply,
            "outcome": outcome, "error": error, "input_tokens": input_tokens, "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens, "cost_usd": cost_usd, "latency_s": latency_s,
        })

    def append_checker(self, task_id: str, answer_text: str, rubric: Dict[str, Any],
                       verdicts: Sequence[Any]) -> Dict[str, Any]:
        return self._append({
            "kind": "checker", "task_id": task_id, "answer_sha256": _sha256(answer_text),
            "rubric_sha256": _sha256(_canonical(rubric)), "checker_sha256": _sha256(CHECKER_SOURCE.read_bytes()),
            "verdicts": [asdict(v) for v in verdicts], "input_tokens": 0, "output_tokens": 0, "cost_usd": 0,
        })
