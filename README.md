# drs — Developer CLI for Dremio Cloud

A developer CLI + Claude Code plugin for Dremio Cloud. Query data, browse catalogs, inspect schemas, manage reflections, monitor jobs, and audit access — all from the terminal.

> **Scope:** Dremio Cloud only. Dremio Software has different auth and API behavior — not supported in this version.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  drs CLI     │────▶│  client.py   │────▶│ Dremio Cloud API │
│  (typer)     │     │  (httpx)     │     │ (REST + SQL)     │
└─────────────┘     └──────────────┘     └─────────────────┘
```

Commands talk to `client.py` (the single HTTP layer). Some operations use the REST API directly (catalog, reflections, access), others use SQL via system tables (jobs, reflection listing by dataset).

## Quickstart

### Install

```bash
# From source
uv tool install .

# Or with pip
pip install .
```

### Configure

Create `~/.config/dremioai/config.yaml`:

```yaml
pat: dremio_pat_xxxxxxxxxxxxx
project_id: your-project-id
# uri: https://api.dremio.cloud  # default, change for EU region
```

Or use environment variables:

```bash
export DREMIO_PAT=dremio_pat_xxxxxxxxxxxxx
export DREMIO_PROJECT_ID=your-project-id
```

### First command

```bash
drs query run "SELECT 1 AS hello"
```

## Commands

| Group | Commands | Description |
|-------|----------|-------------|
| `drs query` | `run`, `status`, `cancel` | Execute SQL queries |
| `drs catalog` | `list`, `get`, `search` | Browse and search the catalog |
| `drs schema` | `describe`, `lineage`, `wiki`, `sample` | Inspect table schemas and data |
| `drs reflect` | `list`, `status`, `refresh`, `drop` | Manage reflections |
| `drs jobs` | `list`, `get`, `profile` | Monitor query jobs |
| `drs access` | `grants`, `roles`, `whoami`, `audit` | Audit permissions |

### Output formats

All commands support `--output json` (default), `--output csv`, or `--output pretty`:

```bash
drs jobs list --status FAILED --output pretty
drs schema describe myspace.mytable --output csv
```

## Claude Code Plugin

Install as a Claude Code plugin for Dremio-aware skills:

```
/plugin marketplace add dremio/cli
/plugin install dremio@dremio-cli
```

### Skills (8)

| Skill | Description |
|-------|-------------|
| `dremio` | Core Dremio Cloud SQL reference, system tables, REST patterns |
| `dremio-setup` | Setup wizard for drs CLI + MCP server |
| `dremio-dbt` | dbt-dremio integration guide (Cloud) |
| `investigate-slow-query` | Diagnose slow queries via job profiles and reflections |
| `audit-dataset-access` | Trace grants and role inheritance |
| `document-dataset` | Generate dataset documentation cards |
| `investigate-data-quality` | Data quality checks: nulls, duplicates, anomalies |
| `onboard-new-source` | Catalog, describe, reflect, verify access |

## Relationship to existing repos

| Repo | Relationship |
|------|-------------|
| `dremio/dremio-mcp` | **Sibling.** MCP server for AI agent integration. `drs` focuses on CLI; config format is shared. |
| `dremio/claude-plugins` | **Absorbed.** Skills rewritten to use `drs` commands instead of raw curl. |
| `developer-advocacy-dremio/dremio-agent-skill` | **Referenced.** Wizard patterns informed skill design. |

## License

Apache 2.0
