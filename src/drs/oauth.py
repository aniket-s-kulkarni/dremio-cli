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
"""OAuth 2.0 PKCE flow for Dremio Cloud — device/browser-based login."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
import threading
import webbrowser
from base64 import urlsafe_b64encode
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Dremio Cloud OAuth well-known endpoints by region
OAUTH_ENDPOINTS = {
    "https://api.dremio.cloud": {
        "authorization_endpoint": "https://login.dremio.cloud/oauth/authorize",
        "token_endpoint": "https://login.dremio.cloud/oauth/token",
    },
    "https://api.eu.dremio.cloud": {
        "authorization_endpoint": "https://login.eu.dremio.cloud/oauth/authorize",
        "token_endpoint": "https://login.eu.dremio.cloud/oauth/token",
    },
}

# Default OAuth client ID for Dremio CLI (public client)
DEFAULT_CLIENT_ID = "https://connectors.dremio.app/claude"
DEFAULT_REDIRECT_PORT = 8976
DEFAULT_SCOPES = "dremio.all offline_access"


class OAuthTokens(BaseModel):
    """Result of an OAuth token exchange."""

    access_token: str
    refresh_token: str | None = None
    expires_in: int | None = None
    token_type: str = "Bearer"


class OAuthMetadata(BaseModel):
    """OAuth authorization server metadata."""

    authorization_endpoint: str
    token_endpoint: str


def get_pkce_pair() -> tuple[str, str]:
    """Generate a PKCE code_verifier + code_challenge pair."""
    code_verifier = secrets.token_urlsafe(96)[:128]
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def discover_oauth_metadata(api_uri: str) -> OAuthMetadata:
    """Discover OAuth endpoints for a Dremio Cloud API URI.

    Tries the well-known endpoint first, falls back to hardcoded mappings.
    """
    # Try well-known discovery
    parsed = urlparse(api_uri)
    well_known_url = f"{parsed.scheme}://{parsed.hostname}/.well-known/oauth-authorization-server"
    try:
        resp = httpx.get(well_known_url, timeout=10, follow_redirects=True)
        if resp.status_code == 200:
            data = resp.json()
            return OAuthMetadata(
                authorization_endpoint=data["authorization_endpoint"],
                token_endpoint=data["token_endpoint"],
            )
    except Exception:
        logger.debug("Well-known discovery failed for %s, using fallback", api_uri)

    # Fallback to hardcoded endpoints
    normalized = api_uri.rstrip("/")
    if normalized in OAUTH_ENDPOINTS:
        return OAuthMetadata(**OAUTH_ENDPOINTS[normalized])

    # Default: derive from the API URI hostname
    # api.X.dremio.cloud -> login.X.dremio.cloud
    hostname = parsed.hostname or ""
    if hostname.startswith("api."):
        login_host = "login." + hostname[4:]
    else:
        login_host = hostname

    return OAuthMetadata(
        authorization_endpoint=f"{parsed.scheme}://{login_host}/authorize",
        token_endpoint=f"{parsed.scheme}://{login_host}/oauth/token",
    )


def do_token_refresh(
    token_endpoint: str,
    client_id: str,
    refresh_token: str,
) -> OAuthTokens | None:
    """Exchange a refresh_token for a new access_token.

    Returns None if the refresh fails.
    """
    try:
        resp = httpx.post(
            token_endpoint,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            body = resp.json()
            return OAuthTokens(
                access_token=body["access_token"],
                refresh_token=body.get("refresh_token", refresh_token),
                expires_in=body.get("expires_in"),
                token_type=body.get("token_type", "Bearer"),
            )
        logger.warning("Token refresh returned HTTP %d: %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.warning("Token refresh request failed: %s", exc)
    return None


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the OAuth redirect callback."""

    auth_code: str | None = None
    error: str | None = None
    server_instance: "_OAuthCallbackServer | None" = None

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "code" in params:
            _OAuthCallbackHandler.auth_code = params["code"][0]
            self._respond_html(
                "<h2>✓ Authentication successful!</h2>"
                "<p>You can close this tab and return to the terminal.</p>"
            )
        elif "error" in params:
            _OAuthCallbackHandler.error = params.get("error_description", params["error"])[0]
            self._respond_html(f"<h2>✗ Authentication failed</h2><p>{_OAuthCallbackHandler.error}</p>")
        else:
            self._respond_html("<h2>Unexpected response</h2>")

        # Signal the server to stop
        if self.server_instance:
            threading.Thread(target=self.server_instance.shutdown, daemon=True).start()

    def _respond_html(self, body: str) -> None:
        html = f"""<!DOCTYPE html>
<html><head><title>Dremio CLI Auth</title>
<style>body{{font-family:system-ui;padding:2em;text-align:center}}</style>
</head><body>{body}</body></html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # Suppress default HTTP server access logs
        logger.debug(format, *args)


class _OAuthCallbackServer(HTTPServer):
    """Minimal HTTP server to receive the OAuth callback."""

    def __init__(self, port: int) -> None:
        super().__init__(("127.0.0.1", port), _OAuthCallbackHandler)
        _OAuthCallbackHandler.server_instance = self
        _OAuthCallbackHandler.auth_code = None
        _OAuthCallbackHandler.error = None


def run_oauth_flow(
    api_uri: str,
    client_id: str = DEFAULT_CLIENT_ID,
    redirect_port: int = DEFAULT_REDIRECT_PORT,
    scopes: str = DEFAULT_SCOPES,
) -> OAuthTokens:
    """Run the full OAuth 2.0 PKCE authorization code flow.

    1. Start local HTTP server for redirect
    2. Open browser to authorization URL
    3. Wait for callback with auth code
    4. Exchange auth code for tokens

    Raises SystemExit on failure.
    """
    metadata = discover_oauth_metadata(api_uri)
    code_verifier, code_challenge = get_pkce_pair()
    redirect_uri = f"http://localhost:{redirect_port}/Callback"

    # Build authorization URL
    auth_params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scopes,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{metadata.authorization_endpoint}?{urlencode(auth_params)}"

    # Start local server in background thread
    server = _OAuthCallbackServer(redirect_port)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        # Open browser
        logger.debug("Opening browser to: %s", auth_url)
        webbrowser.open(auth_url)

        # Wait for callback (blocks until the GET handler calls shutdown)
        server_thread.join(timeout=300)

        if _OAuthCallbackHandler.error:
            raise SystemExit(f"OAuth error: {_OAuthCallbackHandler.error}")

        auth_code = _OAuthCallbackHandler.auth_code
        if not auth_code:
            raise SystemExit("OAuth flow timed out — no authorization code received.")

        # Exchange code for tokens
        token_data = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": auth_code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        }

        resp = httpx.post(metadata.token_endpoint, data=token_data, timeout=15)
        if resp.status_code != 200:
            raise SystemExit(f"Token exchange failed (HTTP {resp.status_code}): {resp.text[:200]}")

        body = resp.json()
        return OAuthTokens(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token"),
            expires_in=body.get("expires_in"),
            token_type=body.get("token_type", "Bearer"),
        )
    finally:
        server.shutdown()
