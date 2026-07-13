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
"""Shared chat history Gantt parsing and rendering helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class ToolSpan:
    """A completed tool call span."""

    lane: int
    step: int
    name: str
    call_id: str
    start: datetime
    end: datetime
    duration_ms: int
    offset_ms: int
    label: str
    arguments: dict[str, Any] | None
    title: str | None
    summarized_title: str | None


@dataclass
class HistoryBounds:
    """Overall event timing bounds for a chat history dump."""

    start: datetime
    end: datetime

    @property
    def total_ms(self) -> int:
        return max(int((self.end - self.start).total_seconds() * 1000), 1)


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp from chat history."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_history_dump(path: Path) -> dict[str, Any]:
    """Load a chat history dump, accepting slightly malformed JSON payloads."""
    text = path.read_text(encoding="utf-8")

    for strict in (True, False):
        try:
            return json.loads(text, strict=strict)
        except json.JSONDecodeError:
            continue

    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line, strict=False))
    return {"data": rows}


def summarize_tool_arguments(arguments: Any) -> str:
    """Return a compact single-line argument summary for chart labels."""
    if not isinstance(arguments, dict) or not arguments:
        return ""

    parts = []
    for value in arguments.values():
        text = str(value).replace("\n", " ").strip()
        if text:
            parts.append(text)
        if len(parts) >= 2:
            break
    return ", ".join(parts)


def truncate_label(label: str, limit: int) -> str:
    if len(label) <= limit:
        return label
    if limit <= 3:
        return label[:limit]
    return label[: limit - 3] + "..."


def build_history_bounds(rows: list[dict]) -> HistoryBounds | None:
    """Compute overall elapsed time across all timestamped events."""
    timestamps = [
        parse_timestamp(str(created_at))
        for row in rows
        if (created_at := row.get("createdAt"))
    ]
    if not timestamps:
        return None
    return HistoryBounds(start=min(timestamps), end=max(timestamps))


def _with_think_time(spans: list[ToolSpan], min_gap_ms: int = 5) -> list[ToolSpan]:
    """Insert synthetic think-time spans between non-overlapping steps."""
    if not spans:
        return spans

    step_bounds: list[tuple[int, datetime, datetime]] = []
    for step in sorted({span.step for span in spans}):
        step_spans = [span for span in spans if span.step == step]
        step_bounds.append((step, min(span.start for span in step_spans), max(span.end for span in step_spans)))

    extra_spans: list[ToolSpan] = []
    next_lane = max(span.lane for span in spans) + 1
    for (step, _step_start, step_end), (next_step, next_start, _next_end) in zip(step_bounds, step_bounds[1:]):
        gap_ms = int((next_start - step_end).total_seconds() * 1000)
        if gap_ms <= min_gap_ms:
            continue
        extra_spans.append(
            ToolSpan(
                lane=next_lane,
                step=next_step,
                name="thinkTime",
                call_id=f"think-{step}-to-{next_step}",
                start=step_end,
                end=next_start,
                duration_ms=gap_ms,
                offset_ms=0,
                label=f"think time (Step {step} -> Step {next_step})",
                arguments=None,
                title=None,
                summarized_title=None,
            )
        )

    if not extra_spans:
        return spans

    all_spans = spans + extra_spans
    first_start = min(span.start for span in all_spans)
    for span in all_spans:
        span.offset_ms = max(int((span.start - first_start).total_seconds() * 1000), 0)
    return sorted(all_spans, key=lambda span: (span.start, span.end, span.lane, span.call_id))


def build_tool_spans(
    rows: list[dict],
    *,
    include_think_time: bool = False,
    min_think_time_ms: int = 5,
) -> tuple[list[ToolSpan], datetime | None, datetime | None]:
    """Build timed tool spans and assign each to a visual lane."""
    pending: dict[str, dict[str, Any]] = {}
    tool_rows: list[tuple[datetime, datetime, str, str, str, dict[str, Any] | None, str | None, str | None]] = []
    current_title: str | None = None

    for row in rows:
        chunk_type = row.get("chunkType")
        call_id = row.get("callId")
        created_at = row.get("createdAt")
        if chunk_type == "model":
            result = row.get("result")
            if isinstance(result, dict):
                title = result.get("title")
                if isinstance(title, str) and title.strip():
                    current_title = title.strip()
        if not call_id or not created_at:
            continue

        timestamp = parse_timestamp(str(created_at))
        if chunk_type == "toolRequest":
            name = str(row.get("name", "tool"))
            arguments = row.get("arguments") if isinstance(row.get("arguments"), dict) else None
            args_summary = summarize_tool_arguments(arguments)
            label = f"{name}({args_summary})" if args_summary else name
            summarized_title = row.get("summarizedTitle")
            pending[call_id] = {
                "start": timestamp,
                "name": name,
                "label": label,
                "arguments": arguments,
                "title": current_title,
                "summarized_title": summarized_title.strip() if isinstance(summarized_title, str) else None,
            }
        elif chunk_type == "toolResponse" and call_id in pending:
            start_info = pending.pop(call_id)
            start = start_info["start"]
            end = timestamp if timestamp >= start else start
            tool_rows.append(
                (
                    start,
                    end,
                    start_info["name"],
                    call_id,
                    start_info["label"],
                    start_info["arguments"],
                    start_info["title"],
                    start_info["summarized_title"],
                )
            )

    if not tool_rows:
        return [], None, None

    tool_rows.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    first_start = min(item[0] for item in tool_rows)
    last_end = max(item[1] for item in tool_rows)
    lane_ends: list[datetime] = []
    current_step = 0
    current_step_end: datetime | None = None
    spans: list[ToolSpan] = []

    for start, end, name, call_id, label, arguments, title, summarized_title in tool_rows:
        if current_step_end is None or start >= current_step_end:
            current_step += 1
            current_step_end = end
        elif end > current_step_end:
            current_step_end = end

        lane = 0
        for idx, lane_end in enumerate(lane_ends):
            if lane_end <= start:
                lane = idx
                lane_ends[idx] = end
                break
        else:
            lane = len(lane_ends)
            lane_ends.append(end)

        spans.append(
            ToolSpan(
                lane=lane,
                step=current_step,
                name=name,
                call_id=call_id,
                start=start,
                end=end,
                duration_ms=max(int((end - start).total_seconds() * 1000), 0),
                offset_ms=max(int((start - first_start).total_seconds() * 1000), 0),
                label=label,
                arguments=arguments,
                title=title,
                summarized_title=summarized_title,
            )
        )

    if include_think_time:
        spans = _with_think_time(spans, min_gap_ms=min_think_time_ms)

    return spans, first_start, last_end


def format_duration_ms(duration_ms: int) -> str:
    seconds = duration_ms / 1000
    if seconds >= 60:
        minutes, rem = divmod(seconds, 60)
        return f"{int(minutes)}m{rem:05.2f}s"
    return f"{seconds:.3f}s"


def render_tool_gantt(
    data: dict[str, Any],
    width: int = 60,
    *,
    include_think_time: bool = False,
    min_think_time_ms: int = 5,
) -> str:
    """Render tool calls from a chat history dump as an ASCII Gantt chart."""
    rows = data.get("data", [])
    if not isinstance(rows, list):
        raise ValueError("Expected top-level 'data' list in chat history dump")

    history_bounds = build_history_bounds(rows)
    spans, first_start, last_end = build_tool_spans(
        rows,
        include_think_time=include_think_time,
        min_think_time_ms=min_think_time_ms,
    )
    if not spans or first_start is None or last_end is None:
        return "No completed tool calls found."

    total_ms = max(int((last_end - first_start).total_seconds() * 1000), 1)
    chart_width = max(width, 20)
    label_width = min(max(len(truncate_label(span.label, 40)) for span in spans), 40)
    axis_ticks = 5
    tick_positions = [round(idx * (chart_width - 1) / axis_ticks) for idx in range(axis_ticks + 1)]
    axis = [" "] * chart_width
    for pos in tick_positions:
        axis[pos] = "|"

    tick_labels = [" "] * chart_width
    for idx, pos in enumerate(tick_positions):
        label = format_duration_ms(round(total_ms * idx / axis_ticks))
        start_idx = min(max(pos - len(label) // 2, 0), max(chart_width - len(label), 0))
        for off, ch in enumerate(label):
            tick_labels[start_idx + off] = ch

    lines = [
        f"Timeline start: {first_start.isoformat()}",
        (
            f"Total time taken: {format_duration_ms(history_bounds.total_ms)} "
            f"({history_bounds.start.isoformat()} -> {history_bounds.end.isoformat()})"
            if history_bounds is not None
            else "Total time taken: unknown"
        ),
        (
            f"Total tool span: {format_duration_ms(total_ms)} across {max(span.step for span in spans)} step(s), "
            f"using {max(span.lane for span in spans) + 1} visual lane(s)"
        ),
        "".join(tick_labels),
        "".join(axis),
    ]

    for span in spans:
        row = [" "] * chart_width
        start_col = min((span.offset_ms * chart_width) // total_ms, chart_width - 1)
        end_col = max(((span.offset_ms + span.duration_ms) * chart_width) // total_ms, start_col + 1)
        end_col = min(end_col, chart_width)
        for idx in range(start_col, end_col):
            row[idx] = "#"
        if end_col - start_col == 1:
            row[start_col] = "*"
        else:
            row[start_col] = "["
            row[end_col - 1] = "]"

        label = truncate_label(span.label, label_width)
        lines.append(
            f"S{span.step} {label.ljust(label_width)}  {''.join(row)}  "
            f"+{format_duration_ms(span.offset_ms)} / {format_duration_ms(span.duration_ms)}"
        )

    return "\n".join(lines)
