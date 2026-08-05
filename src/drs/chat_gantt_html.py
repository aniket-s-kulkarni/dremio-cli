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
"""Standalone HTML export for chat history Gantt timelines."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any

from drs.chat_gantt import (
    build_history_bounds,
    build_tool_spans,
    extract_history_rows,
    format_duration_ms,
)
from drs.chat_render import extract_model_text


def _extract_conversation_summary(rows: list[dict[str, Any]]) -> dict[str, str | None]:
    """Extract the latest user-visible model title/summary/text from conversation history."""
    title: str | None = None
    summary: str | None = None

    for row in rows:
        if row.get("chunkType") != "model":
            continue
        result = row.get("result")
        if not isinstance(result, dict):
            continue
        candidate_title = result.get("title")
        if isinstance(candidate_title, str) and candidate_title.strip():
            title = candidate_title.strip()
        candidate_summary = result.get("summary")
        if isinstance(candidate_summary, str) and candidate_summary.strip():
            summary = candidate_summary.strip()
        elif not summary:
            extracted = extract_model_text(str(row.get("name", "")), result).strip()
            if extracted:
                summary = extracted

    return {"title": title, "summary": summary}


def _extract_conversation_result(rows: list[dict[str, Any]]) -> str | None:
    """Extract the latest user-visible model text for the conversation result."""
    for row in reversed(rows):
        if row.get("chunkType") != "model":
            continue
        result = row.get("result")
        if not isinstance(result, dict):
            continue
        text = extract_model_text(str(row.get("name", "")), result).strip()
        if text:
            return text
    return None


def _extract_tool_details(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Collect tool request/response details keyed by call ID."""
    details: dict[str, dict[str, Any]] = {}
    for row in rows:
        call_id = str(row.get("callId", "")).strip()
        if not call_id:
            continue

        entry = details.setdefault(call_id, {})
        if row.get("chunkType") == "toolRequest":
            entry["arguments"] = row.get("arguments")
        elif row.get("chunkType") == "toolResponse":
            entry["toolResult"] = row.get("result")
            error_message = row.get("errorMessage") or row.get("error") or row.get("message")
            if error_message:
                entry["errorMessage"] = error_message
    return details


def _build_duration_stats(values: list[int]) -> dict[str, Any]:
    """Build aggregate statistics for a collection of durations."""
    if not values:
        return {
            "count": 0,
            "meanMs": 0,
            "medianMs": 0,
            "stdDevMs": 0,
            "minMs": 0,
            "maxMs": 0,
            "totalMs": 0,
            "meanLabel": format_duration_ms(0),
            "medianLabel": format_duration_ms(0),
            "stdDevLabel": format_duration_ms(0),
            "minLabel": format_duration_ms(0),
            "maxLabel": format_duration_ms(0),
            "totalLabel": format_duration_ms(0),
        }

    mean_ms = round(mean(values))
    median_ms = round(median(values))
    std_dev_ms = round(pstdev(values)) if len(values) > 1 else 0
    min_ms = min(values)
    max_ms = max(values)
    total_ms = sum(values)
    return {
        "count": len(values),
        "meanMs": mean_ms,
        "medianMs": median_ms,
        "stdDevMs": std_dev_ms,
        "minMs": min_ms,
        "maxMs": max_ms,
        "totalMs": total_ms,
        "meanLabel": format_duration_ms(mean_ms),
        "medianLabel": format_duration_ms(median_ms),
        "stdDevLabel": format_duration_ms(std_dev_ms),
        "minLabel": format_duration_ms(min_ms),
        "maxLabel": format_duration_ms(max_ms),
        "totalLabel": format_duration_ms(total_ms),
    }


