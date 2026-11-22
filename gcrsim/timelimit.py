"""The time limit ``--max-time``: real (elapsed) time of the whole run, measured from the start of the program.

``parse_duration`` reads the value of the option (seconds, or a number with the suffix ``s``, ``m`` or ``h``), ``describe`` writes a
number of seconds back in that form, and ``Deadline`` is what the simulator checks while it works.
"""

from __future__ import annotations

import re
import time
from typing import Optional

from .errors import GcrsimError

_START = time.perf_counter()  # the start of the program; the command line renews it when it starts
_DURATION = re.compile(r"(\d+(?:\.\d*)?|\.\d+)([smh]?)")
_FACTOR = {"": 1.0, "s": 1.0, "m": 60.0, "h": 3600.0}


def mark_start() -> None:
    """Take now as the start of the program (the command line calls this first, so that loading the model is counted)."""
    global _START
    _START = time.perf_counter()


def program_start() -> float:
    return _START


def parse_duration(text: str) -> float:
    """The seconds of ``90``, ``90s``, ``1.5m`` or ``2h``: a positive number, with an optional suffix. Anything else is a
    ``GcrsimError``."""
    m = _DURATION.fullmatch(text.strip()) if isinstance(text, str) else None
    seconds = float(m.group(1)) * _FACTOR[m.group(2)] if m else 0.0
    if not m or not 0.0 < seconds < float("inf"):
        raise GcrsimError("bad time limit %r: give a positive number of seconds, or a number with the suffix s, m or h "
                          "(for example 90, 90s, 1.5m, 2h)" % (text,))
    return seconds


def describe(seconds: float) -> str:
    """A number of seconds as ``2h``, ``3m``, ``90s`` or ``0.5s``."""
    for suffix, size in (("h", 3600.0), ("m", 60.0)):
        if seconds >= size and (seconds / size) == int(seconds / size):
            return "%d%s" % (int(seconds / size), suffix)
    return ("%d" % seconds if seconds == int(seconds) else "%g" % seconds) + "s"


class Deadline:
    """A moment on the clock of time.perf_counter. ``Deadline(seconds)`` ends ``seconds`` after ``start`` (the start of the program unless
    given)."""

    __slots__ = ("seconds", "at")

    def __init__(self, seconds: float, start: Optional[float] = None):
        self.seconds = seconds
        self.at = (_START if start is None else start) + seconds

    def expired(self) -> bool:
        return time.perf_counter() >= self.at

    def __str__(self) -> str:
        return describe(self.seconds)
