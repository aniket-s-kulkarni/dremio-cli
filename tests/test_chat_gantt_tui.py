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
"""Tests for theme-aware chat Gantt TUI colors."""

from __future__ import annotations

from types import SimpleNamespace

from drs.chat_gantt_tui import _palette


def test_palette_defaults_to_dark_mode() -> None:
    palette = _palette(None)

    assert palette.label == "white"
    assert palette.panel_border == "bright_blue"


def test_palette_switches_for_light_theme() -> None:
    app = SimpleNamespace(current_theme=SimpleNamespace(dark=False))

    palette = _palette(app)

    assert palette.label == "black"
    assert palette.panel_border == "blue"
    assert palette.selection_border == "dark_green"
