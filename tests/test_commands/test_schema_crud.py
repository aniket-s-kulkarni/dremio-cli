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
"""Tests for schema CRUD commands (set-wiki, set-tags)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from drs.commands.schema import set_wiki, set_tags


@pytest.mark.asyncio
async def test_set_wiki(mock_client) -> None:
    mock_client.get_catalog_by_path = AsyncMock(return_value={"id": "entity-1"})
    mock_client.get_wiki = AsyncMock(return_value={"text": "old", "version": 2})
    mock_client.set_wiki = AsyncMock(return_value={"text": "new wiki", "version": 3})

    result = await set_wiki(mock_client, "myspace.table", "new wiki")

    mock_client.set_wiki.assert_called_once_with("entity-1", "new wiki", version=2)
    assert result["wiki"] == "new wiki"


@pytest.mark.asyncio
async def test_set_wiki_no_existing(mock_client) -> None:
    mock_client.get_catalog_by_path = AsyncMock(return_value={"id": "entity-1"})
    request = httpx.Request("GET", "https://api.dremio.cloud/v0/projects/p/catalog/entity-1/collaboration/wiki")
    response = httpx.Response(404, request=request)
    mock_client.get_wiki = AsyncMock(
        side_effect=httpx.HTTPStatusError("Not Found", request=request, response=response)
    )
    mock_client.set_wiki = AsyncMock(return_value={"text": "first wiki", "version": 0})

    result = await set_wiki(mock_client, "myspace.table", "first wiki")

    mock_client.set_wiki.assert_called_once_with("entity-1", "first wiki", version=None)


@pytest.mark.asyncio
async def test_set_tags(mock_client) -> None:
    mock_client.get_catalog_by_path = AsyncMock(return_value={"id": "entity-1"})
    mock_client.get_tags = AsyncMock(return_value={"tags": ["old"], "version": 1})
    mock_client.set_tags = AsyncMock(return_value={"tags": ["pii", "finance"], "version": 2})

    result = await set_tags(mock_client, "myspace.table", ["pii", "finance"])

    mock_client.set_tags.assert_called_once_with("entity-1", ["pii", "finance"], version=1)
    assert result["tags"] == ["pii", "finance"]
