"""List terminal words from the completed frontiers of a simulation."""

from __future__ import annotations

import copy
import os
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Union

from ._search import Pruner, check_options, declared_terminals, terminal_chars
from .engine import Simulator, _undeclared_functions
from .errors import GcrsimError, LimitReached, TimeLimitReached
from .model import Model, parse_model_file
from .pattern import compile_pattern
from .settings import Settings, apply_settings, settings_for_model
from .timelimit import Deadline


@dataclass
class LanguageResult:
    """The listed words as symbol arrays, observed counts by symbol length, and the outcome of the exploration.

    A complete result covers the selected component of the effective configured model under the stated
    restrictions and word selection. A partial result contains the words collected so far.
    """

    component: int
    bounds: Dict[str, Any]
    words: List[List[str]] = field(default_factory=list)
    counts: Dict[int, int] = field(default_factory=dict)
    steps: int = 0
    outcome: str = "partial"
    reason: str = "interrupted"
    detail: str = "interrupted"
    restrictions: Dict[str, Any] = field(default_factory=dict)
    limit: Optional[str] = None

    @property
    def status(self) -> int:
        return 0 if self.outcome == "complete" else 3

    def to_dict(self) -> Dict[str, Any]:
        """The result metadata, also used in the JSONL end record. Each word has its own record."""
        return {"status": self.status, "steps": self.steps, "component": self.component,
                "outcome": self.outcome, "reason": self.reason, "detail": self.detail, "limit": self.limit,
                "counts": dict(self.counts), "bounds": dict(self.bounds), "restrictions": dict(self.restrictions)}


def listing_result(max_len: int, pattern: Optional[str], component: int, max_steps: Optional[int],
                   max_nonterminals: Optional[int], deadline: Optional[Deadline],
                   max_step_candidates: Optional[int], max_history: Optional[int],
                   max_step_accepted: Optional[int]) -> LanguageResult:
    bounds = {"max_word_len": max_len, "pattern": pattern, "max_steps": max_steps, "max_nonterminals": max_nonterminals,
              "max_time": deadline.seconds if deadline is not None else None, "max_step_candidates": max_step_candidates,
              "max_history": max_history, "max_step_accepted": max_step_accepted}
    for key in ("max_word_len", "max_steps", "max_nonterminals", "max_step_candidates", "max_history", "max_step_accepted"):
        value = bounds[key]
        if value is None and key != "max_word_len":
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise GcrsimError("--%s must be a nonnegative integer, not %r" % (key.replace("_", "-"), value))
    if isinstance(component, bool) or not isinstance(component, int):
        raise GcrsimError("the component must be an integer, not %r" % (component,))
    if pattern is not None and not isinstance(pattern, str):
        raise GcrsimError("--match must be a regular expression string, not %r" % (pattern,))
    return LanguageResult(component, bounds)


