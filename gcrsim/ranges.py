r"""Ranges: ``[symbols.ranges]`` and the references ``{:X}`` that expand a declaration or a rule line into several.

A range is a finite inclusive interval of integers, declared as ``X = "1..3"``. A reference ``{:EXPR}`` is replaced by the value of
the integer expression ``EXPR`` (integers, the names of ranges, ``+``, ``-``, ``*``, ``%`` and parentheses; ``*`` needs a constant
operand, ``%`` a positive constant divisor). The expansion is a text stage that runs when a model is loaded, before the ordinary
parsing: the rest of the program never sees the syntax.

* In the symbol declarations (``alphabet``, ``lexemes``, ``terminals``, the classes) every word that has references stands for one word
  per combination of the ranges it uses; in an axiom, one axiom per combination; in a rule line, one rule per combination.
* The ranges of a line are bound in the order in which they first appear in it, the first one varying slowest.
"""

from __future__ import annotations

import itertools
import re
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple, Union

from .errors import ModelError

DEFAULT_MAX_EXPANDED = 100_000
MAX_DECLARED_WORDS = 1_000_000  # a sanity bound for the words that one declaration word may expand to (not the rule limit)
MAX_EXPRESSION = 300  # characters in a reference
MAX_DEPTH = 40  # nesting of parentheses and signs in a reference
MAX_DIGITS = 15
_WORD = re.compile(r"(?:\{:[^}]*\}|\S)+")
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_RANGE_VALUE = re.compile(r"\s*(0|[1-9][0-9]*)\s*\.\.\s*(0|[1-9][0-9]*)\s*")
_TOKEN = re.compile(r"[ \t]*(?:(?P<num>[0-9]+)|(?P<name>[A-Za-z_][A-Za-z0-9_]*)|(?P<op>[-+*%()]))")

Expr = Tuple[Any, ...]  # ("num", n), ("name", s), ("neg", e) or ("bin", op, left, right)
Ranges = Dict[str, Tuple[int, int]]
Part = Union[str, Expr]


class RangeFail(Exception):
    """An error in an expression or a declaration; the caller adds the file and the line."""


def read_ranges(table: Any, path: str) -> Ranges:
    """The ranges of ``[symbols.ranges]`` (``X = "1..3"``): name -> (first, last)."""
    if table is None:
        return {}
    if not isinstance(table, dict):
        raise ModelError("[symbols.ranges] must be a table of name = \"first..last\"", path)
    out: Ranges = {}
    for name, value in table.items():
        if not _NAME.fullmatch(name):
            raise ModelError("bad range name %r (letters, digits and underscore, not starting with a digit)" % name, path)
        m = _RANGE_VALUE.fullmatch(value) if isinstance(value, str) else None
        if m is None:
            raise ModelError("the range %s = %r must be written \"first..last\", for example \"1..3\" (non-negative integers)" % (name, value), path)
        if len(m.group(1)) > MAX_DIGITS or len(m.group(2)) > MAX_DIGITS:
            raise ModelError("the range %s = %r has a number with more than %d digits" % (name, value, MAX_DIGITS), path)
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo > hi:
            raise ModelError("the range %s = %r is empty: the first value is larger than the last" % (name, value), path)
        out[name] = (lo, hi)
    return out


# ---------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------


