r"""Convert a Perl-era model (and its configuration) to the current format.

``convert_model(text)`` returns the new text and a list of warnings.  The
conversion keeps the meaning of every rule it can translate; a rule it cannot
translate (the Perl program would not have compiled it, or it uses a construct
Python's ``re`` lacks) is written as a ``#`` comment and reported.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple
from .errors import ModelError
from .model import parse_model
from .pattern import _WS_RE
from .pattern import compile_pattern

_OLD_RULE_RE = re.compile(r"(?:(\d*),)?([^-]*)->([^,]*)(?:,(\d*))?")
_CLAUSE_START = re.compile(r";(?=(?:permit|forbid):)")

# Perl regex constructs without a Python equivalent (or with a different meaning)
_LHS_PERL_ONLY = [
    (re.compile(r"\(\?<[A-Za-z_]"), "named group (?<name>...) (Python: (?P<name>...))"),
    (re.compile(r"\\g\{"), r"relative or braced back-reference \g{...}"),
    (re.compile(r"\\[zKhHRvVXN]"), "Perl-only escape"),
    (re.compile(r"\(\?\^"), "(?^...) flag group"),
    (re.compile(r"\\\$"), r"'\$' (Perl turned this into a backslash followed by an end anchor)"),
    (re.compile(r"\(\?[aiLmsu]*x"), "verbose flag (?x): '#' is an ordinary symbol and spaces are ignored in models"),
]


_RHS_SINGLE_DOLLAR = re.compile(r"\$(?!\$\d|\d)")
_RHS_DOUBLE_DOLLAR = re.compile(r"\$\$(?=\d)")
_OCTAL = "01234567"
_HEX_ESCAPE = re.compile(r"(?:\{([0-9a-fA-F]+)\}|([0-9a-fA-F]{1,2}))")


def _compile_rhs(rhs: str) -> Tuple[List[Any], bool]:
    """Compile a right-hand side the way Perl's ``eval`` would interpret it.

    Returns ``(parts, broken)``.  ``parts`` is a list of literal strings and
    integer capture-group numbers.  ``broken`` is True when the Perl code
    string would not compile (unescaped quote, trailing backslash, ``@name``
    interpolation, ...): such a rule produces no results, as in Perl.
    """
    text = _RHS_SINGLE_DOLLAR.sub(lambda m: "\\$", rhs)
    text = _RHS_DOUBLE_DOLLAR.sub("$", text)
    parts: List[Any] = []
    buf: List[str] = []
    i = 0
    n = len(text)

    def flush() -> None:
        if buf:
            parts.append("".join(buf))
            del buf[:]

    while i < n:
        ch = text[i]
        if ch == "\\":
            if i + 1 >= n:
                return [], True
            nxt = text[i + 1]
            i += 2
            if nxt in "nrtfabe":
                buf.append({"n": "\n", "r": "\r", "t": "\t", "f": "\f", "a": "\a", "b": "\b", "e": "\x1b"}[nxt])
            elif nxt in _OCTAL:
                j = i
                digits = nxt
                while j < n and len(digits) < 3 and text[j] in _OCTAL:
                    digits += text[j]
                    j += 1
                i = j
                value = int(digits, 8)
                if value > 255:
                    raise ModelError("octal escape \\%s in a right-hand side exceeds one byte" % digits)
                buf.append(chr(value))
            elif nxt == "x":
                hexm = _HEX_ESCAPE.match(text, i)
                if hexm is None:
                    raise ModelError("invalid \\x escape in a right-hand side (expected \\xHH or \\x{HH})")
                value = int(hexm.group(1) or hexm.group(2), 16)
                if value > 255:
                    raise ModelError("\\x escape in a right-hand side exceeds one byte")
                buf.append(chr(value))
                i = hexm.end()
            elif nxt in "cNuUlLQEo":
                raise ModelError("unsupported escape \\%s in a right-hand side" % nxt)
            else:
                buf.append(nxt)  # includes \\ \" \$ \@; unknown escapes pass through
        elif ch == '"':
            return [], True
        elif ch == "$":
            j = i + 1
            while j < n and text[j].isdigit() and text[j] in "0123456789":
                j += 1
            if j == i + 1:
                return [], True  # bare variable: does not compile under strict
            num = int(text[i + 1 : j])
            if num == 0:
                raise ModelError("$0 is not supported in a right-hand side")
            flush()
            parts.append(num)
            i = j
        elif ch == "@":
            nxt = text[i + 1] if i + 1 < n else ""
            if nxt and (nxt.isalpha() or nxt == "_") and nxt.isascii():
                return [], True
            if nxt in ("{", "@"):
                return [], True
            if nxt in ("-", "+", ":"):
                raise ModelError("@%s is not supported in a right-hand side" % nxt)
            if nxt and nxt in "0123456789":
                j = i + 1
                while j < n and text[j] in "0123456789":
                    j += 1
                i = j  # an empty array interpolates to nothing
                continue
            buf.append("@")
            i += 1
        else:
            buf.append(ch)
            i += 1
    flush()
    return parts, False


def _capture(num: int, next_is_digit: bool) -> str:
    if num < 10 and not next_is_digit:
        return "\\%d" % num
    return "\\g<%d>" % num


_REGEX_META = frozenset("\\.^|?*+()[]{}")
_PLAIN_FORBIDDEN = frozenset("{},()")


def _rhs_parts(rhs: str, lhs: str) -> Tuple[Optional[List[Any]], Optional[str]]:
    """The old right-hand side as literal strings and group numbers, or ``(None, reason)``."""
    try:
        parts, broken = _compile_rhs(rhs)
    except ModelError as exc:
        return None, str(exc)
    if broken:
        return None, "the Perl simulator could not compile this right-hand side (it produced no results)"
    try:
        groups = re.compile(lhs).groups
    except re.error:
        groups = 0
    return [p for p in parts if not (isinstance(p, int) and p > groups)], None  # Perl: a missing group is empty


def _render_re_rhs(parts: List[Any]) -> str:
    """The right-hand side of a ``re(...)`` rule: escapes for backslash, comma, whitespace and slashes."""
    out: List[str] = []
    for idx, part in enumerate(parts):
        if isinstance(part, int):
            following = parts[idx + 1] if idx + 1 < len(parts) else ""
            out.append(_capture(part, isinstance(following, str) and following[:1].isdigit()))
            continue
        piece: List[str] = []
        for k, ch in enumerate(part):
            if ch == "\\":
                piece.append("\\\\")
            elif ch == "," or ch.isspace() or ord(ch) < 32:
                piece.append("\\x%02x" % ord(ch) if ord(ch) < 256 else "\\u%04x" % ord(ch))
            elif ch == "/" and (part[k - 1 : k] == "/" or part[k + 1 : k + 2] == "/"):
                piece.append("\\x2f")
            else:
                piece.append(ch)
        out.append("".join(piece))
    return "".join(out)


def _render_plain_rhs(parts: List[Any]) -> Optional[str]:
    """The literal right-hand side of a plain rule, or None when it needs captures or syntax characters."""
    if any(isinstance(p, int) for p in parts):
        return None
    text = "".join(parts)
    if any(ch in _PLAIN_FORBIDDEN or ch.isspace() or ord(ch) < 32 for ch in text) or "->" in text or "//" in text:
        return None
    return text


def _convert_axiom_items(items: List[str]) -> str:
    """The axioms of a component as a TOML list of strings; the empty string stays the empty word."""
    while items and items[-1] == "":
        items = items[:-1]
    ordered = [""] * ("" in items) + [i for i in items if i != ""]
    return "[" + ", ".join(json.dumps(i, ensure_ascii=False) for i in ordered) + "]"


def convert_model(text: str, extra: str = "") -> Tuple[str, List[str]]:
    """Convert a Perl-era model text; returns ``(new_text, warnings)``. ``extra`` (settings sections) goes before the axioms."""
    warnings: List[str] = []
    out: List[str] = []
    in_rules = False
    axiom_no = 0
    emitted_axioms = False
    emitted_rules = False
    extra_lines = extra.rstrip("\n").split("\n") + [""] if extra else []

    def open_axioms() -> None:
        nonlocal emitted_axioms
        if not emitted_axioms:
            out.extend(extra_lines)
            extra_lines.clear()
            out.append("[axioms]")
            emitted_axioms = True

    lines = text.replace("\r\n", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    for lineno, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if stripped.startswith("//"):
            out.append("# " + stripped[2:].strip())
            continue
        if stripped.startswith("#"):
            out.append(stripped)
            continue
        trailing = ""
        line = _WS_RE.sub("", raw)
        cut = line.find("//")
        if cut >= 0:
            trailing = raw[raw.find("//") + 2 :].strip()
            line = line[:cut]
        if not line:
            if not stripped:
                out.append("")
            elif trailing:
                out.append("# " + trailing)
            continue
        if trailing:
            out.append("# " + trailing)
        if re.match("Axioms", line, re.I):
            open_axioms()
            continue
        if re.match("ConfigFile", line, re.I):
            warnings.append("line %d: ConfigFile %s dropped (its settings are put in the model's [model] and [run] sections)" % (lineno, line[10:]))
            continue
        if not in_rules and re.match(r"Symbols", line, re.I):
            warnings.append(
                "line %d: the Symbols directive was dropped; declare lexemes with 'lexemes', 'alphabet' or 'classes' in the [symbols] section" % lineno
            )
            continue
        if re.match("Rules", line, re.I):
            in_rules = True
            if not emitted_rules:
                out.append("[rules]")
                emitted_rules = True
            continue
        if not in_rules:
            if re.search(r"\[(.*)\]", line):
                open_axioms()
                axiom_no += 1
                items = re.sub(r"\[|\]", "", line).split(",")
                out.append("%d = %s" % (axiom_no, _convert_axiom_items(items)))
            continue
        m = _OLD_RULE_RE.search(line)
        if m is None:
            warnings.append("line %d: cannot parse rule %r; kept as a comment" % (lineno, line))
            out.append("# " + line)
            continue
        src_s, lhs, rhs, tgt_s = m.groups()
        tail = line[m.end() :]
        src = int(src_s) if src_s else 1
        tgt = int(tgt_s) if tgt_s else 1
        reasons = [why for rx, why in _LHS_PERL_ONLY if rx.search(lhs)]
        parts, why = _rhs_parts(rhs, lhs)
        if tgt_s is None and (";permit:" in rhs or ";forbid:" in rhs):
            reasons.append("a ;permit:/;forbid: clause needs the target component before it")
        if why:
            reasons.append(why)
        if not reasons:
            try:
                compile_pattern(lhs)
            except (re.error, ValueError) as exc:
                reasons.append("left-hand side does not compile in Python: %s" % exc)
        clauses = ""
        if tail.startswith(";permit:") or tail.startswith(";forbid:"):
            clauses = tail
            if any(ch in _PLAIN_FORBIDDEN for ch in clauses.replace(",", "")):
                reasons.append("a permit/forbid word contains a character the plain syntax cannot hold")
        elif tail:
            warnings.append("line %d: text after the target component ignored (as before): %r" % (lineno, tail))
        if reasons:
            warnings.append("line %d: rule %r not converted: %s" % (lineno, line, "; ".join(reasons)))
            out.append("# not converted: " + line)
            continue
        plain_rhs = _render_plain_rhs(parts)
        is_plain = (
            plain_rhs is not None
            and not any(ch in _REGEX_META or ch.isspace() or ch in _PLAIN_FORBIDDEN for ch in lhs)
            and "->" not in lhs
            and "//" not in lhs
        )
        if is_plain:
            body = "%s->%s" % (lhs, plain_rhs)
            prefix = "%d," % src if (src != 1 or lhs.startswith("#")) else ""
        else:
            # Deliberately not done: recognising that a regex rule is really ins/del/sub (a literal context around a
            # captured literal) and emitting that form. Proving the two equivalent means reasoning about regex
            # semantics, and a wrong guess would silently change the model; so the rule stays re(...) and can be
            # rewritten by hand into the guaranteed plain fragment.
            body = "re(%s)->%s" % (lhs, _render_re_rhs(parts))
            prefix = "%d," % src if src != 1 else ""
        looks_like_clause = ";permit:" in body or ";forbid:" in body
        target = ",%d" % tgt if (tgt != 1 or clauses or looks_like_clause) else ""
        new_line = "%s%s%s%s" % (prefix, body, target, clauses)
        try:  # the converted rule must be a rule of the current syntax
            parse_model("[axioms]\n1 = [" + chr(34) + "$" + chr(34) + "]\n[rules]\n" + new_line + "\n")  # '$': whether the whole model uses it is unknown here
        except ModelError as exc:
            warnings.append("line %d: rule %r not converted: the result is not valid (%s)" % (lineno, line, exc))
            out.append("# not converted: " + line)
            continue
        if is_plain and lhs and any(lhs[:k] == lhs[-k:] for k in range(1, len(lhs))):
            warnings.append(
                "line %d: the left-hand side %r can overlap itself; every overlapping occurrence now applies "
                "(the Perl simulator applied only non-overlapping ones)" % (lineno, lhs)
            )
        elif not is_plain and re.search(r"[+*|]|\{\d*,\d*\}", lhs):
            warnings.append(
                "line %d: the pattern %r can match in several lengths or overlap itself; every start position now "
                "applies (the Perl simulator continued after each match, e.g. 'a+' on 'aaa' gave one result, "
                "now it gives three)" % (lineno, lhs)
            )
        out.append(new_line)
    out = extra_lines + out  # a model without axioms: the settings still come first
    return "\n".join(out) + "\n", warnings



# ---------------------------------------------------------------------------
# Perl configuration files and the command line
# ---------------------------------------------------------------------------

_CFG_ASSIGN = re.compile(r"^\s*(?:our\s+|my\s+)?\$(\w+)\s*=\s*(.+?)\s*;\s*(?:#.*)?$")
_CFG_INT_KEYS = ("print_len", "add_skip_len")  # Perl names
_CFG_NEW_NAME = {"print_len": "print_max_len", "add_skip_len": "reject_max_len", "print_skip": "print_hide", "add_skip": "reject_strings"}
_CFG_BOOL_KEYS = ("history", "show_detailed_application")
_CFG_RE_KEYS = ("print_skip", "add_skip")


_PERL_SIMPLE_ESC = {"n": "\n", "t": "\t", "r": "\r", "f": "\f", "b": "\b", "a": "\a", "e": "\x1b"}
_PERL_UNSUPPORTED_ESC = "QEULulNc"


def _perl_string(token: str) -> Optional[str]:
    """The value of a Perl string literal (single or double quoted), or None if ``token`` is not one.

    Raises ``ValueError`` for a double-quoted string that interpolates a variable or uses an escape
    that cannot be reproduced (``\\Q``, ``\\U``, ...).
    """
    if not (len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'"):
        return None
    body = token[1:-1]
    out: List[str] = []
    i = 0
    n = len(body)
    if token[0] == "'":  # only \\ and \' are escapes
        while i < n:
            if body[i] == "\\" and i + 1 < n and body[i + 1] in "\\'":
                out.append(body[i + 1])
                i += 2
            else:
                out.append(body[i])
                i += 1
        return "".join(out)
    while i < n:
        ch = body[i]
        if ch in "$@" and i + 1 < n and (body[i + 1].isalnum() or body[i + 1] in "_{"):
            raise ValueError("the string interpolates a variable (%s...)" % ch)
        if ch != "\\" or i + 1 >= n:
            out.append(ch)
            i += 1
            continue
        nxt = body[i + 1]
        if nxt in _PERL_UNSUPPORTED_ESC:
            raise ValueError("the string uses the escape \\%s" % nxt)
        if nxt in _PERL_SIMPLE_ESC:
            out.append(_PERL_SIMPLE_ESC[nxt])
            i += 2
        elif nxt == "x":
            m = re.match(r"\{([0-9a-fA-F]+)\}|([0-9a-fA-F]{1,2})", body[i + 2 :])
            if m is None:
                out.append("\0")
                i += 2
            else:
                out.append(chr(int(m.group(1) or m.group(2), 16)))
                i += 2 + m.end()
        elif nxt in "01234567":
            m = re.match(r"[0-7]{1,3}", body[i + 1 :])
            out.append(chr(int(m.group(0), 8)))
            i += 1 + m.end()
        else:
            out.append(nxt)  # Perl drops the backslash before any other character
            i += 2
    return "".join(out)


def _perl_int(token: str) -> Optional[int]:
    """A Perl integer literal (decimal, 0octal, 0xhex, 0bbinary, with underscores), or None."""
    t = token.strip().replace("_", "")
    try:
        if t.lower().startswith("0x"):
            return int(t, 16)
        if t.lower().startswith("0b"):
            return int(t, 2)
        if len(t) > 1 and t.startswith("0") and t.isdigit():
            return int(t, 8)
        return int(t) if t.isdigit() else None
    except ValueError:
        return None


def _perl_truth(token: str) -> Optional[bool]:
    """Perl truth of a literal: undef, 0, '' and '0' are false; None if it is not a simple literal."""
    t = token.strip()
    if t == "undef":
        return False
    number = _perl_int(t)
    if number is not None:
        return number != 0
    try:
        text = _perl_string(t)
    except ValueError:
        return None
    if text is None:
        return None
    return text not in ("", "0")


def _toml_string(value: str) -> str:
    """A TOML string for ``value``: a literal string when possible, otherwise a basic string with escapes."""
    controls = set(chr(c) for c in range(32)) | {chr(127)}
    if "'" not in value and not any(ch in controls for ch in value):
        return "'" + value + "'"
    out = []
    for ch in value:
        if ch == chr(92):
            out.append(chr(92) * 2)
        elif ch == '"':
            out.append(chr(92) + '"')
        elif ch in controls:
            out.append(chr(92) + "u%04x" % ord(ch))
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def _anchors_to_z(pattern: str) -> str:
    r"""A Perl pattern with the end anchor ``$`` (outside classes) written as ``\Z``, as the new syntax needs."""
    from .lexicon import _escape_end

    out: List[str] = []
    i = 0
    n = len(pattern)
    in_class = False
    while i < n:
        c = pattern[i]
        if c == "\\":
            j = _escape_end(pattern, i)
            out.append("\\Z" if pattern[i:j] == "\\z" else pattern[i:j])
            i = j
            continue
        if in_class:
            in_class = c != "]"
        elif c == "[":
            in_class = True
            out.append(c)
            i += 1
            if i < n and pattern[i] == "^":
                out.append("^")
                i += 1
            if i < n and pattern[i] == "]":
                out.append("]")
                i += 1
            continue
        elif c == "$":
            out.append("\\Z")
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def convert_cfg(text: str) -> Tuple[str, List[str], bool]:
    """Convert a Perl configuration to a TOML text: ``(toml, warnings, has_filter_function)``."""
    warnings: List[str] = []
    values: List[str] = []
    seen = set()
    for lineno, raw in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        if raw.lstrip().startswith("#"):
            continue
        m = _CFG_ASSIGN.match(raw)
        if m is None:
            continue
        key, token = m.group(1), m.group(2)
        if key not in _CFG_INT_KEYS + _CFG_BOOL_KEYS + _CFG_RE_KEYS:
            continue  # other variables are not settings
        if key in seen:
            warnings.append("line %d: %s is set twice; the later value is used" % (lineno, key))
            values = [v for v in values if not v.startswith(_CFG_NEW_NAME.get(key, key) + " =")]
        seen.add(key)
        if key in _CFG_BOOL_KEYS:
            truth = _perl_truth(token)
            if truth is None:
                warnings.append("line %d: %s = %s is not a simple value; skipped" % (lineno, key, token))
                continue
            values.append("%s = %s" % (_CFG_NEW_NAME.get(key, key), "true" if truth else "false"))
        elif key in _CFG_INT_KEYS:
            number = _perl_int(token)
            if number is None:
                warnings.append("line %d: %s = %s is not a plain number; skipped" % (lineno, key, token))
                continue
            values.append("%s = %d" % (_CFG_NEW_NAME.get(key, key), number))
        else:
            try:
                pattern = _perl_string(token.strip())
            except ValueError as exc:
                warnings.append("line %d: %s = %s skipped: %s" % (lineno, key, token, exc))
                continue
            if pattern is None:
                warnings.append("line %d: %s = %s is not a plain string; skipped" % (lineno, key, token))
                continue
            if pattern in ("@", ""):
                values.append('%s = ""' % _CFG_NEW_NAME.get(key, key))  # the Perl idiom for 'no skip'
                continue
            values.append("%s = %s" % (_CFG_NEW_NAME.get(key, key), _toml_string(_anchors_to_z(pattern))))
    has_filter = bool(re.search(r"(?m)^\s*sub\s+filter_next\b", text))
    if has_filter:
        warnings.append(
            "the configuration defines filter_next: it is not converted; express it with the filters and "
            "marks in the TOML file, or rewrite it as a Python filter function"
        )
    from .sections import section_of

    grouped: Dict[str, List[str]] = {"model": [], "run": []}
    for v in values:
        grouped[section_of(v.split(" ", 1)[0]) or "model"].append(v)
    sections = []
    for name in ("model", "run"):
        if grouped[name]:
            sections.append("[%s]\n" % name + "\n".join(grouped[name]) + "\n")
    return "\n".join(sections), warnings, has_filter


def main_convert(argv: Optional[Sequence[str]] = None) -> int:
    """``gcrsim-convert OLD_MODEL [-o NEW_MODEL] [--source-encoding ENC]``."""
    import argparse
    import os
    import sys

    if argv is None:
        argv = sys.argv[1:]
    p = argparse.ArgumentParser(prog="gcrsim-convert", description="Convert a Perl-era model (and its .cfg) to the current notation.")
    p.add_argument("model", help="the old model file")
    p.add_argument("-o", "--output", metavar="NEW_MODEL", help="write the new model here (default: standard output)")
    p.add_argument("--source-encoding", default="latin-1", help="encoding of the Perl files (default latin-1, as Perl read them)")
    args = p.parse_args(list(argv))
    try:
        with open(args.model, "rb") as fh:
            old = fh.read().decode(args.source_encoding)
    except (OSError, UnicodeDecodeError) as exc:
        sys.stderr.write("gcrsim-convert: %s\n" % exc)
        return 2
    cfg_name = None
    for raw in old.replace("\r\n", "\n").split("\n"):
        stripped = _WS_RE.sub("", raw)
        cut = stripped.find("//")
        stripped = stripped if cut < 0 else stripped[:cut]
        m = re.match("ConfigFile(.*)", stripped, re.I)
        if m and m.group(1):
            cfg_name = m.group(1)
            break
    if cfg_name is None:
        cfg_name = "gcrsim.cfg"  # the default of the Perl simulator
        implicit = True
    else:
        implicit = False
    toml_text = ""
    warnings_cfg: List[str] = []
    if cfg_name:
        for base in (os.getcwd(), os.path.dirname(os.path.abspath(args.model))):
            cand = cfg_name if os.path.isabs(cfg_name) else os.path.join(base, cfg_name)
            if os.path.isfile(cand):
                with open(cand, "rb") as fh:
                    toml_text, cfg_warnings, _ = convert_cfg(fh.read().decode(args.source_encoding))
                warnings_cfg += ["%s: %s" % (cfg_name, w) for w in cfg_warnings]
                break
        else:
            if not implicit:
                warnings_cfg.append("the configuration %s named in the model was not found" % cfg_name)
    new, warnings = convert_model(old, toml_text)
    warnings += warnings_cfg
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(new)
    else:
        sys.stdout.write(new)
    for w in warnings:
        sys.stderr.write("gcrsim-convert: %s\n" % w)
    return 0
