"""Search: is a word derivable in a component, and by which derivation?

The search is a breadth-first run of the simulator (the same engine, the same filters and limits) that stops after the step in which
the word appears in the component, and then reconstructs the derivation, so the witness is a shortest one in steps. It ends with
one of three outcomes:

* ``found`` (exit status 0): the word appeared at step ``n``; ``derivation`` is a derivation of it.
* ``not_found`` (status 6): the search covered everything within its bounds. The reason is ``frontier_exhausted`` (no string
  remains: every string within the bounds was explored) or ``depth_bound`` (the steps up to ``max_steps`` were all completed).
* ``inconclusive`` (status 3): a limit (``max-history``, ``max-step-candidates``, ``max-step-accepted``, ``max-retained``), the time
  limit or an interruption stopped it. A partial exploration is never reported as "not found".

Pruning. The terminals must be declared (``terminals`` in the model's ``[symbols]``, or the argument ``terminals``). When no rule
deletes or rewrites a terminal, a string whose terminals, in order, are not a subsequence of the terminals of the word can never
lead to the word, so it is dropped (sound pruning). The check of this condition is ``pruning_obstacle``; if it fails, or cannot be made,
pruning is off and the result says why. ``max_nonterminals`` is a restriction, not a sound pruning: a negative answer then holds only
within it. Components count from 1 in the arguments of this module and in the result; the internal strings of the simulator are
used inside.
"""

from __future__ import annotations

import copy
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from ._meta import NOT_FOUND_STATUS
from .engine import DerivationStep, Simulator
from .errors import GcrsimError, LimitReached, ModelError, TimeLimitReached
from .model import Model, parse_model_file
from .rules import ANY, RegexRule, SubRule
from .settings import Settings, apply_settings, settings_for_model
from .timelimit import Deadline, describe
from .lexicon import SEP
from .measures import Measures, measure
from .wordsep import check_word_sep, model_symbols

# the conditions that make a negative answer hold only under an assumption (in this order)
CONDITIONS = ("python_filter", "hash_history", "max_nonterminals", "max_len")


# ---------------------------------------------------------------------------
# Terminals and the soundness condition
# ---------------------------------------------------------------------------


def declared_terminals(model: Model, override: Union[None, str, Sequence[str]] = None) -> List[str]:
    """The terminals as symbol names: ``override`` (a string of symbols separated by white space, or a list of names) if given,
    otherwise the ``terminals`` of the model's ``[symbols]``. Not declared, or a name that is not a symbol of the model: a
    ``GcrsimError``."""
    if override is None:
        raw: Any = model.config.get("terminals")
        where = "the setting terminals of the model"
    else:
        raw, where = override, "the terminals"
    if raw is None:
        raise GcrsimError("the terminals are not declared: set `terminals = \"a b\"` in the [symbols] section of the model, "
                          "or give them with --terminals \"a b\" (search needs to know which symbols are terminals)")
    if isinstance(raw, str):
        names = raw.split()
    elif isinstance(raw, (list, tuple)) and all(isinstance(x, str) for x in raw):
        names = list(raw)  # an entry is one whole symbol name
    else:
        raise GcrsimError("%s must be a string of symbols separated by white space, or a list of symbols, not %r" % (where, raw))
    if not names:
        raise GcrsimError("%s declares no terminals (an empty set: name at least one symbol)" % where)
    lex = model.lexicon
    known = model_symbols(model)
    for rules in model.rules:  # the symbols that a regular-expression rule writes are symbols of the model too
        for r in rules:
            if isinstance(r, RegexRule):
                known = known | {lex.decode(ch) for part in r.parts if isinstance(part, str) for ch in part}
    out: List[str] = []
    for name in names:
        enc = lex.encode(name) if name and not any(lex.is_internal(ch) or ch == SEP for ch in name) else ""
        if len(enc) != 1 or lex.decode(enc) not in known:
            raise GcrsimError("%s: %r is not a symbol of the model" % (where, name))
        if name not in out:
            out.append(name)
    return out


def terminal_chars(model: Model, names: Sequence[str]) -> str:
    """The internal characters of the terminals (every symbol is one character)."""
    return "".join(model.lexicon.encode(n) for n in names)


