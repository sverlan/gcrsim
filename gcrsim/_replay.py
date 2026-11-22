"""Replay: check that a given sequence of forms is a derivation of a model.

A form is a string in a component. The check looks at each pair of consecutive forms and asks whether some rule of the
source component, with the target component of the second form, rewrites the first string into the second one (guards included).
It does not run the simulator, so the history, the length bounds, ``reject_strings``, the component filters, the filter
function and the marks play no part: a derivation that the simulator would drop is still a legal one here.

Components in the objects of this module count from 0, as everywhere in the package; in the input (``2: abc``) they count from 1.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from .errors import GcrsimError, ModelError, TimeLimitReached
from .model import Model, parse_model_file
from .lexicon import EMPTY
from .measures import Measures, measure, model_terminals
from .rules import Rule, edit_record
from .timelimit import Deadline
from .wordsep import check_word_sep

_FORM = re.compile(r"\s*(?:([0-9]+)\s*:)?(.*)", re.DOTALL)


class ReplayStep:
    """One legal step of a replay: ``source`` in component ``source_component`` became ``result`` in ``target_component``.

    ``rule``, ``start`` and ``end`` are the first rule (in the order of the model) and the span that give the step, and ``ways``
    is the number of (rule, span) pairs that give it. ``lines`` are the input lines of the two forms. ``source`` and ``result``
    have the real symbol names; ``internal_source`` and ``internal_result`` are the internal strings.

    The step is also described like a ``DerivationStep`` (see there): ``before`` and ``after`` (lists of symbols), ``removed`` and
    ``inserted`` (the symbols of the edit; ``start`` and ``end`` are positions in symbols) and ``provenance`` (the rule: ``line``,
    ``kind``, ``notation``, ``u``, ``x``, ``y``, ``v``, ``name``). ``to_dict`` gives the JSON form of ``--format jsonl``."""

    __slots__ = ("index", "lines", "source_component", "source", "target_component", "result", "rule", "start", "end", "ways",
                 "internal_source", "internal_result", "lexicon")

    def __init__(self, index, lines, source_component, source, target_component, result, rule, start, end, ways,
                 internal_source, internal_result, lexicon=None):
        self.index = index
        self.lines = lines
        self.source_component = source_component
        self.source = source
        self.target_component = target_component
        self.result = result
        self.rule = rule
        self.start = start
        self.end = end
        self.ways = ways
        self.internal_source = internal_source
        self.internal_result = internal_result
        self.lexicon = lexicon or EMPTY

    def _record(self) -> Dict[str, Any]:
        """The symbol data of the step (the one place where they are built), computed when asked for: a step holds only the
        internal strings, and every call gives new lists."""
        return edit_record(self.lexicon, self.rule, self.internal_source, self.start, self.end, self.internal_result)

    @property
    def before(self) -> List[str]:
        return self._record()["before"]

    @property
    def after(self) -> List[str]:
        return self._record()["after"]

    @property
    def removed(self) -> List[str]:
        return self._record()["removed"]

    @property
    def inserted(self) -> List[str]:
        return self._record()["inserted"]

    @property
    def provenance(self) -> Dict[str, Any]:
        return self.rule.provenance(self.lexicon)

    def to_dict(self) -> Dict[str, Any]:
        """The step as JSON-ready data (the ``derivation_step`` object of ``--format jsonl``): the fields of
        ``DerivationStep.to_dict`` (``step`` is the index) with ``lines`` and ``ways``. Components count from 1. The object that the
        command line writes also has ``type`` and the fields ``before_string`` and ``after_string``."""
        rec = self._record()
        return {
            "step": self.index,
            "lines": list(self.lines),
            "component": self.source_component + 1,
            "target": self.target_component + 1,
            "before": rec["before"],
            "after": rec["after"],
            "rule": rec["rule"],
            "start": self.start,
            "end": self.end,
            "removed": rec["removed"],
            "inserted": rec["inserted"],
            "ways": self.ways,
        }

    def __repr__(self) -> str:
        return "ReplayStep(index=%d, %r => %r, rule line %d, position %d, ways %d)" % (
            self.index, self.source, self.result, self.rule.line, self.start, self.ways)


class ReplayFailure:
    """The first form or transition that is not legal.

    ``step`` is the number of the step that failed (1 is the first pair of forms) or 0 when the first form is not an axiom.
    ``line`` is the input line of the form that is wrong: the second form of the pair, or the first form. ``target`` and
    ``target_component`` are None when the first form is not an axiom."""

    __slots__ = ("line", "step", "source_component", "source", "target_component", "target", "reason",
                 "internal_source", "internal_target")

    def __init__(self, line, step, source_component, source, target_component, target, reason, internal_source, internal_target):
        self.line = line
        self.step = step
        self.source_component = source_component
        self.source = source
        self.target_component = target_component
        self.target = target
        self.reason = reason
        self.internal_source = internal_source
        self.internal_target = internal_target

    def __repr__(self) -> str:
        return "ReplayFailure(step=%d, line=%d, %s)" % (self.step, self.line, self.reason)


class ReplayReport:
    """The result of a replay: ``ok``, the legal ``steps`` checked (a list of ``ReplayStep``), the ``failure`` (None when
    ``ok``), whether the first form was exempt from the axiom test (``fragment``) and the number of ``forms`` read. ``measures`` are the
    ``Measures`` of the steps checked (all the steps when ``ok``, otherwise the legal ones before the failure); None when the first form
    is not accepted (not an axiom) or was not read."""

    __slots__ = ("ok", "steps", "failure", "fragment", "forms", "first", "first_component", "terminals", "_measures")

    def __init__(self, ok: bool, steps: List[ReplayStep], failure: Optional[ReplayFailure], fragment: bool, forms: int,
                 first: Optional[str] = None, first_component: int = 0, terminals: Optional[str] = None):
        self.first = first  # the internal first form (None: not accepted)
        self.first_component = first_component
        self.terminals = terminals
        self._measures: Optional[Measures] = None
        self.ok = ok
        self.steps = steps
        self.failure = failure
        self.fragment = fragment
        self.forms = forms

    @property
    def measures(self) -> Optional[Measures]:
        if self._measures is None and self.first is not None:
            self._measures = measure(self.first, self.steps, self.terminals, self.first_component)
        return self._measures

    def __repr__(self) -> str:
        return "ReplayReport(ok=%r, steps=%d, failure=%r)" % (self.ok, len(self.steps), self.failure)


def _fail(where: str, line: int, message: str) -> GcrsimError:
    return GcrsimError("%s, line %d: %s" % (where, line, message))


def check_replay_word_sep(model: Model, word_sep: str) -> None:
    """``check_word_sep``, and in a replay file ``:`` marks the component, so a ``word_sep`` with a colon is refused."""
    if chr(10) in word_sep or chr(13) in word_sep:
        raise GcrsimError("word_sep %r cannot be used in a replay: it contains a line break" % word_sep)
    if ":" in word_sep:
        raise GcrsimError("word_sep %r cannot be used in a replay: ':' marks the component in the forms (N: WORD); "
                          "use another separator" % word_sep)
    check_word_sep(model, word_sep)


def model_word_sep(model: Model) -> str:
    """The ``word_sep`` written in the model's own ``[run]`` (only that setting is read, the others are not validated)."""
    value = model.config.get("word_sep", "")
    if not isinstance(value, str):
        raise GcrsimError("%s: 'word_sep' must be a string, not %r" % (model.path, value))
    return value


