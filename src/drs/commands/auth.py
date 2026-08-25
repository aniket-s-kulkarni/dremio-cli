#
# Copyright (C) 2017-2026 Dremio Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""drs auth — OAuth login, status, and token refresh for Dremio Cloud."""

from __future__ import annotations

import sys
from datetime import UTC
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from drs.auth import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_URI,
    clear_oauth_tokens,
    save_oauth_tokens,
)
from drs.oauth import (
    DEFAULT_CLIENT_ID,
    DEFAULT_REDIRECT_PORT,
    discover_oauth_metadata,
    do_token_refresh,
    run_oauth_flow,
)

app = typer.Typer(
    help="Authenticate with Dremio Cloud via OAuth.",
    context_settings={"help_option_names": ["-h", "--help"]},
)

console = Console()
err_console = Console(stderr=True)


@app.command("login")
def login_command(
    ctx: typer.Context,
    client_id: str = typer.Option(DEFAULT_CLIENT_ID, "--client-id", help="OAuth client ID."),
    port: int = typer.Option(DEFAULT_REDIRECT_PORT, "--port", help="Local port for OAuth redirect listener."),
    uri: str | None = typer.Option(
        None,
        "--uri",
        help="Dremio API base URI (overrides config). E.g. https://api.eu.dremio.cloud",
    ),
) -> None:
    """Log in to Dremio Cloud via browser-based OAuth (PKCE flow).

    Opens your browser to authenticate, then stores the access token and
    refresh token in ~/.config/dremioai/config.yaml. Subsequent CLI commands
    will use this token automatically and refresh it when expired.
    """
    if not sys.stdin.isatty():
        err_console.print("[bold red]dremio auth login[/bold red] requires an interactive terminal.")
        raise typer.Exit(1)

    # Determine config path and API URI
    config_path = _get_config_path(ctx)
    api_uri = _resolve_uri(uri, config_path)

    console.print()
    console.print(
        Panel(
            f"[bold]OAuth Login[/bold]\n\n"
            f"  API:       {api_uri}\n"
            f"  Client ID: {client_id}\n"
            f"  Port:      {port}\n\n"
            "A browser window will open for you to sign in to Dremio Cloud.",
            title="[bold cyan]dremio auth login[/bold cyan]",
            border_style="cyan",
        )
    )

    console.print("\n[dim]Opening browser...[/dim]")

    try:
        tokens = run_oauth_flow(
            api_uri=api_uri,
            client_id=client_id,
            redirect_port=port,
        )
    except SystemExit as exc:
        err_console.print(f"\n[red]✗ {exc}[/red]")
        raise typer.Exit(1)

    # Save tokens to config
    save_oauth_tokens(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        client_id=client_id,
        config_path=config_path,
    )

    console.print("\n[green]✓ Logged in successfully![/green]")
    console.print(f"  Tokens saved to [cyan]{config_path}[/cyan]")
    if tokens.refresh_token:
        console.print("  [dim]Refresh token stored — CLI will auto-refresh on expiry.[/dim]")
    else:
        console.print("  [yellow]No refresh token received — you'll need to re-login when the token expires.[/yellow]")


@app.command("status")
def status_command(
    ctx: typer.Context,
) -> None:
    """Show current authentication status — token type, expiry, and stored credentials."""
    import yaml

    config_path = _get_config_path(ctx)

    if not config_path.exists():
        console.print("[yellow]No config file found.[/yellow]")
        console.print(f"  Expected at: {config_path}")
        console.print("  Run [bold cyan]dremio auth login[/bold cyan] or [bold cyan]dremio setup[/bold cyan] first.")
        raise typer.Exit(1)

    with config_path.open() as f:
        raw = yaml.safe_load(f) or {}

    tbl = Table(title="Authentication Status", show_header=True, header_style="bold")
    tbl.add_column("Field", style="cyan", no_wrap=True)
    tbl.add_column("Value")

    # Config path
    tbl.add_row("Config file", str(config_path))

    # URI
    api_uri = raw.get("uri", raw.get("endpoint", DEFAULT_URI))
    tbl.add_row("API URI", api_uri)

    # Project ID
    project_id = raw.get("project_id", raw.get("projectId", ""))
    tbl.add_row("Project ID", project_id or "[dim]not set[/dim]")

    # Auth method
    has_oauth = "oauth" in raw and isinstance(raw.get("oauth"), dict)
    has_pat = bool(raw.get("pat") or raw.get("token"))

    if has_oauth:
        oauth = raw["oauth"]
        access_token = oauth.get("access_token", "")
        refresh_token = oauth.get("refresh_token", "")
        client_id = oauth.get("client_id", "")

        tbl.add_row("Auth method", "[bold green]OAuth[/bold green]")
        tbl.add_row("Client ID", client_id or "[dim]not set[/dim]")
        tbl.add_row("Access token", _redact(access_token))
        tbl.add_row("Refresh token", _redact(refresh_token) if refresh_token else "[dim]none[/dim]")

        # Try to decode JWT expiry
        expiry_info = _decode_token_expiry(access_token)
        if expiry_info:
            tbl.add_row("Token expiry", expiry_info)
    elif has_pat:
        pat = raw.get("pat") or raw.get("token", "")
        tbl.add_row("Auth method", "[bold]PAT (Personal Access Token)[/bold]")
        tbl.add_row("Token", _redact(pat))
    else:
        tbl.add_row("Auth method", "[red]Not configured[/red]")

    console.print()
    console.print(tbl)
    console.print()


