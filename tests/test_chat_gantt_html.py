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
"""Tests for standalone chat Gantt HTML export."""

from __future__ import annotations

from drs.chat_gantt_html import build_html_report_payload, render_html_report


def test_build_html_report_payload_supports_multiple_conversations() -> None:
    payload = build_html_report_payload(
        [
            {
                "id": "conv-1",
                "label": "Conversation 1",
                "source": "conversation",
                "data": {
                    "data": [
                        {
                            "chunkType": "model",
                            "name": "modelSqlAnswer",
                            "createdAt": "2026-07-31T12:10:36.000Z",
                            "result": {
                                "title": "Direct Reports to Myra Richmond",
                                "summary": "Three people report to Myra Richmond.",
                            },
                        },
                        {
                            "chunkType": "toolRequest",
                            "callId": "c1",
                            "name": "runSql",
                            "createdAt": "2026-07-31T12:10:33.467Z",
                            "arguments": {"sqlText": "select 1"},
                        },
                        {
                            "chunkType": "toolResponse",
                            "callId": "c1",
                            "name": "runSql",
                            "createdAt": "2026-07-31T12:10:35.270Z",
                            "result": {"rows": [["Lesley Ellis"]]},
                        },
                    ]
                },
            },
            {
                "id": "conv-2",
                "label": "Conversation 2",
                "source": "dump",
                "data": {
                    "data": [
                        {
                            "chunkType": "toolRequest",
                            "callId": "c2",
                            "name": "validateSql",
                            "createdAt": "2026-07-31T12:11:33.467Z",
                            "arguments": {"sqlText": "select 2"},
                        },
                        {
                            "chunkType": "toolResponse",
                            "callId": "c2",
                            "name": "validateSql",
                            "createdAt": "2026-07-31T12:11:34.270Z",
                            "result": {"rows": []},
                        },
                    ]
                },
            },
        ]
    )

    assert payload["conversationCount"] == 2
    assert payload["overview"]["toolCalls"] == 2
    assert payload["overview"]["avgToolCallsPerConversation"] == 1
    assert payload["overview"]["runTime"]["count"] == 2
    assert payload["overview"]["toolDuration"]["count"] == 2
    assert (
        payload["conversations"][0]["conversationResult"]
        == "Direct Reports to Myra Richmond\n\nThree people report to Myra Richmond."
    )
    assert payload["conversations"][0]["timeline"]["spans"][0]["callId"] == "c1"
    assert payload["conversations"][0]["timeline"]["spans"][0]["toolResult"] == {"rows": [["Lesley Ellis"]]}
    assert payload["conversations"][1]["timeline"]["spans"][0]["callId"] == "c2"
    assert payload["conversations"][0]["conversationSummary"]["title"] == "Direct Reports to Myra Richmond"
    assert payload["conversations"][0]["conversationSummary"]["summary"] == "Three people report to Myra Richmond."