def read_word(model: Model, text: str, where: str = "<forms>", line: int = 1, word_sep: str = "") -> str:
    """The internal string of a word: symbols written together, or separated by white space or by ``word_sep``.

    A symbol outside the alphabet of the model, or a text with several readings, is a ``GcrsimError`` that names ``where``
    and ``line``."""
    lexicon = model.lexicon
    try:
        encoded = lexicon.encode_spaced(text, word_sep)
        lexicon.check(encoded, "the word")
    except ModelError as exc:
        raise _fail(where, line, str(exc)) from None
    return encoded


def parse_forms(model: Model, forms: Iterable[Union[str, Tuple[int, str]]], component: int = 1,
                where: str = "<forms>", word_sep: str = "",
                checked: bool = False) -> List[Tuple[int, int, str]]:
    """The forms as ``(line, component, internal string)`` triples (components from 0).

    An element of ``forms`` is a line of text, ``[N:] WORD`` (blank lines and lines whose first character that is not white
    space is ``#`` are skipped), or a pair ``(N, WORD)`` with the component counted from 1. The line number of a form is the
    position of its element, counted from 1. ``word_sep`` also separates the symbols of a word (see ``check_word_sep`` for
    what it may be)."""
    if not checked:
        check_replay_word_sep(model, word_sep)
    if not (1 <= component <= model.ncomp):
        raise GcrsimError("the component must be between 1 and %d, not %d" % (model.ncomp, component))
    out: List[Tuple[int, int, str]] = []
    for lineno, item in enumerate(forms, 1):
        if isinstance(item, str):
            text = item.rstrip("\r\n")
            if not text.strip() or text.lstrip().startswith("#"):
                continue
            m = _FORM.fullmatch(text)
            assert m is not None
            number = component
            if m.group(1) is not None:
                digits = m.group(1).lstrip("0") or "0"
                number = int(digits) if len(digits) <= 9 else 10 ** 9  # out of range, and no huge integer to convert
            word = m.group(2)
        else:
            try:
                number, word = item
                number = int(number)
            except (TypeError, ValueError):
                raise _fail(where, lineno, "a form is a line of text or a pair (component, word)") from None
        if not (1 <= number <= model.ncomp):
            shown = number if number < 10 ** 9 else "in the prefix"
            raise _fail(where, lineno, "the component %s does not exist (the model has %d)" % (shown, model.ncomp))
        out.append((lineno, number - 1, read_word(model, word, where, lineno, word_sep)))
    if not out:
        raise GcrsimError("%s: no forms" % where)
    return out


