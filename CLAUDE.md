# northdata-connectors — Dev Notes

Monorepo für eine produktseitige Kapselung der [NorthData](https://www.northdata.com)-API in drei Schichten: CLI, MCP-Server, Claude-Skill.

## Repo-Layout

```
northdata-connectors/
├── README.md                          # Public-facing
├── CLAUDE.md                          # diese Datei (Dev-Kontext)
├── diagrams/                          # lokale Sample-Diagramme (via .gitignore, NICHT committed)
├── northdata-cli/                     # CLI-Paket (→ PyPI: northdata-cli)
├── northdata-mcp/                     # MCP-Server (→ PyPI: northdata-mcp, → MCP Registry)
│   └── server.json                    # MCP-Registry-Manifest
└── skills/northdata/                  # Claude Skill (→ skills.sh + Clawhub)
    └── SKILL.md
```

## Sub-Pakete

### `northdata-cli/`
Installierbare Python-CLI als Wrapper um die NorthData-API. Single Source of Truth für die API-Logik.
- Python 3.10+, Typer, httpx, Rich, hatchling
- Entry-Point: `northdata`
- Commands: `suggest`, `search`, `company`, `person`, `publications`, `reference`, `billing`, `credits`
- Credit Guard zweistufig: `NORTHDATA_APPROVAL_THRESHOLD` (25) + `NORTHDATA_ABSOLUTE_MAX` (100, flag-immun)
- Globale Flags: `--api-key`, `--pretty`, `--dry-run`, `--approve-high-cost`
- Lokaler Log: `~/.northdata/credits.jsonl`
- Tests: 58 (Client, CreditGuard, Config, Output, CLI via `httpx.MockTransport`)

### `northdata-mcp/`
MCP-Server (FastMCP v3, stdio-Transport) als dünner Wrapper um `NorthDataClient` + `CreditGuard` aus der CLI.
- Entry-Point: `northdata-mcp`
- 9 Tools: `suggest`, `billing`, `reference_overview`, `reference_segment_codes`, `local_credit_log`, `search`, `company`, `person`, `publications`
- Tags `free` / `billed`, Annotations `readOnlyHint`/`openWorldHint`
- `dry_run=true` auf allen billed Tools
- Fehler als strukturiertes Dict (`error`, `status_code`, `message`, `body`) — keine Exception-Leaks
- Tests: 17 (in-memory FastMCP-Client)
- `server.json` im Paket-Root für MCP-Registry-Publish

### `skills/northdata/`
Claude Skill als Bedienungsanleitung + Credit-Guard-Leitplanken.
- Detection-Logik: MCP → sonst CLI → sonst Install-Hinweis
- Best-Practice-Workflow: free-first, dry-run, ein `company`-Call deckt meistens alles ab
- Tool-Referenz als CLI↔MCP-Matrix mit Costs
- Pfadkonvention `skills/<name>/SKILL.md` → via `npx skills add p-meier/northdata-connectors` aus GitHub auffindbar

## Arbeitsweise

- **CLI ist Single Source of Truth.** MCP und Skill bauen darauf auf, duplizieren keine Logik.
- **NorthData-Billing-Modell** (pro abgerufener Firma, nicht pro HTTP-Call) ist die wichtigste Architektur-Constraint und muss in CLI (Credit Guard) und Skill (Disziplin-Hinweise) explizit adressiert sein.
- **Doku auf Deutsch** in CLAUDE.md / lokalen Notizen; Public READMEs auf Englisch. Code/Identifier auf Englisch.

## Publishing

| Ziel | Tool | Befehl |
|---|---|---|
| GitHub | `gh` | bereits live unter `p-meier/northdata-connectors` |
| PyPI (CLI) | `uv` | `cd northdata-cli && uv build && uv publish` |
| PyPI (MCP) | `uv` | `cd northdata-mcp && uv build && uv publish` (nach CLI!) |
| MCP Registry | `mcp-publisher` | `cd northdata-mcp && mcp-publisher login github && mcp-publisher publish` |
| skills.sh | — | automatisch via `npx skills add p-meier/northdata-connectors` (kein Publish-Step) |
| Clawhub | `clawhub` | `npx clawhub skill publish ./skills/northdata --slug northdata --name "NorthData" --version 0.1.0 --changelog "Initial release"` |

Reihenfolge: CLI-PyPI → MCP-PyPI → MCP-Registry → Clawhub. Skill discovery läuft automatisch, sobald das Repo public ist.

## Dev-Umgebung

- **API-Key**: `NORTHDATA_API_KEY` als Env-Var setzen — niemals in Dateien committen.
- **Venvs** unter `northdata-cli/.venv` und `northdata-mcp/.venv` (via `python3 -m venv .venv && pip install -e ".[dev]"`).
- **Test-Commands**:
  - CLI: `cd northdata-cli && .venv/bin/python -m pytest`
  - MCP: `cd northdata-mcp && .venv/bin/pip install -e ../northdata-cli && .venv/bin/python -m pytest`

## Diagramme

`diagrams/` ist via `.gitignore` ausgeschlossen — die Excalidraw-/PNG-Dateien sind nur lokal und werden nicht ins öffentliche Repo gespiegelt. Re-Rendering (lokal) nach Änderung:

```bash
cd ~/.claude/skills/excalidraw-diagram/references
uv run python render_excalidraw.py <pfad>.excalidraw --output <pfad>.png --scale 2
```

## Offen / nächste Schritte

- PyPI-Publish `northdata-cli`, dann `northdata-mcp`
- MCP-Registry-Publish via `mcp-publisher publish`
- Clawhub-Publish via `clawhub skill publish`
- Ggf. GitHub Actions: pytest auf push + Release-Automatisierung bei Tag-Push
- Ggf. HTTP-Transport im MCP-Server nachrüsten
