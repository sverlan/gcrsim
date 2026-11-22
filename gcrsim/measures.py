"""Measures of a derivation, computed from its step records only.

A derivation is its first form (the axiom, or the first form of a replay) and its steps. ``measure`` gives the number of steps,
the longest form, how many times each rule is used, the symbols created and deleted, the peak number of non-terminals (when the
terminals are declared) and the number of forms in each component. ``format_measures`` writes them as the command line prints them.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from .errors import GcrsimError


class Measures:
    """The measures of one derivation.

    ``steps`` is the number of steps. ``max_len`` is the largest number of symbols of a form, the first form included, and
    ``max_len_step`` the first step at which it occurs (0 is the first form). ``rules`` lists how many times each rule is used, as
    dictionaries ``line``, ``component`` (the component the rule rewrites from, counted from 1), ``notation``, ``name``, ``kind`` and
    ``count``, in the order of the lines. ``created`` and ``deleted`` are the numbers of symbols inserted and removed over all steps.
    ``max_nonterminals`` and ``max_nonterminals_step`` are the largest number of symbols that are not declared terminals over the
    forms (the first form included) and the first step where it occurs; both are None when no terminals are declared.
    ``components`` lists, for every component that occurs, the number of forms that the derivation has in it (the first form counts
    in its component, then every step counts in its target component): dictionaries ``component`` (from 1) and ``forms``."""

    __slots__ = ("steps", "max_len", "max_len_step", "rules", "created", "deleted", "max_nonterminals", "max_nonterminals_step",
                 "components")

    def __init__(self, steps: int, max_len: int, max_len_step: int, rules: List[Dict[str, Any]], created: int, deleted: int,
                 max_nonterminals: Optional[int], max_nonterminals_step: Optional[int], components: List[Dict[str, int]]):
        self.steps = steps
        self.max_len = max_len
        self.max_len_step = max_len_step
        self.rules = rules
        self.created = created
        self.deleted = deleted
        self.max_nonterminals = max_nonterminals
        self.max_nonterminals_step = max_nonterminals_step
        self.components = components

    def to_dict(self) -> Dict[str, Any]:
        """The measures as JSON-ready data (the ``measures`` object of ``--format jsonl``)."""
        return {
            "steps": self.steps,
            "max_len": self.max_len,
            "max_len_step": self.max_len_step,
            "rules": [dict(r) for r in self.rules],
            "created": self.created,
            "deleted": self.deleted,
            "max_nonterminals": self.max_nonterminals,
            "max_nonterminals_step": self.max_nonterminals_step,
            "components": [dict(c) for c in self.components],
        }

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Measures) and self.to_dict() == other.to_dict()

    __hash__ = None  # type: ignore[assignment]

    def __repr__(self) -> str:
        return "Measures(steps=%d, max_len=%d, created=%d, deleted=%d)" % (self.steps, self.max_len, self.created, self.deleted)


def measure(first: str, steps: Sequence[Any], terminals: Optional[Iterable[str]] = None, first_component: int = 0) -> Measures:
    """The measures of the derivation that starts with the internal string ``first`` (in component ``first_component``, counted
    from 0) and goes on with ``steps`` (``DerivationStep`` or ``ReplayStep``). ``terminals`` are the internal characters of the
    terminals (None: not declared). Only the step records are read."""
    term = None if terminals is None else frozenset(terminals)

    def nonterminals(s: str) -> int:
        return len(s) - sum(1 for ch in s if ch in term)  # type: ignore[operator]

    max_len = len(first)
    max_len_step = 0
    best_nt = nonterminals(first) if term is not None else None
    best_nt_step = 0
    created = deleted = 0
    forms: Dict[int, int] = {first_component: 1}
    used: Dict[Tuple[int, int], List[Any]] = {}
    for k, st in enumerate(steps, 1):
        after = st.internal_result
        if len(after) > max_len:
            max_len, max_len_step = len(after), k
        if term is not None:
            n = nonterminals(after)
            if n > best_nt:  # type: ignore[operator]
                best_nt, best_nt_step = n, k
        rec = st._record()
        created += len(rec["inserted"])
        deleted += len(rec["removed"])
        forms[st.target_component] = forms.get(st.target_component, 0) + 1
        entry = used.get((st.rule.line, st.source_component))
        if entry is None:
            used[(st.rule.line, st.source_component)] = [st, 1]
        else:
            entry[1] += 1
    rules = []
    for (line, comp), (st, count) in sorted(used.items()):
        prov = st.provenance
        rules.append({"line": line, "component": comp + 1, "notation": prov["notation"], "name": prov["name"], "kind": prov["kind"],
                      "count": count})
    components = [{"component": c + 1, "forms": n} for c, n in sorted(forms.items())]
    return Measures(len(steps), max_len, max_len_step, rules, created, deleted, best_nt, best_nt_step if term is not None else None,
                    components)


def _plural(n: int, word: str) -> str:
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


def format_measures(m: Measures, indent: str = "    ") -> str:
    """Two short lines, as the command line prints them after a derivation."""
    parts = [_plural(m.steps, "step"), "longest form %s (step %d)" % (_plural(m.max_len, "symbol"), m.max_len_step)]
    if m.max_nonterminals is not None:
        parts.append("at most %s (step %d)" % (_plural(m.max_nonterminals, "non-terminal"), m.max_nonterminals_step))
    parts.append("%s created, %d deleted" % (_plural(m.created, "symbol"), m.deleted))
    several = len({r["component"] for r in m.rules}) > 1
    labels = [r["name"] or r["notation"] for r in m.rules]
    rules = ", ".join("%s (line %d)%s x%d" % (lab, r["line"],
                                      " (component %d)" % r["component"] if several else "", r["count"])
                      for lab, r in zip(labels, m.rules)) or "none"
    comps = ", ".join("%d (%s)" % (c["component"], _plural(c["forms"], "form")) for c in m.components)
    return "%smeasures: %s\n%srules: %s; components: %s\n" % (indent, ", ".join(parts), indent, rules, comps)


def model_terminals(model: Any) -> Optional[str]:
    """The internal characters of the terminals that the model declares (``terminals`` in ``[symbols]``), or None when it declares
    none, or declares them wrongly (the measures then leave the non-terminals out)."""
    from ._search import declared_terminals, terminal_chars

    if model.config.get("terminals") is None:
        return None
    try:
        return terminal_chars(model, declared_terminals(model))
    except GcrsimError:
        return None


def derivation_measures(steps: Sequence[Any], first: Optional[str], terminals: Optional[str], first_component: int = 0) -> Measures:
    """``measure`` for a derivation whose first form is ``first`` (None: the ``internal_source`` of the first step)."""
    if first is None:
        if not steps:
            raise GcrsimError("the first form of an empty derivation is needed: give it as first=")
        first, first_component = steps[0].internal_source, steps[0].source_component
    return measure(first, steps, terminals, first_component)


def measure_derivation(derivation: Sequence[Any], model: Any = None, terminals: Union[None, str, Sequence[str]] = None,
                       first: Union[None, str, Sequence[str]] = None, component: int = 1) -> Measures:
    """The measures of ``derivation``, a list of ``DerivationStep`` or ``ReplayStep``.

    ``model`` (a ``Model`` or the path of a model file) gives the terminals when ``terminals`` is None (the ``terminals`` of its
    ``[symbols]``, if declared); ``terminals`` is a string of symbols separated by white space or a list of symbol names. The
    first form is that of the first step; for a derivation without steps (an axiom) give it as ``first`` (a list of symbols, or
    text read as a word of ``model``) and its ``component`` (counted from 1). Without terminals, ``max_nonterminals`` is None."""
    from .model import Model, parse_model_file

    if model is not None and not isinstance(model, Model):
        model = parse_model_file(os.fspath(model))
    lexicon = model.lexicon if model is not None else (derivation[0].lexicon if derivation else None)
    chars: Optional[str] = None
    if terminals is not None:
        if lexicon is None:
            raise GcrsimError("terminals need a model (or a derivation with steps) to name the symbols")
        names = terminals.split() if isinstance(terminals, str) else list(terminals)
        chars = "".join(lexicon.encode(n) for n in names)
    elif model is not None:
        chars = model_terminals(model)
    internal: Optional[str] = None
    comp0 = component - 1
    if derivation:
        internal, comp0 = None, 0
        if first is not None:
            internal, comp0 = _encode_first(lexicon, first), component - 1
    else:
        if first is None:
            raise GcrsimError("the first form of an empty derivation is needed: give it as first=")
        if lexicon is None:
            raise GcrsimError("first= needs a model to read the symbols")
        internal = _encode_first(lexicon, first)
    return derivation_measures(list(derivation), internal, chars, comp0)


def _encode_first(lexicon: Any, first: Union[str, Sequence[str]]) -> str:
    if isinstance(first, str):
        return lexicon.encode_spaced(first)
    return "".join(lexicon.encode(s) for s in first)


def chain_measures(model: Any, chain: Sequence[Any], word: str, component: int, terminals: Optional[str] = None) -> Measures:
    """The measures of the derivation ``chain`` of the internal string ``word`` in ``component`` (counted from 0), as the command
    line computes them. An empty chain is an axiom: the word is the first form. ``terminals``: the internal characters of the
    terminals, or None for those that the model declares."""
    chars = model_terminals(model) if terminals is None else terminals
    if chain:
        return measure(chain[0].internal_source, chain, chars, chain[0].source_component)
    return measure(word, chain, chars, component)
