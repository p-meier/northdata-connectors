# NorthData MCP Server

<!--
mcp-name: io.github.p-meier/northdata-mcp
-->

> Connect the [NorthData](https://www.northdata.com) company-data API to Claude Desktop, Claude Code, Cursor, and other AI assistants.

The [Model Context Protocol](https://modelcontextprotocol.io) (MCP) standardizes how Large Language Models (LLMs) talk to external services like NorthData. This server exposes NorthData's suggest, search, company, person, publications, reference, and billing endpoints as MCP tools, with a built-in **credit guard** that prevents accidental high-cost calls. See the [full list of tools](#tools).

Built on **[FastMCP v3](https://gofastmcp.com)**. Uses **stdio** transport — the MCP client launches `northdata-mcp` as a subprocess.

---

## Setup

### 1. Read the security notes

Before running the server, skim the [security considerations](#security-considerations). NorthData costs real money per returned company, and MCP lets LLMs spend those credits autonomously. The credit guard mitigates this, but defence in depth matters.

### 2. Install the server

```bash
pipx install northdata-mcp
```

This pulls in the sibling [`northdata-cli`](https://pypi.org/project/northdata-cli/) package automatically and exposes the `northdata-mcp` console script globally.

Alternative via `uv`:

```bash
uvx northdata-mcp --help
```

### 3. Get a NorthData API key

Obtain a key at <https://www.northdata.com>. You'll put it into the MCP client config in the next step.

Optional credit-guard overrides (set as env vars in the MCP client config):

| Env var | Default | Purpose |
|---|---|---|
| `NORTHDATA_APPROVAL_THRESHOLD` | `25` | `search` `limit` above this requires `approve_high_cost=true` |
| `NORTHDATA_ABSOLUTE_MAX` | `100` | Hard cap on `search` `limit`, flag-immune |
| `NORTHDATA_CREDIT_LOG` | `~/.northdata/credits.jsonl` | Local credit log path |

### 4. Configure your MCP client

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS) — adjust the path on Windows / Linux:

```json
{
  "mcpServers": {
    "northdata": {
      "command": "northdata-mcp",
      "env": {
        "NORTHDATA_API_KEY": "XXXX-XXXX"
      }
    }
  }
}
```

Restart Claude Desktop. The NorthData tools will appear in the tool picker.

### Claude Code

```bash
claude mcp add northdata --env NORTHDATA_API_KEY=XXXX-XXXX -- northdata-mcp
```

### Cursor

Add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "northdata": {
      "command": "northdata-mcp",
      "env": { "NORTHDATA_API_KEY": "XXXX-XXXX" }
    }
  }
}
```

### Any MCP client (generic)

Run `northdata-mcp` as a subprocess and speak MCP over stdio. The environment must contain `NORTHDATA_API_KEY`.

---

## Tools

_**Note:** this server is pre-1.0, expect minor breaking changes between versions._

Every tool is a thin wrapper around the equivalent `northdata-cli` command. Tools are tagged `free` (no credits spent) or `billed` (consumes NorthData credits). MCP annotations (`readOnlyHint`, `openWorldHint`) are set on every tool so well-behaved clients can surface them in the UI.

### Free tools

No NorthData credits are consumed by these tools.

- **`suggest`** — Autocomplete company or person names. Cheap first step before spending a credit on `company` or `person`.
- **`billing`** — Current remote credit usage for the billing period (`numberOfRequests`, `periodStart`, `periodEnd`).
- **`reference_overview`** — API reference data: standards, countries, legal forms, events.
- **`reference_segment_codes`** — Complete segment-code list for a given standard (default `NACE2025`).
- **`local_credit_log`** — Credit log maintained locally by this server: total, per-month, per-entry breakdown.

### Billed tools

Every one of these **spends NorthData credits**. NorthData charges per returned company, not per request. The credit guard enforces a two-tier ceiling on `search` (see [Credit guard](#credit-guard)). All billed tools accept `dry_run=true` to build and return the URL without spending credits.

- **`search`** — Power search. Cost: up to `limit` credits. Filters: `segment_codes`, `segment_standard`, `legal_forms`, `address`, `max_distance_km`, `countries`, `status`, `revenue_min/max`, `earnings_min/max`, `limit`, `pos`, `approve_high_cost`.
- **`company`** — Full company profile (1 credit). Identify by `register` (e.g. `HRB 123456/Muenchen`) or by `name` + optional `city`. Toggles: `owners`, `financials`, `representatives`, `extras`, `sheets`, `events`.
- **`person`** — Person lookup (1 credit). Returns birth date and known roles. Takes `first_name`, `last_name`, optional `city`.
- **`publications`** — Publications lookup (1 credit). Useful for shareholder lists via `source="Hrb"`.

---

## Credit guard

NorthData bills per returned company. A single `search` call with `limit=100` costs up to 100 credits. This server enforces two tiers:

| Tier | Default | Override |
|---|---|---|
| Approval threshold — `limit` above this requires `approve_high_cost=true` | `25` | `NORTHDATA_APPROVAL_THRESHOLD` |
| Absolute maximum — hard cap, ignores `approve_high_cost` | `100` | `NORTHDATA_ABSOLUTE_MAX` (set explicitly by a human, never by an LLM) |

Every billed tool call is appended to the local credit log (JSON-lines). The `local_credit_log` tool surfaces it. The log is informational; `billing` remains the source of truth.

Use `dry_run=true` on any billed tool to inspect the request URL before spending anything.

---

## Security considerations

Connecting a credit-consuming data source to an LLM carries real costs and real risks. A malicious or malformed prompt can cause an agent to burn credits, leak structured company data into an untrusted chat, or combine NorthData data with other tools in unintended ways.

### Recommendations

- **Keep the credit guard strict.** The defaults (approval 25, absolute max 100) exist to prevent a runaway agent from draining your credits in a single call. Only raise them deliberately.
- **Prefer free tools during exploration.** `suggest`, `reference_*`, and `billing` are free. LLMs should call these before moving to `company` / `person` / `publications`.
- **Use `dry_run=true`** when experimenting with new search parameters or register identifiers.
- **Review tool calls before approval.** Most MCP clients (Claude Desktop, Cursor) ask you to approve each tool call. Leave that setting on.
- **Limit scope per session.** Launch the server with a trial API key, not your main production key, when giving it to an agent for open-ended work.
- **Prompt injection.** NorthData responses contain user-generated text (company descriptions, publications) that an adversary could stuff with instructions. Treat tool output as untrusted data, not as trusted instructions to the LLM.

---

## Development

```bash
cd northdata-mcp
python -m venv .venv && source .venv/bin/activate
pip install -e "../northdata-cli"   # local editable CLI
pip install -e ".[dev]"
pytest
```

Tests use FastMCP's in-memory transport — no subprocess, no network. The underlying `NorthDataClient` is injected via a mock factory backed by `httpx.MockTransport`.

---

## Resources

- **Model Context Protocol:** <https://modelcontextprotocol.io>
- **FastMCP v3 docs:** <https://gofastmcp.com>
- **NorthData API:** <https://www.northdata.com/doc/api>
- **Sibling package:** [`northdata-cli`](../northdata-cli) — same tools, plain command-line

---

## License

MIT. See [LICENSE](LICENSE).
