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
"""Tests for chat renderer detail output."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from drs.chat_render import ChatRenderer, PlainRenderer, extract_model_text


def test_extract_model_text_prefers_title_and_summary() -> None:
    text = extract_model_text(
        "modelSqlAnswer",
        {"title": "Direct Reports", "summary": "Three people report to Myra."},
    )

    assert text == "Direct Reports\n\nThree people report to Myra."


def test_chat_renderer_tool_response_details_include_duration() -> None:
    stream = StringIO()
    renderer = ChatRenderer(console=Console(file=stream, force_terminal=False), show_tool_details=True)

    renderer.render_tool_response(
        call_id="call-1",
        name="runSql",
        result={"rows": [["Lesley Ellis"]]},
        created_at="2026-07-31T12:10:35.270Z",
        duration_ms=1803,
    )

    output = stream.getvalue()
    assert "Finished: 12:10:35" in output
    assert "Duration: 1.80s" in output
    assert '"rows"' in output


def test_plain_renderer_tool_request_details_include_timestamp(capsys) -> None:
    renderer = PlainRenderer(show_tool_details=True)

    renderer.render_tool_request(
        call_id="call-1",
        name="runSql",
        arguments={"sqlText": "select 1"},
        title="Run direct reports query",
        created_at="2026-07-31T12:10:33.467Z",
    )

    captured = capsys.readouterr()
    assert "Run direct reports query [12:10:33]" in captured.err
    assert "sqlText=select 1" in captured.err
