"""HTTP-Client für die NorthData-API.

Credit-Modell:
    NorthData rechnet pro zurückgegebener Firma ab, nicht pro HTTP-Call.
    Bei Power Search gilt: bis zu ``limit`` Firmen = bis zu ``limit`` Credits
    pro Request. Dieser Client erzwingt einen zweistufigen Schutz:

    - ``approval_threshold`` (Default 25): ``limit`` darüber braucht
      ``approve_high_cost=True``.
    - ``absolute_max`` (Default 100): harte Obergrenze, kann nicht per Flag
      umgangen werden — nur via Env-Var ``NORTHDATA_ABSOLUTE_MAX``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Iterable

import httpx


BASE_URL = "https://www.northdata.com/_api"
DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 3
DEFAULT_POWER_LIMIT = 5


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(
            f"Env-Var {name}={raw!r} ist keine gültige Ganzzahl."
        ) from exc


class CreditGuardError(Exception):
    """Vorab-Abbruch eines potenziell teuren Requests."""


class NorthDataAPIError(Exception):
    """Fehler bei der NorthData-API (HTTP-Fehler, Timeouts, etc.)."""

    def __init__(self, message: str, status_code: int | None = None, body: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


Indicator = tuple[str, float | int | None, float | int | None]


@dataclass
class NorthDataClient:
    """Synchroner NorthData-Client.

    Der Client ist bewusst dünn — keine Domain-Logik, keine Filterung,
    keine Workflow-Annahmen. Nur Endpoint-Wrapper + Credit-Guard.
    """

    api_key: str
    base_url: str = BASE_URL
    dry_run: bool = False
    timeout: float = DEFAULT_TIMEOUT
    retries: int = DEFAULT_RETRIES
    approval_threshold: int = field(
        default_factory=lambda: _env_int("NORTHDATA_APPROVAL_THRESHOLD", 25)
    )
    absolute_max: int = field(
        default_factory=lambda: _env_int("NORTHDATA_ABSOLUTE_MAX", 100)
    )
    transport: httpx.BaseTransport | None = None

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ValueError(
                "api_key fehlt. Setze NORTHDATA_API_KEY oder übergib --api-key."
            )
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "X-Api-Key": self.api_key,
                "Accept": "application/json",
                "User-Agent": "northdata-cli/0.1.0",
            },
            timeout=self.timeout,
            transport=self.transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "NorthDataClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ── Low-level ─────────────────────────────────────────────────────

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        clean_params = (
            {k: v for k, v in params.items() if v is not None}
            if params
            else None
        )
        if self.dry_run:
            req = self._client.build_request("GET", path, params=clean_params)
            return {"_dry_run": True, "url": str(req.url)}

        last_exc: Exception | None = None
        for attempt in range(self.retries):
            try:
                resp = self._client.get(path, params=clean_params)
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < self.retries - 1:
                    continue
                raise NorthDataAPIError(
                    f"Netzwerk-Fehler nach {self.retries} Versuchen: {exc}"
                ) from exc

            if resp.status_code == 429:
                if attempt < self.retries - 1:
                    continue
                raise NorthDataAPIError(
                    "Rate-Limit überschritten (HTTP 429). Bitte später erneut "
                    "versuchen.",
                    status_code=429,
                    body=resp.text,
                )
            if resp.status_code >= 500 and attempt < self.retries - 1:
                continue
            if resp.status_code >= 400:
                raise NorthDataAPIError(
                    f"HTTP {resp.status_code} von {path}",
                    status_code=resp.status_code,
                    body=resp.text,
                )
            if not resp.content:
                return None
            return resp.json()

        raise NorthDataAPIError(f"Unerwarteter Abbruch: {last_exc}")

    # ── Kostenlose Endpoints ──────────────────────────────────────────

    def billing(self, year: int | None = None, month: int | None = None) -> Any:
        """Kostenlos. Aktueller Credit-Verbrauch."""
        params: dict[str, Any] = {}
        if year is not None:
            params["year"] = str(year)
        if month is not None:
            params["month"] = str(month)
        return self._get("/billing/v1/requests", params or None)

    def suggest(
        self,
        query: str,
        domain: str = "company",
        status: str = "active",
        countries: str = "DE",
        limit: int = 10,
    ) -> Any:
        """Kostenlos. Autocomplete / Firmen-/Personen-Vorschläge."""
        return self._get(
            "/search/v1/suggest",
            {
                "query": query,
                "domain": domain,
                "status": status,
                "countries": countries,
                "limit": str(limit),
            },
        )

    def reference_overview(self) -> Any:
        """Kostenlos. Referenzdaten (Standards, Länder, Rechtsformen, …)."""
        return self._get("/reference/v1/overview")

    def reference_segment_codes(self, standard: str = "NACE2025") -> Any:
        """Kostenlos. Segment-Codes für einen Standard."""
        return self._get("/reference/v1/segmentCodes", {"standard": standard})

    # ── Power Search (kostenpflichtig) ────────────────────────────────

    def build_power_params(
        self,
        *,
        segment_codes: Iterable[str] | None = None,
        segment_standard: str = "NACE2025",
        legal_forms: Iterable[str] | None = None,
        indicators: Iterable[Indicator] | None = None,
        address: str | None = None,
        max_distance_km: int | None = None,
        countries: str = "DE",
        status: str = "active",
        limit: int = DEFAULT_POWER_LIMIT,
        pos: str | None = None,
        extra_params: dict[str, Any] | None = None,
        approve_high_cost: bool = False,
    ) -> dict[str, Any]:
        """Baut die Query-Params für Power Search und validiert das Limit."""
        self._validate_limit(limit, approve_high_cost)

        params: dict[str, Any] = {
            "countries": countries,
            "status": status,
            "segmentCodeStandard": segment_standard,
            "limit": str(limit),
        }
        if segment_codes:
            params["segmentCodes"] = "|".join(segment_codes)
        if legal_forms:
            params["legalForm"] = "|".join(legal_forms)
        if address:
            params["address"] = address
        if max_distance_km is not None:
            params["maxDistanceKm"] = str(max_distance_km)
        if indicators:
            ids, lowers, uppers = [], [], []
            for ind_id, lo, up in indicators:
                ids.append(ind_id)
                lowers.append("" if lo is None else str(int(lo)))
                uppers.append("" if up is None else str(int(up)))
            params["indicatorId"] = "|".join(ids)
            params["lowerBound"] = "|".join(lowers)
            params["upperBound"] = "|".join(uppers)
        if pos:
            params["pos"] = pos
        if extra_params:
            params.update(extra_params)
        return params

    def _validate_limit(self, limit: int, approve_high_cost: bool) -> None:
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise CreditGuardError(
                f"limit muss eine Ganzzahl sein, erhalten: {type(limit).__name__}."
            )
        if limit < 1:
            raise CreditGuardError("limit muss >= 1 sein.")
        if limit > self.absolute_max:
            raise CreditGuardError(
                f"limit={limit} überschreitet ABSOLUTE_MAX={self.absolute_max}. "
                f"Dieser Schutz kann nicht per Flag umgangen werden. Erhöhe "
                f"NORTHDATA_ABSOLUTE_MAX explizit als Env-Var oder teile die "
                f"Suche via pos-Parameter auf."
            )
        if limit > self.approval_threshold and not approve_high_cost:
            raise CreditGuardError(
                f"limit={limit} überschreitet APPROVAL_THRESHOLD="
                f"{self.approval_threshold} und ist nicht genehmigt. "
                f"Setze approve_high_cost=True (CLI: --approve-high-cost) "
                f"oder reduziere limit auf <= {self.approval_threshold}."
            )

    def power_search(
        self,
        *,
        segment_codes: Iterable[str] | None = None,
        segment_standard: str = "NACE2025",
        legal_forms: Iterable[str] | None = None,
        indicators: Iterable[Indicator] | None = None,
        address: str | None = None,
        max_distance_km: int | None = None,
        countries: str = "DE",
        status: str = "active",
        limit: int = DEFAULT_POWER_LIMIT,
        pos: str | None = None,
        extra_params: dict[str, Any] | None = None,
        approve_high_cost: bool = False,
    ) -> Any:
        """Kostenpflichtig. Kosten = Anzahl zurückgegebener Firmen (max. limit)."""
        params = self.build_power_params(
            segment_codes=segment_codes,
            segment_standard=segment_standard,
            legal_forms=legal_forms,
            indicators=indicators,
            address=address,
            max_distance_km=max_distance_km,
            countries=countries,
            status=status,
            limit=limit,
            pos=pos,
            extra_params=extra_params,
            approve_high_cost=approve_high_cost,
        )
        return self._get("/search/v1/power", params)

    # ── Firmen-Detail (1 Credit pro Call) ─────────────────────────────

    def company(
        self,
        *,
        name: str | None = None,
        city: str | None = None,
        register: str | None = None,
        owners: bool = True,
        financials: bool = True,
        representatives: bool = True,
        extras: bool = True,
        sheets: bool = True,
        events: bool = True,
        language: str = "de",
    ) -> Any:
        """1 Credit. Vollprofil einer Firma.

        Entweder ``register`` (z.B. ``HRB123456/Muenchen``) ODER ``name`` [+ ``city``]
        angeben.
        """
        if not register and not name:
            raise ValueError("Entweder register oder name angeben.")
        params: dict[str, Any] = {
            "language": language,
            "owners": "true" if owners else "false",
            "financials": "true" if financials else "false",
            "representatives": "true" if representatives else "false",
            "extras": "true" if extras else "false",
            "sheets": "true" if sheets else "false",
            "events": "true" if events else "false",
        }
        if register:
            params["register"] = register
        else:
            params["name"] = name
            if city:
                params["address"] = city
        return self._get("/company/v1/company", params)

    def person(
        self,
        *,
        first_name: str,
        last_name: str,
        city: str | None = None,
        language: str = "de",
    ) -> Any:
        """1 Credit. Personendetails inkl. Geburtsdatum / Rollen."""
        params: dict[str, Any] = {
            "firstName": first_name,
            "lastName": last_name,
            "language": language,
        }
        if city:
            params["address"] = city
        return self._get("/person/v1/person", params)

    def publications(
        self,
        *,
        name: str | None = None,
        register: str | None = None,
        source: str | None = None,
        language: str = "de",
    ) -> Any:
        """Kostenpflichtig. Publikationen (z.B. Gesellschafterlisten via source=Hrb)."""
        params: dict[str, Any] = {"language": language}
        if name:
            params["name"] = name
        if register:
            params["register"] = register
        if source:
            params["source"] = source
        return self._get("/pub/v1/publications", params)