def build_html_report_payload(
    conversations: list[dict[str, Any]],
    *,
    include_think_time: bool = False,
    min_think_time_ms: int = 5,
) -> dict[str, Any]:
    """Build the JSON payload embedded into the standalone HTML report."""
    payload_conversations: list[dict[str, Any]] = []
    for conversation in conversations:
        rows = extract_history_rows(conversation["data"])
        history_bounds = build_history_bounds(rows)
        conversation_summary = _extract_conversation_summary(rows)
        conversation_result = _extract_conversation_result(rows)
        tool_details = _extract_tool_details(rows)
        spans, first_start, last_end = build_tool_spans(
            rows,
            include_think_time=include_think_time,
            min_think_time_ms=min_think_time_ms,
        )
        if history_bounds is None:
            continue

        payload_conversations.append(
            {
                "id": conversation["id"],
                "label": conversation["label"],
                "source": conversation["source"],
                "conversationSummary": conversation_summary,
                "conversationResult": conversation_result,
                "raw": conversation["data"],
                "historyBounds": {
                    "start": history_bounds.start.isoformat(),
                    "end": history_bounds.end.isoformat(),
                    "totalMs": history_bounds.total_ms,
                    "totalLabel": format_duration_ms(history_bounds.total_ms),
                },
                "timeline": {
                    "start": first_start.isoformat() if first_start else None,
                    "end": last_end.isoformat() if last_end else None,
                    "totalMs": max(int((last_end - first_start).total_seconds() * 1000), 1)
                    if first_start and last_end
                    else 0,
                    "laneCount": max((span.lane for span in spans), default=-1) + 1,
                    "stepCount": max((span.step for span in spans), default=0),
                    "spans": [
                        {
                            "lane": span.lane,
                            "step": span.step,
                            "name": span.name,
                            "callId": span.call_id,
                            "start": span.start.isoformat(),
                            "end": span.end.isoformat(),
                            "durationMs": span.duration_ms,
                            "durationLabel": format_duration_ms(span.duration_ms),
                            "offsetMs": span.offset_ms,
                            "offsetLabel": format_duration_ms(span.offset_ms),
                            "label": span.label,
                            "arguments": tool_details.get(span.call_id or "", {}).get("arguments", span.arguments),
                            "title": span.title,
                            "summarizedTitle": span.summarized_title,
                            "failed": span.failed,
                            "errorMessage": tool_details.get(span.call_id or "", {}).get(
                                "errorMessage", span.error_message
                            ),
                            "toolResult": tool_details.get(span.call_id or "", {}).get("toolResult"),
                        }
                        for span in spans
                    ],
                },
                "summary": {
                    "toolCalls": sum(1 for span in spans if span.name != "thinkTime"),
                    "thinkTimeMs": sum(span.duration_ms for span in spans if span.name == "thinkTime"),
                    "toolTimeMs": sum(span.duration_ms for span in spans if span.name != "thinkTime"),
                },
            }
        )

    run_times = [conv["historyBounds"]["totalMs"] for conv in payload_conversations]
    tool_times = [conv["summary"]["toolTimeMs"] for conv in payload_conversations]
    think_times = [conv["summary"]["thinkTimeMs"] for conv in payload_conversations]
    tool_call_counts = [conv["summary"]["toolCalls"] for conv in payload_conversations]
    tool_span_durations = [
        span["durationMs"]
        for conv in payload_conversations
        for span in conv["timeline"]["spans"]
        if span["name"] != "thinkTime"
    ]

    return {
        "conversationCount": len(payload_conversations),
        "includeThinkTime": include_think_time,
        "overview": {
            "toolCalls": sum(tool_call_counts),
            "toolSpans": len(tool_span_durations),
            "avgToolCallsPerConversation": round(mean(tool_call_counts), 2) if tool_call_counts else 0,
            "runTime": _build_duration_stats(run_times),
            "toolTime": _build_duration_stats(tool_times),
            "thinkTime": _build_duration_stats(think_times),
            "toolDuration": _build_duration_stats(tool_span_durations),
        },
        "conversations": payload_conversations,
    }