class _Parser:
    def __init__(self, text: str):
        self.text = text
        self.depth = 0
        if len(text) > MAX_EXPRESSION:
            raise RangeFail("a range reference of %d characters is too long (at most %d)" % (len(text), MAX_EXPRESSION))
        self.tokens: List[Tuple[str, str]] = []
        pos = 0
        text_s = text.rstrip(" \t")
        while pos < len(text_s):
            m = _TOKEN.match(text_s, pos)
            if m is None:
                raise RangeFail("unexpected character %r in {:%s}" % (text_s[pos:].lstrip()[:1], text))
            kind = m.lastgroup or ""
            self.tokens.append((kind, m.group(kind)))
            pos = m.end()
        self.i = 0

    def peek(self) -> Tuple[str, str]:
        return self.tokens[self.i] if self.i < len(self.tokens) else ("end", "")

    def take(self) -> Tuple[str, str]:
        tok = self.peek()
        self.i += 1
        return tok

    def parse(self) -> Expr:
        if not self.tokens:
            raise RangeFail("empty range reference {:}")
        e = self.expr()
        if self.peek()[0] != "end":
            raise RangeFail("unexpected %r in {:%s}" % (self.peek()[1], self.text))
        return e

    def expr(self) -> Expr:
        left = self.term()
        while self.peek() in (("op", "+"), ("op", "-")):
            op = self.take()[1]
            left = ("bin", op, left, self.term())
        return left

    def term(self) -> Expr:
        left = self.factor()
        while self.peek() in (("op", "*"), ("op", "%")):
            op = self.take()[1]
            right = self.factor()
            if op == "*" and not (_is_const(left) or _is_const(right)):
                raise RangeFail("{:%s}: '*' needs a constant operand (a product of two ranges is not allowed)" % self.text)
            if op == "%":
                if not _is_const(right):
                    raise RangeFail("{:%s}: '%%' needs a constant divisor" % self.text)
                if _eval(right, {}) <= 0:
                    raise RangeFail("{:%s}: the divisor of '%%' must be a positive constant" % self.text)
            left = ("bin", op, left, right)
        return left

    def factor(self) -> Expr:
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise RangeFail("{:%s}: too deeply nested" % self.text[:40])
        try:
            return self._factor()
        finally:
            self.depth -= 1

    def _factor(self) -> Expr:
        kind, val = self.take()
        if kind == "num":
            if len(val) > MAX_DIGITS:
                raise RangeFail("{:%s}: a number with more than %d digits (numbers up to %d digits are allowed)" % (self.text[:40], MAX_DIGITS, MAX_DIGITS))
            if len(val) > 1 and val[0] == "0":
                raise RangeFail("{:%s}: the number %s has a leading zero" % (self.text, val))
            return ("num", int(val))
        if kind == "name":
            return ("name", val)
        if kind == "op" and val == "(":
            e = self.expr()
            if self.take() != ("op", ")"):
                raise RangeFail("{:%s}: missing ')'" % self.text)
            return e
        if kind == "op" and val == "-":
            return ("neg", self.factor())
        raise RangeFail("{:%s}: a number, a range name or '(' is expected%s" % (self.text, "" if kind == "end" else " before %r" % val))


def _is_const(e: Expr) -> bool:
    return not _names(e)


def _names(e: Expr) -> List[str]:
    if e[0] == "name":
        return [e[1]]
    if e[0] == "neg":
        return _names(e[1])
    if e[0] == "bin":
        return _names(e[2]) + _names(e[3])
    return []


def _eval(e: Expr, env: Dict[str, int]) -> int:
    kind = e[0]
    if kind == "num":
        return e[1]
    if kind == "name":
        return env[e[1]]
    if kind == "neg":
        return -_eval(e[1], env)
    op, a, b = e[1], _eval(e[2], env), _eval(e[3], env)
    return a + b if op == "+" else a - b if op == "-" else a * b if op == "*" else a % b


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


class Template:
    """A text with references: its ``parts`` (literal strings and expressions) and the ``names`` of the ranges in the order of
    their first appearance."""

    __slots__ = ("parts", "names", "texts")

    def __init__(self, parts: List[Part], names: List[str], texts: List[str]):
        self.parts = parts
        self.names = names
        self.texts = texts  # the written form of each expression part, for messages


def parse_template(text: str, escape: bool = False) -> Template:
    """Split ``text`` at its references ``{:...}``. With ``escape`` a reference preceded by an odd number of backslashes is the
    literal text ``{:`` (the escape of a regular expression). Raises ``RangeFail`` (turned into a ``ModelError`` by the caller)."""
    parts: List[Part] = []
    texts: List[str] = []
    names: List[str] = []
    pos = 0
    start = 0
    while True:
        i = text.find("{:", pos)
        if i < 0:
            break
        if escape:
            j = i
            while j > 0 and text[j - 1] == "\\":
                j -= 1
            if (i - j) % 2 == 1:
                pos = i + 2
                continue
        end = text.find("}", i)
        if end < 0:
            raise RangeFail("a range reference {: is not closed with '}'")
        body = text[i + 2 : end]
        expr = _Parser(body).parse()
        parts.append(text[start:i])
        parts.append(expr)
        texts.append(body)
        for n in _names(expr):
            if n not in names:
                names.append(n)
        pos = start = end + 1
    parts.append(text[start:])
    return Template(parts, names, texts)


def parse_expression(body: str) -> Expr:
    """The expression written between ``{:`` and ``}``; raises ``RangeFail``."""
    return _Parser(body).parse()


