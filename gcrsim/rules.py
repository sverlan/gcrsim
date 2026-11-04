r"""Rules: the rule forms and their single enumeration of edits.

Every rule is a function from a source string to a list of *edits* ``(start, end, replacement)``, in
increasing position.  A candidate is the source with ``s[start:end]`` replaced by ``replacement``.

* ``SubRule``: plain rewriting and ``ins`` / ``del`` / ``sub`` with literal contexts.  All of them are
  ``sub(u, y, x, v)``: ``y`` is replaced by ``x`` where ``u`` ends right before it and ``v`` starts right
  after it; the contexts stay.  A plain rule ``l -> r`` is ``sub("", l, r, "")``.
* ``SendRule``: ``send()``, the whole string unchanged (one edit that changes nothing).
* ``RegexRule``: ``re(pattern) -> rhs``, one match per start position.

Operands of the first two forms are sequences of items (a symbol, a set of symbols from a class, the
string boundaries ``{start}`` / ``{end}`` or ``{any}``); no regular expression is involved.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Iterator, List, Optional, Sequence, Tuple, Union
from .errors import ModelError
from .lexicon import SEP, EMPTY, Lexicon
from .pattern import compile_pattern

Edit = Tuple[int, int, str]


class _Marker:
    __slots__ = ("name",)

    def __init__(self, name: str):
        self.name = name

    def __repr__(self) -> str:
        return "{%s}" % self.name


START = _Marker("start")
END = _Marker("end")
ANY = _Marker("any")
Item = Union[str, frozenset, _Marker]

_REF = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_SYNTAX = frozenset("{},()")


# ---------------------------------------------------------------------------
# Operands of the plain forms
# ---------------------------------------------------------------------------


def parse_operand(text: str, lexicon: Lexicon, what: str) -> List[Item]:
    """A matching operand: symbols and ``{start}``, ``{end}``, ``{any}``, ``{CLASS}``."""
    if "->" in text:
        raise ModelError("%s %r contains '->'; write such rules with re(...)" % (what, text))
    items: List[Item] = []
    buf: List[str] = []

    def flush() -> None:
        if buf:
            items.extend(lexicon.encode("".join(buf)))
            del buf[:]

    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == "{":
            m = _REF.match(text, i)
            if m is None:
                raise ModelError("%s %r: '{' must start a class reference such as {start}" % (what, text))
            flush()
            name = m.group(1)
            if name == "start":
                items.append(START)
            elif name == "end":
                items.append(END)
            elif name == "any":
                items.append(ANY)
            else:
                items.append(lexicon.class_codes(name))
            i = m.end()
        elif c in _SYNTAX:
            raise ModelError(
                "%s %r: the character %r cannot be used in a plain rule (write the rule with re(...))" % (what, text, c)
            )
        else:
            buf.append(c)
            i += 1
    flush()
    return items


def parse_literal(text: str, lexicon: Lexicon, what: str) -> str:
    """A literal operand (right-hand side, inserted string, permit/forbid word): encoded symbols only."""
    for c in text:
        if c in _SYNTAX:
            raise ModelError(
                "%s %r: the character %r cannot be used in a plain rule (write the rule with re(...))" % (what, text, c)
            )
    if "->" in text:
        raise ModelError("%s %r contains '->'; write such rules with re(...)" % (what, text))
    return lexicon.encode(text)


def _check_alphabet(lexicon: Lexicon, encoded: str, what: str) -> None:
    if lexicon.alphabet is not None and encoded:
        lexicon.check(encoded, what)


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


class Rule:
    """Common part of all rules; subclasses implement ``edits``."""

    __slots__ = (
        "index",
        "line",
        "text",
        "source",
        "target",
        "lhs",
        "rhs",
        "permit",
        "forbid",
        "any_of",
        "guarded",
        "expand",
    )

    def __init__(
        self,
        index: int,
        line: int,
        text: str,
        source: int,
        target: int,
        lhs: str,
        rhs: str,
        permit: Sequence[str],
        forbid: Sequence[str],
        lexicon: Lexicon,
    ):
        self.index = index
        self.line = line
        self.text = text
        self.source = source
        self.target = target
        self.lhs = lhs.replace(SEP, "")  # the text as shown (the separator marks of the model text are dropped)
        self.rhs = rhs.replace(SEP, "")
        self.permit = tuple(parse_literal(w, lexicon, "permit word") for w in permit)
        self.forbid = tuple(parse_literal(w, lexicon, "forbid word") for w in forbid)
        for w in self.permit + self.forbid:
            _check_alphabet(lexicon, w, "a permit/forbid word of rule %r" % text)
        self.any_of: tuple = ()
        self.guarded = bool(self.permit or self.forbid)

    def add_any(self, words: Sequence[str], lexicon: Lexicon) -> None:
        """Add the ``permit-any`` condition: at least one of ``words`` occurs."""
        self.any_of = tuple(parse_literal(w, lexicon, "permit-any word") for w in words)
        for w in self.any_of:
            _check_alphabet(lexicon, w, "a permit-any word of rule %r" % self.text)
        self.guarded = True
        inner = self.expand
        any_words = self.any_of
        self.expand = lambda s: inner(s) if any(w in s for w in any_words) else ()

    def _finish(self, base: Callable[[str], Sequence[str]]) -> None:
        """Install ``expand``: ``base`` (a candidate builder) behind the permit/forbid check."""
        if not self.guarded:
            self.expand = base
            return
        permit_words = self.permit
        forbid_words = self.forbid

        def expand_guarded(s: str) -> Sequence[str]:
            for word in permit_words:
                if word not in s:
                    return ()
            for word in forbid_words:
                if word in s:
                    return ()
            return base(s)

        self.expand = expand_guarded

    def permits(self, s: str) -> bool:
        """The permit/forbid conditions hold for ``s``."""
        for word in self.permit:
            if word not in s:
                return False
        for word in self.forbid:
            if word in s:
                return False
        return not self.any_of or any(w in s for w in self.any_of)

    def edits(self, s: str) -> List[Edit]:  # pragma: no cover - implemented by subclasses
        raise NotImplementedError

    def edit_count(self, s: str) -> int:
        """How many edits ``edits(s)`` has, without building replacements that are costly to build."""
        return len(self.edits(s))

    @staticmethod
    def build(s: str, edits: Sequence[Edit]) -> List[str]:
        """The candidates for a list of edits."""
        return [s[:a] + mid + s[b:] for a, b, mid in edits]

    def spans(self, s: str) -> List[Tuple[int, int, str]]:
        """All edits as ``(start, end, result)``; used for tracing and tests."""
        return [(a, b, s[:a] + mid + s[b:]) for a, b, mid in self.edits(s)]

    def __repr__(self) -> str:
        return "%s(line %d: %s)" % (type(self).__name__, self.line, self.text)


def _step(item: Item, s: str, pos: int) -> int:
    """Position after matching ``item`` at ``pos``, or -1."""
    if item is START:
        return pos if pos == 0 else -1
    if item is END:
        return pos if pos == len(s) else -1
    if pos >= len(s):
        return -1
    if item is ANY:
        return pos + 1
    if isinstance(item, frozenset):
        return pos + 1 if s[pos] in item else -1
    return pos + 1 if s[pos] == item else -1


class SubRule(Rule):
    """``sub(u, y, x, v)``: replace ``y`` by ``x`` between ``u`` and ``v`` (plain rules, ins, del)."""

    __slots__ = ("U", "Y", "V", "x", "word", "a", "b")

    def __init__(
        self,
        index: int,
        line: int,
        text: str,
        source: int,
        target: int,
        lhs: str,
        rhs: str,
        permit: Sequence[str],
        forbid: Sequence[str],
        lexicon: Lexicon,
        u: str,
        y: str,
        x: str,
        v: str,
    ):
        super().__init__(index, line, text, source, target, lhs, rhs, permit, forbid, lexicon)
        self.U = parse_operand(u, lexicon, "context")
        self.Y = parse_operand(y, lexicon, "left-hand side")
        self.V = parse_operand(v, lexicon, "context")
        self.x = parse_literal(x, lexicon, "right-hand side")
        for item in self.U + self.Y + self.V:
            if isinstance(item, str):
                _check_alphabet(lexicon, item, "rule %r" % text)
        _check_alphabet(lexicon, self.x, "the right-hand side of rule %r" % text)
        if all(isinstance(item, str) for item in self.U + self.Y + self.V):
            self.word: Optional[str] = "".join(self.U + self.Y + self.V)  # type: ignore[arg-type]
            self.a = len(self.U)
            self.b = len(self.U) + len(self.Y)
        else:
            self.word = None
            self.a = self.b = 0
        self._finish(self._make_expand())

    def _make_expand(self) -> Callable[[str], Sequence[str]]:
        word, a, b, x = self.word, self.a, self.b, self.x
        if word is None:
            return lambda s: self.build(s, self._generic(s))
        if not word:

            def expand_everywhere(s: str) -> Sequence[str]:
                return [s[:i] + x + s[i:] for i in range(len(s) + 1)]

            return expand_everywhere
        find = str.find

        def expand_literal(s: str) -> Sequence[str]:
            i = find(s, word)
            if i < 0:
                return ()
            out = []
            append = out.append
            while i >= 0:
                append(s[: i + a] + x + s[i + b :])
                i = find(s, word, i + 1)
            return out

        return expand_literal

    def edit_count(self, s: str) -> int:
        if self.guarded and not self.permits(s):
            return 0
        word = self.word
        if word is None:
            return len(self._generic(s))
        if not word:
            return len(s) + 1
        count, find = 0, s.find
        i = find(word)
        while i >= 0:
            count += 1
            i = find(word, i + 1)
        return count

    def _generic(self, s: str) -> List[Edit]:
        """Match the item sequences at every start position (classes, boundaries, ``{any}``)."""
        U, Y, V, x = self.U, self.Y, self.V, self.x
        out: List[Edit] = []
        for i in range(len(s) + 1):
            pos = i
            for item in U:
                pos = _step(item, s, pos)
                if pos < 0:
                    break
            else:
                start = pos
                for item in Y:
                    pos = _step(item, s, pos)
                    if pos < 0:
                        break
                else:
                    end = pos
                    for item in V:
                        pos = _step(item, s, pos)
                        if pos < 0:
                            break
                    else:
                        out.append((start, end, x))
        return out

    def edits(self, s: str) -> List[Edit]:
        if self.guarded and not self.permits(s):
            return []
        word = self.word
        if word is None:
            return self._generic(s)
        if not word:
            return [(i, i, self.x) for i in range(len(s) + 1)]
        a, b, x = self.a, self.b, self.x
        out: List[Edit] = []
        i = s.find(word)
        while i >= 0:
            out.append((i + a, i + b, x))
            i = s.find(word, i + 1)
        return out


class SendRule(Rule):
    """``send()``: the whole string, unchanged."""

    __slots__ = ()

    def __init__(self, index, line, text, source, target, permit, forbid, lexicon):
        super().__init__(index, line, text, source, target, "send()", "", permit, forbid, lexicon)
        self._finish(lambda s: [s])

    def edits(self, s: str) -> List[Edit]:
        return [(0, 0, "")] if self.permits(s) else []


# -- regular-expression rules ----------------------------------------------------------------


def _matches(search: Callable[..., Any], s: str) -> Iterator["re.Match[str]"]:
    """One match per start position: every occurrence counts, overlapping ones included.

    ``search(s, pos)`` returns the leftmost match starting at or after ``pos``;
    the next search starts one position after that match started.  At most
    ``len(s) + 1`` matches.
    """
    pos = 0
    n = len(s)
    while pos <= n:
        m = search(s, pos)
        if m is None:
            return
        yield m
        pos = m.start() + 1


_GROUP_REF = re.compile(r"<([A-Za-z_][A-Za-z0-9_]*|[0-9]+)>")
_HEX = "0123456789abcdefABCDEF"


def _compile_rhs(rhs: str, pattern: "re.Pattern[str]", lexicon: Lexicon = EMPTY) -> List[Any]:
    r"""Compile the right-hand side of a ``re(...)`` rule: literal text with escapes.

    ``\N`` (one digit 1-9) and ``\g<N>`` / ``\g<name>`` insert a captured group, ``\\`` is a backslash,
    ``\xHH`` and ``\uXXXX`` are code points.  Everything else is literal.  Returns literal strings and
    group numbers.
    """
    parts: List[Any] = []
    buf: List[str] = []
    i = 0
    n = len(rhs)
    groups = pattern.groups
    while i < n:
        ch = rhs[i]
        if ch != "\\":
            buf.append(ch)
            i += 1
            continue
        if i + 1 >= n:
            raise ModelError("a right-hand side cannot end with a single backslash (write two for one)")
        nxt = rhs[i + 1]
        if nxt == "\\":
            buf.append("\\")
            i += 2
            continue
        if nxt in "xu":
            width = 2 if nxt == "x" else 4
            digits = rhs[i + 2 : i + 2 + width]
            if len(digits) != width or any(d not in _HEX for d in digits):
                raise ModelError("bad \\%s escape in a right-hand side (expected %d hex digits)" % (nxt, width))
            ch = chr(int(digits, 16))
            if lexicon.is_internal(ch):
                raise ModelError("the code point U+%04X is reserved for a lexeme of this model" % ord(ch))
            buf.append(ch)
            i += 2 + width
            continue
        if nxt in "123456789":
            num = int(nxt)
            i += 2
        elif nxt == "g":
            m = _GROUP_REF.match(rhs, i + 2)
            if m is None:
                raise ModelError("bad group reference in a right-hand side (expected \\g<N> or \\g<name>)")
            ref = m.group(1)
            if ref.isdigit():
                num = int(ref)
            elif ref in pattern.groupindex:
                num = pattern.groupindex[ref]
            else:
                raise ModelError("unknown group name %r in a right-hand side" % ref)
            i = m.end()
        else:
            raise ModelError("unknown escape \\%s in a right-hand side (write \\\\ for a backslash)" % nxt)
        if num > groups or num < 1:
            raise ModelError("the right-hand side refers to group %d, but the left-hand side has %d" % (num, groups))
        if buf:
            parts.append("".join(buf))
            buf = []
        parts.append(num)
    if buf:
        parts.append("".join(buf))
    return parts


class RegexRule(Rule):
    """``re(pattern) -> rhs``: a regular expression, one match per start position."""

    __slots__ = ("pattern", "parts", "const")

    def __init__(
        self,
        index: int,
        line: int,
        text: str,
        source: int,
        target: int,
        lhs: str,
        rhs: str,
        permit: Sequence[str],
        forbid: Sequence[str],
        lexicon: Lexicon,
    ):
        super().__init__(index, line, text, source, target, lhs, rhs, permit, forbid, lexicon)
        try:
            self.pattern = compile_pattern(lhs, lexicon)
        except (re.error, ValueError) as exc:
            raise ModelError("bad regular expression %r: %s" % (lhs, exc))
        parts = _compile_rhs(lexicon.encode_rhs(rhs), self.pattern, lexicon)
        merged: List[Any] = []
        for p in parts:
            if isinstance(p, str):
                _check_alphabet(lexicon, p, "the right-hand side of rule %r" % text)
            if merged and isinstance(p, str) and isinstance(merged[-1], str):
                merged[-1] += p
            else:
                merged.append(p)
        self.parts = merged
        self.const = "".join(merged) if all(isinstance(p, str) for p in merged) else None
        self._finish(self._make_expand())

    def _mid(self, m: "re.Match[str]") -> str:
        if self.const is not None:
            return self.const
        return "".join(p if p.__class__ is str else (m.group(p) or "") for p in self.parts)

    def _make_expand(self) -> Callable[[str], Sequence[str]]:
        search = self.pattern.search
        const = self.const
        if const is not None:
            return lambda s: [s[: m.start()] + const + s[m.end() :] for m in _matches(search, s)]
        parts = self.parts

        def expand_template(s: str) -> Sequence[str]:
            out = []
            for m in _matches(search, s):
                mid = "".join(p if p.__class__ is str else (m.group(p) or "") for p in parts)
                out.append(s[: m.start()] + mid + s[m.end() :])
            return out

        return expand_template

    def edits(self, s: str) -> List[Edit]:
        if self.guarded and not self.permits(s):
            return []
        return [(m.start(), m.end(), self._mid(m)) for m in _matches(self.pattern.search, s)]

    def edit_count(self, s: str) -> int:
        if self.guarded and not self.permits(s):
            return 0
        return sum(1 for _ in _matches(self.pattern.search, s))
