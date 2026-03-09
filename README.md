# drs — Developer CLI for Dremio Cloud

A command-line tool for working with Dremio Cloud. Run SQL queries, browse the catalog, inspect table schemas, manage reflections, monitor jobs, and audit access — from your terminal or any automation pipeline.

Built for developers who want to script against Dremio without clicking through a UI, and for AI agents that need structured access to Dremio metadata and query execution.

> **Dremio Cloud only.** Dremio Software (self-hosted) has different auth and API behavior and is not supported in this version.

## Status

This project is in active development on the [`draft/drs-spike`](https://github.com/dremio/cli/tree/draft/drs-spike) branch. See [PR #1](https://github.com/dremio/cli/pull/1) for the full implementation.

## Why this exists

Dremio Cloud has a powerful REST API and rich system tables, but no official CLI. That means:

- Debugging a slow query requires navigating the UI to find the job, then manually inspecting the profile
- Scripting catalog operations means hand-rolling `curl` commands with auth headers
- AI agents (Claude, GPT, etc.) need structured tool interfaces, not raw HTTP

`drs` wraps all of this into a single binary with consistent output formats, input validation, and structured error handling.

## What it does

21 commands across 6 groups:

| Group | Commands | What it does |
|-------|----------|--------------|
| `drs query` | `run`, `status`, `cancel` | Execute SQL, check job status, cancel running jobs |
| `drs catalog` | `list`, `get`, `search` | Browse sources/spaces, get entity metadata, full-text search |
| `drs schema` | `describe`, `lineage`, `wiki`, `sample` | Column types, upstream/downstream deps, wiki docs, preview rows |
| `drs reflect` | `list`, `status`, `refresh`, `drop` | List reflections on a dataset, check freshness, trigger refresh |
| `drs jobs` | `list`, `get`, `profile` | Recent jobs with filters, job details, operator-level profiles |
| `drs access` | `grants`, `roles`, `whoami`, `audit` | ACLs on entities, org roles, user permission audit |

Plus a Claude Code plugin with 8 workflow skills (slow query diagnosis, access audit, data quality checks, source onboarding, and more).

## Quick look

```bash
# Run a query
drs query run "SELECT * FROM myspace.orders LIMIT 5" --output pretty

# Search the catalog
drs catalog search "revenue"

# Describe a table
drs schema describe myspace.analytics.monthly_revenue

# Check reflections on a dataset
drs reflect list myspace.orders

# Find failed jobs
drs jobs list --status FAILED

# Audit a user's permissions
drs access audit rahim.bhojani
```

All commands output JSON by default (for piping to `jq` or agent consumption), with `--output csv` and `--output pretty` also available.

## Prerequisites

- **Python 3.11+**
- **A Dremio Cloud account** with a project
- **A Personal Access Token (PAT)** — generate from Dremio Cloud > Account Settings > Personal Access Tokens

## Getting started

```bash
# Clone and install
git clone https://github.com/dremio/cli.git
cd cli
git checkout draft/drs-spike
uv tool install .

# Configure
mkdir -p ~/.config/dremioai
cat > ~/.config/dremioai/config.yaml << 'EOF'
pat: dremio_pat_xxxxxxxxxxxxx
project_id: your-project-id
EOF
chmod 600 ~/.config/dremioai/config.yaml

# Verify
drs query run "SELECT 1 AS hello"
```

Or use environment variables instead of a config file:

```bash
export DREMIO_PAT=dremio_pat_xxxxxxxxxxxxx
export DREMIO_PROJECT_ID=your-project-id
```

## How it works

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  drs CLI     │────▶│  client.py   │────▶│ Dremio Cloud API │
│  (typer)     │     │  (httpx)     │     │ (REST + SQL)     │
└─────────────┘     └──────────────┘     └─────────────────┘
```

- **One HTTP layer** — `client.py` is the only file that makes network calls
- **REST + SQL hybrid** — some operations use REST (catalog, reflections), others query system tables via SQL (jobs, reflection listing by dataset). The user doesn't need to know which.
- **Input validation** — all agent/user-provided values are validated before use (UUID format checks, SQL injection prevention, path traversal detection)

## For AI agents

`drs` is designed to be agent-friendly:

- **JSON output by default** — structured, no parsing needed
- **`drs describe <command>`** — agents can discover parameter schemas at runtime
- **`--fields` filtering** — reduce output to specific fields to fit context windows
- **Consistent error format** — API errors return `{"error": "...", "status_code": N}`

Import directly for programmatic use:

```python
from drs.auth import load_config
from drs.client import DremioClient
from drs.commands.query import run_query

config = load_config()
client = DremioClient(config)
result = await run_query(client, "SELECT * FROM myspace.orders LIMIT 10")
```

## Related projects

| Repo | Relationship |
|------|-------------|
| `dremio/dremio-mcp` | Sibling — MCP server for AI agent integration. Config format is shared. |
| `dremio/claude-plugins` | Predecessor — skills rewritten to use `drs` commands. |

## License

Apache 2.0
