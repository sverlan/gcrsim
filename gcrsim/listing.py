"""The data formats of a run: ``csv`` and ``jsonl``. The other two outputs, ``text`` (the default) and ``perl`` (the layout of the original simulator), are written by the command
line itself.

* ``csv``: only the strings. A header row ``step,component,string`` (the separator is chosen by ``--csv-sep``; a tab by default; ``--csv-sep ,`` for commas),
  then one row per string; plain CSV, read by any CSV tool. Banners, marks and derivations go to the standard error stream. Every
  step but the last is complete; the exit status says if the run ended normally.
* ``jsonl`` (JSON Lines): one JSON object per line with a field ``type``: ``header`` (the run), ``step`` (all the strings of one
  step, so a complete line is a complete step), ``message`` (text of a mark, a derivation, a callback), ``end`` (the run is over,
  with the number of steps and the status). A last line that cannot be parsed is an interrupted write and is dropped; a missing
  ``end`` line means that the run was interrupted.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Callable, Dict, List, Optional, Sequence

def separator(name: str) -> str:
    """A single character, or ``tab`` (a tab is awkward to type in a shell)."""
    if name == "tab":
        return "\t"
    if len(name) == 1:
        return name
    raise ValueError("a separator is a single character or `tab`, not %r" % name)


def visible(contents: Sequence[Sequence[str]], skip: Optional[Callable[[str], Any]], limit: Optional[int]) -> List[List[str]]:
    """The strings of each component that the print settings let through."""
    return [[s for s in comp if (limit is None or len(s) <= limit) and (skip is None or not skip(s))] for comp in contents]


class Format:
    """What a format writes. ``write`` takes text, ``decode`` maps internal symbol codes back to names, ``log`` is where the
    text that is not data goes when the format has no place for it."""

    name = ""

    def __init__(self, write: Callable[[str], Any], decode: Callable[[str], str], log: Callable[[str], Any]):
        self._write = write
        self.decode = decode
        self._log = log

    def start(self, version: str, input_file: str, config: str, contents, skip, limit, description: str = "") -> None: ...
    def step(self, number: int, contents, skip, limit) -> None: ...
    def text(self, text: str) -> None:
        """Marks, derivations, callback output (whole lines)."""
        self._log(self.decode(text))
    def end(self, steps: int, status: int) -> None: ...


class Csv(Format):
    name = "csv"

    def __init__(self, write, decode, log, sep: str = "\t"):
        super().__init__(write, decode, log)
        self.sep = sep

    def _rows(self, rows: List[List[Any]]) -> None:
        buffer = io.StringIO()
        csv.writer(buffer, delimiter=self.sep, lineterminator="\n").writerows(rows)
        self._write(buffer.getvalue())

    def start(self, version, input_file, config, contents, skip, limit, description="") -> None:
        self._rows([["step", "component", "string"]])
        self.step(0, contents, skip, limit)

    def step(self, number: int, contents, skip, limit) -> None:
        self._rows([[number, c + 1, self.decode(s)] for c, comp in enumerate(visible(contents, skip, limit)) for s in comp])


class Jsonl(Format):
    name = "jsonl"

    def _line(self, obj: Dict[str, Any]) -> None:
        self._write(json.dumps(obj, ensure_ascii=False) + "\n")

    def start(self, version, input_file, config, contents, skip, limit, description="") -> None:
        self._line({"type": "header", "version": version, "model": input_file, "configuration": config, "description": description})
        self.step(0, contents, skip, limit)

    def step(self, number: int, contents, skip, limit) -> None:
        shown = [[self.decode(s) for s in comp] for comp in visible(contents, skip, limit)]
        self._line({"type": "step", "step": number, "components": shown})

    def text(self, text: str) -> None:
        decoded = self.decode(text).rstrip("\n")
        if decoded:
            self._line({"type": "message", "text": decoded})

    def end(self, steps: int, status: int) -> None:
        self._line({"type": "end", "steps": steps, "status": status})
