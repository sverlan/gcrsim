"""Declarative filters: component conditions and marks built from the configuration."""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from .errors import ConfigError, ModelError
from .lexicon import EMPTY, Lexicon
from .pattern import compile_pattern


_FILTER_KEYS = {"forbid", "require", "max_count"}
_DEFAULT_MESSAGE = object()  # sentinel: use the standard mark line


def _compile_expected_re(spec: Any, where: str, lexicon: Lexicon = EMPTY) -> Tuple[Callable[[str], Any], ...]:
    """Compile the ``expected_re`` part of a mark: regexes and/or predicates that mean 'this string is expected'."""
    if isinstance(spec, str) or callable(spec):
        items = [spec]
    elif isinstance(spec, (list, tuple)) and spec:
        items = list(spec)
    else:
        raise ConfigError("%s: 'expected_re' must be a regular expression, a function, or a list of them" % where)
    compiled: List[Callable[[str], Any]] = []
    for item in items:
        if isinstance(item, str):
            compiled.append(_compile_regex(item, "%s expected_re" % where, lexicon).search)
        elif callable(item):
            compiled.append(item if not lexicon.active else (lambda s, f=item: f(lexicon.decode(s))))
        else:
            raise ConfigError("%s: 'expected_re' entries must be regular expressions or functions, got %r" % (where, item))
    return tuple(compiled)


def _compile_marks(
    labels: Any, where: str, lexicon: Lexicon = EMPTY
) -> List[Tuple[str, Tuple["re.Pattern[str]", ...], Any, Tuple[Callable[[str], Any], ...]]]:
    """Compile one ``marks`` entry.

    ``{label: pattern | [patterns] | {"pattern": .., "message": .., "expected_re": ..}}``.  A string that
    matches a pattern is marked unless an ``expected_re`` regex matches it or an ``expected_re`` function
    returns true for it (the 'expected' strings).
    """
    if not isinstance(labels, dict) or not labels:
        raise ConfigError("%s must be a non-empty dict mapping labels to regular expressions" % where)
    compiled = []
    for label, spec in labels.items():
        if not isinstance(label, str) or not label:
            raise ConfigError("%s: labels must be non-empty strings, got %r" % (where, label))
        message: Any = _DEFAULT_MESSAGE
        expected_re: Tuple[Callable[[str], Any], ...] = ()
        if isinstance(spec, dict):
            unknown = set(spec) - {"pattern", "message", "expected_re", "expected"}
            if unknown or "pattern" not in spec:
                raise ConfigError(
                    "%s[%r]: expected keys 'pattern' and optionally 'message', 'expected', 'expected_re'" % (where, label)
                )
            if "expected_re" in spec:
                expected_re = _compile_expected_re(spec["expected_re"], "%s[%r]" % (where, label), lexicon)
            if "expected" in spec:
                strings = spec["expected"]
                if isinstance(strings, (str, bytes)) or not hasattr(strings, "__iter__"):
                    raise ConfigError("%s[%r]: 'expected' must be a collection of strings" % (where, label))
                strings = frozenset(strings)
                strings_enc = frozenset(lexicon.encode(x) for x in strings if isinstance(x, str))
                if not all(isinstance(s, str) for s in strings):
                    raise ConfigError("%s[%r]: 'expected' must contain only strings" % (where, label))
                expected_re = expected_re + (strings_enc.__contains__,)  # exact membership: the expected strings are not marked
            if "message" in spec:
                message = spec["message"]
                if message is not None:
                    if not isinstance(message, str):
                        raise ConfigError("%s[%r]: message must be a string or None" % (where, label))
                    try:  # fail now, not in the middle of a long run
                        message.format(string="", component=1, step=1, label=label)
                    except (KeyError, IndexError, ValueError) as exc:
                        raise ConfigError(
                            "%s[%r]: bad message template (fields: string, component, step, label): %s"
                            % (where, label, exc)
                        )
            spec = spec["pattern"]
        patterns = [spec] if isinstance(spec, str) else list(spec) if isinstance(spec, (list, tuple)) else None
        if not patterns or not all(isinstance(p, str) for p in patterns):
            raise ConfigError("%s[%r]: expected a regular expression or a list of them" % (where, label))
        compiled.append((label, tuple(_compile_regex(p, "%s[%r]" % (where, label), lexicon) for p in patterns), message, expected_re))
    return compiled


