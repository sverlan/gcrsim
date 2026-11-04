"""Buffered output sink, configuration printing and content digests."""

from __future__ import annotations

import errno
import sys
import time
from typing import Any, Callable, Iterable, List, Optional, Sequence


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


class Output:
    """Buffered, ordered output sink that can stand in for ``sys.stdout``.

    Everything the simulator and the user callbacks print goes through one
    buffer, so callback output can never overtake earlier simulator output.
    Text is encoded as UTF-8.  The buffer
    is flushed at the end of every step and whenever it holds ``max_lines``
    pending writes; ``flush`` is also called before reading interactive input.
    """

    def __init__(
        self,
        stream: Any = None,
        max_items: int = 4096,
        flush_interval: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._stream = stream if stream is not None else sys.__stdout__
        self._buf: List[str] = []
        self._max_items = max_items
        self._interval = flush_interval
        self._clock = clock
        self._last_flush = clock()
        self._size = 0
        self.encoding = "utf-8"
        self.errors = "strict"
        self.broken = False
        self.decode: Optional[Callable[[str], str]] = None  # maps internal symbol codes back to names

    def write(self, text: str) -> int:
        self._buf.append(text)
        self._size += len(text)
        if (
            len(self._buf) >= self._max_items
            or self._size >= 1 << 20
            or (self._interval and self._clock() - self._last_flush >= self._interval)
        ):
            self.flush()
        return len(text)

    def text(self, s: str) -> str:
        """``s`` with internal symbol codes replaced by the real names (for messages)."""
        return self.decode(s) if self.decode is not None else s

    def flush(self) -> None:
        self._last_flush = self._clock()
        if self.broken:
            self._buf = []
            self._size = 0
            return
        data = "".join(self._buf)
        if self.decode is not None:
            data = self.decode(data)
        self._buf = []
        self._size = 0
        try:
            if data:
                binary = getattr(self._stream, "buffer", None)
                if binary is not None:
                    binary.write(data.encode("utf-8", "backslashreplace"))
                else:
                    self._stream.write(data)
            self._stream.flush()
        except OSError as exc:
            # a closed pipe is EPIPE on POSIX and EINVAL on Windows
            if isinstance(exc, BrokenPipeError) or exc.errno in (errno.EPIPE, errno.EINVAL):
                self.broken = True
                raise BrokenPipeError(errno.EPIPE, "output closed") from None
            raise

    def isatty(self) -> bool:
        return False

    def writable(self) -> bool:
        return True


def format_conf(
    contents: Sequence[Sequence[str]],
    print_hide: Optional[Callable[[str], Any]],
    print_max_len: Optional[int],
) -> Iterable[str]:
    """Yield the lines that describe the print filters in the header."""
    for m, comp in enumerate(contents):
        yield "\nComponent %d:\n" % (m + 1)
        if print_max_len is None:
            lines = comp if print_hide is None else [s for s in comp if not print_hide(s)]
        elif print_hide is None:
            lines = [s for s in comp if len(s) <= print_max_len]
        else:
            lines = [s for s in comp if len(s) <= print_max_len and not print_hide(s)]
        step = 50000
        for i in range(0, len(lines), step):
            yield "\n".join(lines[i : i + step]) + "\n"


def digest_contents(hasher: Any, step: int, contents: Sequence[Sequence[str]]) -> Any:
    """Feed one step's contents into ``hasher`` with unambiguous framing.

    For every component: ``step NUL component NUL count NUL`` followed by one
    ``length:bytes`` record per string, so equal digests mean equal ordered
    contents regardless of print filters.
    """
    for c, comp in enumerate(contents):
        hasher.update(("%d\0%d\0%d\0" % (step, c, len(comp))).encode("ascii"))
        for s in comp:
            b = s.encode("utf-8", "backslashreplace")
            hasher.update(b"%d:" % len(b) + b)
    return hasher