def pruning_obstacle(model: Model, term_chars: str) -> Optional[str]:
    """None when no rule deletes or rewrites a terminal, so that pruning by the terminals is sound; otherwise the first reason
    why it is not, or cannot be checked, naming the rule. Only the part that a rule replaces or deletes (``x``) counts: the contexts,
    the guards, insertions and ``send()`` cannot remove a terminal. A class or ``{any}`` in that part, and a regular-expression rule,
    can match a terminal in a way that cannot be seen from the rule, so they make the check impossible."""
    terms = set(term_chars)
    decode = model.lexicon.decode
    for r in sorted((r for rules in model.rules for r in rules), key=lambda r: (r.line, r.index)):  # in the order of the file
        where = "rule %s (line %d)" % (r.name or r.notation, r.line)
        if isinstance(r, RegexRule):
            return "%s is a regular-expression rule: cannot be checked" % where
        if not isinstance(r, SubRule):
            continue  # send(): moves the string unchanged
        for item in r.Y:
            if isinstance(item, str):
                hit = next((ch for ch in item if ch in terms), None)
                if hit is not None:
                    return "%s %s the terminal %s" % (where, "deletes" if r.kind == "del" else "rewrites", decode(hit))
            elif item is ANY:
                return "%s has {any} in the part it replaces: cannot be checked" % where
            elif isinstance(item, frozenset):
                return "%s has a class in the part it replaces: cannot be checked" % where
    return None


def order_obstacle(settings: Settings) -> Optional[str]:
    """None, or why pruning is off because a function of the user may depend on the order of its calls: pruning changes which
    strings the function sees, and so what a function with state accepts. A function declared pure (``keep.pure = True``, or
    ``pure(...)``) cannot depend on it."""
    if settings.filter_next is not None and not getattr(settings.filter_next, "pure", False):
        return "the filter function keep is not declared pure (keep.pure = True): what it accepts may depend on the strings it has seen"
    for spec in (settings.filters or {}).values():
        for key in ("forbid", "require"):
            for f in spec.get(key, ()):
                if callable(f) and not getattr(f, "pure", False):
                    return "the function %s in the filters of a component is not declared pure: what it accepts may depend on the strings it has seen" % (
                        getattr(f, "__name__", repr(f)))
    return None


class Pruner:
    """The filter that the simulator applies to every batch of candidates before anything else: it keeps the strings whose terminals
    are a subsequence of the terminals of the word (``target``; None: no such test) and that have at most ``max_nonterminals``
    symbols that are not terminals (None: no limit). A symbol that is not a terminal counts as a non-terminal, so a regular-expression
    rule that produces any character cannot make a terminal of one."""

    def __init__(self, term_chars: str, target: Optional[str], max_nonterminals: Optional[int]):
        self._strip = re.compile("[^%s]+" % "".join(re.escape(c) for c in sorted(set(term_chars)))) if term_chars else re.compile(".+", re.S)
        self.target = None if target is None else "".join(ch for ch in target if ch in set(term_chars))
        self.max_nonterminals = max_nonterminals
        self._cache: Dict[str, bool] = {}  # the projections already tested (many strings share one)
        self.check: Optional[Callable[[], Any]] = None  # called now and then: the time limit

    def __call__(self, cands: Sequence[str]) -> List[str]:
        if self.check is not None:
            cands = self._polled(cands, self.check)
        strip = self._strip.sub
        word = self.target
        limit = self.max_nonterminals
        cache = self._cache
        out: List[str] = []
        for c in cands:
            proj = strip("", c)
            if limit is not None and len(c) - len(proj) > limit:
                continue
            if word is not None:
                ok = cache.get(proj)
                if ok is None:
                    ok = len(proj) <= len(word)
                    if ok:
                        it = iter(word)
                        ok = all(ch in it for ch in proj)  # a subsequence test: each symbol is looked for after the last one
                    if len(cache) > 200_000:
                        cache.clear()
                    cache[proj] = ok
                if not ok:
                    continue
            out.append(c)
        return out

    @staticmethod
    def _polled(cands: Sequence[str], check: Callable[[], Any]) -> Any:
        for n, c in enumerate(cands):
            if not n & 1023:
                check()
            yield c


