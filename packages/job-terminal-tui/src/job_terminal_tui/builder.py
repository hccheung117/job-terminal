from __future__ import annotations

import re

from rich.markup import escape as _rich_escape


def _escape(msg: str) -> str:
    """Escape user text for embedding in Rich markup strings."""
    msg = msg.replace("&", "&amp;")
    escaped = _rich_escape(msg)
    return re.sub(r"(?<!\\)\[(?![a-z#/@])", r"\\[", escaped)


class TuiFormatter:
    """Pure string builder for job-terminal CLI output.

    The formatter returns Rich markup strings but never prints. Command layers
    are responsible for sending the rendered string to the terminal.
    """

    def __init__(self) -> None:
        self._lines: list[str] = []

    def header(self, msg: str) -> None:
        self._lines.append(f"\n{msg}")

    def info(self, msg: str, indent: int = 0) -> None:
        self._line("•", msg, indent=indent)

    def success(self, msg: str, indent: int = 0) -> None:
        self._line("[green]✓[/green]", msg, indent=indent)

    def error(self, msg: str, indent: int = 0) -> None:
        self._line("[red]✗[/red]", msg, indent=indent)

    def added(self, msg: str, indent: int = 0) -> None:
        self._line("[green]+[/green]", msg, indent=indent)

    def dropped(self, msg: str, indent: int = 0) -> None:
        self._line("[red]-[/red]", msg, indent=indent)

    def rejected_with_reason(self, msg: str, reason: str, indent: int = 0) -> None:
        self.error(msg, indent=indent)
        self._lines.append(f"{' ' * (indent + 2)}[dim]Reason: {_escape(reason)}[/dim]")

    @staticmethod
    def dim(msg: str) -> str:
        return f"[dim]{_escape(msg)}[/dim]"

    def render(self) -> str:
        return "\n".join(self._lines)

    def _line(self, prefix: str, msg: str, indent: int) -> None:
        self._lines.append(f"{' ' * indent}{prefix} {_escape(msg)}")
