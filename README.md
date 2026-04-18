# NorthData Connectors

> Generic, product-side wrapper around the [NorthData](https://www.northdata.com) API — a Python CLI, an MCP server, and a Claude Skill, sharing one credit guard.

[![PyPI — northdata-cli](https://img.shields.io/pypi/v/northdata-cli?label=northdata-cli)](https://pypi.org/project/northdata-cli/)
[![PyPI — northdata-mcp](https://img.shields.io/pypi/v/northdata-mcp?label=northdata-mcp)](https://pypi.org/project/northdata-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

This monorepo ships three layers on top of the NorthData API:

| Package | What it is | Install |
|---|---|---|
| [`northdata-cli`](./northdata-cli) | Command-line client. JSON-by-default, table with `--pretty`. Single source of API logic. | `pipx install northdata-cli` |
| [`northdata-mcp`](./northdata-mcp) | [Model Context Protocol](https://modelcontextprotocol.io) server exposing every CLI command as a tool. Works with Claude Desktop, Claude Code, Cursor, etc. | `pipx install northdata-mcp` |
| [`skills/northdata`](./skills/northdata) | Claude Skill with usage guidance, credit-guard discipline, and endpoint cheat-sheet. | `npx skills add p-meier/northdata-connectors` |

All three share **one credit guard** because NorthData charges per returned company, not per HTTP call.

---

## Why this exists

NorthData's API is the canonical source for German commercial-register data (company profiles, owners, representatives, financials, publications). This repo makes it trivial to consume that data from:

- Shell scripts and CI pipelines (`northdata search ...`)
- AI agents in any MCP-capable client (Claude Desktop, Cursor, Claude Code, …)
- Claude Skills that want domain-aware guidance without duplicating API code

The three layers never duplicate logic — the CLI is the library, the MCP server imports it, the Skill references the MCP tools.

---

## Quick start

### 1. Get a NorthData API key

At <https://www.northdata.com>. Set it as `NORTHDATA_API_KEY`.

### 2. Install what you need

```bash
# Shell usage
pipx install northdata-cli
export NORTHDATA_API_KEY=XXXX-XXXX
northdata suggest "Siemens" --pretty

# MCP server for Claude Desktop / Cursor / Claude Code
pipx install northdata-mcp
# then add the stdio server to your MCP client config
# (see northdata-mcp/README.md)

# Claude Skill — usage guidance for agents
npx skills add p-meier/northdata-connectors
```

### 3. Credit-safe by default

Every billable call respects two tiers:

| Tier | Default | Env var |
|---|---|---|
| Approval threshold | `25` | `NORTHDATA_APPROVAL_THRESHOLD` |
| Absolute maximum | `100` | `NORTHDATA_ABSOLUTE_MAX` |

Use `--dry-run` (CLI) or `dry_run=true` (MCP) to inspect a request without spending credits.

---

## Architecture

```
                      ┌─────────────────────────────────────────┐
                      │         NorthData API (HTTP)            │
                      └─────────────────────────────────────────┘
                                        ▲
                                        │ httpx + Credit Guard
                                        │
                            ┌───────────────────────┐
                            │   northdata-cli       │  ← single source of API logic
                            │   (Python library)    │     (client, credit guard,
                            └───────────────────────┘      config, output)
                                ▲               ▲
                    imports     │               │  invokes
                                │               │
              ┌───────────────────────┐   ┌───────────────────────┐
              │   northdata-mcp       │   │   shell / CI /        │
              │   (FastMCP, stdio)    │   │   scripts             │
              └───────────────────────┘   └───────────────────────┘
                        ▲
                        │ MCP over stdio
                        │
              ┌───────────────────────┐
              │   Claude / Cursor /   │   ← with skills/northdata/SKILL.md
              │   any MCP client      │     loaded for usage guidance
              └───────────────────────┘
```

The CLI holds the API logic; the MCP server is a thin wrapper; the Skill is documentation-as-code. All three share one credit guard.

---

## Development

```bash
git clone https://github.com/p-meier/northdata-connectors.git
cd northdata-connectors

# CLI
cd northdata-cli && python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]" && pytest

# MCP
cd ../northdata-mcp && python -m venv .venv && source .venv/bin/activate
pip install -e "../northdata-cli" -e ".[dev]" && pytest
```

---

## License

MIT. See [LICENSE](northdata-cli/LICENSE).

---

## Links

- **NorthData API docs:** <https://www.northdata.com/doc/api>
- **Model Context Protocol:** <https://modelcontextprotocol.io>
- **Claude Skills (skills.sh):** <https://skills.sh>
