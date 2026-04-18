from __future__ import annotations

import httpx
import pytest

from northdata_cli.client import (
    CreditGuardError,
    NorthDataAPIError,
    NorthDataClient,
)

from conftest import load_fixture, make_client


# ── Construction ─────────────────────────────────────────────────────


def test_requires_api_key():
    with pytest.raises(ValueError):
        NorthDataClient(api_key="")


def test_absolute_max_from_env(monkeypatch):
    monkeypatch.setenv("NORTHDATA_ABSOLUTE_MAX", "200")
    monkeypatch.setenv("NORTHDATA_APPROVAL_THRESHOLD", "50")

    def handler(request):
        return httpx.Response(200, json={})

    client = make_client(handler)
    assert client.absolute_max == 200
    assert client.approval_threshold == 50


def test_invalid_env_value_raises(monkeypatch):
    monkeypatch.setenv("NORTHDATA_ABSOLUTE_MAX", "not-a-number")

    def handler(request):  # pragma: no cover
        return httpx.Response(200, json={})

    with pytest.raises(ValueError):
        make_client(handler)


# ── Free endpoints ───────────────────────────────────────────────────


def test_suggest_happy_path():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        return httpx.Response(200, json=load_fixture("suggest.json"))

    client = make_client(handler)
    data = client.suggest(query="Example")
    assert data["items"][0]["name"] == "Example GmbH"
    assert "/search/v1/suggest" in captured["url"]
    assert "query=Example" in captured["url"]


def test_billing_free():
    def handler(request):
        assert "/billing/v1/requests" in str(request.url)
        return httpx.Response(200, json=load_fixture("billing.json"))

    data = make_client(handler).billing()
    assert data["numberOfRequests"] == 85


def test_reference_overview():
    def handler(request):
        assert "/reference/v1/overview" in str(request.url)
        return httpx.Response(200, json={"standards": ["NACE2025"]})

    data = make_client(handler).reference_overview()
    assert "standards" in data


def test_reference_segments():
    def handler(request):
        assert "standard=NACE2025" in str(request.url)
        return httpx.Response(200, json={"codes": [{"code": "62", "label": "IT"}]})

    data = make_client(handler).reference_segment_codes("NACE2025")
    assert data["codes"][0]["code"] == "62"


# ── Power Search ─────────────────────────────────────────────────────


def test_power_search_happy_path():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        return httpx.Response(200, json=load_fixture("power.json"))

    client = make_client(handler)
    data = client.power_search(
        segment_codes=["62", "63"],
        legal_forms=["GmbH"],
        indicators=[("Revenue", 5_000_000, 50_000_000)],
        address="Munich",
        max_distance_km=150,
        limit=5,
    )
    assert data["items"][0]["name"] == "Alpha GmbH"
    url = captured["url"]
    assert "segmentCodes=62%7C63" in url
    assert "legalForm=GmbH" in url
    assert "limit=5" in url
    assert "indicatorId=Revenue" in url


def test_power_search_limit_invalid_type():
    client = make_client(lambda r: httpx.Response(200, json={}))
    with pytest.raises(CreditGuardError, match="Ganzzahl"):
        client.power_search(limit="5")  # type: ignore[arg-type]


def test_power_search_limit_zero():
    client = make_client(lambda r: httpx.Response(200, json={}))
    with pytest.raises(CreditGuardError, match=">= 1"):
        client.power_search(limit=0)


def test_power_search_limit_requires_approval():
    client = make_client(lambda r: httpx.Response(200, json={}))
    with pytest.raises(CreditGuardError, match="APPROVAL_THRESHOLD"):
        client.power_search(limit=50)


def test_power_search_limit_approved():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json={"items": []})

    client = make_client(handler)
    client.power_search(limit=50, approve_high_cost=True)
    assert "limit=50" in calls[0]


def test_power_search_absolute_max_hard_stop():
    client = make_client(lambda r: httpx.Response(200, json={}))
    with pytest.raises(CreditGuardError, match="ABSOLUTE_MAX"):
        client.power_search(limit=150, approve_high_cost=True)


def test_power_search_boolean_is_rejected_as_limit():
    client = make_client(lambda r: httpx.Response(200, json={}))
    with pytest.raises(CreditGuardError, match="Ganzzahl"):
        client.power_search(limit=True)  # booleans are ints in Python


def test_dry_run_does_not_call_api():
    def handler(request):  # pragma: no cover
        raise AssertionError("API should not be called in dry-run")

    client = make_client(handler, dry_run=True)
    result = client.power_search(segment_codes=["62"], legal_forms=["GmbH"], limit=5)
    assert result["_dry_run"] is True
    assert "segmentCodes=62" in result["url"]


# ── Company ──────────────────────────────────────────────────────────


def test_company_requires_identifier():
    client = make_client(lambda r: httpx.Response(200, json={}))
    with pytest.raises(ValueError):
        client.company()


def test_company_by_register():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        return httpx.Response(200, json=load_fixture("company.json"))

    client = make_client(handler)
    data = client.company(register="HRB 123456/Muenchen")
    assert data["name"] == "Example GmbH"
    assert "register=HRB+123456%2FMuenchen" in captured["url"] or "HRB%20123456" in captured["url"]
    assert "owners=true" in captured["url"]


def test_company_flags_toggle_off():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        return httpx.Response(200, json={})

    client = make_client(handler)
    client.company(name="Example", owners=False, sheets=False)
    assert "owners=false" in captured["url"]
    assert "sheets=false" in captured["url"]


# ── Person ───────────────────────────────────────────────────────────


def test_person():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"birthDate": "1965-05-12"})

    client = make_client(handler)
    data = client.person(first_name="Max", last_name="Mustermann", city="Munich")
    assert data["birthDate"] == "1965-05-12"
    assert "firstName=Max" in captured["url"]
    assert "address=Munich" in captured["url"]


# ── Publications ─────────────────────────────────────────────────────


def test_publications():
    def handler(request):
        assert "/pub/v1/publications" in str(request.url)
        assert "source=Hrb" in str(request.url)
        return httpx.Response(200, json={"items": []})

    client = make_client(handler)
    client.publications(name="Example GmbH", source="Hrb")


# ── HTTP error handling ──────────────────────────────────────────────


def test_http_404_raises():
    def handler(request):
        return httpx.Response(404, text="not found")

    client = make_client(handler)
    with pytest.raises(NorthDataAPIError) as exc_info:
        client.billing()
    assert exc_info.value.status_code == 404


def test_http_429_raises_after_retries():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429, text="rate limited")

    client = make_client(handler, retries=2)
    with pytest.raises(NorthDataAPIError) as exc_info:
        client.billing()
    assert exc_info.value.status_code == 429
    assert len(calls) == 2


def test_http_500_retries_then_succeeds():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) < 2:
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json={"ok": True})

    client = make_client(handler, retries=3)
    data = client.billing()
    assert data == {"ok": True}
    assert len(calls) == 2


def test_empty_response_returns_none():
    def handler(request):
        return httpx.Response(200, content=b"")

    assert make_client(handler).billing() is None


def test_context_manager_closes():
    def handler(request):
        return httpx.Response(200, json={})

    with make_client(handler) as client:
        client.billing()
    # httpx.Client.is_closed is True after close
    assert client._client.is_closed


def test_none_params_are_dropped():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        return httpx.Response(200, json={})

    client = make_client(handler)
    client.billing(year=None, month=None)
    assert "year=" not in captured["url"]
    assert "month=" not in captured["url"]
