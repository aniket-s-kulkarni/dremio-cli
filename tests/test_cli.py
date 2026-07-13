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
"""Tests for CLI --version and --help flags."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

from typer.testing import CliRunner

from drs import __version__
from drs.cli import app

runner = CliRunner()


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert f"dremio-cli {__version__}" in result.output


def test_help_includes_version() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert f"(version {__version__})" in result.output


def test_help_short_flag() -> None:
    result = runner.invoke(app, ["-h"])
    assert result.exit_code == 0
    assert f"(version {__version__})" in result.output


def test_chat_gantt_command(tmp_path) -> None:
    dump_path = tmp_path / "history.json"
    dump_path.write_text(
        json.dumps(
            {
                "data": [
                    {
                        "chunkType": "toolRequest",
                        "callId": "c1",
                        "name": "searchViewsAndTables",
                        "createdAt": "2026-07-13T12:39:29.860Z",
                        "arguments": {"arg0": "supplier contract risk exposure"},
                    },
                    {
                        "chunkType": "toolResponse",
                        "callId": "c1",
                        "name": "searchViewsAndTables",
                        "createdAt": "2026-07-13T12:39:32.719Z",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["chat", "gantt", str(dump_path), "--ascii", "--width", "20"])

    assert result.exit_code == 0
    assert "Timeline start: 2026-07-13T12:39:29.860000+00:00" in result.output
    assert "S1 searchViewsAndTables" in result.output


def test_chat_history_gantt_command(monkeypatch) -> None:
    from drs.commands import chat

    client = type("DummyClient", (), {"close": AsyncMock()})()
    monkeypatch.setattr(chat, "_get_client", lambda: client)

    async def fake_get_messages(client, conversation_id, limit=50):
        return {
            "data": [
                {
                    "chunkType": "toolRequest",
                    "callId": "c1",
                    "name": "searchViewsAndTables",
                    "createdAt": "2026-07-13T12:39:29.860Z",
                    "arguments": {"arg0": "supplier contract risk exposure"},
                },
                {
                    "chunkType": "toolResponse",
                    "callId": "c1",
                    "name": "searchViewsAndTables",
                    "createdAt": "2026-07-13T12:39:32.719Z",
                },
            ]
        }

    monkeypatch.setattr(chat, "get_messages", fake_get_messages)

    result = runner.invoke(app, ["chat", "history", "conv-1", "--gantt", "--ascii", "--think-time"])

    assert result.exit_code == 0
    assert "Timeline start: 2026-07-13T12:39:29.860000+00:00" in result.output
    assert "S1 searchViewsAndTables" in result.output