@app.command("refresh")
def refresh_command(
    ctx: typer.Context,
    uri: str | None = typer.Option(None, "--uri", help="Dremio API base URI (overrides config)."),
) -> None:
    """Refresh the OAuth access token using the stored refresh token.

    On success, updates the stored access token in the config file.
    """
    import yaml

    config_path = _get_config_path(ctx)

    if not config_path.exists():
        err_console.print("[red]No config file found.[/red]")
        err_console.print("  Run [bold cyan]dremio auth login[/bold cyan] first.")
        raise typer.Exit(1)

    with config_path.open() as f:
        raw = yaml.safe_load(f) or {}

    oauth = raw.get("oauth", {})
    if not isinstance(oauth, dict):
        oauth = {}

    refresh_token = oauth.get("refresh_token")
    client_id = oauth.get("client_id")

    if not refresh_token:
        err_console.print("[red]No refresh token found in config.[/red]")
        err_console.print("  Run [bold cyan]dremio auth login[/bold cyan] to re-authenticate.")
        raise typer.Exit(1)

    if not client_id:
        err_console.print("[red]No client_id found in config.[/red]")
        err_console.print("  Run [bold cyan]dremio auth login[/bold cyan] to re-authenticate.")
        raise typer.Exit(1)

    api_uri = _resolve_uri(uri, config_path)

    console.print("[dim]Refreshing token...[/dim]")
    metadata = discover_oauth_metadata(api_uri)
    result = do_token_refresh(metadata.token_endpoint, client_id, refresh_token)

    if result is None:
        err_console.print("[red]✗ Token refresh failed.[/red]")
        err_console.print("  The refresh token may have expired. Run [bold cyan]dremio auth login[/bold cyan] again.")
        raise typer.Exit(1)

    # Save the new tokens
    save_oauth_tokens(
        access_token=result.access_token,
        refresh_token=result.refresh_token or refresh_token,
        client_id=client_id,
        config_path=config_path,
    )

    console.print("[green]✓ Token refreshed successfully![/green]")
    console.print(f"  Updated tokens in [cyan]{config_path}[/cyan]")


@app.command("logout")
def logout_command(
    ctx: typer.Context,
) -> None:
    """Remove stored OAuth tokens from the config file."""
    config_path = _get_config_path(ctx)
    clear_oauth_tokens(config_path)
    console.print("[green]✓ OAuth tokens removed.[/green]")


# -- Helpers --


def _get_config_path(ctx: typer.Context) -> Path:
    """Extract the config path from the typer context."""
    if ctx.obj and ctx.obj.get("config_path"):
        return ctx.obj["config_path"]
    return DEFAULT_CONFIG_PATH


def _resolve_uri(explicit_uri: str | None, config_path: Path) -> str:
    """Determine the API URI from explicit flag, config, or default."""
    if explicit_uri:
        return explicit_uri

    if config_path.exists():
        import yaml

        with config_path.open() as f:
            raw = yaml.safe_load(f) or {}
        return raw.get("uri", raw.get("endpoint", DEFAULT_URI))

    return DEFAULT_URI


def _redact(value: str | None, keep: int = 12) -> str:
    """Redact a token for display."""
    if not value:
        return "[dim]empty[/dim]"
    if len(value) <= keep:
        return value
    return f"{value[:keep]}..."


def _decode_token_expiry(token: str | None) -> str | None:
    """Try to decode JWT expiry without verifying signature."""
    if not token:
        return None
    try:
        import base64
        import json
        from datetime import datetime

        # Decode JWT payload (second segment)
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload = parts[1]
        # Fix padding
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding
        decoded = json.loads(base64.urlsafe_b64decode(payload))
        exp = decoded.get("exp")
        if exp:
            exp_dt = datetime.fromtimestamp(exp, tz=UTC)
            now = datetime.now(tz=UTC)
            if exp_dt < now:
                return f"[red]{exp_dt.isoformat()} (EXPIRED)[/red]"
            delta = exp_dt - now
            hours = int(delta.total_seconds() // 3600)
            minutes = int((delta.total_seconds() % 3600) // 60)
            return f"{exp_dt.isoformat()} (expires in {hours}h {minutes}m)"
    except Exception:
        pass
    return None
