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
"""Rich terminal renderer for Dremio AI Agent chat sessions."""

from __future__ import annotations

import json
import sys
import threading
from datetime import datetime
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

# Spinner frames for the "Thinking..." animation.
_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
_SPINNER_INTERVAL = 0.08


def extract_model_text(name: str, result: dict[str, Any]) -> str:
    """Extract the most useful user-facing text from a model result payload."""
    title = result.get("title")
    summary = result.get("summary")
    if isinstance(title, str) and title.strip() and isinstance(summary, str) and summary.strip():
        return f"{title}\n\n{summary}"

    for key in ("text", "response", "answer", "explanation", "sql_query", "plan", "title"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value

    if name == "modelRequestToolApproval":
        tool_requests = result.get("toolRequests")
        if isinstance(tool_requests, list) and tool_requests:
            titles: list[str] = []
            for request in tool_requests:
                if not isinstance(request, dict):
                    continue
                title = request.get("summarizedTitle") or request.get("name")
                if isinstance(title, str) and title.strip():
                    titles.append(title.strip())
            if titles:
                return "Tool approval required:\n" + "\n".join(f"- {title}" for title in titles)
        return "Tool approval required."

    if result:
        return json.dumps(result, indent=2, default=str)
    return ""


def _format_tool_result(result: Any, max_len: int | None = 500) -> str:
    """Return a readable tool result string with optional truncation."""
    if isinstance(result, dict):
        text = json.dumps(result, indent=2, default=str)
    elif isinstance(result, str):
        text = result
    else:
        text = str(result)

    if max_len is not None and len(text) > max_len:
        return text[:max_len] + "\n..."
    return text


def _parse_timestamp(value: str | None) -> datetime | None:
    """Parse ISO-8601 timestamps emitted by the chat API."""
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _format_timestamp(value: str | None) -> str:
    ts = _parse_timestamp(value)
    if ts is None:
        return ""
    return ts.strftime("%H:%M:%S")


def _format_duration_ms(duration_ms: float | None) -> str:
    if duration_ms is None:
        return ""
    if duration_ms < 1000:
        return f"{int(duration_ms)} ms"
    return f"{duration_ms / 1000:.2f}s"


class _Spinner:
    """A lightweight terminal spinner that does NOT use Rich's Live display.

    Rich's ``Status`` / ``Live`` captures all ``console.print()`` calls and
    renders them on its own refresh cycle, which can visually delay SSE events.
    This spinner writes its animation directly to *stderr* using ANSI escape
    codes so that ``console.print()`` output flows to the terminal immediately.
    """

    def __init__(self, message: str = "Thinking...") -> None:
        self._message = message
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=1.0)
        self._thread = None
        # Clear the spinner line
        sys.stderr.write("\r\033[K")
        sys.stderr.flush()

    def _run(self) -> None:
        idx = 0
        while not self._stop_event.is_set():
            frame = _SPINNER_FRAMES[idx % len(_SPINNER_FRAMES)]
            sys.stderr.write(f"\r{frame} {self._message}")
            sys.stderr.flush()
            idx += 1
            self._stop_event.wait(_SPINNER_INTERVAL)


