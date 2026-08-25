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
"""Tests for retry logic in DremioClient."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from drs.client import DremioClient


@pytest.mark.asyncio
async def test_retry_on_timeout(config) -> None:
    """Should retry on timeout and succeed on second attempt."""
    client = DremioClient(config)
    ok_response = httpx.Response(200, json={"ok": True}, request=httpx.Request("GET", "https://example.com"))

    client._client.request = AsyncMock(
        side_effect=[
            httpx.TimeoutException("timed out"),
            ok_response,
        ]
    )

    with patch("drs.client.asyncio.sleep", new_callable=AsyncMock):
        result = await client._get("https://example.com/test")

    assert result == {"ok": True}
    assert client._client.request.call_count == 2


@pytest.mark.asyncio
async def test_retry_on_429(config) -> None:
    """Should retry on 429 Too Many Requests."""
    client = DremioClient(config)
    rate_limited = httpx.Response(429, request=httpx.Request("GET", "https://example.com"))
    ok_response = httpx.Response(200, json={"ok": True}, request=httpx.Request("GET", "https://example.com"))

    client._client.request = AsyncMock(side_effect=[rate_limited, ok_response])

    with patch("drs.client.asyncio.sleep", new_callable=AsyncMock):
        result = await client._get("https://example.com/test")

    assert result == {"ok": True}
    assert client._client.request.call_count == 2


@pytest.mark.asyncio
async def test_retry_on_503(config) -> None:
    """Should retry on 503 Service Unavailable."""
    client = DremioClient(config)
    unavailable = httpx.Response(503, request=httpx.Request("POST", "https://example.com"))
    ok_response = httpx.Response(200, json={"data": 1}, request=httpx.Request("POST", "https://example.com"))

    client._client.request = AsyncMock(side_effect=[unavailable, ok_response])

    with patch("drs.client.asyncio.sleep", new_callable=AsyncMock):
        result = await client._post("https://example.com/test", json={"sql": "SELECT 1"})

    assert result == {"data": 1}
    assert client._client.request.call_count == 2


@pytest.mark.asyncio
async def test_no_retry_on_400(config) -> None:
    """Should NOT retry on 400 Bad Request."""
    client = DremioClient(config)
    bad_request = httpx.Response(400, json={"error": "bad"}, request=httpx.Request("GET", "https://example.com"))

    client._client.request = AsyncMock(return_value=bad_request)

    with pytest.raises(httpx.HTTPStatusError):
        await client._get("https://example.com/test")

    assert client._client.request.call_count == 1


@pytest.mark.asyncio
async def test_no_retry_on_404(config) -> None:
    """Should NOT retry on 404 Not Found."""
    client = DremioClient(config)
    not_found = httpx.Response(404, json={"error": "not found"}, request=httpx.Request("GET", "https://example.com"))

    client._client.request = AsyncMock(return_value=not_found)

    with pytest.raises(httpx.HTTPStatusError):
        await client._get("https://example.com/test")

    assert client._client.request.call_count == 1


@pytest.mark.asyncio
async def test_exhausted_retries_raises_timeout(config) -> None:
    """Should raise TimeoutException after all retries exhausted."""
    client = DremioClient(config)

    client._client.request = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

    with patch("drs.client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep, pytest.raises(httpx.TimeoutException):
        await client._get("https://example.com/test")

    assert client._client.request.call_count == 3
    assert mock_sleep.call_count == 2


@pytest.mark.asyncio
async def test_exhausted_retries_returns_last_status(config) -> None:
    """Should raise HTTPStatusError if all retries return retryable status."""
    client = DremioClient(config)
    unavailable = httpx.Response(503, request=httpx.Request("GET", "https://example.com"))

    client._client.request = AsyncMock(return_value=unavailable)

    with patch("drs.client.asyncio.sleep", new_callable=AsyncMock), pytest.raises(httpx.HTTPStatusError):
        await client._get("https://example.com/test")

    assert client._client.request.call_count == 3


@pytest.mark.asyncio
async def test_retry_backoff_delays(config) -> None:
    """Should use exponential backoff delays (1s, 2s)."""
    client = DremioClient(config)
    ok_response = httpx.Response(200, json={"ok": True}, request=httpx.Request("GET", "https://example.com"))

    client._client.request = AsyncMock(
        side_effect=[
            httpx.TimeoutException("timed out"),
            httpx.TimeoutException("timed out"),
            ok_response,
        ]
    )

    with patch("drs.client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await client._get("https://example.com/test")

    assert result == {"ok": True}
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(1.0)
    mock_sleep.assert_any_call(2.0)


@pytest.mark.asyncio
async def test_401_triggers_token_refresh(config) -> None:
    """401 should trigger OAuth refresh and retry with the new token."""
    from drs.auth import OAuthConfig

    config.oauth = OAuthConfig(
        access_token="expired-token",
        refresh_token="my-refresh-token",
        client_id="my-client-id",
    )
    client = DremioClient(config)

    unauthorized = httpx.Response(401, request=httpx.Request("GET", "https://example.com/test"))
    ok_response = httpx.Response(200, json={"ok": True}, request=httpx.Request("GET", "https://example.com/test"))

    # First call returns 401, after refresh the second call succeeds
    client._client.request = AsyncMock(side_effect=[unauthorized, ok_response])

    from drs.oauth import OAuthTokens

    mock_tokens = OAuthTokens(access_token="new-access-token", refresh_token="new-refresh-token")

    with (
        patch("drs.oauth.discover_oauth_metadata") as mock_discover,
        patch("drs.oauth.do_token_refresh", return_value=mock_tokens) as mock_refresh,
        patch("drs.client.save_oauth_tokens") as mock_save,
    ):
        mock_discover.return_value = type("Meta", (), {"token_endpoint": "https://login.dremio.cloud/oauth/token"})()
        result = await client._get("https://example.com/test")

    assert result == {"ok": True}
    assert client._client.request.call_count == 2
    mock_refresh.assert_called_once_with("https://login.dremio.cloud/oauth/token", "my-client-id", "my-refresh-token")
    mock_save.assert_called_once_with(
        access_token="new-access-token",
        refresh_token="new-refresh-token",
        client_id="my-client-id",
    )
    # Verify the client header was updated
    assert client._client.headers["Authorization"] == "Bearer new-access-token"


@pytest.mark.asyncio
async def test_401_no_refresh_without_oauth_config(config) -> None:
    """401 without OAuth config should NOT attempt refresh — just raise."""
    client = DremioClient(config)

    unauthorized = httpx.Response(
        401, json={"error": "unauthorized"}, request=httpx.Request("GET", "https://example.com/test")
    )
    client._client.request = AsyncMock(return_value=unauthorized)

    with pytest.raises(httpx.HTTPStatusError):
        await client._get("https://example.com/test")

    # Only one request, no retry
    assert client._client.request.call_count == 1


@pytest.mark.asyncio
async def test_401_refresh_only_once(config) -> None:
    """Should only attempt refresh once per client instance — no infinite loops."""
    from drs.auth import OAuthConfig

    config.oauth = OAuthConfig(
        access_token="expired-token",
        refresh_token="my-refresh-token",
        client_id="my-client-id",
    )
    client = DremioClient(config)
    # Simulate: first refresh succeeds but token is still invalid (401 again)
    client._refreshed = True  # already refreshed once

    unauthorized = httpx.Response(
        401, json={"error": "unauthorized"}, request=httpx.Request("GET", "https://example.com/test")
    )
    client._client.request = AsyncMock(return_value=unauthorized)

    with pytest.raises(httpx.HTTPStatusError):
        await client._get("https://example.com/test")

    assert client._client.request.call_count == 1


@pytest.mark.asyncio
async def test_401_refresh_fails_raises_original(config) -> None:
    """If token refresh fails, the original 401 should propagate."""
    from drs.auth import OAuthConfig

    config.oauth = OAuthConfig(
        access_token="expired-token",
        refresh_token="my-refresh-token",
        client_id="my-client-id",
    )
    client = DremioClient(config)

    unauthorized = httpx.Response(
        401, json={"error": "unauthorized"}, request=httpx.Request("GET", "https://example.com/test")
    )
    client._client.request = AsyncMock(return_value=unauthorized)

    with (
        patch("drs.oauth.discover_oauth_metadata") as mock_discover,
        patch("drs.oauth.do_token_refresh", return_value=None),
        pytest.raises(httpx.HTTPStatusError),
    ):
        mock_discover.return_value = type("Meta", (), {"token_endpoint": "https://login.dremio.cloud/oauth/token"})()
        await client._get("https://example.com/test")

    # Only one request attempt — refresh failed so no retry
    assert client._client.request.call_count == 1
