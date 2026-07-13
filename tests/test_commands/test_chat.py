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
"""Tests for drs.commands.chat — core async functions."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from rich.console import Console

from drs.chat_gantt import (
    ToolSpan,
    build_history_bounds,
    build_tool_spans,
    extract_history_rows,
    load_history_dump,
    render_tool_gantt,
)
from drs.chat_gantt_tui import ToolTimeline, _build_span_sections
from drs.commands.chat import (
    cancel_run,
    create_conversation,
    delete_conversation,
    get_messages,
    list_conversations,
    send_message,
)


@pytest.mark.asyncio
async def test_create_conversation(mock_client) -> None:
    mock_client.create_conversation = AsyncMock(
        return_value={"id": "conv-1", "runId": "run-1"},
    )
    result = await create_conversation(mock_client, "hello")
    mock_client.create_conversation.assert_called_once_with(
        {"prompt": {"text": "hello"}},
    )
    assert result["id"] == "conv-1"
    assert result["runId"] == "run-1"


@pytest.mark.asyncio
async def test_create_conversation_with_model(mock_client) -> None:
    mock_client.create_conversation = AsyncMock(return_value={"id": "conv-1"})
    await create_conversation(mock_client, "hello", model="gpt-test")
    call_args = mock_client.create_conversation.call_args[0][0]
    assert call_args["model"] == "gpt-test"


@pytest.mark.asyncio
async def test_send_message_text(mock_client) -> None:
    mock_client.send_conversation_message = AsyncMock(
        return_value={"runId": "run-2"},
    )
    result = await send_message(mock_client, "conv-1", text="follow-up")
    mock_client.send_conversation_message.assert_called_once()
    body = mock_client.send_conversation_message.call_args[0][1]
    assert body["prompt"]["text"] == "follow-up"
    assert result["runId"] == "run-2"


@pytest.mark.asyncio
async def test_send_message_approval(mock_client) -> None:
    mock_client.send_conversation_message = AsyncMock(
        return_value={"runId": "run-3"},
    )
    approvals = {
        "approvalNonce": "nonce-1",
        "toolDecisions": [{"callId": "c1", "decision": "approved"}],
    }
    result = await send_message(mock_client, "conv-1", approvals=approvals)
    body = mock_client.send_conversation_message.call_args[0][1]
    assert body["prompt"]["approvals"] == approvals
    assert result["runId"] == "run-3"


@pytest.mark.asyncio
async def test_list_conversations(mock_client) -> None:
    mock_client.list_conversations = AsyncMock(
        return_value={"data": [{"id": "c1", "title": "test"}]},
    )
    result = await list_conversations(mock_client, limit=10)
    mock_client.list_conversations.assert_called_once_with(limit=10)
    assert len(result["data"]) == 1


@pytest.mark.asyncio
async def test_get_messages(mock_client) -> None:
    mock_client.get_conversation_messages = AsyncMock(
        return_value={"data": [{"role": "user", "content": "hi"}]},
    )
    result = await get_messages(mock_client, "conv-1", limit=25)
    mock_client.get_conversation_messages.assert_called_once_with("conv-1", limit=25)
    assert len(result["data"]) == 1


@pytest.mark.asyncio
async def test_delete_conversation(mock_client) -> None:
    mock_client.delete_conversation = AsyncMock(return_value={"status": "ok"})
    result = await delete_conversation(mock_client, "conv-1")
    mock_client.delete_conversation.assert_called_once_with("conv-1")
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_cancel_run(mock_client) -> None:
    mock_client.cancel_conversation_run = AsyncMock(return_value={"status": "ok"})
    result = await cancel_run(mock_client, "conv-1", "run-1")
    mock_client.cancel_conversation_run.assert_called_once_with("conv-1", "run-1")
    assert result["status"] == "ok"


def test_build_tool_spans_assigns_parallel_lanes() -> None:
    rows = [
        {
            "chunkType": "model",
            "createdAt": "2026-07-13T12:39:29.847Z",
            "result": {
                "title": "Supplier Contract Risk Exposure",
            },
        },
        {
            "chunkType": "toolRequest",
            "callId": "c1",
            "name": "searchViewsAndTables",
            "createdAt": "2026-07-13T12:39:29.860Z",
            "arguments": {"arg0": "supplier contract risk exposure"},
            "summarizedTitle": "Search supplier contract risk exposure",
        },
        {
            "chunkType": "toolRequest",
            "callId": "c2",
            "name": "searchViewsAndTables",
            "createdAt": "2026-07-13T12:39:29.900Z",
            "arguments": {"arg0": "purchase order supplier spend"},
            "summarizedTitle": "Search purchase order supplier spend",
        },
        {
            "chunkType": "toolResponse",
            "callId": "c1",
            "name": "searchViewsAndTables",
            "createdAt": "2026-07-13T12:39:32.719Z",
        },
        {
            "chunkType": "toolResponse",
            "callId": "c2",
            "name": "searchViewsAndTables",
            "createdAt": "2026-07-13T12:39:32.729Z",
        },
    ]

    spans, first_start, last_end = build_tool_spans(rows)

    assert first_start is not None
    assert last_end is not None
    assert len(spans) == 2
    assert {span.lane for span in spans} == {0, 1}
    assert {span.step for span in spans} == {1}
    assert spans[0].duration_ms == 2859
    assert spans[1].offset_ms == 40
    assert spans[0].arguments == {"arg0": "supplier contract risk exposure"}
    assert spans[0].title == "Supplier Contract Risk Exposure"
    assert spans[0].summarized_title == "Search supplier contract risk exposure"


def test_load_history_dump_accepts_unescaped_control_chars(tmp_path) -> None:
    dump_path = tmp_path / "history.json"
    dump_path.write_text('{"data":[{"chunkType":"model","result":{"text":"line 1\nline 2"}}]}', encoding="utf-8")

    loaded = load_history_dump(dump_path)

    assert loaded["data"][0]["result"]["text"] == "line 1\nline 2"


def test_extract_history_rows_accepts_messages_envelope() -> None:
    rows = [{"chunkType": "toolRequest", "callId": "c1", "createdAt": "2026-07-13T12:39:29.860Z"}]

    extracted = extract_history_rows({"messages": rows})

    assert extracted == rows


def test_build_history_bounds_uses_all_events() -> None:
    rows = [
        {"chunkType": "userMessage", "createdAt": "2026-07-13T12:39:17.794Z"},
        {"chunkType": "toolRequest", "callId": "c1", "createdAt": "2026-07-13T12:39:29.860Z"},
        {"chunkType": "toolResponse", "callId": "c1", "createdAt": "2026-07-13T12:39:32.719Z"},
        {"chunkType": "model", "createdAt": "2026-07-13T12:39:35.000Z"},
    ]

    bounds = build_history_bounds(rows)

    assert bounds is not None
    assert bounds.total_ms == 17206


def test_build_tool_spans_can_insert_think_time() -> None:
    rows = [
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
        {
            "chunkType": "toolRequest",
            "callId": "c2",
            "name": "runSql",
            "createdAt": "2026-07-13T12:39:32.900Z",
            "arguments": {"arg0": "select 1"},
        },
        {
            "chunkType": "toolResponse",
            "callId": "c2",
            "name": "runSql",
            "createdAt": "2026-07-13T12:39:33.200Z",
        },
    ]

    spans, _, _ = build_tool_spans(rows, include_think_time=True)

    think_spans = [span for span in spans if span.name == "thinkTime"]
    assert len(think_spans) == 1
    assert think_spans[0].duration_ms == 181
    assert think_spans[0].step == 2


def test_build_tool_spans_marks_failed_tool_calls() -> None:
    rows = [
        {
            "chunkType": "toolRequest",
            "callId": "c1",
            "name": "runSql",
            "createdAt": "2026-07-13T12:39:29.860Z",
            "arguments": {"sql": "select * from missing_table"},
        },
        {
            "chunkType": "toolResponse",
            "callId": "c1",
            "name": "runSql",
            "createdAt": "2026-07-13T12:39:32.719Z",
            "status": "failed",
            "result": {"errorMessage": "Table missing_table not found"},
        },
    ]

    spans, _, _ = build_tool_spans(rows)

    assert len(spans) == 1
    assert spans[0].failed is True
    assert spans[0].error_message == "Table missing_table not found"


def test_build_tool_spans_extracts_nested_error_message() -> None:
    rows = [
        {
            "chunkType": "toolRequest",
            "callId": "c1",
            "name": "runSql",
            "createdAt": "2026-07-13T12:39:29.860Z",
            "arguments": {"sql": "select * from missing_table"},
        },
        {
            "chunkType": "toolResponse",
            "callId": "c1",
            "name": "runSql",
            "createdAt": "2026-07-13T12:39:32.719Z",
            "status": "failed",
            "result": {"payload": {"details": {"message": "Nested query failure"}}},
        },
    ]

    spans, _, _ = build_tool_spans(rows)

    assert len(spans) == 1
    assert spans[0].failed is True
    assert spans[0].error_message == "Nested query failure"


def test_render_tool_gantt_outputs_chart() -> None:
    data = {
        "data": [
            {
                "chunkType": "userMessage",
                "createdAt": "2026-07-13T12:39:17.794Z",
            },
            {
                "chunkType": "toolRequest",
                "callId": "c1",
                "name": "searchViewsAndTables",
                "createdAt": "2026-07-13T12:39:29.860Z",
                "arguments": {"arg0": "supplier contract risk exposure"},
            },
            {
                "chunkType": "toolRequest",
                "callId": "c2",
                "name": "searchViewsAndTables",
                "createdAt": "2026-07-13T12:39:29.900Z",
                "arguments": {"arg0": "purchase order supplier spend"},
            },
            {
                "chunkType": "toolResponse",
                "callId": "c1",
                "name": "searchViewsAndTables",
                "createdAt": "2026-07-13T12:39:32.719Z",
            },
            {
                "chunkType": "toolResponse",
                "callId": "c2",
                "name": "searchViewsAndTables",
                "createdAt": "2026-07-13T12:39:32.729Z",
            },
            {
                "chunkType": "model",
                "createdAt": "2026-07-13T12:39:35.000Z",
            },
        ]
    }

    rendered = render_tool_gantt(data, width=30)

    assert "Total time taken: 17.206s" in rendered
    assert "Total tool span: 2.869s across 1 step(s), using 2 visual lane(s)" in rendered
    assert "S1 searchViewsAndTables" in rendered


def test_render_tool_gantt_accepts_messages_envelope() -> None:
    data = {
        "messages": [
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

    rendered = render_tool_gantt(data, width=20)

    assert "S1 searchViewsAndTables" in rendered


def test_build_span_sections_includes_error_details() -> None:
    span = ToolSpan(
        lane=0,
        step=1,
        name="runSql",
        call_id="c1",
        start=build_tool_spans(
            [
                {"chunkType": "toolRequest", "callId": "c1", "name": "runSql", "createdAt": "2026-07-13T12:39:29.860Z"},
                {
                    "chunkType": "toolResponse",
                    "callId": "c1",
                    "name": "runSql",
                    "createdAt": "2026-07-13T12:39:32.719Z",
                },
            ]
        )[1],
        end=build_tool_spans(
            [
                {"chunkType": "toolRequest", "callId": "c1", "name": "runSql", "createdAt": "2026-07-13T12:39:29.860Z"},
                {
                    "chunkType": "toolResponse",
                    "callId": "c1",
                    "name": "runSql",
                    "createdAt": "2026-07-13T12:39:32.719Z",
                },
            ]
        )[2],
        duration_ms=2859,
        offset_ms=0,
        label="runSql",
        arguments={"sql": "select * from missing_table"},
        title="Broken query",
        summarized_title="Run broken query",
        failed=True,
        error_message="Table missing_table not found",
    )
    timeline = ToolTimeline(
        spans=[span],
        start=span.start,
        end=span.end,
        history_bounds=build_history_bounds(
            [
                {"chunkType": "toolRequest", "createdAt": "2026-07-13T12:39:29.860Z"},
                {"chunkType": "toolResponse", "createdAt": "2026-07-13T12:39:32.719Z"},
            ]
        ),
    )

    sections = _build_span_sections(span, timeline)

    console = Console(width=120, record=True)
    for section in sections:
        console.print(section)
    rendered = console.export_text()
    assert "Table missing_table not found" in rendered
    assert "sql" in rendered