def expression_names(expr: Expr) -> List[str]:
    """The names of the ranges in an expression."""
    return _names(expr)


def template_from_spans(text: str, spans: Sequence[Tuple[int, int]]) -> Template:
    """The template of ``text`` whose references are the given spans (each ``{:...}``, braces included)."""
    parts: List[Part] = []
    texts: List[str] = []
    names: List[str] = []
    pos = 0
    for a, b in spans:
        body = text[a + 2 : b - 1]
        expr = _Parser(body).parse()
        parts.append(text[pos:a])
        parts.append(expr)
        texts.append(body)
        for n in _names(expr):
            if n not in names:
                names.append(n)
        pos = b
    parts.append(text[pos:])
    return Template(parts, names, texts)


def split_words(text: str) -> List[str]:
    """The words of a declaration: separated by white space, except inside a reference ``{:...}``."""
    return _WORD.findall(text) if "{:" in text else text.split()


def check_declared(t: Template, ranges: Ranges) -> None:
    for n in t.names:
        if n not in ranges:
            raise RangeFail("the range %s is not declared (declare it in [symbols.ranges]: %s = \"1..3\")" % (n, n))


def size_of(t: Template, ranges: Ranges) -> int:
    total = 1
    for n in t.names:
        lo, hi = ranges[n]
        total *= hi - lo + 1
    return total


def instances(t: Template, ranges: Ranges) -> Iterator[Tuple[Dict[str, int], str]]:
    """The bindings (name -> value, in the order of the template's names) and the text for each combination, in the order of the
    bindings (the first name varies slowest)."""
    check_declared(t, ranges)
    spans = [range(ranges[n][0], ranges[n][1] + 1) for n in t.names]
    for combo in itertools.product(*spans):
        env = dict(zip(t.names, combo))
        out: List[str] = []
        k = 0
        for p in t.parts:
            if isinstance(p, str):
                out.append(p)
            else:
                v = _eval(p, env)
                if v < 0:
                    raise _Negative(t.texts[k], v, env)
                out.append(str(v))
                k += 1
        yield env, "".join(out)


class _Negative(RangeFail):
    def __init__(self, text: str, value: int, env: Dict[str, int]):
        super().__init__("{:%s} is %d for %s: a value cannot be negative" % (text, value, binding_text(env)))


def binding_text(env: Dict[str, int]) -> str:
    return ", ".join("%s=%d" % kv for kv in env.items())


def binding_suffix(bindings: Optional[Dict[str, int]]) -> str:
    """``[X=1,Y=2]``, or ``""`` for no bindings."""
    return "" if bindings is None else "[" + ",".join("%s=%d" % kv for kv in bindings.items()) + "]"


# ---------------------------------------------------------------------------
# The stages used by the model loader
# ---------------------------------------------------------------------------


def _fail(exc: RangeFail, path: str, lineno: Optional[int], what: str) -> ModelError:
    return ModelError("%s: %s" % (what, exc), path, lineno)


def expand_words(text: str, ranges: Ranges, limit: int, path: str, what: str, lineno: Optional[int] = None) -> str:
    """A declaration (``alphabet``, ``lexemes``, ``terminals``, a class): every word with references is replaced by its
    expansions, separated by spaces. A text without references is returned unchanged."""
    if "{:" not in text:
        return text
    out: List[str] = []
    for word in split_words(text):
        if "{:" not in word:
            out.append(word)
            continue
        out.extend(_expand_one(word, ranges, limit, path, what, lineno))
    return " ".join(out)


def expand_each(texts: Sequence[str], ranges: Ranges, limit: int, path: str, what: str, lineno: Optional[int] = None) -> List[str]:
    """A list of words (or axioms): every entry with references is replaced by its expansions, in place."""
    out: List[str] = []
    for text in texts:
        out.extend(_expand_one(text, ranges, limit, path, what, lineno) if "{:" in text else [text])
    return out


def _expand_one(text: str, ranges: Ranges, limit: int, path: str, what: str, lineno: Optional[int]) -> List[str]:
    try:
        t = parse_template(text)
        if not t.names and all(isinstance(p, str) for p in t.parts):
            return [text]
        check_declared(t, ranges)
        if size_of(t, ranges) > MAX_DECLARED_WORDS:
            raise RangeFail("%r would give more than %d words" % (text, MAX_DECLARED_WORDS))
        return [s for _, s in instances(t, ranges)]
    except RangeFail as exc:
        raise _fail(exc, path, lineno, what) from None
