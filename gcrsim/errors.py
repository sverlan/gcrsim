"""Exception classes and their exit codes."""

from __future__ import annotations

from typing import Dict, Optional


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class GcrsimError(Exception):
    """Base class of all simulator errors; carries a process exit status."""

    exit_code = 2


class ModelError(GcrsimError):
    """A problem in a model file (reported with file name and line number)."""

    def __init__(self, message: str, path: Optional[str] = None, line: Optional[int] = None):
        self.path = path
        self.line = line
        where = ""
        if path is not None:
            where = "%s:%d: " % (path, line) if line else "%s: " % path
        super().__init__(where + message)


class ConfigError(GcrsimError):
    """A problem in a configuration file or setting."""


class TraceError(GcrsimError):
    """Trace-back is not possible (not enabled, lost, or string not found)."""


class CallbackError(GcrsimError):
    """The user's ``filter_next`` raised an exception."""


class LimitReached(GcrsimError):
    """A resource limit stopped the run; the last step is incomplete."""

    exit_code = 3

    def __init__(self, limit: str, value: int, step: int, counts: Dict[str, int]):
        self.limit = limit
        self.value = value
        self.step = step
        self.counts = counts
        detail = ", ".join("%s=%d" % kv for kv in sorted(counts.items()))
        if step == 0:
            super().__init__("limit %s=%d reached by the initial configuration (%s)" % (limit, value, detail))
        else:
            super().__init__(
                "limit %s=%d reached during step %d (%s); that step is incomplete "
                "and the results must not be compared with an unlimited run"
                % (limit, value, step, detail)
            )
