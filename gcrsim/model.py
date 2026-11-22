r"""The model file: `Model` and `parse_model`.

A model is a TOML document in which the rules are lines::

    [symbols]               # how the text is read: alphabet or lexemes, [symbols.classes]
    alphabet = "a b p1 S"
    [model]                 # what is simulated: history, reject_*, [model.components.N.filters], [model.components.N.marks]
    [run]                   # how it is run and shown: steps, print_*, ...
    [axioms]
    1 = ["S"]               # component 1 holds S
    2 = ["", "a", "b c"]    # component 2 holds the empty string, a and the two symbols b c
    [rules]                 # general: [i,]lhs->rhs[,j]
    1,S->aS,2
    [rules.2]               # every rule here starts in component 2; the target is required
    S->Sb,1

A comment is a line whose first non-blank character is ``#``; elsewhere ``#`` is an
ordinary symbol.  Whitespace inside rule lines is ignored.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from .errors import ModelError
from .pattern import _WS_RE
from .lexicon import SEP, EMPTY, Lexicon, build_lexicon, comment_end
from .sections import flatten
from .rules import RegexRule, Rule, SendRule, SubRule
from .ranges import (DEFAULT_MAX_EXPANDED, RangeFail, Ranges, Template, binding_text, check_declared, expand_each, expand_words,
                     expression_names, instances, parse_expression, read_ranges, size_of)


class Model:
    """A parsed model: axioms per component, rules per component."""

    def __init__(
        self,
        axioms: List[List[str]],
        rules: List[List[Rule]],
        path: str = "<string>",
        lexicon: Lexicon = EMPTY,
        config: Optional[Dict[str, Any]] = None,
        ranges: Optional[Ranges] = None,
    ):
        self.axioms = axioms
        self.rules = rules
        self.path = path
        self.lexicon = lexicon
        self.config = {} if config is None else config
        self.ranges: Ranges = {} if ranges is None else ranges  # the declared ranges: name -> (first, last)

    @property
    def ncomp(self) -> int:
        return len(self.axioms)


_HEADER_RE = re.compile(r"\[[ \t]*([A-Za-z_][A-Za-z0-9_-]*)((?:[ \t]*\.[ \t]*[A-Za-z0-9_-]+)*)[ \t]*\][ \t]*(?:#.*)?")
_CLASS_REF = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_PREFIX_RE = re.compile(r"([0-9]*),")
_CLAUSE_START = re.compile(r";(?=(?:permit-any|permit|forbid|name):)")
_GUARD_START = re.compile(r";(?=(?:permit-any|permit|forbid):)")  # before the target only the conditions are recognized
_RAW_NAME = re.compile(r";\s*name\s*:(.*?)(?=;\s*(?:permit-any|permit|forbid|name)\s*:|$)", re.S)
_CLAUSE_KINDS = (";permit:", ";forbid:", ";permit-any:", ";name:")


def _check_name(name: str, path: str, lineno: int) -> str:
    """A rule name: a letter, then letters, digits, ``_``, ``-`` or ``.``."""
    shown = name.replace(SEP, " ")
    if name == "":
        raise ModelError("empty rule name in a name: clause", path, lineno)
    if not name[0].isalpha() or not all(ch.isalpha() or ch in "0123456789_-." for ch in name):
        raise ModelError(
            "bad rule name %r: a name is a letter followed by letters, digits, '_', '-' or '.'" % shown, path, lineno
        )
    return name


def _split_clauses(tail: str, path: str, lineno: int, marker: str = "") -> Tuple[List[str], List[str], List[str], Optional[str]]:
    """Parse ``;permit:w1,w2;forbid:w3;permit-any:w4,w5;name:N`` (the text after the target component)."""
    permit: List[str] = []
    forbid: List[str] = []
    any_of: List[str] = []
    name: Optional[str] = None
    for clause in _CLAUSE_START.split(tail)[1:]:
        kind, _, body = clause.partition(":")
        if kind == "name":
            if marker and marker in body:
                raise ModelError("a range reference cannot be used in the name of a rule: the values of the ranges are added to the "
                                 "name (grow[X=1])", path, lineno)
            if name is not None:
                raise ModelError("a rule has more than one name: clause", path, lineno)
            name = _check_name(body, path, lineno)
            continue
        words = body.split(",")
        if any(w == "" for w in words):
            raise ModelError("empty word in the %s list of a rule" % kind, path, lineno)
        {"permit": permit, "forbid": forbid, "permit-any": any_of}[kind].extend(words)
    return permit, forbid, any_of, name


def find_re_end(body: str, start: int) -> int:
    """Index of the ``)`` that closes the pattern of ``re(...)`` (``start`` is just after the opening parenthesis).

    Escapes, character classes and nested groups are skipped; returns -1 if the pattern is not closed.
    """
    i = start
    n = len(body)
    depth = 1
    while i < n:
        ch = body[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "[":
            i += 1
            if i < n and body[i] == "^":
                i += 1
            if i < n and body[i] == "]":
                i += 1  # a leading ] is a member of the class
            while i < n and body[i] != "]":
                i += 2 if body[i] == "\\" else 1
            i += 1
            continue
        if ch == "(":
            if body.startswith("(?#", i):
                end = comment_end(body, i)
                i = n if end < 0 else end + 1
                continue
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


_RE_HEAD = re.compile(r"\s*(?:\d*\s*,\s*)?re\s*\(")
_MARKED: Dict[str, Tuple[Any, Any, Any]] = {}


def _marked(marker: str) -> Tuple[Any, Any, Any]:
    """The patterns that read a component number, for a line in which the character ``marker`` stands for a range reference: it
    counts as a digit there. Without a marker these are the patterns of every ordinary line."""
    if not marker:
        return _RE_HEAD, _PREFIX_RE, re.compile(r"([0-9]*)(.*)", re.S)
    found = _MARKED.get(marker)
    if found is None:
        q = re.escape(marker)
        found = _MARKED[marker] = (re.compile(r"\s*(?:[\d%s]*\s*,\s*)?re\s*\(" % q), re.compile(r"([0-9%s]*)," % q),
                                   re.compile(r"([0-9%s]*)(.*)" % q, re.S))
    return found
_ESCAPED_WS = re.compile(r"(\\.)|\s+", re.S)
_NO_SEPARATOR_NEXT_TO = frozenset(",;:(){}")


def _squeeze(raw: str) -> str:
    """A line without white space; a space between two symbols stays as a separator mark (see ``lexicon.SEP``)."""
    pieces = raw.split()
    out = pieces[0] if pieces else ""
    for p, q in zip(pieces, pieces[1:]):
        arrow = p.endswith("->") or q.startswith("->") or (p[-1] == "-" and q[0] == ">")
        keep = not arrow and p[-1] not in _NO_SEPARATOR_NEXT_TO and q[0] not in _NO_SEPARATOR_NEXT_TO
        out += (SEP if keep else "") + q
    return out


def _strip_ws(raw: str, marker: str = "") -> str:
    """The line without whitespace; inside the pattern of ``re(...)`` an escaped space is kept."""
    head = _marked(marker)[0].match(raw)
    if head is None:
        return _squeeze(raw)
    end = find_re_end(raw, head.end())
    if end < 0:
        return _WS_RE.sub("", raw)
    pattern = _ESCAPED_WS.sub(lambda m: m.group(1) or "", raw[head.end() : end])
    return _WS_RE.sub("", raw[: head.end()]) + pattern + _WS_RE.sub("", raw[end:])


class _Form:
    """A parsed rule line, before the rule objects are built."""

    __slots__ = ("kind", "args", "src", "tgt", "permit", "forbid", "any_of", "name", "shown", "pattern")

    def __init__(self, kind, args, src, tgt, permit, forbid):
        self.pattern: Optional[Tuple[int, int]] = None  # the span of the pattern of a re(...) rule in the line
        self.kind = kind  # plain, ins, del, sub, send, re
        self.args = args  # raw operand texts
        self.src = src
        self.tgt = tgt
        self.permit = permit
        self.forbid = forbid
        self.any_of: List[str] = []
        self.name: Optional[str] = None
        self.shown = ""  # the rule line as shown (without the name clause)


def _after_target(rest: str, line: str, path: str, lineno: int, marker: str = "") -> Tuple[Optional[int], str]:
    """``rest`` is what follows a form: ``[,target][;permit:..][;forbid:..]``; returns (target, clauses)."""
    if not rest:
        return None, ""
    if not rest.startswith(","):
        raise ModelError("unexpected text after the rule in %r" % line, path, lineno)
    tm = _marked(marker)[2].match(rest[1:])
    digits, tail = tm.group(1), tm.group(2)
    if tail and not tail.startswith(_CLAUSE_KINDS):
        raise ModelError("unexpected text after the target component in rule %r" % line, path, lineno)
    if not digits:
        raise ModelError("a comma after the rule must be followed by the target component number in %r" % line, path, lineno)
    return _component_number(digits, line, path, lineno, marker), tail


MAX_COMPONENT = 10_000


def _component_number(digits: str, line: str, path: str, lineno: int, marker: str = "") -> int:
    if marker and marker in digits:
        return 1  # a range reference: the number is checked on each expanded line
    if len(digits.lstrip("0")) > 8:  # do not convert a huge number
        raise ModelError("a component number has too many digits (the limit is %d)" % MAX_COMPONENT, path, lineno)
    number = int(digits)
    if number > MAX_COMPONENT:
        raise ModelError("component number %d is larger than the limit %d (%r)" % (number, MAX_COMPONENT, line), path, lineno)
    return number


def _parse_rule(line: str, section: Optional[int], path: str, lineno: int, marker: str = "") -> _Form:
    """Parse one rule line; components are returned 0-based. ``marker`` is the character that stands for a range reference in a
    line that has them (see ``_analyse_rule``)."""
    src: Optional[int] = None
    pm = _marked(marker)[1].match(line)
    pattern: Optional[Tuple[int, int]] = None
    if pm:
        src = _component_number(pm.group(1), line, path, lineno, marker) if pm.group(1) else None
        body = line[pm.end() :]
    else:
        body = line
    tgt: Optional[int] = None
    clauses = ""
    if body.startswith("send()"):
        kind, args = "send", ()
        tgt, clauses = _after_target(body[6:], line, path, lineno, marker)
    elif body[:4] in ("ins(", "del(", "sub("):
        kind = body[:3]
        close = body.find(")")
        if close < 0:
            raise ModelError("missing ')' in rule %r" % line, path, lineno)
        args = tuple(body[4:close].split(","))
        if len(args) != (4 if kind == "sub" else 3):
            raise ModelError(
                "%s(...) takes %d comma-separated operands, got %d in rule %r"
                % (kind, 4 if kind == "sub" else 3, len(args), line),
                path,
                lineno,
            )
        tgt, clauses = _after_target(body[close + 1 :], line, path, lineno, marker)
    else:
        if body.startswith("re("):
            kind = "re"
            end = find_re_end(body, 3)
            if end < 0:
                raise ModelError("missing ')' in the pattern of rule %r" % line, path, lineno)
            lhs = body[3:end]
            offset = len(line) - len(body)
            pattern = (offset + 3, offset + end)
            if not body.startswith("->", end + 1):
                raise ModelError("re(...) must be followed by '->' in rule %r" % line, path, lineno)
            right = body[end + 3 :]
        else:
            kind = "plain"
            arrow = body.find("->")
            if arrow < 0:
                raise ModelError("cannot parse rule %r (expected [N,]lhs->rhs[,M])" % line, path, lineno)
            lhs, right = body[:arrow], body[arrow + 2 :]
        head, comma, tail = right.partition(",")
        if comma:
            tgt, clauses = _after_target("," + tail, line, path, lineno, marker)
        elif _GUARD_START.search(head):
            raise ModelError(
                "a ;permit: / ;forbid: / ;permit-any: / ;name: clause needs the target component before it (write ',N' after the right-hand side)",
                path,
                lineno,
            )
        args = (lhs, head)
    permit: List[str] = []
    forbid: List[str] = []
    any_of: List[str] = []
    name: Optional[str] = None
    if clauses:
        permit, forbid, any_of, name = _split_clauses(clauses, path, lineno, marker)
    if section is None:
        src = 1 if src is None else src
        tgt = 1 if tgt is None else tgt
    else:
        if src is not None and src != section:
            raise ModelError("rule %r is in section [rules.%d] but starts with component %d" % (line, section, src), path, lineno)
        src = section
        if tgt is None:
            raise ModelError(
                "a rule in [rules.%d] needs its target component (write ',N' after the rule)" % section, path, lineno
            )
    if src < 1 or tgt < 1:
        raise ModelError("component numbers start at 1 (rule %r)" % line, path, lineno)
    result = _Form(kind, args, src - 1, tgt - 1, permit, forbid)
    result.any_of = any_of
    result.name = name
    result.shown = line
    result.pattern = pattern
    if name is not None:  # the notation does not repeat the name
        keep = "".join(";" + c for c in _CLAUSE_START.split(clauses)[1:] if not c.startswith("name:"))
        result.shown = line[: len(line) - len(clauses)] + keep
    return result


def _mentions_dollar(text: str) -> bool:
    """A '$' written directly or by an escape (a hex or unicode escape of U+0024) in an operand or replacement."""
    return "$" in text or re.search(r"\\(?:x24|u0024|U00000024)", text, re.I) is not None


def make_rule(index: int, lineno: int, text: str, form: _Form, lexicon: Lexicon) -> Rule:
    """Build the rule object for a parsed line."""
    rule = _build_rule(index, lineno, text, form, lexicon)
    rule.kind = form.kind
    if form.any_of:
        rule.add_any(form.any_of, lexicon)
    rule.name = form.name
    return rule


def _build_rule(index: int, lineno: int, text: str, form: _Form, lexicon: Lexicon) -> Rule:
    kind, a = form.kind, form.args
    common = (index, lineno, text, form.src, form.tgt)
    if kind == "send":
        return SendRule(*common, form.permit, form.forbid, lexicon)
    if kind == "re":
        return RegexRule(*common, a[0], a[1], form.permit, form.forbid, lexicon)
    if kind == "plain":
        return SubRule(*common, a[0], a[1], form.permit, form.forbid, lexicon, "", a[0], a[1], "")
    shown = "%s(%s)" % (kind, ",".join(a))
    if kind == "ins":
        return SubRule(*common, shown, "", form.permit, form.forbid, lexicon, a[0], "", a[1], a[2])
    if kind == "del":
        return SubRule(*common, shown, "", form.permit, form.forbid, lexicon, a[0], a[1], "", a[2])
    return SubRule(*common, shown, "", form.permit, form.forbid, lexicon, a[0], a[1], a[2], a[3])  # sub


def _has_multiline_string(text: str) -> bool:
    """True if the TOML text opens a triple-quoted string (comments and ordinary strings are skipped)."""
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "#":
            end = text.find("\n", i)
            i = n if end < 0 else end
        elif ch in "\"'":
            if text.startswith(ch * 3, i):
                return True
            i += 1
            while i < n and text[i] != ch and text[i] != "\n":
                i += 2 if (ch == '"' and text[i] == "\\") else 1
            i += 1
        else:
            i += 1
    return False


def _axiom_strings(value: Any, number: int, path: str, lineno: int) -> List[str]:
    """The strings of one axiom entry ``N = ["s1", "s2"]``; a space between two symbols separates them."""
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ModelError(
            'the axioms of component %d must be a list of strings (for example %d = ["S", "a b"])' % (number, number),
            path,
            lineno,
        )
    return [SEP.join(v.split()) for v in value]


def _toml_part(text: str, path: str) -> Dict[str, Any]:
    import tomllib

    if _has_multiline_string(text):
        raise ModelError("multi-line strings are not allowed in a model", path)
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ModelError("%s" % exc, path) from None


_SECTION_HEADER = re.compile(r"\[[ \t]*rules[ \t]*(\.[^\]#]*)?\][ \t]*(?:#.*)?", re.I)


def _candidates(raw: str, path: str, lineno: int) -> List[Tuple[int, int]]:
    r"""The references ``{:...}`` of a rule line as ``(start, end)``. A ``{:`` after an odd number of backslashes is never a
    reference: it is left as written, so that the ordinary parser reads it (in the pattern of a ``re(...)`` rule it is the
    literal text ``{:``)."""
    out: List[Tuple[int, int]] = []
    i = raw.find("{:")
    while i >= 0:
        j = i
        while j > 0 and raw[j - 1] == "\\":
            j -= 1
        if (i - j) % 2 == 1:
            i = raw.find("{:", i + 2)
            continue
        end = raw.find("}", i)
        if end < 0:
            raise ModelError("a range reference {: is not closed with '}'", path, lineno)
        out.append((i, end + 1))
        i = raw.find("{:", end + 1)
    return out


def _marker(raw: str) -> str:
    """A character that is not in the line."""
    code = 0xE000
    while chr(code) in raw:
        code += 1
    return chr(code)


class _Analysed:
    """A rule line with references: its template (the stripped line with the references as expressions), the line as written (the
    notation of the source) and the name of the rule."""

    __slots__ = ("template", "source", "name")

    def __init__(self, template: Template, source: str, name: Optional[str]):
        self.template = template
        self.source = source
        self.name = name


def _name_error(path: str, lineno: int) -> ModelError:
    return ModelError("a range reference cannot be used in the name of a rule: the values of the ranges are added to the "
                      "name (grow[X=1])", path, lineno)


def _analyse_rule(raw: str, path: str, lineno: int) -> Optional[_Analysed]:
    r"""The analysis of a rule line that has range references, or None when it has none (a ``{:`` that is only the escaped literal
    text of a pattern). The line is read by the ordinary parser with one marker character in place of every reference, so the
    components, the pattern, the clauses and the name are found as in any rule line; then the markers are the places where the
    values go. ``\{:`` is literal only inside the pattern of a ``re(...)`` rule."""
    if "{:" not in raw:
        return None
    cands = _candidates(raw, path, lineno)
    if not cands:
        return None
    marker = _marker(raw)
    pieces: List[str] = []
    pos = 0
    for a, b in cands:
        pieces.append(raw[pos:a])
        pos = b
    pieces.append(raw[pos:])
    masked = marker.join(pieces)
    line = _strip_ws(masked, marker)
    form = _parse_rule(line, None, path, lineno, marker)
    if form.name is not None:
        found = _RAW_NAME.findall(masked)
        if marker in form.name or (found and marker in found[-1]):
            raise _name_error(path, lineno)
        if found:
            _check_name(found[-1].strip(), path, lineno)
    where = [i for i, c in enumerate(line) if c == marker]
    parts: List[Any] = []
    texts: List[str] = []
    names: List[str] = []
    last = 0
    for (a, b), at in zip(cands, where):
        parts.append(line[last:at])
        last = at + 1
        try:
            expr = parse_expression(raw[a + 2 : b - 1])
        except RangeFail as exc:
            raise ModelError(str(exc), path, lineno) from None
        parts.append(expr)
        texts.append(raw[a + 2 : b - 1])
        for n in expression_names(expr):
            if n not in names:
                names.append(n)
    parts.append(line[last:])
    shown = iter(raw[a:b] for a, b in cands)
    source = "".join(next(shown).replace(" ", "").replace("\t", "") if c == marker else c for c in form.shown)
    return _Analysed(Template(parts, names, texts), source.replace(SEP, " "), form.name)


class _Pending:
    """A rule line waiting for the model to be loaded: an ordinary rule (``form``) or a line with ranges (``template``)."""

    __slots__ = ("lineno", "shown", "form", "raw", "section", "bindings", "source", "origin")

    def __init__(self, lineno: int, shown: str, form: Optional[_Form], raw: Optional[str] = None, section: Optional[int] = None):
        self.lineno = lineno
        self.shown = shown
        self.form = form
        self.raw = raw  # a line that has "{:" and is read when the ranges are known
        self.section = section
        self.bindings: Optional[Dict[str, int]] = None
        self.source: Optional[str] = None
        self.origin = 0  # the index of the source line


def _with_binding(exc: ModelError, path: str, lineno: int, bindings: Dict[str, int]) -> ModelError:
    prefix = "%s:%d: " % (path, lineno)
    message = str(exc)
    if message.startswith(prefix):
        message = message[len(prefix) :]
    return ModelError("%s (expansion %s)" % (message, binding_text(bindings)), path, lineno)


def _ordinary_rule(raw: str, section: Optional[int], path: str, lineno: int) -> _Pending:
    """An ordinary rule line, parsed."""
    line = _strip_ws(raw)
    form = _parse_rule(line, section, path, lineno)
    if form.name is not None:  # the name is checked as written: white space is allowed only around it
        found = _RAW_NAME.findall(raw)
        if found:
            _check_name(found[-1].strip(), path, lineno)
    return _Pending(lineno, form.shown.replace(SEP, " "), form)


def _expand_rules(pending: List[_Pending], ranges: Ranges, limit: int, path: str) -> List[_Pending]:
    """Replace each rule line that has ranges by its instances (parsed as ordinary rule lines), in the order of the file."""
    out: List[_Pending] = []
    generated = 0
    for origin, p in enumerate(pending):
        p.origin = origin
        if p.raw is None:
            out.append(p)
            continue
        analysis = _analyse_rule(p.raw, path, p.lineno)
        if analysis is None:  # no reference: the "{:" is the literal text of a regular expression
            out.append(_ordinary_rule(p.raw, p.section, path, p.lineno))
            out[-1].origin = origin
            continue
        t, source = analysis.template, analysis.source
        try:
            check_declared(t, ranges)
        except RangeFail as exc:
            raise ModelError(str(exc), path, p.lineno) from None
        count = size_of(t, ranges)
        if t.names and generated + count > limit:
            raise ModelError(
                "this line would give %d rules, and the model would have more than %d generated rules: the limit is the setting "
                "max_expanded_rules in [model] (raise it, or use smaller ranges)" % (count, limit), path, p.lineno)
        try:
            for env, text in instances(t, ranges):
                try:
                    form = _parse_rule(text, p.section, path, p.lineno)  # the text is a stripped line already
                except ModelError as exc:
                    raise _with_binding(exc, path, p.lineno, env) from None
                q = _Pending(p.lineno, form.shown.replace(SEP, " "), form)
                q.origin = origin
                if t.names:
                    q.bindings, q.source = env, source
                    generated += 1
                out.append(q)
        except RangeFail as exc:
            message = str(exc)
            if analysis.name and "negative" in message:
                message += " (rule %s)" % analysis.name
            raise ModelError(message, path, p.lineno) from None
    return out


def _expand_declarations(config: Dict[str, Any], ranges: Ranges, limit: int, path: str) -> None:
    """Expand the references in ``symbols`` (lexemes), ``alphabet``, ``terminals`` and the classes of the model's configuration."""
    for key in ("symbols", "alphabet", "terminals"):
        value = config.get(key)
        what = "the setting %s" % ("lexemes" if key == "symbols" else key)
        if isinstance(value, str):
            config[key] = expand_words(value, ranges, limit, path, what)
        elif isinstance(value, list) and all(isinstance(v, str) for v in value):
            config[key] = expand_each(value, ranges, limit, path, what)
    classes = config.get("classes")
    if isinstance(classes, dict):
        for name, value in list(classes.items()):
            if isinstance(value, str):
                classes[name] = expand_words(value, ranges, limit, path, "the class %s" % name)
            elif isinstance(value, list) and all(isinstance(v, str) for v in value):
                classes[name] = expand_each(value, ranges, limit, path, "the class %s" % name)


def parse_model(text: str, path: str = "<string>") -> Model:
    """Parse model text (already decoded; see ``parse_model_file``)."""
    if SEP in text:
        raise ModelError("the model contains a NUL character", path)
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    pending: List[_Pending] = []
    toml_lines: List[str] = []  # one per line of the file (rules blocks are blanked), so error line numbers stay right
    in_rules = False
    section: Optional[int] = None
    axioms_line = 0
    max_comp = 0
    for lineno, raw in enumerate(lines, 1):
        raw = raw.rstrip("\r")
        if lineno == 1:
            raw = raw.lstrip("﻿")
        stripped = raw.strip()
        header = _SECTION_HEADER.fullmatch(stripped) if "{:" in stripped else None
        if header is not None and "{:" in (header.group(1) or ""):
            raise ModelError(
                "a range reference cannot be used in a section header: write the component numbers in the rules of the general "
                "[rules] section instead (for example {:X}, A -> B, {:X+1})", path, lineno)
        hm = _HEADER_RE.fullmatch(stripped)
        if hm is not None:
            head = hm.group(1).lower()
            parts = [q.strip() for q in hm.group(2).split(".")[1:]]
            if head == "rules":
                if len(parts) > 1 or (parts and not parts[0].isdigit()):
                    raise ModelError("a rules section is [rules] or [rules.N] with the component number N", path, lineno)
                number = int(parts[0]) if parts else None
                if number is not None and not 1 <= number <= MAX_COMPONENT:
                    raise ModelError("component numbers start at 1 and are at most %d" % MAX_COMPONENT, path, lineno)
                in_rules, section = True, number
                if number is not None:
                    max_comp = max(max_comp, number - 1)
                toml_lines.append("")
                continue
            in_rules = False
            if head == "axioms":
                axioms_line = lineno
            toml_lines.append("[" + head + hm.group(2) + "]")
            continue
        if not in_rules:
            toml_lines.append(raw)
            continue
        toml_lines.append("")
        if not stripped or stripped.startswith("#"):
            continue
        if "{:" in raw:  # read when the ranges are known
            pending.append(_Pending(lineno, "", None, raw, section))
            continue
        pending.append(_ordinary_rule(raw, section, path, lineno))
    doc = _toml_part("\n".join(toml_lines), path)
    symbols_table = doc.get("symbols")
    ranges = read_ranges(symbols_table.get("ranges") if isinstance(symbols_table, dict) else None, path)
    model_table = doc.get("model")
    limit = model_table.get("max_expanded_rules", DEFAULT_MAX_EXPANDED) if isinstance(model_table, dict) else DEFAULT_MAX_EXPANDED
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ModelError("max_expanded_rules must be a positive integer, not %r" % (limit,), path)

    def reject(message: str) -> None:
        raise ModelError(message, path)

    config: Optional[Dict[str, Any]] = None
    if ranges or "{:" in text:
        # the declarations first (the ranges, then the symbols), then the rules, so that the first mistake in that order is reported
        config = flatten({k: v for k, v in doc.items() if k != "axioms"}, "", True, reject)
        config.pop("ranges", None)
        config.pop("max_expanded_rules", None)
        _expand_declarations(config, ranges, limit, path)
    pending_rules = _expand_rules(pending, ranges, limit, path)
    for q in pending_rules:
        max_comp = max(max_comp, q.form.src, q.form.tgt)  # type: ignore[union-attr]
    axiom_table = doc.pop("axioms", {})
    if not isinstance(axiom_table, dict):
        raise ModelError("[axioms] must be a table of component = [strings]", path, axioms_line)
    axiom_lines: Dict[int, List[str]] = {}
    for key, value in axiom_table.items():
        if not key.isdigit() or not 1 <= int(key) <= MAX_COMPONENT:
            raise ModelError(
                "the axioms of %r: a component is a number from 1 to %d (for example 1 = [\"S\"])" % (key, MAX_COMPONENT),
                path,
                axioms_line,
            )
        number = int(key)
        if isinstance(value, list) and all(isinstance(v, str) for v in value):
            value = expand_each(value, ranges, limit, path, "an axiom of component %s" % key, axioms_line)
        axiom_lines[number] = _axiom_strings(value, number, path, axioms_line)
        max_comp = max(max_comp, number - 1)

    if config is None:
        config = flatten(doc, "", True, reject)
        config.pop("ranges", None)
        config.pop("max_expanded_rules", None)
    if "terminals" in config and not isinstance(config["terminals"], str):
        raise ModelError("terminals must be a string of symbols separated by white space, not %r" % (config["terminals"],), path)
    ncomp = max_comp + 1
    lexicon = build_lexicon(config, text, path)
    axioms: List[List[str]] = []
    for i in range(ncomp):
        for a in axiom_lines.get(i + 1, []):
            for ref in _CLASS_REF.finditer(a):
                if ref.group(1) in lexicon.classes or ref.group(1) in ("start", "end", "any"):
                    raise ModelError(
                        "an axiom of component %d uses {%s}: a class stands for a set of symbols, so an axiom must write the "
                        "symbols themselves" % (i + 1, ref.group(1)),
                        path,
                        axioms_line,
                    )
        encoded = [lexicon.encode(a) for a in axiom_lines.get(i + 1, [])]
        for enc in encoded:
            lexicon.check(enc, "an axiom of component %d" % (i + 1), path, axioms_line)
        axioms.append(encoded)
    lexicon.dollar_used = (
        any("$" in a for comp in axiom_lines.values() for a in comp)
        or any(_mentions_dollar(t) for q in pending_rules for k, t in enumerate(q.form.args) if not (q.form.kind == "re" and k == 0))
        or any("$" in w for q in pending_rules for w in q.form.permit + q.form.forbid + q.form.any_of)
    )
    rules: List[List[Rule]] = [[] for _ in range(ncomp)]
    named: Dict[str, Tuple[int, int]] = {}
    for idx, q in enumerate(pending_rules):
        form, lineno = q.form, q.lineno
        if form.name is not None:
            if form.name in named and named[form.name][1] != q.origin:
                raise ModelError(
                    "the rule name %r is used by the rules at lines %d and %d" % (form.name, named[form.name][0], lineno), path, lineno
                )
            named[form.name] = (lineno, q.origin)
        try:
            rule = make_rule(idx, lineno, q.shown, form, lexicon)
        except (ModelError, OverflowError) as exc:  # an oversized repetition such as a{100000000000000} is an OverflowError
            if q.bindings is not None:
                raise _with_binding(exc, path, lineno, q.bindings) from None
            raise ModelError(str(exc), path, lineno) from None
        if q.bindings is not None:
            rule.bindings, rule.source_notation = q.bindings, q.source
        rules[form.src].append(rule)
    return Model(axioms=axioms, rules=rules, path=path, lexicon=lexicon, config=config, ranges=ranges)


def parse_model_file(path: str) -> Model:
    """Read a model file (UTF-8, an optional BOM is accepted) and parse it."""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        raise ModelError("cannot read model: %s" % exc.strerror, str(path))
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ModelError("the file is not valid UTF-8 (byte %d): %s" % (exc.start, exc.reason), str(path)) from None
    return parse_model(text, str(path))