class ChatRenderer:
    """Renders agent SSE events to a Rich console (interactive mode)."""

    def __init__(self, console: Console | None = None, show_tool_details: bool = False) -> None:
        self.console = console or Console()
        self._spinner: _Spinner | None = None
        self._show_tool_details = show_tool_details

    # -- Model output --

    def render_model_chunk(self, name: str, result: dict) -> None:
        """Render a model output chunk based on the task type."""
        text = extract_model_text(name, result)
        if not text:
            return

        if name == "modelGenerateSql":
            self.console.print(Syntax(text, "sql", theme="monokai", line_numbers=False))
        elif name == "modelReject":
            self.console.print(Text(text, style="bold yellow"))
        else:
            # modelGeneric, modelSqlAnswer, and others
            self.console.print(Markdown(text))

    # -- Tool events --

    def render_tool_request(
        self,
        call_id: str,
        name: str,
        arguments: dict | None = None,
        title: str | None = None,
        created_at: str | None = None,
    ) -> None:
        """Show a tool call request in a bordered panel."""
        display_name = title or name
        args_summary = ""
        if arguments:
            args_summary = _summarize_args(arguments)

        body_lines: list[str] = []
        if self._show_tool_details:
            formatted_time = _format_timestamp(created_at)
            if formatted_time:
                body_lines.append(f"Started: {formatted_time}")
        body_lines.append(args_summary or "(no arguments)")
        body = Text("\n".join(body_lines), style="dim")
        self.console.print(
            Panel(body, title=f"[bold cyan]Tool: {display_name}[/]", border_style="cyan", expand=False),
        )

    def render_tool_response(
        self,
        call_id: str,
        name: str,
        result: Any,
        created_at: str | None = None,
        duration_ms: float | None = None,
    ) -> None:
        """Show a tool result in a muted panel."""
        if self._show_tool_details:
            meta: list[str] = []
            formatted_time = _format_timestamp(created_at)
            formatted_duration = _format_duration_ms(duration_ms)
            if formatted_time:
                meta.append(f"Finished: {formatted_time}")
            if formatted_duration:
                meta.append(f"Duration: {formatted_duration}")
            text = _format_tool_result(result, max_len=None)
            if meta:
                text = "\n".join(meta) + "\n\n" + text
        else:
            text = _format_tool_result(result)

        self.console.print(
            Panel(Text(text, style="dim"), title=f"[dim]{name} result[/]", border_style="dim", expand=False),
        )

    def render_tool_progress(self, status: str, message: str) -> None:
        """Inline progress for long-running tools."""
        self.console.print(Text(f"  ⏳ {message}", style="dim italic"))

    # -- Errors --

    def render_error(self, error_type: str, message: str) -> None:
        """Red error display."""
        self.console.print(Text(f"Error ({error_type}): {message}", style="bold red"))

    # -- Conversation metadata --

    def render_conversation_title(self, title: str) -> None:
        """Show conversation title update."""
        self.console.print(Text(f"📝 {title}", style="bold"))

    # -- Spinner --

    def start_spinner(self) -> None:
        """Start an animated 'Thinking...' indicator."""
        if self._spinner is None:
            self._spinner = _Spinner()
            self._spinner.start()

    def stop_spinner(self) -> None:
        """Stop the spinner."""
        if self._spinner is not None:
            self._spinner.stop()
            self._spinner = None

    # -- Tool approval --

    def prompt_tool_approval(self, nonce: str, tools: list[dict]) -> dict:
        """Ask user Y/n for each pending tool call; return approval payload.

        Returns a dict suitable for the ``approvals`` field of the message body.
        """
        decisions: list[dict] = []
        for tool in tools:
            tool_name = tool.get("name", "unknown")
            tool_id = tool.get("executionId", tool.get("callId", tool.get("id", "")))
            args = tool.get("arguments", {})
            self.render_tool_request(tool_id, tool_name, args)
            try:
                answer = self.console.input(f"  Approve [bold cyan]{tool_name}[/]? [Y/n] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = "n"
            approved = answer in ("", "y", "yes")
            decisions.append(
                {
                    "executionId": tool_id,
                    "name": tool_name,
                    "arguments": args if isinstance(args, dict) else {},
                    "approved": approved,
                }
            )
        return {
            "approvalNonce": nonce,
            "toolDecisions": decisions,
        }

    # -- Separators --

    def print_separator(self) -> None:
        """Print a visual separator between exchanges."""
        self.console.print(Text("─" * 40, style="dim"))

    def print_welcome(self, conv_id: str | None = None) -> None:
        """Print welcome banner for interactive mode."""
        self.console.print(
            Panel(
                "[bold]Dremio AI Chat[/]\n"
                "Type a question or use /help for commands.\n"
                "Press [bold]Ctrl+D[/] or type [bold]/quit[/] to exit.",
                border_style="blue",
                expand=False,
            ),
        )
        if conv_id:
            self.console.print(Text(f"Resuming conversation: {conv_id}", style="dim"))

    def print_help(self) -> None:
        """Print slash command help."""
        help_text = (
            "[bold]Commands:[/]\n"
            "  /new          Start a new conversation\n"
            "  /list         List recent conversations\n"
            "  /continue <id> Resume a conversation by ID\n"
            "  /history      Show message history for current conversation\n"
            "  /cancel       Cancel the active run\n"
            "  /delete [id]  Delete current or specified conversation\n"
            "  /info         Show current conversation metadata\n"
            "  /quit         Exit (or Ctrl+D)"
        )
        self.console.print(Panel(help_text, border_style="blue", expand=False))


class PlainRenderer:
    """Non-interactive renderer.

    When stdout is a terminal, model output is rendered as Rich Markdown.
    When piped, plain text is written with no ANSI codes.
    Tool events and progress always go to stderr.
    """

    def __init__(self, show_tool_details: bool = False) -> None:
        self._is_tty = sys.stdout.isatty()
        self._console = Console() if self._is_tty else None
        self._stderr_console = Console(stderr=True, highlight=False)
        self._spinner: _Spinner | None = None
        self._show_tool_details = show_tool_details

    def render_model_chunk(self, name: str, result: dict) -> None:
        text = extract_model_text(name, result)
        if not text:
            return
        if self._console is not None:
            if name == "modelGenerateSql":
                self._console.print(Syntax(text, "sql", theme="monokai", line_numbers=False))
            elif name == "modelReject":
                self._console.print(Text(text, style="bold yellow"))
            else:
                self._console.print(Markdown(text))
        else:
            sys.stdout.write(text)
            sys.stdout.flush()

    def render_tool_request(
        self,
        call_id: str,
        name: str,
        arguments: dict | None = None,
        title: str | None = None,
        created_at: str | None = None,
    ) -> None:
        if self._show_tool_details:
            display_name = title or name
            header = f"  ⚙ {display_name}"
            formatted_time = _format_timestamp(created_at)
            if formatted_time:
                header += f" [{formatted_time}]"
            args_summary = _summarize_args(arguments) if arguments else "(no arguments)"
            self._stderr_console.print(
                Panel(Text(args_summary, style="dim"), title=header, border_style="cyan", expand=False),
            )
            return
        self._stderr_console.print(Text(f"  ⚙ {title or name}", style="dim cyan"))

    def render_tool_response(
        self,
        call_id: str,
        name: str,
        result: Any,
        created_at: str | None = None,
        duration_ms: float | None = None,
    ) -> None:
        if self._show_tool_details:
            header = f"  ✓ {name}"
            formatted_duration = _format_duration_ms(duration_ms)
            if formatted_duration:
                header += f" ({formatted_duration})"
            formatted_time = _format_timestamp(created_at)
            if formatted_time:
                header += f" [{formatted_time}]"
            self._stderr_console.print(
                Panel(
                    Text(_format_tool_result(result, max_len=None), style="dim"),
                    title=header,
                    border_style="dim",
                    expand=False,
                ),
            )
            return
        self._stderr_console.print(Text(f"  ✓ {name} done", style="dim"))

    def render_tool_progress(self, status: str, message: str) -> None:
        self._stderr_console.print(
            Text(f"  ⏳ {message}", style="dim italic"),
        )

    def render_error(self, error_type: str, message: str) -> None:
        self._stderr_console.print(
            Text(f"Error ({error_type}): {message}", style="bold red"),
        )

    def render_conversation_title(self, title: str) -> None:
        pass

    def start_spinner(self) -> None:
        if self._is_tty and self._spinner is None:
            self._spinner = _Spinner()
            self._spinner.start()

    def stop_spinner(self) -> None:
        if self._spinner is not None:
            self._spinner.stop()
            self._spinner = None

    def print_separator(self) -> None:
        sys.stdout.write("\n")
        sys.stdout.flush()


def _summarize_args(args: dict, max_len: int = 200) -> str:
    """Produce a compact summary of tool arguments."""
    parts: list[str] = []
    for k, v in args.items():
        s = str(v)
        if len(s) > 60:
            s = s[:57] + "..."
        parts.append(f"{k}={s}")
    text = ", ".join(parts)
    if len(text) > max_len:
        text = text[:max_len] + "..."
    return text
