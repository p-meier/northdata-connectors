from __future__ import annotations

import json

import httpx
import pytest
from fastmcp import Client

from conftest import load_fixture, make_server


# ── Discovery ────────────────────────────────────────────────────────


async def test_list_tools_contains_every_command():
    def handler(request):  # pragma: no cover
        return httpx.Response(200, json={})

    server = make_server(handler)
    async with Client(server) as client:
        tools = await client.list_tools()

    names = {t.name for t in tools}
    assert {
        "suggest",
        "billing",
        "reference_overview",
        "reference_segment_codes",
        "local_credit_log",
        "search",
        "company",
        "person",
        "publications",
    } <= names


async def test_free_tools_tagged_free():
    def handler(request):  # pragma: no cover
        return httpx.Response(200, json={})

    server = make_server(handler)
    async with Client(server) as client:
        tools = {t.name: t for t in await client.list_tools()}

    # Tags are surfaced via meta
    for free_name in ["suggest", "billing", "reference_overview"]:
        tool = tools[free_name]
        # Tags are in tool._meta / tool.meta (FastMCP attaches to meta)
        meta = (tool.meta or {})
        # Tags live under the fastmcp namespace in v3
        ns = meta.get("fastmcp") or meta.get("_fastmcp") or {}
        tags = ns.get("tags") or meta.get("tags") or []
        assert "free" in tags, f"{free_name} not tagged 'free' (meta={meta})"


# ── Free tools ───────────────────────────────────────────────────────


async def test_suggest_returns_data(tmp_credit_log):
    def handler(request):
        assert "/search/v1/suggest" in str(request.url)
        return httpx.Response(200, json=load_fixture("suggest.json"))

    server = make_server(handler, log_path=tmp_credit_log)
    async with Client(server) as client:
        result = await client.call_tool("suggest", {"query": "Example"})

    payload = result.data
    assert payload["items"][0]["name"] == "Example GmbH"
    # Free tool must not write to the credit log
    assert not tmp_credit_log.exists()


async def test_billing_returns_remote_counter(tmp_credit_log):
    def handler(request):
        return httpx.Response(200, json=load_fixture("billing.json"))

    server = make_server(handler, log_path=tmp_credit_log)
    async with Client(server) as client:
        result = await client.call_tool("billing", {})
    assert result.data["numberOfRequests"] == 85


async def test_reference_overview(tmp_credit_log):
    def handler(request):
        assert "/reference/v1/overview" in str(request.url)
        return httpx.Response(200, json={"standards": ["NACE2025"]})

    server = make_server(handler, log_path=tmp_credit_log)
    async with Client(server) as client:
        result = await client.call_tool("reference_overview", {})
    assert "standards" in result.data


async def test_reference_segment_codes(tmp_credit_log):
    def handler(request):
        assert "standard=NACE2025" in str(request.url)
        return httpx.Response(200, json={"codes": [{"code": "62"}]})

    server = make_server(handler, log_path=tmp_credit_log)
    async with Client(server) as client:
        result = await client.call_tool("reference_segment_codes", {})
    assert result.data["codes"][0]["code"] == "62"


# ── Billed tools ─────────────────────────────────────────────────────


async def test_company_records_one_credit(tmp_credit_log):
    def handler(request):
        assert "/company/v1/company" in str(request.url)
        return httpx.Response(200, json=load_fixture("company.json"))

    server = make_server(handler, log_path=tmp_credit_log)
    async with Client(server) as client:
        result = await client.call_tool(
            "company", {"name": "Example GmbH", "city": "Munich"}
        )

    assert result.data["name"] == "Example GmbH"
    assert tmp_credit_log.exists()
    line = tmp_credit_log.read_text(encoding="utf-8").strip()
    assert '"command": "company"' in line
    assert '"estimated_credits": 1' in line


async def test_company_dry_run_does_not_record(tmp_credit_log):
    def handler(request):  # pragma: no cover
        raise AssertionError("dry_run should not call the API")

    server = make_server(handler, log_path=tmp_credit_log)
    async with Client(server) as client:
        result = await client.call_tool(
            "company",
            {"name": "Example GmbH", "city": "Munich", "dry_run": True},
        )

    assert result.data["_dry_run"] is True
    assert "register=" not in (result.data["url"])
    assert "name=Example" in result.data["url"]
    assert not tmp_credit_log.exists()


