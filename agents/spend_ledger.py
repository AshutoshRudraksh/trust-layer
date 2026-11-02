"""Persistent spend ledger shared by every process that calls a paid model.

The file holds cumulative spend per provider plus the ids of recorded calls.
Recording the same call id twice is a no op, so retries cannot double count.
Each write goes to a temp file in the same directory, is flushed and fsynced,
then renamed over the ledger with os.replace, so a crash leaves either the old
file or the new one and never a partial file. An flock on a sidecar lock file
serializes writers across processes.
"""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Union

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LEDGER_PATH = REPO_ROOT / "runs" / "spend_ledger.json"
LEDGER_PATH_ENV = "PYX_SPEND_LEDGER"


def default_ledger_path() -> Path:
    override = os.getenv(LEDGER_PATH_ENV)
    return Path(override) if override else DEFAULT_LEDGER_PATH


class SpendLedger:
    def __init__(self, path: Optional[Union[str, Path]] = None) -> None:
        self.path = Path(path) if path is not None else default_ledger_path()
        self._lock_path = self.path.with_name(self.path.name + ".lock")

    def _empty(self) -> Dict[str, Any]:
        return {"version": 1, "providers": {}}

    def _read(self) -> Dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        with self.path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock_path.open("a") as lock_fh:
            fcntl.flock(lock_fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_fh, fcntl.LOCK_UN)

    def _write_atomic(self, data: Dict[str, Any]) -> None:
        fd, tmp_name = tempfile.mkstemp(prefix=".ledger.", suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, sort_keys=True)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, self.path)
        except BaseException:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
            raise

    def total_usd(self, provider: str) -> float:
        return float(self._read()["providers"].get(provider, {}).get("total_usd", 0.0))

    def record(self, provider: str, call_id: str, cost_usd: float) -> float:
        """Add one call's cost once. Returns the provider's cumulative total."""
        with self._locked():
            data = self._read()
            entry = data["providers"].setdefault(provider, {"total_usd": 0.0, "call_ids": []})
            if call_id in entry["call_ids"]:
                return float(entry["total_usd"])
            entry["call_ids"].append(call_id)
            entry["total_usd"] = round(float(entry["total_usd"]) + float(cost_usd), 8)
            self._write_atomic(data)
            return float(entry["total_usd"])

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        """Per provider totals and call counts, for run reports."""
        providers = self._read()["providers"]
        return {
            name: {"total_usd": float(entry["total_usd"]), "calls": len(entry["call_ids"])}
            for name, entry in providers.items()
        }
