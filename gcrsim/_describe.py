"""Describe a model without running it: its rules by kind, its insertion-deletion size, its symbols and its control graph."""

from __future__ import annotations

import os
import textwrap
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Union

from ._search import header_terminals
from .model import Model, parse_model_file
from .ranges import binding_suffix
from .rules import ANY, END, START, RegexRule, SubRule
from .wordsep import model_symbols

KINDS = ("ins", "del", "sub", "plain", "send", "re")


def _count(items: Sequence[Any]) -> int:
    """The number of symbols an operand matches: a symbol, a class or ``{any}`` is one, ``{start}`` and ``{end}`` are none."""
    return sum(0 if (item is START or item is END) else 1 for item in items)


def _kind_counts(rules: Sequence[Any]) -> Dict[str, int]:
    c = Counter(rule.kind for rule in rules)
    return {k: c.get(k, 0) for k in KINDS}


def _size(rules: Sequence[Any]) -> Dict[str, Any]:
    """The insertion-deletion size of a set of rules (the guards are ignored)."""
    kinds = _kind_counts(rules)
    ins: Optional[Dict[str, int]] = None
    dele: Optional[Dict[str, int]] = None
    for rule in rules:
        if rule.kind == "ins" and isinstance(rule, SubRule):
            ins = ins or {"n": 0, "m": 0, "m_right": 0}
            ins["n"] = max(ins["n"], len(rule.x))
            ins["m"] = max(ins["m"], _count(rule.U))
            ins["m_right"] = max(ins["m_right"], _count(rule.V))
        elif rule.kind == "del" and isinstance(rule, SubRule):
            dele = dele or {"p": 0, "q": 0, "q_right": 0}
            dele["p"] = max(dele["p"], _count(rule.Y))
            dele["q"] = max(dele["q"], _count(rule.U))
            dele["q_right"] = max(dele["q_right"], _count(rule.V))
    other = [k for k in ("sub", "plain", "re") if kinds[k]]
    return {"insdel": not other, "other_kinds": other, "ins": ins, "del": dele}


def _triple(part: Optional[Dict[str, int]], keys: Sequence[str]) -> str:
    return ",".join(str(part[k]) if part else "0" for k in keys)


def size_tuple(size: Dict[str, Any]) -> str:
    """``(n,m,m';p,q,q')``."""
    return "(%s;%s)" % (_triple(size["ins"], ("n", "m", "m_right")), _triple(size["del"], ("p", "q", "q_right")))


@dataclass
class Description:
    """What a model is made of. ``rules``, ``size``, ``components``, ``symbols`` and ``notes`` are the groups of ``to_dict()``."""

    model: str
    rules: Dict[str, Any]
    size: Dict[str, Any]
    components: List[Dict[str, Any]]
    symbols: Dict[str, Any]
    notes: List[str] = field(default_factory=list)
    expansions: List[Dict[str, Any]] = field(default_factory=list)
    ranges: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"rules": self.rules, "size": self.size, "components": self.components, "symbols": self.symbols,
                "notes": list(self.notes), "ranges": self.ranges, "expansions": self.expansions}

    def text(self) -> str:
        return _text(self)


def describe(model: Union[Model, str, "os.PathLike[str]"]) -> Description:
    """Describe a model (a ``Model`` or the path of a model file) without running it."""
    if not isinstance(model, Model):
        model = parse_model_file(os.fspath(model))
    lex = model.lexicon
    allrules = [r for comp in model.rules for r in comp]
    notes: List[str] = []
    rules = {"count": len(allrules), "by_kind": _kind_counts(allrules), "with_conditions": sum(1 for r in allrules if r.guarded)}
    size = _size(allrules)
    if size["other_kinds"]:
        notes.append("not an insertion-deletion system: it has %s rules" % ", ".join(size["other_kinds"]))
    if rules["with_conditions"]:
        notes.append("%d rule%s with conditions (permit/forbid); the size ignores them" % (
            rules["with_conditions"], "" if rules["with_conditions"] == 1 else "s"))
    if size["insdel"] and size["ins"] is None and size["del"] is not None:
        notes.append("no insertion rules")
    if size["insdel"] and size["del"] is None and size["ins"] is not None:
        notes.append("no deletion rules")

    components = []
    for c, comp in enumerate(model.rules):
        targets = Counter(r.target + 1 for r in comp)
        components.append({"component": c + 1, "rules": len(comp), "by_kind": _kind_counts(comp), "size": _size(comp),
                           "targets": [{"target": t, "rules": n} for t, n in sorted(targets.items())],
                           "axioms": len(model.axioms[c])})

    inserted, deleted = set(), set()
    any_deleted = False
    for r in allrules:
        if not isinstance(r, SubRule):
            continue
        if r.kind in ("ins", "sub", "plain"):
            inserted.update(lex.decode(ch) for ch in r.x)
        if r.kind in ("del", "sub", "plain"):
            for item in r.Y:
                if isinstance(item, str):
                    deleted.add(lex.decode(item))
                elif isinstance(item, frozenset):  # a class
                    deleted.update(lex.decode(ch) for ch in item)
                elif item is ANY:
                    any_deleted = True
    universe = set(model_symbols(model)) | inserted | deleted
    for r in allrules:  # the symbols that a regular-expression rule writes are symbols of the model too
        if isinstance(r, RegexRule):
            universe.update(lex.decode(ch) for part in r.parts if isinstance(part, str) for ch in part)
    if lex.alphabet_order is not None:
        rank = {s: i for i, s in enumerate(lex.alphabet_order)}

        def order(ss: Any) -> List[str]:
            return sorted(ss, key=lambda s: (rank.get(s, len(rank)), s))
    else:
        def order(ss: Any) -> List[str]:
            return sorted(ss)
    has_re = any(r.kind == "re" for r in allrules)
    if has_re:
        notes.append("roles of the symbols are approximate: the regular-expression rules are not analysed")
    if any_deleted:
        notes.append("roles of the symbols are approximate: {any} in a deleted part stands for any symbol")
    symbols = {"count": len(universe), "declared": lex.alphabet is not None, "terminals": header_terminals(model),
               "roles": {"inserted_only": order(inserted - deleted), "deleted_only": order(deleted - inserted),
                         "inserted_and_deleted": order(inserted & deleted),
                         "never_edited": order(universe - inserted - deleted)},
               "roles_exact": not (has_re or any_deleted)}
    return Description(model.path, rules, size, components, symbols, notes, _expansions(model, allrules),
                       {name: [lo, hi] for name, (lo, hi) in model.ranges.items()})