def _compile_regex(pattern: str, what: str, lexicon: Lexicon = EMPTY) -> "re.Pattern[str]":
    try:
        return compile_pattern(pattern, lexicon)
    except (re.error, ValueError) as exc:
        raise ConfigError("bad regular expression %r in %s: %s" % (pattern, what, exc))


def _test_of(item: Any, what: str, lexicon: Lexicon) -> Callable[[str], Any]:
    """A ``forbid`` or ``require`` entry as a test on the string: a regular expression is searched, a function is called
    (it sees the real symbol names and should depend only on the string, as the declarative filters do)."""
    if callable(item):
        return item if not lexicon.active else (lambda s, f=item: f(lexicon.decode(s)))
    if not isinstance(item, str):
        raise ConfigError("%s: an entry is a regular expression or a function, not %r" % (what, item))
    return _compile_regex(item, what, lexicon).search


def _build_check(specs: Sequence[Dict[str, Any]], lexicon: Lexicon = EMPTY) -> Optional[Callable[[str], bool]]:
    """Combine declarative conditions into one ``accept(s) -> bool`` function."""
    max_counts: List[Tuple[Tuple[str, ...], int]] = []   # (the symbols counted together, the limit)
    forbids: List[Callable[[str], Any]] = []     # each tells whether the string is rejected: a regular expression's search, or a function
    requires: List[Callable[[str], Any]] = []    # each tells whether the string is kept
    each: List[Tuple["re.Pattern[str]", int]] = []
    for spec in specs:
        unknown = set(spec) - _FILTER_KEYS
        if unknown:
            raise ConfigError("unknown filter key(s): %s" % ", ".join(sorted(map(str, unknown))))
        for lit, n in dict(spec.get("max_count", {})).items():
            if not lit:
                raise ConfigError("max_count needs non-empty symbols")
            if isinstance(n, dict) and lit == "re":  # max_count.re."p." = 2: every token matched by the pattern, separately
                for pat, limit in n.items():
                    rx = _compile_regex(pat, "filters max_count re", lexicon)
                    if rx.search(""):
                        raise ConfigError("max_count re pattern %r can match the empty string; use a nonempty token" % pat)
                    each.append((rx, int(limit)))
                continue
            if isinstance(n, dict):  # max_count.class.N = 2: the symbols of the class N are counted together
                if lit != "class":
                    raise ConfigError("max_count: only the keys 'class' and 're' can hold a table (got %r)" % lit)
                for name, limit in n.items():
                    try:
                        members = tuple(sorted(lexicon.class_codes(str(name))))
                    except ModelError as exc:
                        raise ConfigError("max_count class %s: %s" % (name, exc))
                    max_counts.append((members, int(limit)))
                continue
            if "{" in lit or "}" in lit:
                raise ConfigError("max_count %r: write a class as  class.NAME = n  (symbols have no braces)" % lit)
            max_counts.append(((lexicon.encode(lit),), int(n)))
        for pat in spec.get("forbid", ()):
            forbids.append(_test_of(pat, "filters forbid", lexicon))
        for pat in spec.get("require", ()):
            requires.append(_test_of(pat, "filters require", lexicon))
    if not (max_counts or forbids or requires or each):
        return None

    def accept(s: str) -> bool:
        for lits, n in max_counts:
            if (s.count(lits[0]) if len(lits) == 1 else sum(map(s.count, lits))) > n:
                return False
        for test in forbids:
            if test(s):
                return False
        for test in requires:
            if not test(s):
                return False
        for rx, n in each:
            counts: Dict[str, int] = {}
            for m in rx.finditer(s):
                tok = m.group(0)
                if not tok:
                    continue  # zero-width matches (lookaheads) are not tokens
                counts[tok] = counts.get(tok, 0) + 1
            if counts and max(counts.values()) > n:
                return False
        return True

    return accept
