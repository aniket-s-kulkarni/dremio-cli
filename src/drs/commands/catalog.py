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
"""drs catalog — browse and search the Dremio catalog."""

from __future__ import annotations

import asyncio

import httpx
import typer

from drs.client import DremioClient
from drs.output import OutputFormat, output, error
from drs.utils import handle_api_error, parse_path

app = typer.Typer(help="Browse and search the Dremio catalog.")


async def list_catalog(client: DremioClient) -> dict:
    """List top-level catalog entities (sources, spaces, home)."""
    try:
        root = await client.get_catalog_entity("")
    except httpx.HTTPStatusError as exc:
        raise handle_api_error(exc) from exc
    children = root.get("data", root.get("children", []))
    return {"entities": children}


async def get_entity(client: DremioClient, path: str) -> dict:
    """Get a catalog entity by dot-separated path."""
    parts = parse_path(path)
    try:
        return await client.get_catalog_by_path(parts)
    except httpx.HTTPStatusError as exc:
        raise handle_api_error(exc) from exc


async def create_space(client: DremioClient, name: str) -> dict:
    """Create a new space."""
    try:
        return await client.create_catalog_entity({"entityType": "space", "name": name})
    except httpx.HTTPStatusError as exc:
        raise handle_api_error(exc) from exc


async def create_folder(client: DremioClient, path: str) -> dict:
    """Create a folder at the given dot-separated path (e.g., myspace.newfolder)."""
    parts = parse_path(path)
    try:
        return await client.create_catalog_entity({"entityType": "folder", "path": parts})
    except httpx.HTTPStatusError as exc:
        raise handle_api_error(exc) from exc


async def delete_entity(client: DremioClient, path: str) -> dict:
    """Delete a catalog entity by path."""
    parts = parse_path(path)
    try:
        entity = await client.get_catalog_by_path(parts)
    except httpx.HTTPStatusError as exc:
        raise handle_api_error(exc) from exc
    entity_id = entity["id"]
    tag = entity.get("tag")
    try:
        return await client.delete_catalog_entity(entity_id, tag=tag)
    except httpx.HTTPStatusError as exc:
        raise handle_api_error(exc) from exc


async def search_catalog(client: DremioClient, term: str) -> dict:
    """Full-text search for catalog entities."""
    try:
        return await client.search(term)
    except httpx.HTTPStatusError as exc:
        raise handle_api_error(exc) from exc


# -- CLI wrappers --

def _get_client() -> DremioClient:
    from drs.cli import get_client
    return get_client()


def _run_command(coro, client, fmt: OutputFormat = OutputFormat.json, fields: str | None = None) -> None:
    async def _execute():
        try:
            return await coro
        finally:
            await client.close()

    try:
        result = asyncio.run(_execute())
    except Exception as exc:
        from drs.utils import DremioAPIError
        if isinstance(exc, DremioAPIError):
            error(str(exc))
            raise typer.Exit(1)
        if isinstance(exc, ValueError):
            error(str(exc))
            raise typer.Exit(1)
        raise
    output(result, fmt, fields=fields)


@app.command("list")
def cli_list(
    fmt: OutputFormat = typer.Option(OutputFormat.json, "--output", "-o", help="Output format"),
    fields: str = typer.Option(None, "--fields", "-f", help="Comma-separated fields to include in output"),
) -> None:
    """List top-level catalog entities: sources, spaces, and home folder."""
    client = _get_client()
    _run_command(list_catalog(client), client, fmt, fields=fields)


@app.command("get")
def cli_get(
    path: str = typer.Argument(help='Dot-separated entity path (e.g., myspace.folder.table). Quote components with dots: \'"My Source".table\''),
    fmt: OutputFormat = typer.Option(OutputFormat.json, "--output", "-o", help="Output format"),
    fields: str = typer.Option(None, "--fields", "-f", help="Comma-separated fields to include in output"),
) -> None:
    """Get full metadata for a catalog entity by path.

    Returns entity type, ID, children (for containers), fields (for datasets),
    and access control information.
    """
    client = _get_client()
    _run_command(get_entity(client, path), client, fmt, fields=fields)


@app.command("create-space")
def cli_create_space(
    name: str = typer.Argument(help="Name for the new space"),
    fmt: OutputFormat = typer.Option(OutputFormat.json, "--output", "-o", help="Output format"),
) -> None:
    """Create a new space in the catalog."""
    client = _get_client()
    _run_command(create_space(client, name), client, fmt)


@app.command("create-folder")
def cli_create_folder(
    path: str = typer.Argument(help="Dot-separated path for new folder (e.g., myspace.newfolder)"),
    fmt: OutputFormat = typer.Option(OutputFormat.json, "--output", "-o", help="Output format"),
) -> None:
    """Create a folder inside a space or another folder."""
    client = _get_client()
    _run_command(create_folder(client, path), client, fmt)


@app.command("delete")
def cli_delete(
    path: str = typer.Argument(help="Dot-separated entity path to delete"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be deleted without deleting"),
    fmt: OutputFormat = typer.Option(OutputFormat.json, "--output", "-o", help="Output format"),
) -> None:
    """Delete a catalog entity (space, folder, view, etc.). Cannot be undone.

    Use --dry-run to see the entity metadata before deleting.
    """
    client = _get_client()
    if dry_run:
        _run_command(get_entity(client, path), client, fmt)
        return
    _run_command(delete_entity(client, path), client, fmt)


@app.command("search")
def cli_search(
    term: str = typer.Argument(help="Search term (matches table names, view names, source names)"),
    fmt: OutputFormat = typer.Option(OutputFormat.json, "--output", "-o", help="Output format"),
) -> None:
    """Full-text search across all catalog entities (tables, views, sources)."""
    client = _get_client()
    _run_command(search_catalog(client, term), client, fmt)
