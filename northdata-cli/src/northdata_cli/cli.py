"""Typer-based CLI entry point."""

from __future__ import annotations

import functools
import sys
from typing import Annotated, Optional

import typer
from rich.console import Console

from northdata_cli import __version__
from northdata_cli.client import (
    CreditGuardError,
    NorthDataAPIError,
    NorthDataClient,
)
from northdata_cli.config import ConfigError, resolve_api_key
from northdata_cli.credits import CreditGuard
from northdata_cli.output import print_json, print_pretty


app = typer.Typer(
    name="northdata",
    help="Command-line client for the NorthData API with a built-in credit guard.",
    no_args_is_help=True,
    add_completion=False,
)
err_console = Console(stderr=True)


# ── Shared options ────────────────────────────────────────────────────

APIKey = Annotated[
    Optional[str],
    typer.Option(
        "--api-key",
        envvar="NORTHDATA_API_KEY",
        help="NorthData API key. Falls back to NORTHDATA_API_KEY env var.",
        show_envvar=False,
    ),
]
Pretty = Annotated[
    bool,
    typer.Option("--pretty", "-p", help="Render as a Rich table instead of JSON."),
]
DryRun = Annotated[
    bool,
    typer.Option(
        "--dry-run",
        help="Build the request URL but do not call the API (no credits spent).",
    ),
]


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"northdata-cli {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        Optional[bool],
        typer.Option(
            "--version", callback=_version_callback, is_eager=True, help="Show version and exit."
        ),
    ] = None,
) -> None:
    """NorthData CLI."""


# ── Helpers ───────────────────────────────────────────────────────────


def _build_client(
    api_key: str | None,
    dry_run: bool = False,
) -> NorthDataClient:
    try:
        key = resolve_api_key(api_key)
    except ConfigError as exc:
        err_console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=2)
    return NorthDataClient(api_key=key, dry_run=dry_run)


def _emit(data, pretty: bool, title: str | None = None) -> None:
    if pretty:
        print_pretty(data, title=title)
    else:
        print_json(data)