# ---------------------------------------------------------------------------
# The result
# ---------------------------------------------------------------------------


class SearchResult:
    """The outcome of a search.

    ``outcome`` is ``found``, ``not_found`` or ``inconclusive``; ``reason`` is ``found``, ``frontier_exhausted`` or ``depth_bound`` for
    the first two, and ``limit``, ``time`` or ``interrupted`` for an inconclusive search (``limit`` is then the name of the limit,
    for example ``max-history``; otherwise None). ``found`` is true for a found word. ``step`` is the step at which the word
    appeared, or the last complete step. ``explored`` is the number of strings that entered the history. ``derivation`` is the
    list of ``DerivationStep`` (empty when nothing was found, or when the word is an axiom). ``bounds`` has ``max_steps``,
    ``max_nonterminals``, ``max_len`` (the model's ``reject_max_len``) and ``max_time`` (seconds), None where not set. ``pruning``
    says whether the pruning by the terminals was on, and ``pruning_note`` why it was not. ``conditional`` lists what makes a
    negative answer hold only under an assumption: ``python_filter``, ``hash_history``, ``max_nonterminals``, ``max_len``.
    ``measures`` are the measures of the derivation (``Measures``; None when not found). ``status`` is the exit status of the command line: 0, 6 or 3."""

    def __init__(self, outcome: str, reason: str, step: int, explored: int, derivation: List[DerivationStep], bounds: Dict[str, Any],
                 pruning: bool, pruning_note: Optional[str], conditional: List[str], limit: Optional[str] = None,
                 limit_value: Any = None, component: int = 1):
        self.outcome = outcome
        self.reason = reason
        self.limit = limit
        self.limit_value = limit_value
        self.step = step
        self.explored = explored
        self.derivation = derivation
        self.bounds = bounds
        self.pruning = pruning
        self.pruning_note = pruning_note
        self.conditional = conditional
        self.component = component
        self.limit_step = None  # the step that a limit stopped (0: the axioms)
        self.first: Optional[str] = None  # the internal first form of the derivation (set when found)
        self.terminals: Optional[str] = None  # the internal characters of the terminals
        self._measures: Optional[Measures] = None

    @property
    def measures(self) -> Optional[Measures]:
        """The ``Measures`` of the derivation found (None when nothing was found). The peak of non-terminals counts the first form,
        while the search does not apply ``max_nonterminals`` to the axioms."""
        if self._measures is None and self.found and self.first is not None:
            self._measures = measure(self.first, self.derivation, self.terminals,
                                      self.derivation[0].source_component if self.derivation else self.component - 1)
        return self._measures

    @property
    def found(self) -> bool:
        return self.outcome == "found"

    @property
    def status(self) -> int:
        return {"found": 0, "not_found": NOT_FOUND_STATUS}.get(self.outcome, 3)

    def to_dict(self) -> Dict[str, Any]:
        """The fields of the ``end`` object of ``--format jsonl``: ``status``, ``steps`` (the last complete step, or the step of
        the word), ``outcome``, ``reason``, ``limit``, ``explored``, ``bounds``, ``pruning`` (``on`` and ``reason``) and
        ``conditional``."""
        return {
            "status": self.status,
            "steps": self.step,
            "outcome": self.outcome,
            "reason": self.reason,
            "limit": self.limit,
            "explored": self.explored,
            "bounds": dict(self.bounds),
            "pruning": {"on": self.pruning, "reason": self.pruning_note},
            "conditional": list(self.conditional),
        }

    def __repr__(self) -> str:
        return "SearchResult(outcome=%r, reason=%r, step=%d, explored=%d)" % (self.outcome, self.reason, self.step, self.explored)


def _user_filter(settings: Settings) -> bool:
    """True if a function of the user can reject strings: the filter function, or a function in the filters of a component."""
    if settings.filter_next is not None:
        return True
    for spec in (settings.filters or {}).values():
        for key in ("forbid", "require"):
            if any(callable(f) for f in spec.get(key, ())):
                return True
    return False


