from __future__ import annotations

import shutil
import sys
from threading import Event
from time import monotonic, sleep
from typing import Any

from mapchar.utils.formatters import format_size

_PROGRESS_UPDATE_INTERVAL = 0.1
_SPINNER_FRAMES = (
    "⠋",
    "⠙",
    "⠹",
    "⠸",
    "⠼",
    "⠴",
    "⠦",
    "⠧",
    "⠇",
    "⠏",
)


def _format_eta(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "--:--"

    total = int(seconds)
    mins, secs = divmod(total, 60)

    if mins >= 60:
        hours, mins = divmod(mins, 60)
        return f"{hours:02d}:{mins:02d}:{secs:02d}"

    return f"{mins:02d}:{secs:02d}"


def _render_progress_line(
    spinner: str,
    current: int,
    total: int,
    elapsed: float,
    width: int,
) -> str:
    if total <= 0:
        percent = 100.0
    else:
        percent = min((current / total) * 100.0, 100.0)

    speed = current / elapsed if elapsed > 0 else 0.0
    remaining = max(total - current, 0)
    eta = (remaining / speed) if speed > 0 else None

    full_line = (
        f"{spinner} "
        f"[{percent:>3.0f}%] "
        f"{format_size(current, d=2)} / {format_size(total, d=2)} @ "
        f"{format_size(speed, d=2)}/s "
        f"ETA {_format_eta(eta)}"
    )

    if len(full_line) <= width:
        return full_line

    return full_line[: max(0, width - 3)] + "..."


def get_progress(e: Event, r: Any, total: int = 100) -> None:
    """Display progress in the terminal."""
    stream = sys.stderr
    start = monotonic()
    frame_index = 0

    stream.write("\033[?25l")

    try:
        while not e.is_set():
            width, _ = shutil.get_terminal_size()
            current = min(int(getattr(r, "value", 0)), total)
            elapsed = monotonic() - start
            spinner = _SPINNER_FRAMES[frame_index % len(_SPINNER_FRAMES)]
            line = _render_progress_line(spinner, current, total, elapsed, width)
            stream.write("\r\033[2K" + line)
            stream.flush()
            frame_index += 1

            if current >= total:
                break

            sleep(_PROGRESS_UPDATE_INTERVAL)

    except KeyboardInterrupt:
        e.set()

    finally:
        stream.write("\033[?25h")
        stream.write("\r\033[2K")
        stream.flush()
