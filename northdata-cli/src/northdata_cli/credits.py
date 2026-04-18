"""Local credit tracking.

NorthData charges per returned company, not per HTTP call. The remote API
exposes used-credit counts via ``/billing/v1/requests`` (see
``NorthDataClient.billing``). On top of that remote counter, this module
maintains an append-only local JSON-lines log at
``~/.northdata/credits.jsonl`` capturing every billable call this CLI
makes. The local log is purely informational — NorthData's counter remains
the source of truth.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


def default_log_path() -> Path:
    override = os.environ.get("NORTHDATA_CREDIT_LOG")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".northdata" / "credits.jsonl"


@dataclass
class CreditEntry:
    timestamp: str
    command: str
    estimated_credits: int
    note: str = ""

    def to_json_line(self) -> str:
        return json.dumps(
            {
                "timestamp": self.timestamp,
                "command": self.command,
                "estimated_credits": self.estimated_credits,
                "note": self.note,
            },
            ensure_ascii=False,
        )


class CreditGuard:
    """Append-only local log of estimated credit spend."""

    def __init__(self, log_path: Path | None = None):
        self.log_path = log_path or default_log_path()

    def record(self, command: str, estimated_credits: int, note: str = "") -> CreditEntry:
        entry = CreditEntry(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S%z") or time.strftime("%Y-%m-%dT%H:%M:%S"),
            command=command,
            estimated_credits=int(estimated_credits),
            note=note,
        )
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(entry.to_json_line() + "\n")
        return entry

    def entries(self) -> list[dict[str, Any]]:
        if not self.log_path.exists():
            return []
        out: list[dict[str, Any]] = []
        with self.log_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    def total(self) -> int:
        return sum(int(e.get("estimated_credits", 0)) for e in self.entries())

    def month_total(self, year: int | None = None, month: int | None = None) -> int:
        today = date.today()
        y = year or today.year
        m = month or today.month
        prefix = f"{y:04d}-{m:02d}"
        return sum(
            int(e.get("estimated_credits", 0))
            for e in self.entries()
            if e.get("timestamp", "").startswith(prefix)
        )


