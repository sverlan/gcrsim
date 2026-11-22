"""The data formats of a run: ``csv`` and ``jsonl``. The other two outputs, ``text`` (the default) and ``perl`` (the layout of the original simulator), are written by the command
line itself.

* ``csv``: only the strings. A header row ``step,component,string`` (the separator is chosen by ``--csv-sep``; a tab by default; ``--csv-sep ,`` for commas),
  then one row per string; plain CSV, read by any CSV tool. Banners, marks and derivations go to the standard error stream. Every
  step but the last is complete; the exit status says if the run ended normally.
* ``jsonl`` (JSON Lines): one JSON object per line with a field ``type``: ``header`` (the run), ``step`` (all the strings of one
  step, so a complete line is a complete step), ``message`` (text of a mark, a callback), ``derivation`` (a traced derivation: the
  word, its component, the step where it appeared, the number of steps) followed by one ``derivation_step`` per step, ``end`` (the run is over,
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
    """What a format writes. ``write`` takes text, ``decode`` maps internal symbol codes back to names (for running text, which it
    never separates), ``show`` writes a string of symbols (with ``print_sep``; ``decode`` if not given), ``log`` is where the text
    that is not data goes when the format has no place for it."""

    name = ""

    def __init__(self, write: Callable[[str], Any], decode: Callable[[str], str], log: Callable[[str], Any],
                 show: Optional[Callable[[str], str]] = None):
        self._write = write
        self.decode = decode
        self.show = show or decode
        self._log = log

    def start(self, version: str, input_file: str, config: str, contents, skip, limit, description: str = "") -> None: ...
    def step(self, number: int, contents, skip, limit) -> None: ...
    def text(self, text: str) -> None:
        """Marks, derivations, callback output (whole lines)."""
        self._log(self.decode(text))
    def end(self, steps: int, status: int) -> None: ...


class Csv(Format):
    name = "csv"

    def __init__(self, write, decode, log, sep: str = "\t", show=None):
        super().__init__(write, decode, log, show)
        self.sep = sep

    def _rows(self, rows: List[List[Any]]) -> None:
        buffer = io.StringIO()
        csv.writer(buffer, delimiter=self.sep, lineterminator="\n").writerows(rows)
        self._write(buffer.getvalue())

    def start(self, version, input_file, config, contents, skip, limit, description="") -> None:
        self._rows([["step", "component", "string"]])
        self.step(0, contents, skip, limit)

    def step(self, number: int, contents, skip, limit) -> None:
        self._rows([[number, c + 1, self.show(s)] for c, comp in enumerate(visible(contents, skip, limit)) for s in comp])


class Jsonl(Format):
    """``decode`` and ``show`` are as in ``Format`` (``show`` writes a string with ``print_sep``: the ``*_string`` fields); ``tokens``
    splits an internal string into its symbols (the arrays)."""

    name = "jsonl"

    def __init__(self, write, decode, log, show=None, tokens=None, terminals=None):
        super().__init__(write, decode, log, show)
        self.tokens = tokens or (lambda s: [self.decode(ch) for ch in s])
        self.terminals = terminals  # the declared terminals (names) written in the header, or None

    def _line(self, obj: Dict[str, Any]) -> None:
        self._write(json.dumps(obj, ensure_ascii=False) + "\n")

    def record(self, obj: Dict[str, Any]) -> None:
        """One JSON object of another operation (the layout of every line is the same)."""
        self._line(obj)

    def derivation(self, word: str, component: int, found_at: int, chain: Sequence[Any], label: Optional[str] = None,
                   measures: Optional[Any] = None) -> None:
        """A derivation: a ``derivation`` object (the word as symbols and as text, its component counted from 1, the step where it appeared and
        the number of steps; ``mark`` is the label when the word is a mark; ``measures``: see ``Measures.to_dict``) and one ``derivation_step`` object per step."""
        head: Dict[str, Any] = {"type": "derivation", "word": self.tokens(word), "word_string": self.show(word), "component": component + 1, "found_at": found_at, "steps": len(chain)}
        if label is not None:
            head["mark"] = label
        if measures is not None:
            head["measures"] = measures.to_dict()
        self._line(head)
        for d in chain:
            self.derivation_step(d)

    def derivation_step(self, d: Any) -> None:
        """One step of a derivation (a ``DerivationStep``, or a ``ReplayStep`` with its ``lines`` and ``ways``): the same object
        in every operation."""
        obj: Dict[str, Any] = {"type": "derivation_step"}
        for key, value in d.to_dict().items():
            obj[key] = value
            if key == "before":
                obj["before_string"] = self.show(d.internal_source)
            elif key == "after":
                obj["after_string"] = self.show(d.internal_result)
        self._line(obj)

    def header(self, version: str, mode: str, input_file: str, config: str, description: str = "", **more: Any) -> None:
        self._line({"type": "header", "version": version, "mode": mode, "model": input_file, "configuration": config,
                    "description": description, "terminals": self.terminals, **more})

    def start(self, version, input_file, config, contents, skip, limit, description="") -> None:
        self.header(version, "run", input_file, config, description)
        self.step(0, contents, skip, limit)

    def step(self, number: int, contents, skip, limit) -> None:
        """The strings of a step as arrays of symbols (``components``) and as the text output prints them (``components_string``)."""
        vis = visible(contents, skip, limit)
        self._line({"type": "step", "step": number, "components": [[self.tokens(s) for s in comp] for comp in vis],
                    "components_string": [[self.show(s) for s in comp] for comp in vis]})

    def text(self, text: str) -> None:
        decoded = self.decode(text).rstrip("\n")
        if decoded:
            self._line({"type": "message", "text": decoded})

    def end(self, steps: int, status: int, **more: Any) -> None:
        self._line({"type": "end", "status": status, "steps": steps, **more})
