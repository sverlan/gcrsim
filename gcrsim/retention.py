"""Storage for the retained contents (trace-back): in memory, or in an SQLite file.

The simulator keeps the accepted content of every step when a derivation may be needed later. In memory this is a dict from the
step number to the list of contents (one list of strings per component). ``SqliteRetention`` has the same interface but keeps
the contents in a database file, one row per string; one step is loaded only when the trace-back reads it. It does not shrink
the history of seen strings, which stays in memory.

The table is ``strings(step, comp, idx, s)``: the string number ``idx`` (from 0, in content order) of component ``comp``
(from 0) at step ``step``. ``lexeme(code, name)`` maps the internal characters of multi-character symbols to their names and
``meta(key, value)`` holds the number of components.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Iterator, List, Optional


class SqliteRetention:
    """A mapping ``step -> list of contents`` stored in an SQLite database (the file is created empty on opening)."""

    def __init__(self, path: str):
        self.path = path
        if os.path.exists(path):
            os.remove(path)
        self._db = sqlite3.connect(path)
        self._db.execute(
            "CREATE TABLE strings (step INTEGER NOT NULL, comp INTEGER NOT NULL, idx INTEGER NOT NULL, s TEXT NOT NULL, "
            "PRIMARY KEY (step, comp, idx)) WITHOUT ROWID"
        )
        self._db.execute("CREATE TABLE lexeme (code TEXT PRIMARY KEY, name TEXT)")
        self._db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value INTEGER)")
        self._steps: set = set()
        self._ncomp: Optional[int] = None
        self._indexed = False

    @classmethod
    def open(cls, path: str) -> "SqliteRetention":
        """An existing retention file (it is not emptied)."""
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        self = cls.__new__(cls)
        self.path = path
        self._db = sqlite3.connect(path)
        self._steps = {r[0] for r in self._db.execute("SELECT DISTINCT step FROM strings")}
        row = self._db.execute("SELECT value FROM meta WHERE key = 'ncomp'").fetchone()
        self._ncomp = row[0] if row else 0
        self._indexed = False
        return self

    def set_lexicon(self, lexicon) -> None:
        """Store the lexemes so that a dump can show the real symbol names."""
        with self._db:
            self._db.executemany("INSERT OR REPLACE INTO lexeme VALUES (?, ?)", list(lexicon.names().items()))

    def __setitem__(self, step: int, contents: List[List[str]]) -> None:
        if self._ncomp is None:
            self._ncomp = len(contents)
            with self._db:
                self._db.execute("INSERT OR REPLACE INTO meta VALUES ('ncomp', ?)", (self._ncomp,))
        rows = [(step, comp, i, s) for comp, content in enumerate(contents) for i, s in enumerate(content)]
        with self._db:
            self._db.executemany("INSERT OR REPLACE INTO strings VALUES (?, ?, ?, ?)", rows)
        self._steps.add(step)

    def __getitem__(self, step: int) -> List[List[str]]:
        if step not in self._steps:
            raise KeyError(step)
        out: List[List[str]] = [[] for _ in range(self._ncomp or 0)]
        for comp, s in self._db.execute("SELECT comp, s FROM strings WHERE step = ? ORDER BY comp, idx", (step,)):
            out[comp].append(s)
        return out

    def get(self, step: int, default: Optional[List[List[str]]] = None) -> Optional[List[List[str]]]:
        return self[step] if step in self._steps else default

    def first_step(self, component: int, string: str) -> Optional[int]:
        """The earliest step whose content holds ``string`` in ``component`` (an index is built on first use)."""
        if not self._indexed:
            with self._db:
                self._db.execute("CREATE INDEX IF NOT EXISTS by_string ON strings (comp, s)")
            self._indexed = True
        row = self._db.execute("SELECT MIN(step) FROM strings WHERE comp = ? AND s = ?", (component, string)).fetchone()
        return row[0]

    def __contains__(self, step: object) -> bool:
        return step in self._steps

    def __iter__(self) -> Iterator[int]:
        return iter(sorted(self._steps))

    def __len__(self) -> int:
        return len(self._steps)

    def close(self) -> None:
        self._db.close()


def dump(path: str, step: Optional[int] = None, component: Optional[int] = None, write=print) -> int:
    """Print the retained contents of a file written with ``--retain-file`` (real symbol names); returns an exit status."""
    db = sqlite3.connect("file:%s?mode=ro" % path.replace("\\", "/"), uri=True)
    names = dict(db.execute("SELECT code, name FROM lexeme").fetchall())
    ncomp = db.execute("SELECT value FROM meta WHERE key = 'ncomp'").fetchone()
    ncomp = ncomp[0] if ncomp else 0

    def show(text: str) -> str:
        return "".join(names.get(ch, ch) for ch in text)

    steps = [r[0] for r in db.execute("SELECT DISTINCT step FROM strings ORDER BY step")]
    if step is None:
        write("%s: %d steps retained" % (path, len(steps)))
        for k in steps:
            counts = [0] * ncomp
            for comp, n in db.execute("SELECT comp, COUNT(*) FROM strings WHERE step = ? GROUP BY comp", (k,)):
                counts[comp] = n
            write("  step %d: strings per component %s" % (k, counts))
        return 0
    if step not in steps:
        write("step %d is not in the file" % step)
        return 2
    for comp in range(ncomp):
        if component is not None and comp + 1 != component:
            continue
        write("Component %d:" % (comp + 1))
        for (s,) in db.execute("SELECT s FROM strings WHERE step = ? AND comp = ? ORDER BY idx", (step, comp)):
            write(show(s))
    return 0


def _encode_by_table(db: sqlite3.Connection, text: str) -> str:
    """Replace the multi-character symbols of ``text`` by their internal characters (longest name first)."""
    table = sorted(((name, code) for code, name in db.execute("SELECT code, name FROM lexeme")), key=lambda t: (-len(t[0]), t[0]))
    out, i = [], 0
    while i < len(text):
        for name, code in table:
            if text.startswith(name, i):
                out.append(code)
                i += len(name)
                break
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def find(path: str, string: str, component: Optional[int] = None, write=print) -> int:
    """Print every step and component of the file that holds ``string`` (real symbol names); returns an exit status."""
    db = sqlite3.connect("file:%s?mode=ro" % path.replace("\\", "/"), uri=True)
    encoded = _encode_by_table(db, string)
    rows = db.execute("SELECT step, comp FROM strings WHERE s = ? ORDER BY step, comp", (encoded,)).fetchall()
    rows = [(k, c) for k, c in rows if component is None or c + 1 == component]
    if not rows:
        write("%r is not in the file" % string)
        return 2
    for k, c in rows:
        write("step %d, component %d" % (k, c + 1))
    return 0


def trace(path: str, model_path: str, string: str, component: int, write=print) -> int:
    """Print the derivation of ``string`` from the contents in a retention file; needs the model whose run wrote the file."""
    from .engine import Simulator, format_derivation
    from .errors import TraceError
    from .model import parse_model_file
    from .settings import settings_for_model

    model = parse_model_file(model_path)
    store = SqliteRetention.open(path)
    sim = Simulator(model, settings_for_model(model), write=lambda t: None, retain=True, retain_store=store)
    sim.step_no = max(store) if len(store) else 0
    try:
        steps = sim.trace(string, component - 1)
    except TraceError as exc:
        write("cannot trace: %s" % exc)
        return 2
    write("Trace of %r (component %d):" % (string, component))
    write(format_derivation(steps).rstrip("\n"))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="gcrsim-retention", description="Show a retention file written with --retain-file.")
    p.add_argument("file")
    p.add_argument("--step", type=int, help="print the strings of this step (default: a summary of all steps)")
    p.add_argument("--component", type=int, help="only this component (1-based; default 1 for --trace)")
    p.add_argument("--find", metavar="STRING", help="list the steps and components that hold this string")
    p.add_argument("--trace", metavar="STRING", help="print the derivation of this string (needs --model)")
    p.add_argument("--model", metavar="MODEL", help="the model file of the run that wrote FILE (for --trace)")
    args = p.parse_args(argv)
    if args.find is not None:
        return find(args.file, args.find, args.component)
    if args.trace is not None:
        if not args.model:
            p.error("--trace needs --model")
        return trace(args.file, args.model, args.trace, args.component or 1)
    return dump(args.file, args.step, args.component)