# ---------------------------------------------------------------------------
# The search
# ---------------------------------------------------------------------------


class Search:
    """One search: ``Search(...).run()``. ``target`` is the internal string of the word and ``component`` counts from 1.

    The pruning decision is made when the object is made: ``pruning`` says whether the pruning by the terminals is on,
    ``pruning_note`` why it is not, and ``obstacle`` is the reason when the condition for sound pruning failed (a note for the
    user; None when pruning was only switched off, or is on)."""

    def __init__(self, model: Model, settings: Settings, target: str, component: int, terminals: str, *,
                 max_steps: Optional[int] = None, max_nonterminals: Optional[int] = None, deadline: Optional[Deadline] = None,
                 pruning: bool = True, write: Optional[Callable[[str], Any]] = None, max_step_candidates: Optional[int] = None,
                 max_history: Optional[int] = None, max_step_accepted: Optional[int] = None, max_retained: Optional[int] = None,
                 retain_store: Optional[Any] = None):
        self.model = model
        self.settings = settings
        self.target = target
        self.component = component
        self.max_steps = max_steps
        self.max_nonterminals = max_nonterminals
        self.deadline = deadline
        self.write = write
        self.limits = {"max_step_candidates": max_step_candidates, "max_history": max_history,
                       "max_step_accepted": max_step_accepted, "max_retained": max_retained}
        self.retain_store = retain_store
        self.terminals = terminals
        self.obstacle = (pruning_obstacle(model, terminals) or order_obstacle(settings)) if pruning else None
        self.pruning = pruning and self.obstacle is None
        self.pruning_note: Optional[str] = None if self.pruning else (self.obstacle or "switched off by the user")
        self.pruner: Optional[Pruner] = None
        if self.pruning or max_nonterminals is not None:
            self.pruner = Pruner(terminals, target if self.pruning else None, max_nonterminals)

    def bounds(self) -> Dict[str, Any]:
        st = self.settings
        return {"max_steps": self.max_steps, "max_nonterminals": self.max_nonterminals, "max_len": st.reject_max_len,
                "max_time": None if self.deadline is None else self.deadline.seconds}

    def conditions(self) -> List[str]:
        st = self.settings
        found = {"python_filter": _user_filter(st), "hash_history": bool(st.hash_history and st.history),
                 "max_nonterminals": self.max_nonterminals is not None, "max_len": st.reject_max_len is not None}
        return [c for c in CONDITIONS if found[c]]

    def run(self, on_step: Optional[Callable[[Simulator], Any]] = None) -> SearchResult:
        """Run the search. ``on_step(sim)`` is called after every completed step."""
        sim: Optional[Simulator] = None
        comp = self.component - 1
        try:
            sim = Simulator(self.model, self.settings, write=self.write, retain=True, retain_store=self.retain_store,
                            deadline=self.deadline, prune=self.pruner, **self.limits)
            dl = self.deadline
            if dl is not None and self.pruner is not None:
                live = sim
                self.pruner.check = lambda: live._time_limit(live.step_no + 1) if dl.expired() else None
            if dl is not None and dl.expired():
                sim._time_limit(sim.step_no + 1)  # no answer, not even about an axiom, after the time is up
            if self.target in sim.cur[comp]:
                return self._found(sim)
            while True:
                if not any(sim.cur):
                    return self._final(sim, "not_found", "frontier_exhausted")
                if self.max_steps is not None and sim.step_no >= self.max_steps:
                    return self._final(sim, "not_found", "depth_bound")
                sim.step()
                if on_step is not None:
                    on_step(sim)
                if self.target in sim.cur[comp]:
                    return self._found(sim)
        except TimeLimitReached:
            return self._done(sim, "inconclusive", "time")
        except LimitReached as exc:
            return self._done(sim, "inconclusive", "limit", exc.limit, exc.value, exc.step)
        except KeyboardInterrupt:
            return self._done(sim, "inconclusive", "interrupted")

    def _explored(self, sim: Optional[Simulator]) -> int:
        """The strings that entered the history; without a history, the candidates generated so far."""
        if sim is None:
            return sum(len(a) for a in self.model.axioms)
        return sim.hist_count if self.settings.history else sim.total_candidates

    def _done(self, sim: Optional[Simulator], outcome: str, reason: str, limit: Optional[str] = None,
              limit_value: Any = None, limit_step: Optional[int] = None) -> SearchResult:
        res = SearchResult(outcome, reason, 0 if sim is None else sim.step_no, self._explored(sim), [], self.bounds(),
                           self.pruning, self.pruning_note, self.conditions(), limit, limit_value, self.component)
        res.limit_step = limit_step
        return res

    def _final(self, sim: Simulator, outcome: str, reason: str) -> SearchResult:
        """A found or not found outcome, unless the time is up: a search whose time limit has passed never answers."""
        if self.deadline is not None and self.deadline.expired():
            return self._done(sim, "inconclusive", "time")
        return self._done(sim, outcome, reason)

    def _found(self, sim: Simulator) -> SearchResult:
        comp = self.component - 1
        chain: List[DerivationStep] = []
        if self.deadline is not None and self.deadline.expired():
            return self._done(sim, "inconclusive", "time")
        if sim.step_no > 0:
            chain = sim._trace_many([(comp, self.target, sim.step_no)])[0]  # the encoded word: symbol boundaries are kept
            if sim.lexicon.has_lexemes:
                for d in chain:
                    d.source, d.result = sim.lexicon.decode(d.internal_source), sim.lexicon.decode(d.internal_result)
        res = self._final(sim, "found", "found")
        if res.found:
            res.derivation = chain
            res.first = chain[0].internal_source if chain else self.target
            res.terminals = self.terminals
        return res