def render_html_report(payload: dict[str, Any]) -> str:
    """Render a self-contained HTML report with embedded JSON payload."""
    payload_json = json.dumps(payload, indent=2)
    title_suffix = ""
    if payload.get("conversationCount") == 1 and payload.get("conversations"):
        first = payload["conversations"][0]
        summary_title = ((first.get("conversationSummary") or {}).get("title") or first.get("label") or "").strip()
        if summary_title:
            title_suffix = f" - {summary_title}"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Dremio Chat Gantt Report{title_suffix}</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: light-dark(#f4f6fb, #111318);
      --panel: light-dark(rgba(255,255,255,0.92), rgba(21,24,31,0.9));
      --panel-strong: light-dark(rgba(255,255,255,0.98), rgba(26,30,38,0.98));
      --border: light-dark(#d5dce8, #334155);
      --text: light-dark(#121826, #e6edf7);
      --muted: light-dark(#526077, #9aa8bf);
      --accent: light-dark(#0f62fe, #7cb1ff);
      --success: light-dark(#1f8f55, #3ccf8e);
      --warn: light-dark(#b26a00, #f4c152);
      --danger: light-dark(#b42318, #ff8b7f);
      --think: light-dark(#7a8191, #788190);
      --shadow: light-dark(0 12px 40px rgba(15, 23, 42, 0.08), 0 18px 48px rgba(0, 0, 0, 0.38));
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
    }}
    .page {{
      display: grid;
      grid-template-columns: 20rem minmax(0, 1fr);
      min-height: 100vh;
    }}
    .sidebar {{
      border-right: 1px solid var(--border);
      background: linear-gradient(180deg, var(--panel-strong), transparent);
      padding: 1rem;
      position: sticky;
      top: 0;
      align-self: start;
      max-height: 100vh;
      overflow: auto;
    }}
    .sidebar h1 {{
      font-size: 1.1rem;
      margin: 0 0 .35rem;
      font-weight: 600;
    }}
    .sidebar p {{
      margin: 0 0 1rem;
      color: var(--muted);
      font-size: .92rem;
    }}
    .conversation-list {{
      display: grid;
      gap: .65rem;
    }}
    .conversation-button.is-overview {{
      border-style: dashed;
    }}
    .conversation-button {{
      width: 100%;
      border: 1px solid var(--border);
      background: var(--panel);
      color: var(--text);
      border-radius: .9rem;
      padding: .8rem .9rem;
      text-align: left;
      cursor: pointer;
      box-shadow: var(--shadow);
    }}
    .conversation-button.active {{
      border-color: color-mix(in srgb, var(--accent) 62%, var(--border));
      outline: 2px solid color-mix(in srgb, var(--accent) 18%, transparent);
    }}
    .conversation-button .meta {{
      color: var(--muted);
      display: block;
      margin-top: .35rem;
      font-size: .82rem;
    }}
    .main {{
      padding: 1.25rem;
      display: grid;
      gap: 1rem;
      align-content: start;
    }}
    .overview-panels {{
      display: grid;
      gap: 1rem;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 1rem;
      box-shadow: var(--shadow);
    }}
    .header {{
      padding: 1rem 1.15rem;
      display: flex;
      justify-content: space-between;
      gap: 1rem;
      align-items: start;
    }}
    .header h2 {{
      margin: 0;
      font-size: 1.15rem;
      font-weight: 600;
    }}
    .header .meta {{
      color: var(--muted);
      font-size: .9rem;
      margin-top: .35rem;
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
      gap: .85rem;
      padding: 0 1.15rem 1.15rem;
    }}
    .summary .metric {{
      background: color-mix(in srgb, var(--panel-strong) 70%, transparent);
      border: 1px solid var(--border);
      border-radius: .9rem;
      padding: .8rem .9rem;
    }}
    .summary .label {{
      display: block;
      color: var(--muted);
      font-size: .78rem;
      margin-bottom: .35rem;
      text-transform: uppercase;
      letter-spacing: .04em;
    }}
    .summary .value {{
      font-size: 1rem;
      font-weight: 600;
    }}
    .timeline-card {{
      padding: 1rem 1.15rem 1.15rem;
    }}
    .axis {{
      display: grid;
      grid-template-columns: 7rem 22rem minmax(40rem, 1fr) 7rem;
      gap: .75rem;
      align-items: end;
      color: var(--muted);
      font-size: .82rem;
      margin-bottom: .5rem;
    }}
    .timeline-rows {{
      display: grid;
      gap: .5rem;
    }}
    .row {{
      display: grid;
      grid-template-columns: 7rem 22rem minmax(40rem, 1fr) 7rem;
      gap: .75rem;
      align-items: center;
      cursor: pointer;
      border-radius: .8rem;
      padding: .2rem .35rem;
    }}
    .row.active {{
      background: color-mix(in srgb, var(--accent) 10%, transparent);
      outline: 1px solid color-mix(in srgb, var(--accent) 25%, transparent);
    }}
    .row-step, .row-duration {{
      color: var(--muted);
      font-variant-numeric: tabular-nums;
      font-size: .83rem;
    }}
    .row-label {{
      min-width: 0;
    }}
    .row-label .title {{
      display: block;
      font-size: .92rem;
      font-weight: 600;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .row-label .subtitle {{
      display: block;
      color: var(--muted);
      font-size: .8rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      margin-top: .16rem;
    }}
    .bar-track {{
      position: relative;
      height: 1.1rem;
      border-radius: 999px;
      background:
        linear-gradient(to right, transparent, transparent),
        repeating-linear-gradient(
          to right,
          color-mix(in srgb, var(--border) 30%, transparent) 0,
          color-mix(in srgb, var(--border) 30%, transparent) 1px,
          transparent 1px,
          transparent calc(20% - 1px)
        );
      overflow: hidden;
    }}
    .bar {{
      position: absolute;
      top: 0;
      height: 100%;
      border-radius: 999px;
      min-width: 2px;
      background: var(--bar-color);
      box-shadow: inset 0 0 0 1px color-mix(in srgb, black 12%, transparent);
    }}
    .details {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(18rem, 24rem);
      gap: 1rem;
      padding: 1rem 1.15rem 1.15rem;
    }}
    .stats-table {{
      padding: 0 1.15rem 1.15rem;
      overflow-x: auto;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: .88rem;
    }}
    th, td {{
      text-align: left;
      padding: .65rem .55rem;
      border-bottom: 1px solid color-mix(in srgb, var(--border) 72%, transparent);
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-weight: 600;
    }}
    td.numeric {{
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }}
    .detail-section {{
      background: color-mix(in srgb, var(--panel-strong) 76%, transparent);
      border: 1px solid var(--border);
      border-radius: .9rem;
      padding: .9rem 1rem;
    }}
    .detail-section h3 {{
      margin: 0 0 .7rem;
      font-size: .95rem;
      font-weight: 600;
    }}
    .markdown-body {{
      font-size: .92rem;
      line-height: 1.55;
    }}
    .markdown-body > :first-child {{
      margin-top: 0;
    }}
    .markdown-body > :last-child {{
      margin-bottom: 0;
    }}
    .markdown-body h1,
    .markdown-body h2,
    .markdown-body h3,
    .markdown-body h4,
    .markdown-body h5,
    .markdown-body h6 {{
      margin: 1rem 0 0.55rem;
      line-height: 1.25;
    }}
    .markdown-body p,
    .markdown-body ul,
    .markdown-body ol,
    .markdown-body pre,
    .markdown-body blockquote {{
      margin: 0.65rem 0;
    }}
    .markdown-body code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 0.88em;
      background: color-mix(in srgb, var(--panel-strong) 82%, transparent);
      padding: 0.08rem 0.3rem;
      border-radius: 0.35rem;
    }}
    .markdown-body pre code {{
      background: transparent;
      padding: 0;
      border-radius: 0;
      font-size: inherit;
    }}
    .markdown-body blockquote {{
      border-left: 3px solid var(--border);
      padding-left: 0.8rem;
      color: var(--muted);
    }}
    .markdown-body table {{
      width: 100%;
      border-collapse: collapse;
      margin: 0.8rem 0;
      font-size: .88rem;
    }}
    .markdown-body th,
    .markdown-body td {{
      text-align: left;
      padding: .5rem .6rem;
      border: 1px solid color-mix(in srgb, var(--border) 80%, transparent);
      vertical-align: top;
    }}
    .markdown-body th {{
      background: color-mix(in srgb, var(--panel-strong) 82%, transparent);
    }}
    .code-block {{
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      font-size: .82rem;
      line-height: 1.45;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      color: var(--text);
      background: color-mix(in srgb, var(--panel-strong) 82%, transparent);
      border: 1px solid var(--border);
      border-radius: .7rem;
      padding: .85rem .95rem;
      overflow-x: auto;
    }}
    .tok-key {{ color: #0f62fe; }}
    .tok-string {{ color: #1f8f55; }}
    .tok-number {{ color: #b26a00; }}
    .tok-bool {{ color: #7c3aed; }}
    .tok-null {{ color: #b42318; }}
    dl {{
      margin: 0;
      display: grid;
      grid-template-columns: 8rem minmax(0, 1fr);
      gap: .45rem .75rem;
      font-size: .88rem;
    }}
    dt {{ color: var(--muted); }}
    dd {{
      margin: 0;
      word-break: break-word;
    }}
    pre {{
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      font-size: .82rem;
      line-height: 1.45;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      color: var(--text);
    }}
    .pill {{
      display: inline-block;
      padding: .18rem .5rem;
      border-radius: 999px;
      font-size: .76rem;
      font-weight: 600;
      border: 1px solid currentColor;
    }}
    .pill.success {{ color: var(--success); }}
    .pill.failed {{ color: var(--danger); }}
    .pill.think {{ color: var(--think); }}
    .empty {{
      color: var(--muted);
      padding: 1rem 0;
    }}
    @media (max-width: 1100px) {{
      .page {{
        grid-template-columns: 1fr;
      }}
      .sidebar {{
        position: static;
        border-right: 0;
        border-bottom: 1px solid var(--border);
        max-height: none;
      }}
    }}
    @media (max-width: 900px) {{
      .axis, .row {{
        grid-template-columns: 5.5rem minmax(0, 1fr);
      }}
      .axis .hide-mobile,
      .row .hide-mobile {{
        display: none;
      }}
      .details {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div id="app"></div>
  <script type="application/json" id="report-data">{payload_json}</script>
  <script>
    const report = JSON.parse(document.getElementById("report-data").textContent);
    const app = document.getElementById("app");

    function duration(ms) {{
      if (ms >= 60000) {{
        const minutes = Math.floor(ms / 60000);
        const seconds = ((ms % 60000) / 1000).toFixed(2).padStart(5, "0");
        return `${{minutes}}m${{seconds}}s`;
      }}
      return `${{(ms / 1000).toFixed(3)}}s`;
    }}

    function fmtTime(value) {{
      if (!value) return "n/a";
      const date = new Date(value);
      return date.toLocaleTimeString([], {{ hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }});
    }}

    function barColor(span, totalMs) {{
      if (span.failed) return "var(--danger)";
      if (span.name === "thinkTime") return "var(--think)";
      const ratio = span.durationMs / Math.max(totalMs, 1);
      if (ratio < 0.05) return "var(--success)";
      if (ratio < 0.15) return "var(--warn)";
      if (ratio < 0.30) return "magenta";
      return "var(--danger)";
    }}

    function conversationButton(conv, index) {{
      const summaryTitle = conv.conversationSummary?.title || conv.label;
      return `
        <button class="conversation-button" data-conversation-index="${{index}}">
          <strong>${{escapeHtml(summaryTitle)}}</strong>
          <span class="meta">${{escapeHtml(conv.source)}} • ${{conv.timeline.spans.length}} span(s)</span>
        </button>
      `;
    }}

    function escapeHtml(value) {{
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
    }}

    function renderInlineMarkdown(text) {{
      return escapeHtml(text)
        .replace(/`([^`]+)`/g, "<code>$1</code>")
        .replace(/\\*\\*([^*]+)\\*\\*/g, "<strong>$1</strong>")
        .replace(/\\*([^*]+)\\*/g, "<em>$1</em>")
        .replace(/\\[([^\\]]+)\\]\\(([^)]+)\\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
    }}

    function renderCodeBlock(value) {{
      const text = typeof value === "string" ? value : JSON.stringify(value ?? null, null, 2);
      try {{
        const parsed = JSON.parse(text);
        return `<pre class="code-block"><code>${{syntaxHighlightJson(parsed)}}</code></pre>`;
      }} catch {{
        return `<pre class="code-block"><code>${{escapeHtml(text)}}</code></pre>`;
      }}
    }}

    function syntaxHighlightJson(value) {{
      const json = JSON.stringify(value, null, 2);
      return escapeHtml(json).replace(
        /&quot;([^&]|&(?!quot;))*&quot;(?=\\s*:)|&quot;([^&]|&(?!quot;))*&quot;|-?\\b\\d+(?:\\.\\d+)?(?:[eE][+-]?\\d+)?\\b|\\btrue\\b|\\bfalse\\b|\\bnull\\b/g,
        (match) => {{
          if (match.startsWith("&quot;") && /(?=\\s*:)$/.test(match)) {{
            return `<span class="tok-key">${{match}}</span>`;
          }}
          if (match.startsWith("&quot;")) {{
            return `<span class="tok-string">${{match}}</span>`;
          }}
          if (match === "true" || match === "false") {{
            return `<span class="tok-bool">${{match}}</span>`;
          }}
          if (match === "null") {{
            return `<span class="tok-null">${{match}}</span>`;
          }}
          return `<span class="tok-number">${{match}}</span>`;
        }}
      );
    }}

    function markdownToHtml(markdown) {{
      const normalized = String(markdown ?? "").replace(/\\r\\n/g, "\\n");
      const lines = normalized.split("\\n");
      const html = [];
      let paragraph = [];
      let listType = null;
      let inCodeBlock = false;
      let codeLines = [];

      function flushParagraph() {{
        if (!paragraph.length) return;
        html.push(`<p>${{renderInlineMarkdown(paragraph.join(" "))}}</p>`);
        paragraph = [];
      }}

      function flushList() {{
        if (listType !== null) {{
          html.push(`</${{listType}}>`);
          listType = null;
        }}
      }}

      function flushCodeBlock() {{
        if (!inCodeBlock) return;
        html.push(renderCodeBlock(codeLines.join("\\n")));
        inCodeBlock = false;
        codeLines = [];
      }}

      function isTableRow(line) {{
        return /\\|/.test(line.trim());
      }}

      function isTableSeparator(line) {{
        const trimmed = line.trim();
        if (!trimmed || !/\\|/.test(trimmed)) return false;
        let normalized = trimmed;
        if (normalized.startsWith("|")) normalized = normalized.slice(1);
        if (normalized.endsWith("|")) normalized = normalized.slice(0, -1);
        const cells = normalized.split("|").map((cell) => cell.trim());
        return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
      }}

      function splitTableRow(line) {{
        let trimmed = line.trim();
        if (trimmed.startsWith("|")) trimmed = trimmed.slice(1);
        if (trimmed.endsWith("|")) trimmed = trimmed.slice(0, -1);
        return trimmed.split("|").map((cell) => renderInlineMarkdown(cell.trim()));
      }}

      function renderTable(headerLine, bodyLines) {{
        const tableHeader = splitTableRow(headerLine);
        const tableRows = bodyLines.map(splitTableRow);
        html.push(
          `<table><thead><tr>${{tableHeader.map((cell) => `<th>${{cell}}</th>`).join("")}}</tr></thead><tbody>${{
            tableRows.map((row) => `<tr>${{row.map((cell) => `<td>${{cell}}</td>`).join("")}}</tr>`).join("")
          }}</tbody></table>`
        );
      }}

      for (let idx = 0; idx < lines.length; idx += 1) {{
        const rawLine = lines[idx];
        const line = rawLine.replace(/\\t/g, "    ");
        const trimmed = line.trim();

        if (trimmed.startsWith("```")) {{
          flushParagraph();
          flushList();
          if (inCodeBlock) {{
            flushCodeBlock();
          }} else {{
            inCodeBlock = true;
            codeLines = [];
          }}
          continue;
        }}

        if (inCodeBlock) {{
          codeLines.push(rawLine);
          continue;
        }}

        if (!trimmed) {{
          flushParagraph();
          flushList();
          continue;
        }}

        if (isTableRow(trimmed) && idx + 1 < lines.length && isTableSeparator(lines[idx + 1])) {{
          flushParagraph();
          flushList();
          const headerLine = trimmed;
          const bodyLines = [];
          idx += 2;
          while (idx < lines.length) {{
            const candidate = lines[idx].trim();
            if (!candidate || !isTableRow(candidate) || isTableSeparator(candidate)) {{
              idx -= 1;
              break;
            }}
            bodyLines.push(candidate);
            idx += 1;
          }}
          renderTable(headerLine, bodyLines);
          continue;
        }}

        const headingMatch = trimmed.match(/^(#{1,6})\\s+(.*)$/);
        if (headingMatch) {{
          flushParagraph();
          flushList();
          const level = headingMatch[1].length;
          html.push(`<h${{level}}>${{renderInlineMarkdown(headingMatch[2])}}</h${{level}}>`);
          continue;
        }}

        const blockquoteMatch = trimmed.match(/^>\\s?(.*)$/);
        if (blockquoteMatch) {{
          flushParagraph();
          flushList();
          html.push(`<blockquote><p>${{renderInlineMarkdown(blockquoteMatch[1])}}</p></blockquote>`);
          continue;
        }}

        const orderedMatch = trimmed.match(/^\\d+\\.\\s+(.*)$/);
        const unorderedMatch = trimmed.match(/^[-*]\\s+(.*)$/);
        if (orderedMatch || unorderedMatch) {{
          flushParagraph();
          const nextListType = orderedMatch ? "ol" : "ul";
          if (listType !== nextListType) {{
            flushList();
            listType = nextListType;
            html.push(`<${{listType}}>`);
          }}
          html.push(`<li>${{renderInlineMarkdown((orderedMatch || unorderedMatch)[1])}}</li>`);
          continue;
        }}

        flushList();
        paragraph.push(trimmed);
      }}

      flushParagraph();
      flushList();
      flushCodeBlock();
      return html.join("");
    }}

    function render() {{
      if (!report.conversations.length) {{
        app.innerHTML = `<div class="page"><main class="main"><section class="card"><div class="header"><div><h2>No timeline data</h2><div class="meta">No conversations contained completed tool calls.</div></div></div></section></main></div>`;
        return;
      }}

      app.innerHTML = `
        <div class="page">
          <aside class="sidebar">
            <h1>Chat Gantt Report</h1>
            <p>${{report.conversationCount}} conversation(s) embedded in this page.</p>
            <div class="conversation-list">
              <button class="conversation-button is-overview active" data-view="overview">
                <strong>Overview</strong>
                <span class="meta">Aggregate stats and navigation</span>
              </button>
              ${{report.conversations.map(conversationButton).join("")}}
            </div>
          </aside>
          <main class="main" id="main"></main>
        </div>
      `;

      document.querySelectorAll(".conversation-button").forEach((button) => {{
        button.addEventListener("click", () => {{
          document.querySelectorAll(".conversation-button").forEach((item) => item.classList.remove("active"));
          button.classList.add("active");
          if (button.dataset.view === "overview") {{
            renderOverview();
            return;
          }}
          const index = Number(button.dataset.conversationIndex);
          renderConversation(index, 0);
        }});
      }});

      renderOverview();
    }}

    function statsRow(label, stats) {{
      return `
        <tr>
          <th scope="row">${{escapeHtml(label)}}</th>
          <td class="numeric">${{stats.count}}</td>
          <td class="numeric">${{escapeHtml(stats.meanLabel)}}</td>
          <td class="numeric">${{escapeHtml(stats.medianLabel)}}</td>
          <td class="numeric">${{escapeHtml(stats.stdDevLabel)}}</td>
          <td class="numeric">${{escapeHtml(stats.minLabel)}}</td>
          <td class="numeric">${{escapeHtml(stats.maxLabel)}}</td>
          <td class="numeric">${{escapeHtml(stats.totalLabel)}}</td>
        </tr>
      `;
    }}

    function renderOverview() {{
      const main = document.getElementById("main");
      const overview = report.overview;
      main.innerHTML = `
        <section class="overview-panels">
          <section class="card">
            <div class="header">
              <div>
                <h2>Overview</h2>
                <div class="meta">Aggregate stats across all embedded conversations.</div>
              </div>
              <div class="meta">${{report.conversationCount}} conversation(s)</div>
            </div>
            <div class="summary">
              <div class="metric"><span class="label">Tool Calls</span><span class="value">${{overview.toolCalls}}</span></div>
              <div class="metric"><span class="label">Avg Tool Calls</span><span class="value">${{overview.avgToolCallsPerConversation}}</span></div>
              <div class="metric"><span class="label">Mean Run Time</span><span class="value">${{overview.runTime.meanLabel}}</span></div>
              <div class="metric"><span class="label">Mean Tool Time</span><span class="value">${{overview.toolTime.meanLabel}}</span></div>
            </div>
          </section>
          <section class="card">
            <div class="header">
              <div>
                <h2>Overall Stats</h2>
                <div class="meta">Mean, median, standard deviation, and totals.</div>
              </div>
            </div>
            <div class="stats-table">
              <table>
                <thead>
                  <tr>
                    <th>Metric</th>
                    <th>Count</th>
                    <th>Mean</th>
                    <th>Median</th>
                    <th>Std Dev</th>
                    <th>Min</th>
                    <th>Max</th>
                    <th>Total</th>
                  </tr>
                </thead>
                <tbody>
                  ${{statsRow("Run Time", overview.runTime)}}
                  ${{statsRow("Tool Time", overview.toolTime)}}
                  ${{statsRow("Think Time", overview.thinkTime)}}
                  ${{statsRow("Tool Duration", overview.toolDuration)}}
                </tbody>
              </table>
            </div>
          </section>
          <section class="card">
            <div class="header">
              <div>
                <h2>Conversations</h2>
                <div class="meta">Jump to an individual gantt chart and compare totals.</div>
              </div>
            </div>
            <div class="stats-table">
              <table>
                <thead>
                  <tr>
                    <th>Conversation</th>
                    <th>Source</th>
                    <th>Tool Calls</th>
                    <th>Run Time</th>
                    <th>Tool Time</th>
                    <th>Think Time</th>
                  </tr>
                </thead>
                <tbody>
                  ${{
                    report.conversations
                      .map((conv, index) => `
                        <tr>
                          <td><button class="conversation-link" data-conversation-index="${{index}}">${{escapeHtml(conv.conversationSummary?.title || conv.label)}}</button></td>
                          <td>${{escapeHtml(conv.source)}}</td>
                          <td class="numeric">${{conv.summary.toolCalls}}</td>
                          <td class="numeric">${{escapeHtml(conv.historyBounds.totalLabel)}}</td>
                          <td class="numeric">${{duration(conv.summary.toolTimeMs)}}</td>
                          <td class="numeric">${{duration(conv.summary.thinkTimeMs)}}</td>
                        </tr>
                      `)
                      .join("")
                  }}
                </tbody>
              </table>
            </div>
          </section>
        </section>
      `;

      document.querySelectorAll(".conversation-link").forEach((button) => {{
        button.addEventListener("click", () => {{
          const index = Number(button.dataset.conversationIndex);
          const sidebarButton = document.querySelector(`.conversation-button[data-conversation-index="${{index}}"]`);
          document.querySelectorAll(".conversation-button").forEach((item) => item.classList.remove("active"));
          sidebarButton?.classList.add("active");
          renderConversation(index, 0);
        }});
      }});
    }}

    function renderConversation(conversationIndex, selectedSpanIndex) {{
      const conv = report.conversations[conversationIndex];
      const main = document.getElementById("main");
      const spans = conv.timeline.spans;
      const selected = spans[selectedSpanIndex] ?? null;
      const conversationTitle = conv.conversationSummary?.title || conv.label;
      const conversationSummary = conv.conversationSummary?.summary || "";
      const conversationResult = conv.conversationResult || "";
      const topMarkdownParts = [];
      if (conversationTitle) {{
        topMarkdownParts.push(`# ${{conversationTitle}}`);
      }}
      if (conversationSummary) {{
        topMarkdownParts.push(conversationSummary);
      }}
      if (conversationResult && conversationResult !== conversationSummary) {{
        topMarkdownParts.push("## Result");
        topMarkdownParts.push(conversationResult);
      }}
      main.innerHTML = `
        <section class="card">
          <div class="header">
            <div>
              <h2>${{escapeHtml(conversationTitle)}}</h2>
              <div class="meta">${{escapeHtml(conv.source)}} • ${{conv.historyBounds.start}} → ${{conv.historyBounds.end}}</div>
              ${{
                conversationSummary
                  ? `<div class="meta" style="max-width:72ch">${{escapeHtml(conversationSummary)}}</div>`
                  : ""
              }}
            </div>
            <div class="meta">${{conv.timeline.spans.length}} span(s)</div>
          </div>
          <div class="summary">
            <div class="metric"><span class="label">Tool Calls</span><span class="value">${{conv.summary.toolCalls}}</span></div>
            <div class="metric"><span class="label">Tool Time</span><span class="value">${{duration(conv.summary.toolTimeMs)}}</span></div>
            <div class="metric"><span class="label">Think Time</span><span class="value">${{duration(conv.summary.thinkTimeMs)}}</span></div>
            <div class="metric"><span class="label">Total Run Time</span><span class="value">${{conv.historyBounds.totalLabel}}</span></div>
          </div>
        </section>
        <section class="card">
          <div class="details" style="grid-template-columns:minmax(0, 1fr);">
            <div class="detail-section">
              <h3>Conversation Result</h3>
              <div class="markdown-body">
                ${{topMarkdownParts.length ? markdownToHtml(topMarkdownParts.join("\\n\\n")) : "<p>No summary available.</p>"}}
              </div>
            </div>
          </div>
        </section>
        <section class="card timeline-card">
          <div class="axis">
            <div>Step</div>
            <div>Tool</div>
            <div class="hide-mobile">Timeline (${{
              conv.timeline.totalMs ? duration(conv.timeline.totalMs) : "n/a"
            }})</div>
            <div class="hide-mobile">Duration</div>
          </div>
          <div class="timeline-rows">
            ${{
              spans.length
                ? spans
                    .map((span, index) => timelineRow(span, conv.timeline.totalMs, index === selectedSpanIndex, index))
                    .join("")
                : `<div class="empty">No completed tool spans were found for this conversation.</div>`
            }}
          </div>
        </section>
        <section class="card details">
          <div style="display:grid; gap:1rem;">
            <div class="detail-section">
              <h3>Payload</h3>
              ${{
                selected
                  ? renderCodeBlock({{
                      arguments: selected.arguments,
                      errorMessage: selected.errorMessage
                    }})
                  : `<div class="empty">Select a timeline row to inspect its details.</div>`
              }}
            </div>
            <div class="detail-section">
              <h3>Tool Result</h3>
              ${{
                selected
                  ? renderCodeBlock(selected.toolResult ?? "No tool result captured.")
                  : `<div class="empty">Select a timeline row to inspect its details.</div>`
              }}
            </div>
          </div>
          <div class="detail-section">
            <h3>Selected Span</h3>
            ${{
              selected
                ? selectedSummary(selected)
                : `<div class="empty">Select a timeline row to inspect its details.</div>`
            }}
          </div>
        </section>
      `;

      document.querySelectorAll(".row").forEach((row) => {{
        row.addEventListener("click", () => renderConversation(conversationIndex, Number(row.dataset.spanIndex)));
      }});
    }}

    function timelineRow(span, totalMs, active, index) {{
      const left = totalMs ? (span.offsetMs / totalMs) * 100 : 0;
      const width = totalMs ? Math.max((span.durationMs / totalMs) * 100, 0.35) : 100;
      const subtitle = span.summarizedTitle || span.title || span.callId;
      return `
        <div class="row${{active ? " active" : ""}}" data-span-index="${{index}}">
          <div class="row-step">S${{span.step}}</div>
          <div class="row-label">
            <span class="title">${{escapeHtml(span.name === "thinkTime" ? "think time" : span.name)}}</span>
            <span class="subtitle">${{escapeHtml(subtitle ?? "")}}</span>
          </div>
          <div class="bar-track hide-mobile">
            <div class="bar" style="left:${{left}}%;width:${{width}}%;--bar-color:${{barColor(span, totalMs)}}"></div>
          </div>
          <div class="row-duration hide-mobile">${{span.durationLabel}}</div>
        </div>
      `;
    }}

    function selectedSummary(span) {{
      let statusClass = "success";
      let statusLabel = "success";
      if (span.name === "thinkTime") {{
        statusClass = "think";
        statusLabel = "think time";
      }} else if (span.failed) {{
        statusClass = "failed";
        statusLabel = "failed";
      }}
      return `
        <div style="margin-bottom:.8rem"><span class="pill ${{statusClass}}">${{statusLabel}}</span></div>
        <dl>
          <dt>Tool</dt><dd>${{escapeHtml(span.name)}}</dd>
          <dt>Step</dt><dd>${{span.step}}</dd>
          <dt>Call ID</dt><dd>${{escapeHtml(span.callId)}}</dd>
          <dt>Start</dt><dd>${{escapeHtml(span.start)}} (${{fmtTime(span.start)}})</dd>
          <dt>End</dt><dd>${{escapeHtml(span.end)}} (${{fmtTime(span.end)}})</dd>
          <dt>Offset</dt><dd>${{span.offsetLabel}}</dd>
          <dt>Duration</dt><dd>${{span.durationLabel}}</dd>
          <dt>Label</dt><dd>${{escapeHtml(span.label)}}</dd>
          <dt>Title</dt><dd>${{escapeHtml(span.title ?? "n/a")}}</dd>
          <dt>Summary</dt><dd>${{escapeHtml(span.summarizedTitle ?? "n/a")}}</dd>
        </dl>
      `;
    }}

    render();
  </script>
</body>
</html>
"""


def write_html_report(path: Path, payload: dict[str, Any]) -> None:
    """Write the standalone report to disk."""
    path.write_text(render_html_report(payload), encoding="utf-8")