def test_render_html_report_embeds_json_payload() -> None:
    html = render_html_report(
        {
            "conversationCount": 1,
            "includeThinkTime": False,
            "overview": {
                "toolCalls": 1,
                "toolSpans": 1,
                "avgToolCallsPerConversation": 1,
                "runTime": {
                    "count": 1,
                    "meanMs": 1803,
                    "medianMs": 1803,
                    "stdDevMs": 0,
                    "minMs": 1803,
                    "maxMs": 1803,
                    "totalMs": 1803,
                    "meanLabel": "1.803s",
                    "medianLabel": "1.803s",
                    "stdDevLabel": "0.000s",
                    "minLabel": "1.803s",
                    "maxLabel": "1.803s",
                    "totalLabel": "1.803s",
                },
                "toolTime": {
                    "count": 1,
                    "meanMs": 1803,
                    "medianMs": 1803,
                    "stdDevMs": 0,
                    "minMs": 1803,
                    "maxMs": 1803,
                    "totalMs": 1803,
                    "meanLabel": "1.803s",
                    "medianLabel": "1.803s",
                    "stdDevLabel": "0.000s",
                    "minLabel": "1.803s",
                    "maxLabel": "1.803s",
                    "totalLabel": "1.803s",
                },
                "thinkTime": {
                    "count": 1,
                    "meanMs": 0,
                    "medianMs": 0,
                    "stdDevMs": 0,
                    "minMs": 0,
                    "maxMs": 0,
                    "totalMs": 0,
                    "meanLabel": "0.000s",
                    "medianLabel": "0.000s",
                    "stdDevLabel": "0.000s",
                    "minLabel": "0.000s",
                    "maxLabel": "0.000s",
                    "totalLabel": "0.000s",
                },
                "toolDuration": {
                    "count": 1,
                    "meanMs": 1803,
                    "medianMs": 1803,
                    "stdDevMs": 0,
                    "minMs": 1803,
                    "maxMs": 1803,
                    "totalMs": 1803,
                    "meanLabel": "1.803s",
                    "medianLabel": "1.803s",
                    "stdDevLabel": "0.000s",
                    "minLabel": "1.803s",
                    "maxLabel": "1.803s",
                    "totalLabel": "1.803s",
                },
            },
            "conversations": [
                {
                    "id": "conv-1",
                    "label": "Conversation 1",
                    "source": "conversation",
                    "conversationSummary": {
                        "title": "Direct Reports to Myra Richmond",
                        "summary": "Three people report to Myra Richmond.",
                    },
                    "conversationResult": "Direct Reports to Myra Richmond\n\nThree people report to Myra Richmond.",
                    "raw": {"data": []},
                    "historyBounds": {
                        "start": "2026-07-31T12:10:33.467+00:00",
                        "end": "2026-07-31T12:10:35.270+00:00",
                        "totalMs": 1803,
                        "totalLabel": "1.803s",
                    },
                    "timeline": {
                        "start": "2026-07-31T12:10:33.467+00:00",
                        "end": "2026-07-31T12:10:35.270+00:00",
                        "totalMs": 1803,
                        "laneCount": 1,
                        "stepCount": 1,
                        "spans": [
                            {
                                "lane": 0,
                                "step": 1,
                                "name": "runSql",
                                "callId": "c1",
                                "start": "2026-07-31T12:10:33.467+00:00",
                                "end": "2026-07-31T12:10:35.270+00:00",
                                "durationMs": 1803,
                                "durationLabel": "1.803s",
                                "offsetMs": 0,
                                "offsetLabel": "0.000s",
                                "label": "runSql",
                                "arguments": {"sqlText": "select 1"},
                                "title": "Direct Reports to Myra Richmond",
                                "summarizedTitle": None,
                                "failed": False,
                                "errorMessage": None,
                                "toolResult": {"rows": [["Lesley Ellis"]]},
                            }
                        ],
                    },
                    "summary": {"toolCalls": 1, "thinkTimeMs": 0, "toolTimeMs": 1803},
                }
            ],
        }
    )

    assert "<!doctype html>" in html
    assert 'id="report-data"' in html
    assert '"conversationCount": 1' in html
    assert "Overview" in html
    assert "Overall Stats" in html
    assert "Conversation 1" in html
    assert "Direct Reports to Myra Richmond" in html
    assert "Three people report to Myra Richmond." in html
    assert "Tool Result" in html
    assert "Conversation Result" in html


def test_render_html_report_escapes_script_terminators_in_payload() -> None:
    html = render_html_report(
        {
            "conversationCount": 1,
            "conversations": [
                {
                    "id": "conv-1",
                    "label": "Conversation 1",
                    "conversationSummary": {"title": "Result"},
                    "conversationResult": "</script><script>alert(1)</script>",
                }
            ],
        }
    )

    assert "</script><script>alert(1)</script>" not in html
    assert "\\u003c/script\\u003e\\u003cscript\\u003ealert(1)\\u003c/script\\u003e" in html
