r"""Shared regular-expression preprocessing for model rules and configuration.

One place decides how a user pattern becomes a compiled ``re`` pattern:

* ``$`` is always a literal symbol (``\A`` and ``\Z`` anchor the string);
* the verbose flag ``x`` is rejected, because ``#`` is an ordinary symbol and
  whitespace is not significant in a model.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Optional

from .errors import ConfigError
from .lexicon import EMPTY, Lexicon, _escape_end, comment_end

# The flags used for every user pattern.
FLAGS = 0  # Unicode semantics: text is UTF-8, one code point is one symbol


_FLAG_GROUP = re.compile(r"\(\?([aiLmsux]*)(?:-[imsx]*)?[:)]")


def inline_flags(pattern: str) -> str:
    """The inline flag letters a pattern turns on, e.g. ``(?i)`` or ``(?x:..)`` (escapes and classes are skipped)."""
    found = []
    i = 0
    n = len(pattern)
    in_class = False
    while i < n:
        c = pattern[i]
        if c == "\\":
            i = _escape_end(pattern, i)
            continue
        if in_class:
            if c == "]":
                in_class = False
            i += 1
            continue
        if c == "[":
            in_class = True
            i += 1
            if i < n and pattern[i] == "^":
                i += 1
            if i < n and pattern[i] == "]":
                i += 1
            continue
        if c == "(" and pattern.startswith("(?#", i):
            end = comment_end(pattern, i)
            i = n if end < 0 else end + 1
            continue
        if c == "(":
            m = _FLAG_GROUP.match(pattern, i)
            if m:
                found.append(m.group(1))
        i += 1
    return "".join(found)


def literal_dollar(pattern: str) -> str:
    r"""Escape every ``$`` that is not already escaped (backslash-parity scan).

    ``a$`` becomes ``a\$``; ``\$`` and ``[$AB]`` keep their meaning; ``a\\$`` (a
    backslash followed by ``$``) has its ``$`` escaped because the backslash
    before it is itself escaped.
    """
    if "$" not in pattern:
        return pattern
    out = []
    i = 0
    n = len(pattern)
    while i < n:
        ch = pattern[i]
        if ch == "\\" and i + 1 < n:
            out.append(pattern[i : i + 2])
            i += 2
            continue
        out.append("\\$" if ch == "$" else ch)
        i += 1
    return "".join(out)


def bare_dollar(pattern: str) -> bool:
    """True if ``pattern`` has a ``$`` outside a bracket class and not escaped (probably meant as an anchor)."""
    i, n = 0, len(pattern)
    while i < n:
        ch = pattern[i]
        if ch == "\\":
            i += 2
            continue
        if pattern.startswith("(?#", i):
            end = comment_end(pattern, i)
            i = n if end < 0 else end + 1
            continue
        if ch == "[":
            i += 1
            if i < n and pattern[i] == "^":
                i += 1
            if i < n and pattern[i] == "]":
                i += 1
            while i < n and pattern[i] != "]":
                i += 2 if pattern[i] == "\\" else 1
        elif ch == "$":
            return True
        i += 1
    return False


def compile_pattern(pattern: str, lexicon: Lexicon = EMPTY) -> "re.Pattern[str]":
    """Compile a user pattern (``$`` literal, verbose flag rejected).

    Raises ``re.error`` for a bad pattern and ``ValueError`` for the verbose flag.
    """
    lexicon.check_pattern_text(pattern)
    pattern = lexicon.encode_pattern(pattern)
    flags = inline_flags(pattern)
    if "x" in flags:
        raise ValueError("the verbose flag (?x) is not allowed: '#' is an ordinary symbol and spaces are ignored")
    if "i" in flags and lexicon.has_lexemes:
        raise ValueError("case-insensitive matching (?i) cannot be combined with lexemes")
    if not lexicon.dollar_used and bare_dollar(pattern):
        raise ValueError(
            "'$' is an ordinary symbol here, not an end anchor, and the model never uses it: "
            "write \\Z for the end (and \\A for the start), or \\$ if the symbol is meant"
        )
    return re.compile(literal_dollar(pattern), FLAGS)


_WS_RE = re.compile(r"\s+", re.ASCII)
_PLAIN_META = frozenset("\\.^|?*+()[]{}")


def _plain_regex(pattern: str) -> bool:
    """True if ``pattern`` is a regex that matches only itself, literally."""
    return not any(ch in _PLAIN_META for ch in pattern)


def make_matcher(pattern: Optional[str], lexicon: Lexicon = EMPTY) -> Optional[Callable[[str], Any]]:
    """Return a truthy-if-found callable for a user regex, or None for 'no skip'.

    An empty pattern means no skip here (Perl would silently reuse the last
    successful pattern for an empty ``$var`` pattern, which is not reproduced).
    """
    if pattern is None or pattern == "":
        return None
    if not lexicon.active and _plain_regex(pattern):
        return lambda s, p=pattern: p in s
    try:
        rx = compile_pattern(pattern, lexicon)
    except (re.error, ValueError) as exc:
        raise ConfigError("bad regular expression %r: %s" % (pattern, exc))
    return rx.search
