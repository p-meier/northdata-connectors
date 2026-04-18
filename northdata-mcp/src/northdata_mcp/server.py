"""FastMCP v3 server exposing NorthData tools.

Every tool reuses :class:`northdata_cli.NorthDataClient` and
:class:`northdata_cli.CreditGuard` so credit-guard enforcement and local
bookkeeping behave identically to the CLI. The server is constructed via
:func:`create_server` which accepts a client factory — this makes the
server trivially testable with an in-memory client backed by
``httpx.MockTransport``.
"""

from __future__ import annotations

import os
from typing import Annotated, Any, Callable

from fastmcp import FastMCP

from northdata_cli.client import (
    CreditGuardError,
    NorthDataAPIError,
    NorthDataClient,
)
from northdata_cli.config import ConfigError, resolve_api_key
from northdata_cli.credits import CreditGuard


ClientFactory = Callable[[], NorthDataClient]


def _default_client_factory() -> NorthDataClient:
    """Instantiate a real NorthDataClient from the environment."""
    api_key = resolve_api_key(None)
    return NorthDataClient(api_key=api_key)


def create_server(
    client_factory: ClientFactory | None = None,
    *,
    credit_guard: CreditGuard | None = None,
    name: str = "northdata-mcp",
    instructions: str | None = None,
) -> FastMCP:
    """Build a FastMCP server instance.

    ``client_factory`` is called each time a tool runs, returning a
    ready-to-use :class:`NorthDataClient`. The default factory uses the
    ``NORTHDATA_API_KEY`` environment variable. Tests inject a factory that
    returns clients wired to ``httpx.MockTransport``.
    """
    factory = client_factory or _default_client_factory
    guard = credit_guard or CreditGuard()

    mcp = FastMCP(
        name=name,
        instructions=instructions
        or (
            "NorthData company data server. Every call to `search`, `company`, "
            "`person`, or `publications` consumes NorthData credits — "
            "NorthData bills per returned company, not per request. Prefer "
            "`suggest` (free) and `reference_*` (free) during exploration, "
            "and use `dry_run=true` on billed tools to inspect the URL "
            "without spending credits."
        ),
    )

    def _call(command: str, credits: int, note: str, fn: Callable[[NorthDataClient], Any]) -> Any:
        try:
            with factory() as client:
                result = fn(client)
        except CreditGuardError as exc:
            return {"error": "credit_guard", "message": str(exc)}
        except NorthDataAPIError as exc:
            return {
                "error": "api_error",
                "status_code": exc.status_code,
                "message": str(exc),
                "body": exc.body,
            }
        except ConfigError as exc:
            return {"error": "config_error", "message": str(exc)}
        guard.record(command=command, estimated_credits=credits, note=note)
        return result

    def _call_free(fn: Callable[[NorthDataClient], Any]) -> Any:
        try:
            with factory() as client:
                return fn(client)
        except NorthDataAPIError as exc:
            return {
                "error": "api_error",
                "status_code": exc.status_code,
                "message": str(exc),
                "body": exc.body,
            }
        except ConfigError as exc:
            return {"error": "config_error", "message": str(exc)}

    # ── Free tools ────────────────────────────────────────────────────

    @mcp.tool(
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"free"},
    )
    def suggest(
        query: Annotated[str, "Company or person name / fragment"],
        domain: Annotated[str, "'company' or 'person'"] = "company",
        status: Annotated[str, "'active', 'inactive', or 'all'"] = "active",
        countries: Annotated[str, "Pipe-separated ISO country codes"] = "DE",
        limit: Annotated[int, "Max number of suggestions"] = 10,
    ) -> dict:
        """Free endpoint. Autocomplete suggestions for companies or persons."""
        return _call_free(
            lambda c: c.suggest(
                query=query,
                domain=domain,
                status=status,
                countries=countries,
                limit=limit,
            )
        )

    @mcp.tool(
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"free"},
    )
    def billing(
        year: Annotated[int | None, "Billing year (>= 2024)"] = None,
        month: Annotated[int | None, "Billing month (1-12)"] = None,
    ) -> dict:
        """Free endpoint. Remote credit usage for the billing period."""
        return _call_free(lambda c: c.billing(year=year, month=month))

    @mcp.tool(
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"free"},
    )
    def reference_overview() -> dict:
        """Free endpoint. API reference overview (standards, countries, ...)."""
        return _call_free(lambda c: c.reference_overview())

    @mcp.tool(
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"free"},
    )
    def reference_segment_codes(
        standard: Annotated[str, "Segment code standard"] = "NACE2025",
    ) -> dict:
        """Free endpoint. Segment codes for a given standard."""
        return _call_free(lambda c: c.reference_segment_codes(standard=standard))

    @mcp.tool(
        annotations={"readOnlyHint": True},
        tags={"free", "local"},
    )
    def local_credit_log() -> dict:
        """Return the local credit log written by this server (best-effort)."""
        return {
            "log_path": str(guard.log_path),
            "total_estimated_credits": guard.total(),
            "month_estimated_credits": guard.month_total(),
            "entries": guard.entries(),
        }

    # ── Billed tools ──────────────────────────────────────────────────

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "openWorldHint": True,
            "destructiveHint": False,
        },
        tags={"billed"},
    )
    def search(
        segment_codes: Annotated[
            list[str] | None,
            "NACE / segment codes, e.g. ['62', '63']",
        ] = None,
        segment_standard: Annotated[str, "Segment code standard"] = "NACE2025",
        legal_forms: Annotated[
            list[str] | None,
            "Legal forms, e.g. ['GmbH', 'UG']",
        ] = None,
        address: Annotated[
            str | None, "Anchor address or city for geo-filtering"
        ] = None,
        max_distance_km: Annotated[
            int | None, "Radius in km around the anchor address"
        ] = None,
        countries: Annotated[str, "Pipe-separated ISO country codes"] = "DE",
        status: Annotated[str, "'active', 'inactive', or 'all'"] = "active",
        revenue_min: Annotated[int | None, "Minimum revenue (EUR)"] = None,
        revenue_max: Annotated[int | None, "Maximum revenue (EUR)"] = None,
        earnings_min: Annotated[int | None, "Minimum earnings (EUR)"] = None,
        earnings_max: Annotated[int | None, "Maximum earnings (EUR)"] = None,
        limit: Annotated[
            int,
            "Max companies returned. Cost = up to this many credits.",
        ] = 5,
        pos: Annotated[
            str | None, "Pagination token from a previous response"
        ] = None,
        approve_high_cost: Annotated[
            bool,
            "Required when limit exceeds the approval threshold (default 25)",
        ] = False,
        dry_run: Annotated[
            bool, "Build the request URL without calling the API"
        ] = False,
    ) -> dict:
        """Billed. Power search. Cost = up to ``limit`` credits."""
        indicators: list[tuple[str, int | None, int | None]] = []
        if revenue_min is not None or revenue_max is not None:
            indicators.append(("Revenue", revenue_min, revenue_max))
        if earnings_min is not None or earnings_max is not None:
            indicators.append(("Earnings", earnings_min, earnings_max))

        def _run(client: NorthDataClient) -> Any:
            original_dry_run = client.dry_run
            client.dry_run = original_dry_run or dry_run
            try:
                return client.power_search(
                    segment_codes=segment_codes,
                    segment_standard=segment_standard,
                    legal_forms=legal_forms,
                    indicators=indicators or None,
                    address=address,
                    max_distance_km=max_distance_km,
                    countries=countries,
                    status=status,
                    limit=limit,
                    pos=pos,
                    approve_high_cost=approve_high_cost,
                )
            finally:
                client.dry_run = original_dry_run

        if dry_run:
            return _call_free(_run)
        return _call(
            command="search",
            credits=limit,
            note=f"limit={limit}",
            fn=_run,
        )

    @mcp.tool(
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"billed"},
    )
    def company(
        name: Annotated[str | None, "Company name"] = None,
        register: Annotated[
            str | None, "Register identifier, e.g. 'HRB 123456/Muenchen'"
        ] = None,
        city: Annotated[str | None, "City to disambiguate by name"] = None,
        owners: Annotated[bool, "Include owners"] = True,
        financials: Annotated[bool, "Include financials"] = True,
        representatives: Annotated[bool, "Include representatives"] = True,
        extras: Annotated[bool, "Include contact extras"] = True,
        sheets: Annotated[bool, "Include balance sheets"] = True,
        events: Annotated[bool, "Include events"] = True,
        language: Annotated[str, "Response language"] = "de",
        dry_run: Annotated[
            bool, "Build the URL without calling the API"
        ] = False,
    ) -> dict:
        """Billed (1 credit). Full company profile."""

        def _run(client: NorthDataClient) -> Any:
            original_dry_run = client.dry_run
            client.dry_run = original_dry_run or dry_run
            try:
                return client.company(
                    name=name,
                    register=register,
                    city=city,
                    owners=owners,
                    financials=financials,
                    representatives=representatives,
                    extras=extras,
                    sheets=sheets,
                    events=events,
                    language=language,
                )
            finally:
                client.dry_run = original_dry_run

        if dry_run:
            return _call_free(_run)
        return _call(
            command="company",
            credits=1,
            note=register or name or "",
            fn=_run,
        )

    @mcp.tool(
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"billed"},
    )
    def person(
        first_name: Annotated[str, "Given name"],
        last_name: Annotated[str, "Family name"],
        city: Annotated[str | None, "City hint for disambiguation"] = None,
        language: Annotated[str, "Response language"] = "de",
        dry_run: Annotated[
            bool, "Build the URL without calling the API"
        ] = False,
    ) -> dict:
        """Billed (1 credit). Person details incl. birth date / roles."""

        def _run(client: NorthDataClient) -> Any:
            original_dry_run = client.dry_run
            client.dry_run = original_dry_run or dry_run
            try:
                return client.person(
                    first_name=first_name,
                    last_name=last_name,
                    city=city,
                    language=language,
                )
            finally:
                client.dry_run = original_dry_run

        if dry_run:
            return _call_free(_run)
        return _call(
            command="person",
            credits=1,
            note=f"{first_name} {last_name}",
            fn=_run,
        )

    @mcp.tool(
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"billed"},
    )
    def publications(
        name: Annotated[str | None, "Company name"] = None,
        register: Annotated[str | None, "Register identifier"] = None,
        source: Annotated[
            str | None, "Publication source filter, e.g. 'Hrb'"
        ] = None,
        language: Annotated[str, "Response language"] = "de",
        dry_run: Annotated[
            bool, "Build the URL without calling the API"
        ] = False,
    ) -> dict:
        """Billed. Publications lookup (e.g. shareholder lists)."""

        def _run(client: NorthDataClient) -> Any:
            original_dry_run = client.dry_run
            client.dry_run = original_dry_run or dry_run
            try:
                return client.publications(
                    name=name,
                    register=register,
                    source=source,
                    language=language,
                )
            finally:
                client.dry_run = original_dry_run

        if dry_run:
            return _call_free(_run)
        return _call(
            command="publications",
            credits=1,
            note=name or register or "",
            fn=_run,
        )

    return mcp


def main() -> None:
    """Entry point for the ``northdata-mcp`` console script.

    Speaks MCP over **stdio** — suitable for subprocess launches by
    Claude Desktop, Claude Code, Cursor, and other MCP clients.
    """
    try:
        resolve_api_key(None)
    except ConfigError as exc:
        raise SystemExit(f"northdata-mcp: {exc}")
    create_server().run()


if __name__ == "__main__":  # pragma: no cover
    main()