def matches(rules: Sequence[Rule], s: str, target: int, t: str) -> List[Tuple[Rule, int, int]]:
    """Every ``(rule, start, end)`` of ``rules`` (the rules of the source component) that rewrites ``s`` into ``t`` in the
    component ``target``, guards included. One pass over the rules; no result string is built unless it can be ``t``."""
    found: List[Tuple[Rule, int, int]] = []
    n, m = len(s), len(t)
    p = q = None  # the common prefix and suffix of s and t, found when the first candidate rule needs them
    for rule in rules:
        if rule.target != target or not rule.permits(s):
            continue
        for a, b, mid in rule.edits(s):
            if n - (b - a) + len(mid) != m:
                continue
            if p is None:
                p = _common_prefix(s, t)
                q = _common_suffix(s, t)
            assert q is not None
            if a <= p and n - b <= q and t[a:m - (n - b)] == mid:
                found.append((rule, a, b))
    return found


def _common_prefix(s: str, t: str) -> int:
    lo, hi = 0, min(len(s), len(t))
    while lo < hi:  # the longest k with s[:k] == t[:k]
        mid = (lo + hi + 1) // 2
        if s[:mid] == t[:mid]:
            lo = mid
        else:
            hi = mid - 1
    return lo


def _common_suffix(s: str, t: str) -> int:
    lo, hi = 0, min(len(s), len(t))
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if s[len(s) - mid:] == t[len(t) - mid:]:
            lo = mid
        else:
            hi = mid - 1
    return lo


def _timed_out(deadline: Deadline, step: int, steps: List[ReplayStep], what: str) -> TimeLimitReached:
    exc = TimeLimitReached(str(deadline), deadline.seconds, step, {}, what)
    exc.steps = steps  # type: ignore[attr-defined]  # the steps that were checked before the time ran out
    return exc


