from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import httpx
import pytest

from northdata_cli.client import NorthDataClient
from northdata_cli.credits import CreditGuard
from northdata_mcp.server import create_server


FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    with (FIXTURES / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


Handler = Callable[[httpx.Request], httpx.Response]


def make_server(handler: Handler, *, log_path: Path | None = None):
    """Build a FastMCP server whose NorthDataClient is backed by MockTransport."""

    def factory() -> NorthDataClient:
        transport = httpx.MockTransport(handler)
        return NorthDataClient(api_key="TEST-KEY", transport=transport)

    guard = CreditGuard(log_path=log_path) if log_path else None
    return create_server(client_factory=factory, credit_guard=guard)


@pytest.fixture
def tmp_credit_log(tmp_path) -> Path:
    return tmp_path / "credits.jsonl"


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for var in [
        "NORTHDATA_API_KEY",
        "NORTHDATA_APPROVAL_THRESHOLD",
        "NORTHDATA_ABSOLUTE_MAX",
        "NORTHDATA_CREDIT_LOG",
    ]:
        monkeypatch.delenv(var, raising=False)