def _handle_api_errors(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except CreditGuardError as exc:
            err_console.print(f"[red]credit-guard:[/red] {exc}")
            raise typer.Exit(code=3)
        except NorthDataAPIError as exc:
            err_console.print(f"[red]api error:[/red] {exc}")
            if exc.body:
                err_console.print(exc.body, style="dim")
            raise typer.Exit(code=4)
        except ConfigError as exc:
            err_console.print(f"[red]config error:[/red] {exc}")
            raise typer.Exit(code=2)

    return wrapper


# ── Commands ──────────────────────────────────────────────────────────


@app.command()
@_handle_api_errors
def suggest(
    query: Annotated[str, typer.Argument(help="Company or person name / fragment.")],
    domain: Annotated[str, typer.Option(help="company | person")] = "company",
    status: Annotated[str, typer.Option(help="active | inactive | all")] = "active",
    countries: Annotated[str, typer.Option(help="Country codes, pipe-separated.")] = "DE",
    limit: Annotated[int, typer.Option(help="Max suggestions.")] = 10,
    api_key: APIKey = None,
    pretty: Pretty = False,
) -> None:
    """Free: autocomplete / suggest companies or persons."""
    with _build_client(api_key) as client:
        data = client.suggest(
            query=query,
            domain=domain,
            status=status,
            countries=countries,
            limit=limit,
        )
    _emit(data, pretty, title=f"Suggest: {query}")


@app.command()
@_handle_api_errors
def search(
    segment_codes: Annotated[
        Optional[str],
        typer.Option(help="Pipe-separated segment codes (e.g. '62|63')."),
    ] = None,
    segment_standard: Annotated[
        str, typer.Option(help="Segment code standard.")
    ] = "NACE2025",
    legal_forms: Annotated[
        Optional[str],
        typer.Option(help="Pipe-separated legal forms (e.g. 'GmbH|UG')."),
    ] = None,
    address: Annotated[
        Optional[str],
        typer.Option(help="Anchor address or city (e.g. 'Munich')."),
    ] = None,
    max_distance_km: Annotated[
        Optional[int], typer.Option(help="Radius in km around --address.")
    ] = None,
    countries: Annotated[str, typer.Option(help="Country codes.")] = "DE",
    status: Annotated[str, typer.Option(help="active | inactive | all")] = "active",
    revenue_min: Annotated[
        Optional[int], typer.Option(help="Minimum revenue (EUR).")
    ] = None,
    revenue_max: Annotated[
        Optional[int], typer.Option(help="Maximum revenue (EUR).")
    ] = None,
    earnings_min: Annotated[
        Optional[int], typer.Option(help="Minimum earnings (EUR).")
    ] = None,
    earnings_max: Annotated[
        Optional[int], typer.Option(help="Maximum earnings (EUR).")
    ] = None,
    limit: Annotated[int, typer.Option(help="Max companies (= max credits).")] = 5,
    pos: Annotated[
        Optional[str], typer.Option(help="Pagination token from previous response.")
    ] = None,
    approve_high_cost: Annotated[
        bool,
        typer.Option(
            "--approve-high-cost",
            help="Required when --limit exceeds the approval threshold.",
        ),
    ] = False,
    api_key: APIKey = None,
    pretty: Pretty = False,
    dry_run: DryRun = False,
) -> None:
    """Billed: power search. Cost = up to --limit companies returned."""
    indicators: list[tuple[str, int | None, int | None]] = []
    if revenue_min is not None or revenue_max is not None:
        indicators.append(("Revenue", revenue_min, revenue_max))
    if earnings_min is not None or earnings_max is not None:
        indicators.append(("Earnings", earnings_min, earnings_max))

    kwargs = {
        "segment_codes": segment_codes.split("|") if segment_codes else None,
        "segment_standard": segment_standard,
        "legal_forms": legal_forms.split("|") if legal_forms else None,
        "indicators": indicators or None,
        "address": address,
        "max_distance_km": max_distance_km,
        "countries": countries,
        "status": status,
        "limit": limit,
        "pos": pos,
        "approve_high_cost": approve_high_cost,
    }
    with _build_client(api_key, dry_run=dry_run) as client:
        data = client.power_search(**kwargs)

    if not dry_run:
        guard = CreditGuard()
        items = data.get("items", []) if isinstance(data, dict) else []
        guard.record(
            command="search",
            estimated_credits=len(items) if items else limit,
            note=f"limit={limit}",
        )
    _emit(data, pretty, title="Power Search")


@app.command()
@_handle_api_errors
def company(
    name: Annotated[
        Optional[str], typer.Option(help="Company name (use --register or --name).")
    ] = None,
    register: Annotated[
        Optional[str], typer.Option(help="e.g. 'HRB123456/Muenchen'.")
    ] = None,
    city: Annotated[Optional[str], typer.Option(help="City to disambiguate.")] = None,
    owners: Annotated[bool, typer.Option(help="Include owners.")] = True,
    financials: Annotated[bool, typer.Option(help="Include financials.")] = True,
    representatives: Annotated[bool, typer.Option(help="Include representatives.")] = True,
    extras: Annotated[bool, typer.Option(help="Include contact extras.")] = True,
    sheets: Annotated[bool, typer.Option(help="Include balance sheets.")] = True,
    events: Annotated[bool, typer.Option(help="Include events.")] = True,
    language: Annotated[str, typer.Option(help="Response language.")] = "de",
    api_key: APIKey = None,
    pretty: Pretty = False,
    dry_run: DryRun = False,
) -> None:
    """Billed (1 credit). Full company profile."""
    with _build_client(api_key, dry_run=dry_run) as client:
        data = client.company(
            name=name,
            city=city,
            register=register,
            owners=owners,
            financials=financials,
            representatives=representatives,
            extras=extras,
            sheets=sheets,
            events=events,
            language=language,
        )
    if not dry_run:
        CreditGuard().record(
            command="company",
            estimated_credits=1,
            note=register or name or "",
        )
    _emit(data, pretty, title=name or register or "Company")


@app.command()
@_handle_api_errors
def person(
    first_name: Annotated[str, typer.Argument()],
    last_name: Annotated[str, typer.Argument()],
    city: Annotated[Optional[str], typer.Option(help="City hint.")] = None,
    language: Annotated[str, typer.Option()] = "de",
    api_key: APIKey = None,
    pretty: Pretty = False,
    dry_run: DryRun = False,
) -> None:
    """Billed (1 credit). Person details incl. birth date."""
    with _build_client(api_key, dry_run=dry_run) as client:
        data = client.person(
            first_name=first_name, last_name=last_name, city=city, language=language
        )
    if not dry_run:
        CreditGuard().record(
            command="person",
            estimated_credits=1,
            note=f"{first_name} {last_name}",
        )
    _emit(data, pretty, title=f"{first_name} {last_name}")


@app.command()
@_handle_api_errors
def publications(
    name: Annotated[Optional[str], typer.Option()] = None,
    register: Annotated[Optional[str], typer.Option()] = None,
    source: Annotated[Optional[str], typer.Option(help="e.g. 'Hrb'.")] = None,
    language: Annotated[str, typer.Option()] = "de",
    api_key: APIKey = None,
    pretty: Pretty = False,
    dry_run: DryRun = False,
) -> None:
    """Billed. Publications lookup (e.g. shareholder lists)."""
    with _build_client(api_key, dry_run=dry_run) as client:
        data = client.publications(
            name=name, register=register, source=source, language=language
        )
    if not dry_run:
        CreditGuard().record(
            command="publications", estimated_credits=1, note=name or register or ""
        )
    _emit(data, pretty, title="Publications")


@app.command()
@_handle_api_errors
def billing(
    year: Annotated[Optional[int], typer.Option()] = None,
    month: Annotated[Optional[int], typer.Option()] = None,
    api_key: APIKey = None,
    pretty: Pretty = False,
) -> None:
    """Free. Current usage for the billing period."""
    with _build_client(api_key) as client:
        data = client.billing(year=year, month=month)
    _emit(data, pretty, title="Billing")


@app.command()
@_handle_api_errors
def reference(
    what: Annotated[
        str,
        typer.Argument(help="'overview' or 'segments'."),
    ],
    standard: Annotated[str, typer.Option(help="For 'segments': e.g. 'NACE2025'.")]
    = "NACE2025",
    api_key: APIKey = None,
    pretty: Pretty = False,
) -> None:
    """Free. Reference data (overview, segment codes, ...)."""
    with _build_client(api_key) as client:
        if what == "overview":
            data = client.reference_overview()
        elif what == "segments":
            data = client.reference_segment_codes(standard=standard)
        else:
            err_console.print(
                f"[red]error:[/red] unknown reference type '{what}'. "
                "Use 'overview' or 'segments'."
            )
            raise typer.Exit(code=2)
    _emit(data, pretty, title=f"Reference: {what}")


@app.command()
def credits(
    pretty: Pretty = False,
) -> None:
    """Show local credit log (this CLI's best-effort tracking)."""
    guard = CreditGuard()
    entries = guard.entries()
    summary = {
        "log_path": str(guard.log_path),
        "total_estimated_credits": guard.total(),
        "month_estimated_credits": guard.month_total(),
        "entry_count": len(entries),
        "entries": entries,
    }
    _emit(summary, pretty, title="Local credit log")


if __name__ == "__main__":  # pragma: no cover
    app()