def check_forms(model: Model, forms: Sequence[Tuple[int, int, str]], fragment: bool = False,
                deadline: Optional[Deadline] = None) -> ReplayReport:
    """Check parsed forms (``(line, component, internal string)``, see ``parse_forms``) and report; stops at the first failure.
    A ``deadline`` (the time limit) is looked at between the steps: when it has passed, ``TimeLimitReached`` is raised."""
    decode = model.lexicon.decode
    steps: List[ReplayStep] = []
    line0, c0, s0 = forms[0]
    if not fragment and s0 not in model.axioms[c0]:
        failure = ReplayFailure(line0, 0, c0, decode(s0), None, None, "not an axiom of component %d" % (c0 + 1), s0, None)
        return ReplayReport(False, steps, failure, fragment, len(forms))
    first = (s0, c0, model_terminals(model))
    for k in range(1, len(forms)):
        if deadline is not None and deadline.expired():
            raise _timed_out(deadline, k, steps, "replay")
        line, d, t = forms[k]
        line_before, c, s = forms[k - 1]
        found = matches(model.rules[c], s, d, t)
        if not found:
            reason = "no rule of component %d gives this string in component %d" % (c + 1, d + 1)
            failure = ReplayFailure(line, k, c, decode(s), d, decode(t), reason, s, t)
            return ReplayReport(False, steps, failure, fragment, len(forms), *first)
        rule, a, b = found[0]
        steps.append(ReplayStep(k, (line_before, line), c, decode(s), d, decode(t), rule, a, b, len(found), s, t, model.lexicon))
    if deadline is not None and deadline.expired():  # a run whose time is up never reports success
        raise _timed_out(deadline, len(forms), steps, "replay-end")
    return ReplayReport(True, steps, None, fragment, len(forms), *first)


def replay(model: Union[Model, str, "os.PathLike[str]"], forms: Iterable[Union[str, Tuple[int, str]]], *, component: int = 1,
           fragment: bool = False, source: str = "<forms>", word_sep: Optional[str] = None) -> ReplayReport:
    """Check that ``forms`` is a derivation of ``model``.

    ``model`` is a ``Model`` or the path of a model file. ``forms`` are lines ``[N:] WORD`` or pairs ``(N, WORD)`` (see
    ``parse_forms``); a line without ``N:`` is in ``component`` (counted from 1). The first form must be an axiom unless
    ``fragment`` is true. ``source`` names the input in error messages. ``word_sep``, if not empty, separates the symbols of a word, as white space
    does (None: the setting of the model; an empty string: none); it must not occur in a symbol of the model. Input that cannot be read raises ``GcrsimError``;
    a derivation that is not legal is not an error: the report has ``ok == False`` and a ``failure``."""
    if not isinstance(model, Model):
        model = parse_model_file(os.fspath(model))
    if word_sep is None:
        word_sep = model_word_sep(model)
    return check_forms(model, parse_forms(model, forms, component, source, word_sep), fragment)


def _lines(text: str) -> List[str]:
    """Split at newlines only (``str.splitlines`` also splits at other characters, which would shift the line numbers)."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def read_lines(path: str, stdin: Any = None) -> List[str]:
    """The lines of a replay file (``-`` is the standard input, or ``stdin``)."""
    try:
        if path == "-":
            stream = sys.stdin if stdin is None else stdin
            data = getattr(stream, "buffer", stream).read()  # bytes, decoded as a file is
        else:
            with open(path, "rb") as fh:
                data = fh.read()
        if isinstance(data, bytes):
            data = data.decode("utf-8-sig")
        return _lines(data.replace("\r\n", "\n"))
    except OSError as exc:
        raise GcrsimError("cannot read the replay file %s: %s" % (path, exc.strerror or exc))
    except UnicodeDecodeError:
        raise GcrsimError("the replay file %s is not UTF-8 text" % ("standard input" if path == "-" else path))


def replay_file(model: Union[Model, str, "os.PathLike[str]"], path: str, *, component: int = 1, fragment: bool = False,
                word_sep: Optional[str] = None) -> ReplayReport:
    """``replay`` of the forms in the file ``path`` (``-`` for the standard input); errors name the file and the line."""
    if not isinstance(model, Model):
        model = parse_model_file(os.fspath(model))
    if word_sep is None:
        word_sep = model_word_sep(model)
    check_replay_word_sep(model, word_sep)  # before the input is read (the standard input is not touched for a bad separator)
    where = "standard input" if path == "-" else path
    forms = parse_forms(model, read_lines(path), component, where, word_sep, checked=True)
    return check_forms(model, forms, fragment)