def collect_language(model: Model, settings: Settings, result: LanguageResult, terminals: Union[None, str, Sequence[str]],
                     deadline: Optional[Deadline], *, write: Optional[Callable[[str], Any]] = None,
                     on_step: Optional[Callable[[Simulator], Any]] = None) -> LanguageResult:
    bounds = result.bounds
    max_steps, cap = bounds["max_steps"], bounds["max_nonterminals"]
    check_options(model, result.component, max_steps, cap)
    names = declared_terminals(model, terminals, operation="language listing")
    bounds["terminals"] = names
    chars = terminal_chars(model, names)
    terminal_set = set(chars)
    pattern = bounds["pattern"]
    try:
        match = compile_pattern(pattern, model.lexicon).fullmatch if pattern is not None else None
    except (re.error, ValueError, OverflowError, RecursionError) as exc:
        raise GcrsimError("bad --match regular expression %r: %s" % (pattern, exc)) from None

    restrictions = {
        "reject_max_len": settings.reject_max_len, "reject_strings": settings.reject_strings,
        "component_filters": [key for key, spec in (settings.filters or {}).items() if any(spec.values())],
        "python_filter": settings.filter_next is not None, "max_nonterminals": cap,
        "history": bool(settings.history), "hash_history": bool(settings.history and settings.hash_history),
    }
    result.restrictions = restrictions
    limits = {key: bounds[key] for key in ("max_step_candidates", "max_history", "max_step_accepted")}
    pruner = Pruner(chars, None, cap) if cap is not None else None
    found: Set[str] = set()
    component = result.component - 1
    collected_step: Optional[int] = None

    def check_time(step: int) -> None:
        if deadline is not None and deadline.expired():
            raise TimeLimitReached(str(deadline), deadline.seconds, step, {})

    def collect(frontier: Sequence[str], step: int) -> None:
        nonlocal collected_step
        batch: Set[str] = set()
        for index, word in enumerate(frontier):
            if not index & 1023:
                check_time(step)
            if (len(word) <= bounds["max_word_len"] and word not in found and terminal_set.issuperset(word)
                    and (match is None or match(word))):
                batch.add(word)
        check_time(step)
        # Roll back any new words if an interrupt hits the merge. Only a whole frontier can advance steps.
        try:
            found.update(batch)
            check_time(step)
            collected_step = step
        except (KeyboardInterrupt, TimeLimitReached):
            if collected_step != step:
                found.difference_update(batch)
            raise

    try:
        check_time(0)
        try:
            sim = Simulator(model, settings, write=write, deadline=deadline, prune=pruner, **limits)
        except LimitReached as exc:
            if exc.step == 0:
                collect(model.axioms[component], 0)
            raise
        if pruner is not None and deadline is not None:
            pruner.check = lambda: check_time(sim.step_no + 1)
        collect(sim.cur[component], 0)
        while any(sim.cur) and (max_steps is None or sim.step_no < max_steps):
            sim.step()
            collect(sim.cur[component], sim.step_no)
            if on_step is not None:
                on_step(sim)
        check_time(sim.step_no)
        if any(sim.cur):
            result.reason, result.detail = "depth_bound", "the step bound was reached with a live frontier"
        else:
            notes = []
            if restrictions["hash_history"]:
                notes.append("History digests may collide")
            if settings.filter_next is not None and not getattr(settings.filter_next, "pure", False):
                notes.append("The Python filter keep is not declared pure")
            undeclared = _undeclared_functions(settings)
            if undeclared:
                notes.append("Functions in component filters or marks are not declared pure (%s)" % ", ".join(undeclared))
            result.reason = "frontier_exhausted"
            result.detail = "the frontier was exhausted"
            if notes:
                result.detail += ". " + ". ".join(notes)
            else:
                result.outcome = "complete"
    except TimeLimitReached:
        result.reason, result.detail = "time", "the time limit (%s) was reached" % deadline
    except LimitReached as exc:
        result.reason, result.detail, result.limit = "limit", str(exc), exc.limit
    except KeyboardInterrupt:
        result.outcome, result.reason, result.detail = "partial", "interrupted", "interrupted"

    result.steps = collected_step if collected_step is not None else 0

    def finish() -> None:
        lex = model.lexicon
        words = [lex.tokens(word) for word in found]
        if lex.alphabet_order is None:
            words.sort(key=lambda word: (len(word), word))
        else:
            rank = {symbol: index for index, symbol in enumerate(lex.alphabet_order)}
            words.sort(key=lambda word: (len(word), [(rank.get(symbol, len(rank)), symbol) for symbol in word]))
        result.words = words
        result.counts = dict(Counter(map(len, words)))

    try:
        finish()
        if result.reason in ("frontier_exhausted", "depth_bound"):
            check_time(result.steps)
    except TimeLimitReached:
        result.outcome, result.reason, result.detail = "partial", "time", "the time limit (%s) was reached" % deadline
    except KeyboardInterrupt:
        result.outcome, result.reason, result.detail = "partial", "interrupted", "interrupted"
        finish()
    return result


def language(model: Union[Model, str, "os.PathLike[str]"], max_len: int, pattern: Optional[str] = None, *,
             component: int = 1, terminals: Union[None, str, Sequence[str]] = None, max_steps: Optional[int] = None,
             max_nonterminals: Optional[int] = None, max_time: Optional[float] = None,
             keep: Optional[Callable[..., Any]] = None, settings: Optional[Settings] = None,
             max_step_candidates: Optional[int] = None, max_history: Optional[int] = None,
             max_step_accepted: Optional[int] = None) -> LanguageResult:
    """List the terminal words of at most ``max_len`` symbols in the given component (counted from 1).

    ``pattern`` is a whole-word regex over symbols. The length, terminals and pattern select listed
    words. Exploration uses the simulator settings, with an optional cap on generated nonterminals.
    """
    started = time.perf_counter()
    deadline = None
    if max_time is not None:
        if isinstance(max_time, bool) or not isinstance(max_time, (int, float)) or not 0 < max_time < float("inf"):
            raise GcrsimError("max_time must be a positive number of seconds, not %r" % (max_time,))
        deadline = Deadline(float(max_time), started)
    result = listing_result(max_len, pattern, component, max_steps, max_nonterminals, deadline,
                            max_step_candidates, max_history, max_step_accepted)
    try:
        if not isinstance(model, Model):
            model = parse_model_file(os.fspath(model))
        st = copy.copy(settings) if settings is not None else settings_for_model(model)
        if keep is not None:
            apply_settings(st, {"filter_next": keep}, "keep")
        return collect_language(model, st, result, terminals, deadline, write=lambda text: None)
    except KeyboardInterrupt:
        return result