# ---------------------------------------------------------------------------
# Reading the arguments
# ---------------------------------------------------------------------------


def read_target(model: Model, text: str, word_sep: str = "") -> str:
    """The internal string of the word to search for, read like the word of ``--trace``: symbols written together (read with the
    alphabet and the lexemes of the model) or separated by ``word_sep``; white space is then an ordinary character. A symbol
    outside the alphabet is a ``GcrsimError``."""
    lex = model.lexicon
    try:
        encoded = lex.encode_spaced(text, word_sep, whitespace=False)
        lex.check(encoded, "the word")
    except ModelError as exc:
        raise GcrsimError(str(exc)) from None
    return encoded


def check_options(model: Model, component: int, max_steps: Optional[int], max_nonterminals: Optional[int]) -> None:
    if not (1 <= component <= model.ncomp):
        raise GcrsimError("the component must be between 1 and %d, not %d" % (model.ncomp, component))
    if max_steps is not None and max_steps < 0:
        raise GcrsimError("--max-steps cannot be negative")
    if max_nonterminals is not None and max_nonterminals < 0:
        raise GcrsimError("--max-nonterminals cannot be negative")


def search(model: Union[Model, str, "os.PathLike[str]"], word: str, *, component: int = 1,
           terminals: Union[None, str, Sequence[str]] = None, max_steps: Optional[int] = None,
           max_nonterminals: Optional[int] = None, max_time: Optional[float] = None, pruning: bool = True,
           keep: Optional[Callable[..., Any]] = None, word_sep: Optional[str] = None, settings: Optional[Settings] = None,
           max_step_candidates: Optional[int] = None, max_history: Optional[int] = None, max_step_accepted: Optional[int] = None,
           max_retained: Optional[int] = None) -> SearchResult:
    """Search for ``word`` in ``component`` (counted from 1) of ``model`` (a ``Model`` or the path of a model file), breadth first.

    ``terminals`` (a string of symbols separated by white space, or a list of names; None: the ``terminals`` of the model's
    ``[symbols]``) must be given one way or the other (``GcrsimError`` otherwise). ``max_steps`` is the depth bound,
    ``max_nonterminals`` a cap on the number of non-terminals in a string (a restriction: a negative answer then holds only
    within it), ``max_time`` a time limit in seconds, ``pruning`` false turns the pruning by the terminals off. ``keep`` is a
    filter function ``keep(s, component[, ctx])`` as in a Python configuration (it runs after the built-in pruning and makes a
    negative answer conditional). ``settings`` are the settings of the run (None: those of the model); ``word_sep`` separates the
    symbols of ``word`` (None: ``settings.word_sep``). The limits ``max_step_candidates``, ``max_history``, ``max_step_accepted``
    and ``max_retained`` stop the search as in a run (the result is then inconclusive). Returns a ``SearchResult``; an interrupted
    search is also a result."""
    started = time.perf_counter()  # the clock of max_time starts here, before the model is read
    if not isinstance(model, Model):
        model = parse_model_file(os.fspath(model))
    st = copy.copy(settings) if settings is not None else settings_for_model(model)
    if keep is not None:
        apply_settings(st, {"filter_next": keep}, "keep")
    if word_sep is None:
        word_sep = st.word_sep
    deadline = None
    if max_time is not None:
        if isinstance(max_time, bool) or not isinstance(max_time, (int, float)) or not 0 < max_time < float("inf"):
            raise GcrsimError("max_time must be a positive number of seconds, not %r" % (max_time,))
        deadline = Deadline(float(max_time), started)
    check_options(model, component, max_steps, max_nonterminals)
    chars = terminal_chars(model, declared_terminals(model, terminals))
    check_word_sep(model, word_sep)
    target = read_target(model, word, word_sep)
    return Search(model, st, target, component, chars, max_steps=max_steps, max_nonterminals=max_nonterminals, deadline=deadline,
                  pruning=pruning, write=lambda text: None, max_step_candidates=max_step_candidates, max_history=max_history,
                  max_step_accepted=max_step_accepted, max_retained=max_retained).run()


