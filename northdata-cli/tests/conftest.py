from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import httpx
import pytest

from northdata_cli.client import NorthDataClient


FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    with (FIXTURES / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


Handler = Callable[[httpx.Request], httpx.Response]


def make_client(handler: Handler, **overrides) -> NorthDataClient:
    transport = httpx.MockTransport(handler)
    return NorthDataClient(
        api_key=overrides.pop("api_key", "TEST-KEY"),
        transport=transport,
        **overrides,
    )


@pytest.fixture
def tmp_credit_log(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "credits.jsonl"
    monkeypatch.setenv("NORTHDATA_CREDIT_LOG", str(path))
    return path


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Prevent env pollution between tests."""
    for var in [
        "NORTHDATA_API_KEY",
        "NORTHDATA_APPROVAL_THRESHOLD",
        "NORTHDATA_ABSOLUTE_MAX",
        "NORTHDATA_CREDIT_LOG",
    ]:
        monkeypatch.delenv(var, raising=False)