async def test_person(tmp_credit_log):
    def handler(request):
        return httpx.Response(200, json={"birthDate": "1965-05-12"})

    server = make_server(handler, log_path=tmp_credit_log)
    async with Client(server) as client:
        result = await client.call_tool(
            "person", {"first_name": "Max", "last_name": "Mustermann"}
        )
    assert result.data["birthDate"] == "1965-05-12"
    assert '"command": "person"' in tmp_credit_log.read_text(encoding="utf-8")


async def test_publications(tmp_credit_log):
    def handler(request):
        assert "source=Hrb" in str(request.url)
        return httpx.Response(200, json={"items": []})

    server = make_server(handler, log_path=tmp_credit_log)
    async with Client(server) as client:
        result = await client.call_tool(
            "publications", {"name": "Example GmbH", "source": "Hrb"}
        )
    assert result.data == {"items": []}


async def test_search_records_credit(tmp_credit_log):
    def handler(request):
        return httpx.Response(200, json=load_fixture("power.json"))

    server = make_server(handler, log_path=tmp_credit_log)
    async with Client(server) as client:
        result = await client.call_tool(
            "search",
            {
                "segment_codes": ["62"],
                "legal_forms": ["GmbH"],
                "limit": 5,
            },
        )
    assert result.data["items"][0]["name"] == "Alpha GmbH"
    assert tmp_credit_log.exists()


async def test_search_credit_guard_blocks_high_limit(tmp_credit_log):
    def handler(request):  # pragma: no cover
        raise AssertionError("guard should block")

    server = make_server(handler, log_path=tmp_credit_log)
    async with Client(server) as client:
        result = await client.call_tool("search", {"limit": 75})
    assert result.data["error"] == "credit_guard"
    assert "APPROVAL_THRESHOLD" in result.data["message"]
    assert not tmp_credit_log.exists()


async def test_search_absolute_max_blocks_with_approval(tmp_credit_log):
    def handler(request):  # pragma: no cover
        raise AssertionError("absolute max should block")

    server = make_server(handler, log_path=tmp_credit_log)
    async with Client(server) as client:
        result = await client.call_tool(
            "search", {"limit": 200, "approve_high_cost": True}
        )
    assert result.data["error"] == "credit_guard"
    assert "ABSOLUTE_MAX" in result.data["message"]


async def test_search_approved_high_cost(tmp_credit_log):
    def handler(request):
        return httpx.Response(200, json={"items": []})

    server = make_server(handler, log_path=tmp_credit_log)
    async with Client(server) as client:
        result = await client.call_tool(
            "search", {"limit": 50, "approve_high_cost": True}
        )
    assert result.data == {"items": []}


# ── API errors ───────────────────────────────────────────────────────


async def test_api_error_returned_as_structured_dict(tmp_credit_log):
    def handler(request):
        return httpx.Response(500, text="boom")

    server = make_server(handler, log_path=tmp_credit_log)
    async with Client(server) as client:
        result = await client.call_tool("billing", {})
    assert result.data["error"] == "api_error"
    assert result.data["status_code"] == 500


async def test_api_error_on_billed_does_not_record(tmp_credit_log):
    def handler(request):
        return httpx.Response(404, text="not found")

    server = make_server(handler, log_path=tmp_credit_log)
    async with Client(server) as client:
        result = await client.call_tool(
            "company", {"name": "does-not-exist"}
        )
    assert result.data["error"] == "api_error"
    assert result.data["status_code"] == 404
    # Ensure we didn't charge ourselves in the local log for a failed call
    assert not tmp_credit_log.exists()


# ── Local credit log tool ────────────────────────────────────────────


async def test_local_credit_log_reports_totals(tmp_credit_log):
    def handler(request):
        return httpx.Response(200, json=load_fixture("company.json"))

    server = make_server(handler, log_path=tmp_credit_log)
    async with Client(server) as client:
        await client.call_tool("company", {"name": "Example GmbH"})
        await client.call_tool("company", {"name": "Example GmbH"})
        result = await client.call_tool("local_credit_log", {})

    data = result.data
    assert data["total_estimated_credits"] == 2
    assert len(data["entries"]) == 2
