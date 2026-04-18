from __future__ import annotations

import json
from pathlib import Path

import pytest

from northdata_cli.credits import CreditGuard, default_log_path


def test_default_log_path_respects_env(monkeypatch, tmp_path):
    monkeypatch.setenv("NORTHDATA_CREDIT_LOG", str(tmp_path / "custom.jsonl"))
    assert default_log_path() == tmp_path / "custom.jsonl"


def test_default_log_path_home(monkeypatch):
    monkeypatch.delenv("NORTHDATA_CREDIT_LOG", raising=False)
    assert default_log_path() == Path.home() / ".northdata" / "credits.jsonl"


def test_record_appends_and_totals(tmp_path):
    guard = CreditGuard(log_path=tmp_path / "c.jsonl")
    guard.record("company", 1, note="HRB 1/Munich")
    guard.record("search", 5, note="limit=5")
    guard.record("company", 1)
    assert guard.total() == 7
    assert len(guard.entries()) == 3


def test_entries_skips_bad_lines(tmp_path):
    path = tmp_path / "c.jsonl"
    path.write_text(
        '{"command": "a", "estimated_credits": 2}\n'
        "not-json\n"
        '{"command": "b", "estimated_credits": 3}\n',
        encoding="utf-8",
    )
    guard = CreditGuard(log_path=path)
    assert guard.total() == 5
    assert len(guard.entries()) == 2


def test_month_total_filters_by_prefix(tmp_path):
    path = tmp_path / "c.jsonl"
    entries = [
        {"timestamp": "2026-03-15T10:00:00", "command": "a", "estimated_credits": 3},
        {"timestamp": "2026-04-01T09:00:00", "command": "b", "estimated_credits": 4},
        {"timestamp": "2026-04-10T09:00:00", "command": "c", "estimated_credits": 2},
    ]
    path.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
    guard = CreditGuard(log_path=path)
    assert guard.month_total(year=2026, month=4) == 6
    assert guard.month_total(year=2026, month=3) == 3


def test_record_creates_parent_dir(tmp_path):
    nested = tmp_path / "nested" / "deeper" / "c.jsonl"
    guard = CreditGuard(log_path=nested)
    guard.record("x", 1)
    assert nested.exists()


