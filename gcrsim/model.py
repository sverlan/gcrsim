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


class Model:
    """A parsed model: axioms per component, rules per component."""

    def __init__(
        self,
        axioms: List[List[str]],
        rules: List[List[Rule]],
        path: str = "<string>",
        lexicon: Lexicon = EMPTY,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.axioms = axioms
        self.rules = rules
        self.path = path
        self.lexicon = lexicon
        self.config = {} if config is None else config

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


def _split_clauses(tail: str, path: str, lineno: int) -> Tuple[List[str], List[str], List[str], Optional[str]]:
    """Parse ``;permit:w1,w2;forbid:w3;permit-any:w4,w5;name:N`` (the text after the target component)."""
    permit: List[str] = []
    forbid: List[str] = []
    any_of: List[str] = []
    name: Optional[str] = None
    for clause in _CLAUSE_START.split(tail)[1:]:
        kind, _, body = clause.partition(":")
        if kind == "name":
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


def _strip_ws(raw: str) -> str:
    """The line without whitespace; inside the pattern of ``re(...)`` an escaped space is kept."""
    head = _RE_HEAD.match(raw)
    if head is None:
        return _squeeze(raw)
    end = find_re_end(raw, head.end())
    if end < 0:
        return _WS_RE.sub("", raw)
    pattern = _ESCAPED_WS.sub(lambda m: m.group(1) or "", raw[head.end() : end])
    return _WS_RE.sub("", raw[: head.end()]) + pattern + _WS_RE.sub("", raw[end:])


class _Form:
    """A parsed rule line, before the rule objects are built."""

    __slots__ = ("kind", "args", "src", "tgt", "permit", "forbid", "any_of", "name", "shown")

    def __init__(self, kind, args, src, tgt, permit, forbid):
        self.kind = kind  # plain, ins, del, sub, send, re
        self.args = args  # raw operand texts
        self.src = src
        self.tgt = tgt
        self.permit = permit
        self.forbid = forbid
        self.any_of: List[str] = []
        self.name: Optional[str] = None
        self.shown = ""  # the rule line as shown (without the name clause)


def _after_target(rest: str, line: str, path: str, lineno: int) -> Tuple[Optional[int], str]:
    """``rest`` is what follows a form: ``[,target][;permit:..][;forbid:..]``; returns (target, clauses)."""
    if not rest:
        return None, ""
    if not rest.startswith(","):
        raise ModelError("unexpected text after the rule in %r" % line, path, lineno)
    tm = re.match(r"([0-9]*)(.*)", rest[1:])
    digits, tail = tm.group(1), tm.group(2)
    if tail and not tail.startswith(_CLAUSE_KINDS):
        raise ModelError("unexpected text after the target component in rule %r" % line, path, lineno)
    if not digits:
        raise ModelError("a comma after the rule must be followed by the target component number in %r" % line, path, lineno)
    return _component_number(digits, line, path, lineno), tail


MAX_COMPONENT = 10_000


def _component_number(digits: str, line: str, path: str, lineno: int) -> int:
    number = int(digits)
    if number > MAX_COMPONENT:
        raise ModelError("component number %d is larger than the limit %d (%r)" % (number, MAX_COMPONENT, line), path, lineno)
    return number


def _parse_rule(line: str, section: Optional[int], path: str, lineno: int) -> _Form:
    """Parse one rule line; components are returned 0-based."""
    src: Optional[int] = None
    pm = _PREFIX_RE.match(line)
    if pm:
        src = _component_number(pm.group(1), line, path, lineno) if pm.group(1) else None
        body = line[pm.end() :]
    else:
        body = line
    tgt: Optional[int] = None
    clauses = ""
    if body.startswith("send()"):
        kind, args = "send", ()
        tgt, clauses = _after_target(body[6:], line, path, lineno)
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
        tgt, clauses = _after_target(body[close + 1 :], line, path, lineno)
    else:
        if body.startswith("re("):
            kind = "re"
            end = find_re_end(body, 3)
            if end < 0:
                raise ModelError("missing ')' in the pattern of rule %r" % line, path, lineno)
            lhs = body[3:end]
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
            tgt, clauses = _after_target("," + tail, line, path, lineno)
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
        permit, forbid, any_of, name = _split_clauses(clauses, path, lineno)
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


def parse_model(text: str, path: str = "<string>") -> Model:
    """Parse model text (already decoded; see ``parse_model_file``)."""
    if SEP in text:
        raise ModelError("the model contains a NUL character", path)
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    pending_rules: List[Tuple[int, str, _Form]] = []
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
        line = _strip_ws(raw)
        form = _parse_rule(line, section, path, lineno)
        if form.name is not None:  # the name is checked as written: white space is allowed only around it
            found = _RAW_NAME.findall(raw)
            if found:
                _check_name(found[-1].strip(), path, lineno)
        max_comp = max(max_comp, form.src, form.tgt)
        pending_rules.append((lineno, form.shown.replace(SEP, " "), form))
    doc = _toml_part("\n".join(toml_lines), path)
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
        axiom_lines[number] = _axiom_strings(value, number, path, axioms_line)
        max_comp = max(max_comp, number - 1)

    def reject(message: str) -> None:
        raise ModelError(message, path)

    config = flatten(doc, "", True, reject)
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
        or any(_mentions_dollar(t) for _, _, f in pending_rules for k, t in enumerate(f.args) if not (f.kind == "re" and k == 0))
        or any("$" in w for _, _, f in pending_rules for w in f.permit + f.forbid + f.any_of)
    )
    rules: List[List[Rule]] = [[] for _ in range(ncomp)]
    named: Dict[str, int] = {}
    for idx, (lineno, line, form) in enumerate(pending_rules):
        if form.name is not None:
            if form.name in named:
                raise ModelError(
                    "the rule name %r is used by the rules at lines %d and %d" % (form.name, named[form.name], lineno), path, lineno
                )
            named[form.name] = lineno
        try:
            rules[form.src].append(make_rule(idx, lineno, line, form, lexicon))
        except ModelError as exc:
            raise ModelError(str(exc), path, lineno) from None
    return Model(axioms=axioms, rules=rules, path=path, lexicon=lexicon, config=config)


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
