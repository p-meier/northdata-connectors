from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest
from typer.testing import CliRunner

import northdata_cli.cli as cli_module
from northdata_cli.cli import app

from conftest import load_fixture


runner = CliRunner()


def _patched_client_builder(handler):
    """Patch _build_client inside cli.py to inject a MockTransport-backed client."""

    def _builder(api_key, dry_run=False):
        from northdata_cli.client import NorthDataClient
        transport = httpx.MockTransport(handler)
        return NorthDataClient(api_key="TEST-KEY", dry_run=dry_run, transport=transport)

    return _builder


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "northdata-cli" in result.stdout


def test_no_args_shows_help():
    result = runner.invoke(app, [])
    assert result.exit_code != 0 or "Usage" in result.stdout


def test_missing_api_key(monkeypatch):
    monkeypatch.delenv("NORTHDATA_API_KEY", raising=False)
    result = runner.invoke(app, ["suggest", "foo"])
    assert result.exit_code == 2
    assert "No API key" in result.stderr


def test_suggest_cmd(monkeypatch, tmp_credit_log):
    monkeypatch.setenv("NORTHDATA_API_KEY", "TEST-KEY")

    def handler(request):
        assert "/search/v1/suggest" in str(request.url)
        return httpx.Response(200, json=load_fixture("suggest.json"))

    with patch.object(cli_module, "_build_client", _patched_client_builder(handler)):
        result = runner.invoke(app, ["suggest", "Example"])
    assert result.exit_code == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["items"][0]["name"] == "Example GmbH"


def test_billing_cmd(monkeypatch, tmp_credit_log):
    monkeypatch.setenv("NORTHDATA_API_KEY", "TEST-KEY")

    def handler(request):
        return httpx.Response(200, json=load_fixture("billing.json"))

    with patch.object(cli_module, "_build_client", _patched_client_builder(handler)):
        result = runner.invoke(app, ["billing"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["numberOfRequests"] == 85


def test_company_cmd_records_credit(monkeypatch, tmp_credit_log):
    monkeypatch.setenv("NORTHDATA_API_KEY", "TEST-KEY")

    def handler(request):
        return httpx.Response(200, json=load_fixture("company.json"))

    with patch.object(cli_module, "_build_client", _patched_client_builder(handler)):
        result = runner.invoke(
            app, ["company", "--register", "HRB 1/Muenchen"]
        )
    assert result.exit_code == 0, result.stderr
    # Credit log should have one entry
    assert tmp_credit_log.exists()
    line = tmp_credit_log.read_text(encoding="utf-8").strip()
    assert '"command": "company"' in line
    assert '"estimated_credits": 1' in line


def test_company_dry_run_does_not_record(monkeypatch, tmp_credit_log):
    monkeypatch.setenv("NORTHDATA_API_KEY", "TEST-KEY")

    def handler(request):  # pragma: no cover
        raise AssertionError("should not call API")

    with patch.object(cli_module, "_build_client", _patched_client_builder(handler)):
        result = runner.invoke(
            app, ["company", "--register", "HRB 1/Muenchen", "--dry-run"]
        )
    assert result.exit_code == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["_dry_run"] is True
    assert not tmp_credit_log.exists()


def test_search_cmd_records_credit(monkeypatch, tmp_credit_log):
    monkeypatch.setenv("NORTHDATA_API_KEY", "TEST-KEY")

    def handler(request):
        return httpx.Response(200, json=load_fixture("power.json"))

    with patch.object(cli_module, "_build_client", _patched_client_builder(handler)):
        result = runner.invoke(
            app,
            [
                "search",
                "--segment-codes", "62",
                "--legal-forms", "GmbH",
                "--limit", "5",
            ],
        )
    assert result.exit_code == 0, result.stderr
    assert tmp_credit_log.exists()
    data = json.loads(result.stdout)
    assert data["items"][0]["name"] == "Alpha GmbH"


def test_search_credit_guard_blocks_high_limit(monkeypatch, tmp_credit_log):
    monkeypatch.setenv("NORTHDATA_API_KEY", "TEST-KEY")

    def handler(request):  # pragma: no cover
        raise AssertionError("guard should block before API call")

    with patch.object(cli_module, "_build_client", _patched_client_builder(handler)):
        result = runner.invoke(app, ["search", "--limit", "75"])
    assert result.exit_code == 3
    assert "APPROVAL_THRESHOLD" in result.stderr


def test_search_absolute_max_blocks_even_with_approval(monkeypatch, tmp_credit_log):
    monkeypatch.setenv("NORTHDATA_API_KEY", "TEST-KEY")

    def handler(request):  # pragma: no cover
        raise AssertionError("guard should block")

    with patch.object(cli_module, "_build_client", _patched_client_builder(handler)):
        result = runner.invoke(
            app, ["search", "--limit", "200", "--approve-high-cost"]
        )
    assert result.exit_code == 3
    assert "ABSOLUTE_MAX" in result.stderr


def test_person_cmd(monkeypatch, tmp_credit_log):
    monkeypatch.setenv("NORTHDATA_API_KEY", "TEST-KEY")

    def handler(request):
        return httpx.Response(200, json={"birthDate": "1965-05-12"})

    with patch.object(cli_module, "_build_client", _patched_client_builder(handler)):
        result = runner.invoke(app, ["person", "Max", "Mustermann"])
    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout)["birthDate"] == "1965-05-12"


def test_publications_cmd(monkeypatch, tmp_credit_log):
    monkeypatch.setenv("NORTHDATA_API_KEY", "TEST-KEY")

    def handler(request):
        assert "source=Hrb" in str(request.url)
        return httpx.Response(200, json={"items": []})

    with patch.object(cli_module, "_build_client", _patched_client_builder(handler)):
        result = runner.invoke(
            app, ["publications", "--name", "Example", "--source", "Hrb"]
        )
    assert result.exit_code == 0, result.stderr


def test_reference_overview(monkeypatch):
    monkeypatch.setenv("NORTHDATA_API_KEY", "TEST-KEY")

    def handler(request):
        return httpx.Response(200, json={"standards": ["NACE2025"]})

    with patch.object(cli_module, "_build_client", _patched_client_builder(handler)):
        result = runner.invoke(app, ["reference", "overview"])
    assert result.exit_code == 0, result.stderr


def test_reference_bad_arg(monkeypatch):
    monkeypatch.setenv("NORTHDATA_API_KEY", "TEST-KEY")

    def handler(request):  # pragma: no cover
        return httpx.Response(200, json={})

    with patch.object(cli_module, "_build_client", _patched_client_builder(handler)):
        result = runner.invoke(app, ["reference", "nope"])
    assert result.exit_code == 2
    assert "unknown reference type" in result.stderr


def test_credits_cmd_empty(monkeypatch, tmp_credit_log):
    monkeypatch.setenv("NORTHDATA_API_KEY", "TEST-KEY")
    result = runner.invoke(app, ["credits"])
    assert result.exit_code == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["total_estimated_credits"] == 0
    assert data["entries"] == []


def test_api_error_surfaces(monkeypatch, tmp_credit_log):
    monkeypatch.setenv("NORTHDATA_API_KEY", "TEST-KEY")

    def handler(request):
        return httpx.Response(500, text="boom")

    with patch.object(cli_module, "_build_client", _patched_client_builder(handler)):
        result = runner.invoke(app, ["billing"])
    assert result.exit_code == 4
    assert "HTTP 500" in result.stderr
