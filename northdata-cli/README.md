# northdata-cli

A command-line client for the [NorthData](https://www.northdata.com) API with a built-in **credit guard**.

`northdata-cli` wraps the relevant NorthData endpoints (suggest, power search, company, person, publications, reference, billing) behind a clean, installable CLI. It is usable interactively by humans and unattended by scripts or agents — every command emits JSON by default and a pretty table with `--pretty`.

> **Why a credit guard?** NorthData charges **per returned company**, not per HTTP call. A single `search --limit 100` can burn 100 credits in one request. This CLI refuses unapproved high-limit calls and keeps a local append-only log of every billed call it makes.

---

## Installation

### Regular install (Recommended)

```bash
pipx install northdata-cli
# or
pip install northdata-cli
```

### One-shot via `uvx` (no install)

```bash
uvx northdata --help
```

### Editable install for development

```bash
git clone https://github.com/p-meier/northdata-connectors.git
cd northdata-connectors/northdata-cli
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

---

## Configuration

### API key (required)

Set the `NORTHDATA_API_KEY` environment variable:

```bash
export NORTHDATA_API_KEY="XXXX-XXXX"
```

Or pass it per invocation:

```bash
northdata suggest "Example GmbH" --api-key XXXX-XXXX
```

Get a key at <https://www.northdata.com>.

### Optional: credit guard thresholds

```bash
export NORTHDATA_APPROVAL_THRESHOLD=25   # above this, --approve-high-cost is required
export NORTHDATA_ABSOLUTE_MAX=100        # absolute ceiling for --limit
export NORTHDATA_CREDIT_LOG=~/.northdata/credits.jsonl  # override log path
```

---

## Quickstart

```bash
# Free: discover what the API knows about a company name
northdata suggest "Siemens" --pretty

# Free: show your current credit usage for the period
northdata billing --pretty

# Billed (1 credit): full company profile by register
northdata company --register "HRB123456/Muenchen" --pretty

# Billed (up to --limit credits): power search with filters
northdata search \
    --segment-codes "62|63" \
    --legal-forms "GmbH|UG" \
    --address "Munich" --max-distance-km 150 \
    --revenue-min 5000000 --revenue-max 50000000 \
    --limit 5 --pretty

# Peek without spending credits
northdata search --segment-codes "62" --legal-forms "GmbH" --limit 5 --dry-run
```

---

## Credit guard

Every billable command respects a two-tier ceiling on `--limit`:

| Tier | Default | Override |
|---|---|---|
| Approval threshold (requires `--approve-high-cost` to exceed) | `25` | `NORTHDATA_APPROVAL_THRESHOLD` |
| Absolute maximum (hard stop, flag-immune) | `100` | `NORTHDATA_ABSOLUTE_MAX` |

On top of that, every billed call is appended to `~/.northdata/credits.jsonl`:

```bash
northdata credits --pretty
```

The local log is informational — the NorthData billing endpoint (`northdata billing`) remains the source of truth for actual credit consumption.

### `--dry-run`

Any billable command with `--dry-run` builds the request URL and returns it without calling the API. Zero credits spent.

```bash
northdata company --register "HRB123456/Muenchen" --dry-run
```

---

## Command reference

| Command | Billed | Purpose |
|---|---|---|
| `suggest QUERY` | — | Autocomplete for company / person names |
| `search [filters]` | up to `--limit` | Power search |
| `company --register \| --name` | 1 | Full company profile |
| `person FIRST LAST` | 1 | Person lookup (incl. birth date) |
| `publications [--name \| --register]` | 1 | Publications (e.g. shareholder lists) |
| `reference overview \| segments` | — | API reference data |
| `billing` | — | Current credit usage for the billing period |
| `credits` | — | Local credit log (this CLI only) |

Use `northdata COMMAND --help` for the full option list.

### Output formats

- Default: JSON on stdout, pipeable into `jq` and friends.
- `--pretty` / `-p`: Rich table on stderr-free stdout for humans.

---

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `2` | Configuration error (missing key, bad argument) |
| `3` | Credit guard refused the request |
| `4` | NorthData API error (HTTP 4xx / 5xx / timeout) |

---

## Development

```bash
pip install -e ".[dev]"
pytest
pytest --cov
```

Tests use `httpx.MockTransport` — no network access required for the unit test suite.

---

## License

MIT. See [LICENSE](LICENSE).

---

## Project status

This CLI is the library layer for the [`northdata-mcp`](https://pypi.org/project/northdata-mcp/) MCP server and the `northdata` Claude skill. The client and credit guard are written to be importable as a Python library so those layers can reuse them directly without shelling out.

See the [monorepo root](https://github.com/p-meier/northdata-connectors) for the full picture.