def _expansions(model: Model, allrules: Sequence[Any]) -> List[Dict[str, Any]]:
    """The rule lines that use ranges: the line as written, the ranges it uses and the rules it generates (in the order of the model)."""
    groups: Dict[int, Dict[str, Any]] = {}
    for r in sorted((r for r in allrules if r.bindings is not None), key=lambda r: r.index):
        g = groups.get(r.line)
        if g is None:
            g = groups[r.line] = {"line": r.line, "notation": r.source_notation, "name": r.name,
                                  "ranges": {k: list(model.ranges[k]) for k in r.bindings}, "rules": []}
        g["rules"].append({"notation": r.notation, "bindings": dict(r.bindings), "component": r.source + 1, "target": r.target + 1})
    return list(groups.values())


def _plural(n: int, word: str) -> str:
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


def _wrap(label: str, items: Sequence[str]) -> List[str]:
    body = " ".join(items) if items else "(none)"
    return textwrap.wrap(body, width=100, initial_indent="  %s: " % label, subsequent_indent="      ",
                         break_long_words=False, break_on_hyphens=False)


def _size_lines(size: Dict[str, Any]) -> List[str]:
    lines = []
    if size["ins"]:
        i = size["ins"]
        lines.append("  ins: inserted %s; left context %d, right context %d" % (_plural(i["n"], "symbol"), i["m"], i["m_right"]))
    if size["del"]:
        d = size["del"]
        lines.append("  del: deleted %s; left context %d, right context %d" % (_plural(d["p"], "symbol"), d["q"], d["q_right"]))
    return lines


def _text(d: Description) -> str:
    r, s = d.rules, d.symbols
    kinds = ", ".join("%d %s" % (n, k) for k, n in r["by_kind"].items() if n)
    out = ["model %s: %s, %s%s" % (d.model, _plural(len(d.components), "component"), _plural(r["count"], "rule"),
                                   " (%s)" % kinds if kinds else "")]
    size = d.size
    if size["other_kinds"]:
        out.append("not an insertion-deletion system (it has %s rules)" % ", ".join(size["other_kinds"]))
        if size["ins"] or size["del"]:
            out.append("size of its insertion and deletion rules (n,m,m';p,q,q') %s" % size_tuple(size))
    else:
        out.append("insertion-deletion size (n,m,m';p,q,q') %s" % size_tuple(size))
    out.extend(_size_lines(size))
    if size["ins"] is None and size["del"] is not None:
        out.append("  no insertion rules")
    if size["del"] is None and size["ins"] is not None:
        out.append("  no deletion rules")
    if r["with_conditions"]:
        out.append("with conditions: %s (the size ignores them)" % _plural(r["with_conditions"], "rule"))
    if len(d.components) > 1:
        for c in d.components:
            if c["size"]["ins"] or c["size"]["del"]:
                out.append("component %d: size %s" % (c["component"], size_tuple(c["size"])))
    terms = " ".join(s["terminals"]) + " (declared)" if s["terminals"] else "not declared"
    out.append("symbols: %d (%s); terminals: %s" % (s["count"], "declared alphabet" if s["declared"] else "found in the model", terms))
    roles = s["roles"]
    for label, key in (("only inserted", "inserted_only"), ("only deleted", "deleted_only"),
                       ("inserted and deleted", "inserted_and_deleted"), ("never edited", "never_edited")):
        out.extend(_wrap(label, roles[key]))
    if not s["roles_exact"]:
        out.append("  (the roles are approximate: " + "; ".join(n.split(": ", 1)[1] for n in d.notes if n.startswith("roles")) + ")")
    if d.expansions:
        total = sum(len(g["rules"]) for g in d.expansions)
        out.append("ranges: %s" % ", ".join("%s=%d..%d" % (k, lo, hi) for k, (lo, hi) in d.ranges.items()))
        out.append("%s with ranges, giving %s:" % (_plural(len(d.expansions), "rule line"), _plural(total, "rule")))
        for g in d.expansions:
            used = ", ".join("%s=%d..%d" % (k, lo, hi) for k, (lo, hi) in g["ranges"].items())
            out.append("  line %d: %s%s (%s): %s" % (g["line"], g["notation"], "" if g["name"] is None else ";name:" + g["name"], used,
                                                     _plural(len(g["rules"]), "rule")))
            for r in g["rules"]:
                label = "" if g["name"] is None else g["name"]
                out.append("    %s%s  %s" % (label, binding_suffix(r["bindings"]), r["notation"]))
    for c in d.components:
        moves = ", ".join("%d -> %d: %s" % (c["component"], t["target"], _plural(t["rules"], "rule")) for t in c["targets"])
        out.append("component %d: %s; axioms: %d" % (c["component"], moves or "no rules", c["axioms"]))
    return "\n".join(out) + "\n"
