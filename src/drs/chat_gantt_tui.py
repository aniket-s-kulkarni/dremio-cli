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
"""Textual UI for chat history Gantt visualization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.pretty import Pretty
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Header, Static

from drs.chat_gantt import (
    HistoryBounds,
    ToolSpan,
    build_history_bounds,
    build_tool_spans,
    extract_history_rows,
    format_duration_ms,
    load_history_dump,
    truncate_label,
)

LABEL_WIDTH = 32
MIN_BAR_WIDTH = 24
ROW_LABEL_WIDTH = 8
ROW_FIXED_WIDTH = 2 + ROW_LABEL_WIDTH + LABEL_WIDTH + 1 + 12


def _header_chart_width(viewport_width: int) -> int:
    """Choose a header chart width that follows the viewport size."""
    return max(viewport_width - 4, 40)


def _row_bar_width(viewport_width: int) -> int:
    """Choose a row bar width that fits within the current viewport."""
    return max(viewport_width - ROW_FIXED_WIDTH, MIN_BAR_WIDTH)


def _duration_color(duration_ms: int, total_ms: int) -> str:
    """Color bars by share of total tool span."""
    ratio = duration_ms / max(total_ms, 1)
    if ratio < 0.05:
        return "green"
    if ratio < 0.15:
        return "yellow"
    if ratio < 0.30:
        return "magenta"
    return "red"


def _span_marker(span: ToolSpan) -> tuple[str, str]:
    if span.failed:
        return "●", "red"
    if span.name == "thinkTime":
        return "•", "bright_black"
    return "●", "green"


def _tool_time_ms(spans: list[ToolSpan]) -> int:
    return sum(span.duration_ms for span in spans if span.name != "thinkTime")


def _think_time_ms(spans: list[ToolSpan]) -> int:
    return sum(span.duration_ms for span in spans if span.name == "thinkTime")


def _tool_call_count(spans: list[ToolSpan]) -> int:
    return sum(1 for span in spans if span.name != "thinkTime")


def _build_span_sections(span: ToolSpan, timeline: ToolTimeline) -> list[RenderableType]:
    body = Text()
    if span.name == "thinkTime":
        body.append("Tool: think time\n", style="dim")
    else:
        body.append(f"Tool: {span.name}\n", style="bold")
    if span.failed:
        body.append("Status: failed\n", style="bold red")
    elif span.name != "thinkTime":
        body.append("Status: success\n", style="green")
    if span.title:
        body.append(f"Title: {span.title}\n")
    if span.summarized_title:
        body.append(f"Summary: {span.summarized_title}\n")
    body.append(f"Step: {span.step}\n")
    body.append(f"Call ID: {span.call_id}\n")
    body.append(f"Start: {span.start.isoformat()}\n")
    body.append(f"End:   {span.end.isoformat()}\n")
    if span.name == "thinkTime":
        body.append(f"Think time: {format_duration_ms(span.duration_ms)}\n", style="dim")
    else:
        body.append(f"Offset: {format_duration_ms(span.offset_ms)}\n")
        body.append(f"Duration: {format_duration_ms(span.duration_ms)}\n")
    body.append(f"Label: {span.label}\n", style="dim" if span.name == "thinkTime" else "")
    body.append(
        f"Run total: {format_duration_ms(timeline.history_bounds.total_ms)} "
        f"({timeline.history_bounds.start.isoformat()} -> "
        f"{timeline.history_bounds.end.isoformat()})\n"
    )
    sections: list[RenderableType] = [body]
    if span.arguments:
        sections.extend([Text("\nArguments:", style="bold"), Pretty(span.arguments, expand_all=True)])
    else:
        body.append("Arguments: (none)\n")
    if span.error_message:
        sections.extend([Text("\nError:", style="bold red"), Pretty(span.error_message, expand_all=True)])
    return sections


@dataclass
class ToolTimeline:
    """Prepared tool timeline data for the TUI."""

    spans: list[ToolSpan]
    start: datetime
    end: datetime
    history_bounds: HistoryBounds

    @property
    def total_ms(self) -> int:
        return max(int((self.end - self.start).total_seconds() * 1000), 1)

    @property
    def lane_count(self) -> int:
        return max(span.lane for span in self.spans) + 1


def load_tool_timeline(path: Path) -> ToolTimeline:
    """Load and validate timeline data from a history dump."""
    data = load_history_dump(path)
    return load_tool_timeline_data(data)


def load_tool_timeline_data(
    data: dict,
    *,
    include_think_time: bool = False,
    min_think_time_ms: int = 5,
) -> ToolTimeline:
    """Load and validate timeline data from an in-memory history dump."""
    rows = extract_history_rows(data)
    history_bounds = build_history_bounds(rows)
    spans, start, end = build_tool_spans(
        rows,
        include_think_time=include_think_time,
        min_think_time_ms=min_think_time_ms,
    )
    if not spans or start is None or end is None or history_bounds is None:
        raise ValueError("No completed tool calls found.")
    return ToolTimeline(spans=spans, start=start, end=end, history_bounds=history_bounds)


class GanttChart(Static):
    """Fixed legend and time axis for the Gantt chart."""

    def __init__(self, timeline: ToolTimeline, **kwargs) -> None:
        super().__init__(**kwargs)
        self.timeline = timeline

    def render(self) -> RenderableType:
        width = _header_chart_width(self.size.width)
        chart_lines = []
        axis_ticks = 5
        tick_positions = [round(idx * (width - 1) / axis_ticks) for idx in range(axis_ticks + 1)]

        labels = [" "] * width
        markers = [" "] * width
        for idx, pos in enumerate(tick_positions):
            markers[pos] = "│"
            label = format_duration_ms(round(self.timeline.total_ms * idx / axis_ticks))
            start_idx = min(max(pos - len(label) // 2, 0), max(width - len(label), 0))
            for off, ch in enumerate(label):
                labels[start_idx + off] = ch

        chart_lines.append(Text("".join(labels), style="dim"))
        chart_lines.append(Text("".join(markers), style="dim"))
        legend = Text("Legend: ", style="bold")
        legend.append("● error  ", style="red")
        legend.append("● success  ", style="green")
        legend.append("■ think time  ", style="bright_black")
        legend.append("■ short (<5%)  ", style="green")
        legend.append("■ medium (5-15%)  ", style="yellow")
        legend.append("■ long (15-30%)  ", style="magenta")
        legend.append("■ very long (30%+)  ", style="red")
        legend.append("▶ selected", style="bold yellow")
        chart_lines.append(legend)

        body = Group(*chart_lines)
        subtitle = (
            f"{max(span.step for span in self.timeline.spans)} step(s)  "
            f"{format_duration_ms(self.timeline.total_ms)} tool span  "
            f"{format_duration_ms(self.timeline.history_bounds.total_ms)} total time  "
            "↑/↓ select  ←/→ pan  Enter details"
        )
        return Panel(body, title="Tool Timeline", subtitle=subtitle, border_style="blue")


class GanttRows(Static):
    """Scrollable tool rows for the Gantt chart."""

    selected_call_id: reactive[str | None] = reactive(None)

    def __init__(self, timeline: ToolTimeline, **kwargs) -> None:
        super().__init__(**kwargs)
        self.timeline = timeline

    def render(self) -> RenderableType:
        label_width = LABEL_WIDTH
        width = _row_bar_width(self.size.width)
        chart_lines = []

        for span in self.timeline.spans:
            bar = Text()
            start_col = min((span.offset_ms * width) // self.timeline.total_ms, width - 1)
            end_col = max(((span.offset_ms + span.duration_ms) * width) // self.timeline.total_ms, start_col + 1)
            end_col = min(end_col, width)
            color = "red" if span.failed else "bright_black" if span.name == "thinkTime" else _duration_color(span.duration_ms, self.timeline.total_ms)
            bar_style = f"bold {color}" if span.call_id == self.selected_call_id else color
            selected = span.call_id == self.selected_call_id
            line_style = "reverse bold" if selected else ""
            fill = [" "] * width
            for idx in range(start_col, end_col):
                fill[idx] = "█"
            if end_col - start_col == 1:
                fill[start_col] = "◆"
            marker, marker_style = _span_marker(span)
            bar.append(("▶ " if selected else "  "), style="bold yellow" if selected else "")
            bar.append(f"Step {span.step}".ljust(ROW_LABEL_WIDTH), style=f"bold {line_style}".strip())
            bar.append(f"{marker} ", style=f"{marker_style} {line_style}".strip())
            bar.append(truncate_label(span.label, label_width - 2).ljust(label_width), style=f"white {line_style}".strip())
            bar.append(" ", style=line_style)
            bar.append("".join(fill), style=bar_style)
            bar.append(f"  {format_duration_ms(span.duration_ms)}", style=f"dim {line_style}".strip())
            chart_lines.append(bar)

        return Group(*chart_lines)


class ChartViewport(ScrollableContainer):
    """Scrollable, focusable viewport for the Gantt chart."""

    can_focus = True
    BINDINGS: ClassVar = [
        ("up", "cursor_up", "Up"),
        ("down", "cursor_down", "Down"),
        ("left", "pan_left", "Pan Left"),
        ("right", "pan_right", "Pan Right"),
        ("enter", "open_details", "Details"),
    ]

    def action_cursor_up(self) -> None:
        self.app.action_cursor_up()

    def action_cursor_down(self) -> None:
        self.app.action_cursor_down()

    def action_pan_left(self) -> None:
        self.app.action_pan_left()

    def action_pan_right(self) -> None:
        self.app.action_pan_right()

    def action_open_details(self) -> None:
        self.app.action_open_details()


class ToolDetails(Static):
    """Details pane for the selected tool call."""

    def show_placeholder(self) -> None:
        self.update(
            Panel(
                Text("Select a Gantt row with ↑/↓ and press Enter to view details.", style="dim"),
                title="Selection",
                border_style="green",
            )
        )

    def show_span(self, span: ToolSpan) -> None:
        sections = _build_span_sections(span, self.app.timeline)
        self.update(Panel(Group(*sections), title="Selection", border_style="green"))


class ToolDetailModal(ModalScreen[None]):
    """Full-screen-ish modal for the selected tool span."""

    CSS = """
    ToolDetailModal {
        align: center middle;
    }
    #detail-modal {
        width: 88%;
        height: 88%;
        border: round $accent;
        background: $surface;
        padding: 1 2;
    }
    #detail-modal-body {
        height: 1fr;
        width: 1fr;
    }
    """

    BINDINGS: ClassVar = [
        ("escape", "dismiss_modal", "Close"),
        ("q", "dismiss_modal", "Close"),
        ("enter", "dismiss_modal", "Close"),
    ]

    def __init__(self, span: ToolSpan, timeline: ToolTimeline) -> None:
        super().__init__()
        self.span = span
        self.timeline = timeline

    def compose(self) -> ComposeResult:
        title = "Tool Call Details" if self.span.name != "thinkTime" else "Think Time Details"
        yield ScrollableContainer(
            Static(
                Panel(
                    Group(*_build_span_sections(self.span, self.timeline)),
                    title=title,
                    subtitle="Esc/Enter/q closes",
                    border_style="green" if not self.span.failed else "red",
                ),
                id="detail-modal-body",
            ),
            id="detail-modal",
        )

    def action_dismiss_modal(self) -> None:
        self.dismiss()


class ChatGanttApp(App[None]):
    """Interactive Textual app for browsing tool timing."""

    CSS = """
    Screen {
        layout: vertical;
    }
    #main {
        height: 1fr;
    }
    #table-pane {
        width: 48;
        min-width: 36;
    }
    #spans {
        height: 1fr;
    }
    #chart-scroll {
        height: 1fr;
        width: 1fr;
    }
    #chart-header-scroll {
        height: 6;
        width: 1fr;
    }
    #details {
        height: 12;
    }
    #summary {
        height: 7;
        min-height: 7;
    }
    """

    BINDINGS: ClassVar = [
        ("up", "cursor_up", "Up"),
        ("down", "cursor_down", "Down"),
        ("left", "pan_left", "Pan Left"),
        ("right", "pan_right", "Pan Right"),
        ("enter", "open_details", "Details"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, timeline: ToolTimeline) -> None:
        super().__init__()
        self.timeline = timeline
        self.selected_index = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main"):
            with Vertical(id="table-pane"):
                yield DataTable(id="spans")
                yield ToolDetails(id="details")
                yield Static(id="summary")
            with Vertical():
                with ScrollableContainer(id="chart-header-scroll"):
                    yield GanttChart(self.timeline, id="chart-header")
                with ChartViewport(id="chart-scroll"):
                    yield GanttRows(self.timeline, id="chart-rows")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#spans", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.can_focus = True
        table.add_columns("Step", "Tool", "Offset", "Duration")
        for span in self.timeline.spans:
            tool_cell: str | Text
            offset_cell: str | Text
            duration_cell: str | Text
            if span.name == "thinkTime":
                tool_cell = Text.assemble(("• ", "bright_black"), ("think time", "dim"))
                offset_cell = Text("", style="dim")
                duration_cell = Text(format_duration_ms(span.duration_ms), style="dim")
            else:
                marker, marker_style = _span_marker(span)
                tool_cell = Text.assemble((f"{marker} ", marker_style), (truncate_label(span.name, 22), "red" if span.failed else ""))
                offset_cell = format_duration_ms(span.offset_ms)
                duration_cell = Text(format_duration_ms(span.duration_ms), style="red" if span.failed else "")
            table.add_row(
                str(span.step),
                tool_cell,
                offset_cell,
                duration_cell,
                key=span.call_id,
            )
        details = self.query_one("#details", ToolDetails)
        details.show_placeholder()
        summary = self.query_one("#summary", Static)
        think_time_ms = _think_time_ms(self.timeline.spans)
        tool_time_ms = _tool_time_ms(self.timeline.spans)
        summary.update(
            Panel(
                Text(
                    "\n".join(
                        [
                            f"Think time: {format_duration_ms(think_time_ms) if think_time_ms else '0.000s'}",
                            f"Tool calls: {_tool_call_count(self.timeline.spans)}",
                            f"Tool time: {format_duration_ms(tool_time_ms)}",
                            f"Total time: {format_duration_ms(self.timeline.history_bounds.total_ms)}",
                        ]
                    )
                ),
                title="Summary",
                border_style="cyan",
            )
        )
        table.focus()
        self._highlight_selected_span()

    def action_cursor_up(self) -> None:
        if self.selected_index > 0:
            self.selected_index -= 1
            self._highlight_selected_span()

    def action_cursor_down(self) -> None:
        if self.selected_index < len(self.timeline.spans) - 1:
            self.selected_index += 1
            self._highlight_selected_span()

    def action_open_details(self) -> None:
        self.push_screen(ToolDetailModal(self.timeline.spans[self.selected_index], self.timeline))

    def action_pan_left(self) -> None:
        chart_header_scroll = self.query_one("#chart-header-scroll", ScrollableContainer)
        chart_scroll = self.query_one("#chart-scroll", ChartViewport)
        chart_header_scroll.scroll_relative(x=-12, animate=False)
        chart_scroll.scroll_relative(x=-12, animate=False)

    def action_pan_right(self) -> None:
        chart_header_scroll = self.query_one("#chart-header-scroll", ScrollableContainer)
        chart_scroll = self.query_one("#chart-scroll", ChartViewport)
        chart_header_scroll.scroll_relative(x=12, animate=False)
        chart_scroll.scroll_relative(x=12, animate=False)

    def _highlight_selected_span(self) -> None:
        span = self.timeline.spans[self.selected_index]
        chart_rows = self.query_one("#chart-rows", GanttRows)
        chart_rows.selected_call_id = span.call_id
        table = self.query_one("#spans", DataTable)
        table.move_cursor(row=self.selected_index, column=0)
        details = self.query_one("#details", ToolDetails)
        details.show_span(span)
        chart_scroll = self.query_one("#chart-scroll", ChartViewport)
        chart_scroll.scroll_to(y=max(self.selected_index, 0), animate=False, force=True)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.control.id != "spans" or event.cursor_row is None:
            return
        self.selected_index = event.cursor_row
        self._highlight_selected_span()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.control.id != "spans" or event.cursor_row is None:
            return
        self.selected_index = event.cursor_row
        self._highlight_selected_span()
        self.action_open_details()


def run_chat_gantt_tui(path: Path, *, include_think_time: bool = False, min_think_time_ms: int = 5) -> None:
    """Launch the Textual app for a history dump."""
    data = load_history_dump(path)
    timeline = load_tool_timeline_data(
        data,
        include_think_time=include_think_time,
        min_think_time_ms=min_think_time_ms,
    )
    ChatGanttApp(timeline).run()


def run_chat_gantt_tui_data(
    data: dict,
    *,
    include_think_time: bool = False,
    min_think_time_ms: int = 5,
) -> None:
    """Launch the Textual app for an in-memory history dump."""
    timeline = load_tool_timeline_data(
        data,
        include_think_time=include_think_time,
        min_think_time_ms=min_think_time_ms,
    )
    ChatGanttApp(timeline).run()
