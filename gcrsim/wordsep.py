"""Reading a typed word with a separator (``word_sep``), the input counterpart of ``print_sep``.

``word_sep`` cuts a typed word into pieces; each piece is read with the alphabet and the lexemes of the model, and no symbol is
read across a separator (``Lexicon.encode_spaced``). The separator must not occur in a symbol of the model: ``check_word_sep``
tests that once, before a word is read. ``warn_print_sep`` warns when a printed word with ``print_sep`` can be read in more than
one way.
"""

from __future__ import annotations

import sys
from typing import Any, Optional, Set, Tuple

from .errors import GcrsimError
from .lexicon import SEP
from .rules import RegexRule, SubRule


def model_symbols(model: Any) -> Set[str]:
    """The symbols of a model: the alphabet and the lexemes, and, for a model without an alphabet, every symbol written in an
    axiom, in an operand of a plain rule (contexts included), in a permit/forbid/permit-any word or in a class."""
    lex = model.lexicon
    symbols: Set[str] = set(lex.declared)
    if lex.alphabet is not None:
        return symbols | set(lex.alphabet)
    for members in lex.classes.values():
        symbols.update(members)
    internal: Set[str] = set()
    for component in model.axioms:
        internal.update("".join(component))
    for component in model.rules:
        for rule in component:
            for word in rule.permit + rule.forbid + rule.any_of:
                internal.update(word)
            if isinstance(rule, SubRule):
                internal.update(rule.x)
                for item in rule.U + rule.Y + rule.V:
                    if isinstance(item, str):
                        internal.add(item)
                    elif isinstance(item, frozenset):
                        internal.update(item)
    symbols.update(lex.decode(ch) for ch in internal)
    return symbols


def _conflict(model: Any, chars: str) -> Optional[Tuple[str, str]]:
    """``(symbol, character)`` of the first symbol that holds a character of ``chars``, or None."""
    for sym in sorted(model_symbols(model), key=lambda s: (len(s), s)):
        for ch in chars:
            if ch in sym:
                return sym, ch
    return None


def check_word_sep(model: Any, word_sep: str) -> None:
    """Refuse a ``word_sep`` with a character that occurs in a symbol of the model (``GcrsimError``); warn on stderr when the
    model has regular-expression rules, which can produce any character. An empty ``word_sep`` is not set: nothing to check."""
    if not word_sep:
        return
    for ch in word_sep:
        if ch == SEP or model.lexicon.is_internal(ch):
            raise GcrsimError("word_sep %r cannot be used: it contains the internal character U+%04X" % (word_sep, ord(ch)))
    found = _conflict(model, word_sep)
    if found is not None:
        sym, ch = found
        raise GcrsimError("word_sep %r cannot be used: its character %r occurs in the symbol %r of the model" % (word_sep, ch, sym))
    if any(isinstance(rule, RegexRule) for component in model.rules for rule in component):
        sys.stderr.write("gcrsim: warning: the model has regular-expression rules; gcrsim cannot check that they never "
                         "produce %r\n" % word_sep)


def warn_print_sep(model: Any, print_sep: str) -> None:
    """Warn on stderr when ``print_sep`` (used only if the model has lexemes) shares a character with a symbol."""
    if not print_sep or not model.lexicon.has_lexemes:
        return
    found = _conflict(model, print_sep)
    if found is not None:
        sym, ch = found
        sys.stderr.write("gcrsim: warning: print_sep %r has the character %r that occurs in the symbol %r: printed words can be "
                         "ambiguous\n" % (print_sep, ch, sym))
