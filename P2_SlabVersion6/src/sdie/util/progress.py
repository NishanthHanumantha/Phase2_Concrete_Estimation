"""Terminal progress reporting for long pipeline runs."""
from __future__ import annotations

import sys
from dataclasses import dataclass, field


@dataclass
class PipelineProgress:
    """Simple stage logger with an ASCII % progress bar."""

    enabled: bool = True
    width: int = 40
    pct: float = 0.0
    stage_name: str = ""
    _last_line_len: int = 0

    def stage(self, name: str, pct: float, detail: str = "") -> None:
        self.stage_name = name
        self.pct = min(100.0, max(self.pct, pct))
        self._emit(name, detail)

    def substep(
        self,
        current: int,
        total: int,
        name: str,
        *,
        base_pct: float,
        span_pct: float,
        detail: str = "",
    ) -> None:
        total = max(total, 1)
        frac = min(1.0, current / total)
        self.stage_name = name
        self.pct = min(100.0, base_pct + span_pct * frac)
        suffix = detail or f"{current}/{total}"
        self._emit(name, suffix)

    def complete(self, detail: str = "done") -> None:
        self.pct = 100.0
        self._emit("Complete", detail, newline=True)

    def _emit(self, name: str, detail: str, *, newline: bool = False) -> None:
        if not self.enabled:
            return
        filled = int(self.width * self.pct / 100.0)
        bar = "#" * filled + "-" * (self.width - filled)
        pct_str = f"{self.pct:5.1f}%"
        msg = f"[{bar}] {pct_str}  {name}"
        if detail:
            msg += f" - {detail}"
        pad = max(0, self._last_line_len - len(msg))
        line = msg + (" " * pad)
        end = "\n" if newline else "\r"
        sys.stderr.write(line + end)
        sys.stderr.flush()
        self._last_line_len = len(msg) if not newline else 0


_active: PipelineProgress | None = None
_NOOP = PipelineProgress(enabled=False)


def set_active(progress: PipelineProgress | None) -> PipelineProgress | None:
    global _active
    prev = _active
    _active = progress
    return prev


def progress_for(enabled: bool = True) -> PipelineProgress:
    if not enabled:
        return _NOOP
    global _active
    if _active is None:
        _active = PipelineProgress(enabled=True)
    return _active


def current_progress() -> PipelineProgress:
    return _active or _NOOP
