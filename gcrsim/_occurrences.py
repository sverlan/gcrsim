"""Occurrence identities along a derivation (private helper, reads the step records only).

``occurrences(steps, first=None, first_component=None)`` follows the symbols of a derivation: every symbol occurrence of the
first form and every symbol that a step inserts gets an identity (an integer, in the order of creation), and each step is
recorded as an event: the occurrences it consumed, those it produced and the occurrences matched by the contexts of the rule.
``steps`` are ``DerivationStep`` or ``ReplayStep`` objects; the first form is that of the first step, or, for a derivation
without steps, given as ``first`` (a list of symbol names) with its component.

Identity rules
--------------
* A step replaces the interval ``[start, end)`` of its ``before`` form by the ``inserted`` symbols. Occurrences outside the
  interval keep their identity, those inside are consumed, the inserted symbols are new occurrences. This holds for ``ins``,
  ``del``, ``sub`` and plain rules. ``send`` edits nothing: every occurrence keeps its identity, only the component changes.
* ``re`` rules: the interval and the symbols removed and inserted still define consumed and produced occurrences, but text that
  the replacement copies from a capture has no identity link to its source, and the contexts are unknown (the event has
  ``supported == False`` and a ``note``).
* Contexts: ``left_context`` are the occurrences matched by ``u``, the ``len(u)`` symbols just before ``start``; ``right_context``
  those matched by ``v``, just after ``end``. Every operand item (a symbol, a class ``{NAME}``, ``{any}``) is one occurrence;
  ``{start}`` and ``{end}`` are zero-width and match no occurrence. Rules without ``u`` and ``v`` (plain, send) have no context.
* ``order`` is one left-to-right row of all occurrences ever present (erased ones stay in it). A new occurrence is placed
  - for a replacement (the step consumes something and produces something), right after the last consumed occurrence;
  - otherwise, when the rule has a left context, right after the last occurrence of that context;
  - otherwise right before the first occurrence that follows the edit place in the current string (the first occurrence of the
    right context, when there is one); at the end of the row when nothing follows.
  Inserted symbols of one step stay together, in their order.
* The invariant ``[symbol of id for id in form] == after`` is checked at every step; a failure, or a context that does not fit in
  the string, raises ``OccurrenceError`` (an internal error: the records are inconsistent).
* A step that the record says could be applied in several ways (``ReplayStep.ways > 1``) follows the application that the record
  holds (its first rule and position) and is marked ``ambiguous``; ``DerivationStep`` records are never marked.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

ZERO_WIDTH = ("{start}", "{end}")
_EXACT_KINDS = ("plain", "ins", "del", "sub", "send")


class OccurrenceError(Exception):
    """The step records do not describe a consistent derivation (an internal error)."""


class Node:
    """One occurrence: ``id``, ``symbol``, ``created`` (step number; 0 for the first form), ``deleted`` (step number or None) and
    ``created_component`` (the component of the form in which it appeared, counted from 0)."""

    __slots__ = ("id", "symbol", "created", "deleted", "created_component")

    def __init__(self, id: int, symbol: str, created: int, created_component: int):
        self.id = id
        self.symbol = symbol
        self.created = created
        self.deleted: Optional[int] = None
        self.created_component = created_component

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "symbol": self.symbol, "created": self.created, "deleted": self.deleted,
                "created_component": self.created_component + 1}


class Form:
    """A form of the derivation: the ``ids`` of its occurrences, left to right, and its ``component`` (from 0)."""

    __slots__ = ("ids", "component")

    def __init__(self, ids: List[int], component: int):
        self.ids = ids
        self.component = component

    def to_dict(self) -> Dict[str, Any]:
        return {"ids": list(self.ids), "component": self.component + 1}


class Event:
    """One step: ``step`` (its number), ``kind`` of rule, the ``rule`` provenance, ``source_component`` and ``target_component``
    (from 0), the ids ``consumed`` and ``produced``, ``left_context`` and ``right_context``, ``supported`` (identities are exact;
    False for ``re`` rules), ``note`` (None, or why they are not exact) and ``ambiguous``."""

    __slots__ = ("step", "kind", "rule", "source_component", "target_component", "consumed", "produced", "left_context",
                 "right_context", "supported", "note", "ambiguous")

    def __init__(self, step, kind, rule, source_component, target_component, consumed, produced, left_context, right_context,
                 supported, note, ambiguous):
        self.step = step
        self.kind = kind
        self.rule = rule
        self.source_component = source_component
        self.target_component = target_component
        self.consumed = consumed
        self.produced = produced
        self.left_context = left_context
        self.right_context = right_context
        self.supported = supported
        self.note = note
        self.ambiguous = ambiguous

    def to_dict(self) -> Dict[str, Any]:
        return {"step": self.step, "kind": self.kind, "rule": self.rule,
                "source_component": self.source_component + 1, "target_component": self.target_component + 1,
                "consumed": list(self.consumed), "produced": list(self.produced),
                "left_context": list(self.left_context), "right_context": list(self.right_context),
                "supported": self.supported, "note": self.note, "ambiguous": self.ambiguous}


class OccurrenceTrace:
    """The occurrences of a derivation: ``nodes`` (a ``Node`` per occurrence, indexed by id), ``order`` (all ids in one row),
    ``forms`` (a ``Form`` for the first form and one for each step), ``events`` (an ``Event`` per step) and ``survivors`` (the
    ids of the last form)."""

    __slots__ = ("nodes", "order", "forms", "events", "survivors")

    def __init__(self, nodes: List[Node], order: List[int], forms: List[Form], events: List[Event], survivors: List[int]):
        self.nodes = nodes
        self.order = order
        self.forms = forms
        self.events = events
        self.survivors = survivors

    def to_dict(self) -> Dict[str, Any]:
        return {"nodes": [n.to_dict() for n in self.nodes], "order": list(self.order),
                "forms": [f.to_dict() for f in self.forms], "events": [e.to_dict() for e in self.events],
                "survivors": list(self.survivors)}


def _width(items: Optional[Sequence[str]]) -> int:
    """The number of occurrences that an operand matches (zero-width items match none)."""
    return 0 if not items else sum(1 for it in items if it not in ZERO_WIDTH)


def occurrences(steps: Sequence[Any], first: Optional[Sequence[str]] = None, first_component: Optional[int] = None) -> OccurrenceTrace:
    """The ``OccurrenceTrace`` of the derivation that starts with the form ``first`` (a list of symbol names; None: the ``before``
    of the first step) in component ``first_component`` (from 0; None: the source component of the first step, or 0) and goes on
    with ``steps``."""
    steps = list(steps)
    if first is None:
        if not steps:
            raise OccurrenceError("the first form of an empty derivation is needed: give it as first=")
        first = steps[0].before
    if first_component is None:
        first_component = steps[0].source_component if steps else 0
    nodes: List[Node] = [Node(i, s, 0, first_component) for i, s in enumerate(first)]
    cur = list(range(len(nodes)))
    order = list(cur)
    forms = [Form(list(cur), first_component)]
    events: List[Event] = []
    prev_component = first_component

    for st in steps:
        number = st.step if hasattr(st, "step") else st.index
        rec = st._record()
        before, after, inserted = rec["before"], rec["after"], rec["inserted"]
        start, end, prov = rec["start"], rec["end"], rec["rule"]
        kind = prov["kind"]
        if [nodes[i].symbol for i in cur] != before:
            raise OccurrenceError("step %s does not continue the previous form" % number)
        if st.source_component != prev_component:
            raise OccurrenceError("step %s starts in component %d, the previous form is in %d"
                                  % (number, st.source_component + 1, prev_component + 1))
        if not 0 <= start <= end <= len(cur):
            raise OccurrenceError("step %s: the edit [%d, %d) does not fit the form" % (number, start, end))

        note: Optional[str] = None
        supported = True
        if kind == "re":
            supported = False
            note = "regular expression: text copied by the replacement has no identity link; contexts unknown"
            lw = rw = 0
        elif kind in _EXACT_KINDS:
            lw, rw = _width(prov.get("u")), _width(prov.get("v"))
        else:
            supported = False
            note = "unknown kind of rule %r: contexts unknown" % kind
            lw = rw = 0
        if start - lw < 0 or end + rw > len(cur):
            raise OccurrenceError("step %s: the context does not fit the form" % number)
        left = cur[start - lw:start]
        right = cur[end:end + rw]
        consumed = cur[start:end]

        new = list(range(len(nodes), len(nodes) + len(inserted)))
        target = st.target_component
        for sym, nid in zip(inserted, new):
            nodes.append(Node(nid, sym, number, target))
        for nid in consumed:
            nodes[nid].deleted = number

        if new:
            if consumed:
                at = order.index(consumed[-1]) + 1
            elif left:
                at = order.index(left[-1]) + 1
            elif end < len(cur):
                at = order.index(cur[end])
            else:
                at = len(order)
            order[at:at] = new
        cur[start:end] = new
        if [nodes[i].symbol for i in cur] != after:
            raise OccurrenceError("step %s: the occurrences do not give the form after the step" % number)

        events.append(Event(number, kind, prov, st.source_component, target, consumed, new, left, right, supported, note,
                            getattr(st, "ways", 1) > 1))
        forms.append(Form(list(cur), target))
        prev_component = target

    return OccurrenceTrace(nodes, order, forms, events, list(cur))