# ---------------------------------------------------------------------------
# The text of the outcome
# ---------------------------------------------------------------------------

_CONDITION_TEXT = {
    "python_filter": "the Python filter",
    "hash_history": "hash_history (digests may collide)",
}


def outcome_text(res: SearchResult, word: str) -> str:
    """The final block of the text format: the outcome in one line and, indented, what was explored, the bounds and the conditions."""
    w = "'%s'" % word if word else "the empty word"
    last = "last complete step %d" % res.step
    if res.outcome == "found":
        head = "found %s in component %d at step %d" % (w, res.component, res.step)
    elif res.outcome == "not_found":
        if res.reason == "frontier_exhausted":
            head = "not found: no strings remain after step %d" % res.step
        else:
            head = "not found: no derivation of at most %d steps" % res.step
    elif res.reason == "time":
        head = "inconclusive: the time limit (%s) stopped step %d; %s" % (describe(res.bounds["max_time"]), res.step + 1, last)
    elif res.reason == "limit" and res.limit_step == 0:
        head = "inconclusive: the limit %s (%s) was reached by the axioms (step 0)" % (res.limit, res.limit_value)
    elif res.reason == "limit":
        head = "inconclusive: the limit %s (%s) stopped step %d; %s" % (res.limit, res.limit_value, res.step + 1, last)
    else:
        head = "inconclusive: interrupted during step %d; %s" % (res.step + 1, last)
    lines = ["search: " + head]
    lines.append("        explored %d strings; pruning %s" % (res.explored, "on" if res.pruning else "off (%s)" % res.pruning_note))
    b = res.bounds
    shown = []
    if b["max_steps"] is not None:
        shown.append("at most %d steps" % b["max_steps"])
    if b["max_nonterminals"] is not None:
        shown.append("at most %d non-terminals in the strings derived (the axioms are not tested)" % b["max_nonterminals"])
    if b["max_len"] is not None:
        shown.append("strings of at most %d symbols" % b["max_len"])
    if b["max_time"] is not None:
        shown.append("time limit %s" % describe(b["max_time"]))
    if shown:
        lines.append("        bounds: " + "; ".join(shown))
    if res.conditional:
        what = [_CONDITION_TEXT.get(c) or "" for c in res.conditional]
        what = [t for t in what if t]
        if "max_nonterminals" in res.conditional:
            what.append("the cap on non-terminals")
        if "max_len" in res.conditional:
            what.append("the length bound")
        lines.append("        %s %s" % ("the answer holds only under:" if res.outcome == "not_found" else "conditions:", "; ".join(what)))
    return "\n".join(lines) + "\n"
