r"""Symbols longer than one character (lexemes), symbol classes and the alphabet.

A model may declare lexemes (``symbols``), classes (``classes``) and an
``alphabet`` in its ``[symbols]`` section.  Every lexeme is replaced by one private-use
character (U+E000 upward, never a character that occurs in the model) when the
model is loaded, so the engine works on plain strings in which one character is
one symbol: ``.``, ``[^X]``, ``{2}``, look-behind and back-references all work
on symbols.  Output is decoded back to the real names with ``decode``.

Tokenisation is longest-match: at each position the longest declared lexeme
wins, otherwise one character is a symbol.  With a declared ``alphabet`` a text is read with the alphabet
instead: a run of symbols without a space that is itself a symbol is that symbol; any other run that can be read in more
than one way is an error (a space, or ``(?:)`` in a ``re(...)`` pattern, separates symbols), and one with a single reading
is read that way.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Set
from .errors import ModelError

SEP = "\x00"  # a space between two symbols of a model line: no multi-character symbol is read across it
_CLASS_REF = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_QUANTIFIER = re.compile(r"\{[0-9]*(?:,[0-9]*)?\}")
_FORBIDDEN_IN_LEXEME = re.compile(r"[\\.^|?*+()\[\]{}\s,]|->")
_GROUP_HEAD = re.compile(r"\(\?(?:<[=!]|[:=!>]|[aiLmsux-]+[:)])")  # (?<=  (?<!  (?:  (?=  (?!  (?i)  (?i:
_ESCAPED_CODE = re.compile(r"\\(?:x([0-9a-fA-F]{2})|u([0-9a-fA-F]{4})|U([0-9a-fA-F]{8}))")
_CLASS_SPECIAL = frozenset("\\]^-[")
_PRIVATE_USE = ((0xE000, 0xF8FF), (0xF0000, 0xFFFFD), (0x100000, 0x10FFFD))  # BMP, plane 15, plane 16
_HEX = "0123456789abcdefABCDEF"
_PATTERN_META = frozenset("\\[](){}.^$|?*+")  # characters that end a run of literal symbols in a pattern


def _symbols_of(value: Any, what: str) -> List[str]:
    if isinstance(value, str):
        return value.split()
    if isinstance(value, (list, tuple)) and all(isinstance(v, str) and v for v in value):
        return list(value)
    raise ModelError("%s must be a string of symbols separated by spaces, or a list of strings" % what)


def comment_end(p: str, i: int) -> int:
    """Index of the ``)`` that closes the regex comment ``(?#...)`` starting at ``p[i]`` (escapes are skipped), or -1."""
    j = i + 3
    n = len(p)
    while j < n:
        if p[j] == "\\":
            j += 2
            continue
        if p[j] == ")":
            return j
        j += 1
    return -1


def _escape_end(p: str, i: int) -> int:
    """End index of the escape sequence that starts with the backslash at ``p[i]``."""
    n = len(p)
    if i + 1 >= n:
        return n
    c = p[i + 1]
    j = i + 2
    if c in "xuU":
        for _ in range({"x": 2, "u": 4, "U": 8}[c]):
            if j < n and p[j] in _HEX:
                j += 1
        return j
    if c == "N" and p.startswith("{", j):
        end = p.find("}", j)
        return n if end < 0 else end + 1
    if c.isdigit():
        while j < n and p[j].isdigit():
            j += 1
        return j
    if c == "g" and p.startswith("<", j):
        end = p.find(">", j)
        return n if end < 0 else end + 1
    return j


def is_uniquely_decodable(code: Iterable[str]) -> bool:
    """Sardinas-Patterson test: no string is a concatenation of ``code`` words in two ways."""
    words = set(code)
    current = {y[len(x) :] for x in words for y in words if x != y and y.startswith(x)}
    visited = set(current)
    while current:
        new = set()
        for w in current:
            for c in words:
                if c.startswith(w):
                    new.add(c[len(w) :])
                if w.startswith(c):
                    new.add(w[len(c) :])
        if "" in new:
            return False
        new -= visited
        visited |= new
        current = new
    return True


class Lexicon:
    """Maps lexemes to private-use characters and back; holds the classes and the alphabet."""

    def __init__(
        self,
        lexemes: Iterable[str] = (),
        classes: Optional[Mapping[str, List[str]]] = None,
        alphabet: Optional[Iterable[str]] = None,
        taboo: str = "",
    ):
        lexemes = list(lexemes)
        self.declared: Set[str] = set(lexemes)  # every symbol listed in the model, one-character ones too
        found = sorted({s for s in lexemes if len(s) > 1}, key=lambda s: (-len(s), s))
        for lex in found:
            if _FORBIDDEN_IN_LEXEME.search(lex):
                raise ModelError(
                    "the symbol %r cannot be a lexeme: it contains a regular-expression character, a comma, whitespace or '->'" % lex
                )
        self.classes: Dict[str, List[str]] = {k: list(v) for k, v in (classes or {}).items()}
        self.alphabet_order = tuple(dict.fromkeys(alphabet)) if alphabet is not None else None
        self.alphabet: Optional[Set[str]] = set(self.alphabet_order) if self.alphabet_order is not None else None
        self.lexemes: List[str] = found
        self.dollar_used = True  # set False by the parser when the model never writes '$': a '$' in a pattern is then a trap
        self._code: Dict[str, str] = {}
        self._name: Dict[int, str] = {}
        used = set(taboo) | set("".join(found))
        codes = (chr(c) for lo, hi in _PRIVATE_USE for c in range(lo, hi + 1) if chr(c) not in used)
        for lex in found:
            try:
                ch = next(codes)
            except StopIteration:
                raise ModelError("too many lexemes: the private-use area is exhausted") from None
            self._code[lex] = ch
            self._name[ord(ch)] = lex
        self._rx = re.compile("|".join(re.escape(s) for s in found)) if found else None
        # two single characters that stand side by side inside a lexeme: printed next to each other they would read as it
        self._joinable = {lex[i : i + 2] for lex in found for i in range(len(lex) - 1)}
        self._by_first: Dict[str, List[str]] = {}
        for word in sorted(self.alphabet or ()):
            self._by_first.setdefault(word[0], []).append(word)
        self._table = self._name or None
        self.active = bool(found) or bool(self.classes)

    def names(self) -> Dict[str, str]:
        """The private-use character of every lexeme, by lexeme name's code: ``{character: lexeme}``."""
        return {chr(code): name for code, name in self._name.items()}

    def is_internal(self, ch: str) -> bool:
        """True if ``ch`` is one of the private-use characters that stand for lexemes."""
        return ord(ch) in self._name

    @property
    def has_lexemes(self) -> bool:
        return self._rx is not None

    # -- encoding -------------------------------------------------------------------------

    def encode(self, text: str) -> str:
        """Plain symbol text (axioms, words): replace each lexeme by its character.

        A separator (a space of the model text between two symbols) stops a lexeme from being read across it and is removed.
        """
        if SEP in text:
            return "".join(self.encode(part) for part in text.split(SEP))
        if self._rx is None:
            return text
        if self.alphabet is not None:
            return self._encode_run(text)
        return self._rx.sub(lambda m: self._code[m.group()], text)

    def encode_spaced(self, text: str, word_sep: str = "", whitespace: bool = True) -> str:
        """A word typed or pasted by the user: symbols written together or separated by white space (which stops a lexeme from
        being read across it, as a space does in a model) and by ``word_sep``, if given. With ``whitespace`` false white space
        is an ordinary character and only ``word_sep`` separates. A text that holds an internal character (the separator mark
        or the code of a lexeme) is an error."""
        pieces = text.split(word_sep) if word_sep else [text]
        for ch in "".join(pieces):
            if ch == SEP or self.is_internal(ch):
                raise ModelError("the text contains the internal character U+%04X, which is not a symbol" % ord(ch))
        if whitespace:
            pieces = [token for piece in pieces for token in piece.split()]
        return self.encode(SEP.join(pieces))

    def _readings(self, run: str, limit: int = 2) -> List[List[str]]:
        """Up to ``limit`` ways to cut ``run`` into words of the alphabet (in the order of the sorted alphabet)."""
        n = len(run)
        ways = [0] * (n + 1)  # the number of readings of run[i:], at most limit
        ways[n] = 1
        for i in range(n - 1, -1, -1):
            ways[i] = min(limit, sum(ways[i + len(w)] for w in self._by_first.get(run[i], ()) if run.startswith(w, i)))
        found: List[List[str]] = []
        if not ways[0]:
            return found

        def candidates(i: int) -> List[str]:
            if i == n:
                return []
            return [w for w in self._by_first.get(run[i], ()) if run.startswith(w, i) and ways[i + len(w)]]

        acc: List[str] = []
        stack = [[0, candidates(0), 0]]  # position, the words that can start there, the next one to try
        while stack and len(found) < limit:
            frame = stack[-1]
            i, cands, k = frame
            if i == n:
                found.append(list(acc))
            if i == n or k >= len(cands):
                stack.pop()
                if acc:
                    acc.pop()
                continue
            frame[2] = k + 1
            w = cands[k]
            acc.append(w)
            stack.append([i + len(w), candidates(i + len(w)), 0])
        return found

    def _encode_run(self, run: str) -> str:
        """A run of symbols without a separator, read with the alphabet: one reading is used, several are an error."""
        if not run:
            return run
        if self._rx is None:
            return run
        if run in self._code:  # a run that is itself a symbol is that symbol: ``ab`` is the symbol, ``a b`` the two
            return self._code[run]
        readings = self._readings(run)
        if not readings:  # a character outside the alphabet: the longest-match reading, which ``check`` reports
            return self._rx.sub(lambda m: self._code[m.group()], run)
        if len(readings) > 1:
            raise ModelError(
                "the text %r can be read in more than one way: %s (separate the symbols with a space; in a re(...) "
                "pattern write (?:) between them)" % (run, " or ".join("'%s'" % " ".join(r) for r in readings))
            )
        return "".join(self._code.get(w, w) for w in readings[0])

    def decode(self, text: str) -> str:
        if self._table is None:
            return text
        return text.translate(self._table)

    def decode_spaced(self, text: str, sep: str) -> str:
        """Like ``decode``, with ``sep`` between a lexeme and the symbol next to it, and between two symbols that printed side
        by side would read as a lexeme (so ``p1`` is never read as ``p`` ``1``, nor ``a b`` as ``ab``)."""
        out: List[str] = []
        prev_lexeme = False
        for ch in text:
            name = self._name.get(ord(ch))
            joined = bool(out) and name is None and not prev_lexeme and (out[-1][-1:] + ch) in self._joinable
            if out and (name is not None or prev_lexeme or joined) and not ch.isspace() and not out[-1][-1:].isspace():
                out.append(sep)
            out.append(ch if name is None else name)
            prev_lexeme = name is not None
        return "".join(out)

    def shower(self, sep: str) -> "Callable[[str], str]":
        """The function that writes an internal string of symbols for output: ``decode_spaced`` when ``sep`` is set and the model
        has multi-character symbols, ``decode`` otherwise. It is for encoded strings only: running text (headings, rule texts,
        numbers) is not passed through it, because in plain text it would split real symbols."""
        if sep and self.has_lexemes:
            return lambda text: self.decode_spaced(text, sep)
        return self.decode

    def class_codes(self, name: str) -> "frozenset[str]":
        """The symbols of a class as a set of internal characters."""
        members = self.classes.get(name)
        if members is None:
            raise ModelError("unknown symbol class {%s}" % name)
        if not members:
            raise ModelError("the symbol class {%s} is empty" % name)
        return frozenset(self.encode(m) for m in members)

    def _class_body(self, name: str) -> str:
        members = self.classes.get(name)
        if members is None:
            raise ModelError("unknown symbol class {%s} (write \\{ for a literal brace)" % name)
        if not members:
            raise ModelError("the symbol class {%s} is empty" % name)
        out = []
        for m in members:
            enc = self.encode(m)
            out.append("".join("\\" + ch if ch in _CLASS_SPECIAL else ch for ch in enc))
        return "".join(out)

    def check_pattern_text(self, pattern: str) -> None:
        """A pattern must not name a lexeme's internal character, raw or by an escape (it would match that lexeme)."""
        if not self._name:
            return
        i, n = 0, len(pattern)
        while i < n:
            ch = pattern[i]
            if ch == "\\":
                j = _escape_end(pattern, i)
                m = _ESCAPED_CODE.fullmatch(pattern, i, j)
                if m:
                    code = int(m.group(1) or m.group(2) or m.group(3), 16)
                    if code in self._name:
                        raise ValueError("the code point U+%04X is reserved for a lexeme of this model" % code)
                i = j
                continue
            if pattern.startswith("(?#", i):
                end = comment_end(pattern, i)
                i = n if end < 0 else end + 1
                continue
            if ord(ch) in self._name:
                raise ValueError("the code point U+%04X is reserved for a lexeme of this model" % ord(ch))
            i += 1

    def encode_pattern(self, pattern: str) -> str:
        """A regular expression: expand ``{CLASS}``, replace lexemes.

        Escape sequences, quantifiers, group names and ``(?#...)`` comments are copied unchanged.
        """
        out: List[str] = []
        i = 0
        n = len(pattern)
        in_class = False
        rx = self._rx
        while i < n:
            c = pattern[i]
            if c == "\\":
                j = _escape_end(pattern, i)
                out.append(pattern[i:j])
                i = j
                continue
            if in_class:
                if c == "]":
                    in_class = False
                    out.append(c)
                    i += 1
                    continue
                if c == "{":
                    m = _CLASS_REF.match(pattern, i)
                    if m:
                        out.append(self._class_body(m.group(1)))
                        i = m.end()
                        continue
            else:
                if c == "[":
                    in_class = True
                    out.append(c)
                    i += 1
                    if i < n and pattern[i] == "^":
                        out.append("^")
                        i += 1
                    if i < n and pattern[i] == "]":
                        out.append("\\]")
                        i += 1
                    continue
                if c == "(":
                    gm = _GROUP_HEAD.match(pattern, i)
                    if gm:
                        out.append(gm.group())
                        i = gm.end()
                        continue
                if c == "(" and pattern.startswith(("(?P<", "(?P=", "(?#", "(?("), i):
                    if pattern.startswith("(?#", i):
                        end = comment_end(pattern, i)
                    else:
                        end = pattern.find(">" if pattern.startswith("(?P<", i) else ")", i)
                    end = n - 1 if end < 0 else end
                    out.append(pattern[i : end + 1])
                    i = end + 1
                    continue
                if c == "{":
                    m = _QUANTIFIER.match(pattern, i)
                    if m:
                        out.append(m.group())
                        i = m.end()
                        continue
                    m = _CLASS_REF.match(pattern, i)
                    if m:
                        out.append("[" + self._class_body(m.group(1)) + "]")
                        i = m.end()
                        continue
            if self.alphabet is not None and c not in _PATTERN_META:
                j = i
                while j < n and pattern[j] not in _PATTERN_META:
                    j += 1
                run = self._encode_run(pattern[i:j])
                self.check(run, "the regular expression %r" % pattern)  # its literal symbols (outside [...]) must be known
                out.append(run)
                i = j
                continue
            if rx is not None:
                m = rx.match(pattern, i)
                if m:
                    out.append(self._code[m.group()])
                    i = m.end()
                    continue
            out.append(c)
            i += 1
        return "".join(out)

    def encode_rhs(self, rhs: str) -> str:
        """A right-hand side: replace lexemes outside ``\\N`` and ``\\g<name>``."""
        if self._rx is None:
            return rhs
        out: List[str] = []
        i = 0
        n = len(rhs)
        while i < n:
            if rhs[i] == "\\":
                j = _escape_end(rhs, i)
                out.append(rhs[i:j])
                i = j
                continue
            if self.alphabet is not None:
                j = rhs.find("\\", i)
                j = n if j < 0 else j
                out.append(self._encode_run(rhs[i:j]))
                i = j
                continue
            m = self._rx.match(rhs, i)
            if m:
                out.append(self._code[m.group()])
                i = m.end()
                continue
            out.append(rhs[i])
            i += 1
        return "".join(out)

    # -- alphabet check --------------------------------------------------------------------

    def tokens(self, encoded: str) -> List[str]:
        """The decoded symbols of an encoded string."""
        return [self.decode(ch) for ch in encoded]

    def check(self, encoded: str, where: str, path: Optional[str] = None, lineno: Optional[int] = None) -> None:
        """Every symbol of ``encoded`` must belong to the declared alphabet (when there is one)."""
        if self.alphabet is None:
            return
        for sym in self.tokens(encoded):
            if sym not in self.alphabet:
                shown = " ".join(self.tokens(encoded))
                raise ModelError(
                    "the symbol %r in %s is not in the alphabet (symbols read as: %s)" % (sym, where, shown), path, lineno
                )


EMPTY = Lexicon()


def build_lexicon(config: Mapping[str, Any], model_text: str, path: str) -> Lexicon:
    """The lexicon declared by a model's ``[symbols]`` (``lexemes``, ``classes``, ``alphabet``)."""
    try:
        lexemes: List[str] = []
        declared: List[str] = []
        if "symbols" in config:
            declared = _symbols_of(config["symbols"], "symbols")
            lexemes += declared
        classes: Dict[str, List[str]] = {}
        raw_classes = config.get("classes", {})
        if not isinstance(raw_classes, dict):
            raise ModelError('classes must be a table of name = "symbols"')
        for name, value in raw_classes.items():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                raise ModelError("bad class name %r (letters, digits and underscore)" % name)
            if name in ("start", "end", "any"):
                raise ModelError("the class name %r is reserved" % name)
            members = _symbols_of(value, "class %s" % name)
            classes[name] = members
            lexemes += members
        alphabet: Optional[List[str]] = None
        if "alphabet" in config:
            alphabet = _symbols_of(config["alphabet"], "alphabet")
            lexemes += alphabet
        if alphabet is not None:
            alphabet = list(dict.fromkeys(alphabet + [m for ms in classes.values() for m in ms]))
            if "symbols" in config:
                raise ModelError(
                    "`lexemes` and `alphabet` are exclusive: the alphabet already lists every symbol of the model, "
                    "and its multi-character words are the multi-character symbols (remove `lexemes`)"
                )
        return Lexicon(lexemes, classes, alphabet, taboo=model_text)
    except ModelError as exc:
        raise ModelError(str(exc), path) from None
