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
"""Tests for catalog CRUD commands (create-space, create-folder, delete)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from drs.commands.catalog import create_space, create_folder, delete_entity


@pytest.mark.asyncio
async def test_create_space(mock_client) -> None:
    mock_client.create_catalog_entity = AsyncMock(return_value={
        "id": "space-1", "entityType": "space", "name": "Analytics"
    })
    result = await create_space(mock_client, "Analytics")
    mock_client.create_catalog_entity.assert_called_once_with({
        "entityType": "space", "name": "Analytics"
    })
    assert result["name"] == "Analytics"


@pytest.mark.asyncio
async def test_create_folder(mock_client) -> None:
    mock_client.create_catalog_entity = AsyncMock(return_value={
        "id": "folder-1", "entityType": "folder", "path": ["myspace", "reports"]
    })
    result = await create_folder(mock_client, "myspace.reports")
    mock_client.create_catalog_entity.assert_called_once_with({
        "entityType": "folder", "path": ["myspace", "reports"]
    })


@pytest.mark.asyncio
async def test_delete_entity(mock_client) -> None:
    mock_client.get_catalog_by_path = AsyncMock(return_value={
        "id": "entity-1", "tag": "v1", "entityType": "space"
    })
    mock_client.delete_catalog_entity = AsyncMock(return_value={"status": "ok"})

    result = await delete_entity(mock_client, "myspace")

    mock_client.get_catalog_by_path.assert_called_once_with(["myspace"])
    mock_client.delete_catalog_entity.assert_called_once_with("entity-1", tag="v1")


@pytest.mark.asyncio
async def test_delete_entity_without_tag(mock_client) -> None:
    mock_client.get_catalog_by_path = AsyncMock(return_value={
        "id": "entity-2", "entityType": "folder"
    })
    mock_client.delete_catalog_entity = AsyncMock(return_value={"status": "ok"})

    await delete_entity(mock_client, "myspace.folder")

    mock_client.delete_catalog_entity.assert_called_once_with("entity-2", tag=None)
