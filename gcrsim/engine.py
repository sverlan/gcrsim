"""The simulation: `Simulator` (contents, history, candidate filters, marks, tracing)."""

from __future__ import annotations

import sys
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from .history import DigestSet
from .errors import CallbackError, ConfigError, GcrsimError, LimitReached, TraceError
from .filters import _DEFAULT_MESSAGE, _build_check, _compile_marks
from .pattern import make_matcher
from .model import Model
from .rules import Rule
from .settings import Settings, _callback_arity, settings_for_model


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------


class DerivationStep:
    """One rewriting step of a derivation."""

    __slots__ = ("step", "source_component", "source", "rule", "start", "end", "target_component", "result")

    def __init__(self, step, source_component, source, rule, start, end, target_component, result):
        self.step = step
        self.source_component = source_component
        self.source = source
        self.rule = rule
        self.start = start
        self.end = end
        self.target_component = target_component
        self.result = result

    def __repr__(self) -> str:
        return "DerivationStep(step=%d, %r => %r, rule line %d, position %d)" % (
            self.step, self.source, self.result, self.rule.line, self.start)


class Mark:
    """A string flagged by a callback with ``ctx.mark``."""

    __slots__ = ("step", "component", "string", "label", "encoded")

    def __init__(self, step: int, component: int, string: str, label: str, encoded: Optional[str] = None):
        self.step = step
        self.component = component
        self.string = string  # with the real symbol names
        self.label = label
        self.encoded = string if encoded is None else encoded  # the internal string (one character per symbol)

    def __repr__(self) -> str:
        return "Mark(step=%d, component=%d, string=%r, label=%r)" % (self.step, self.component, self.string, self.label)


def format_derivation(derivation: Sequence[DerivationStep]) -> str:
    if not derivation:
        return "    (axiom: no derivation steps)\n"
    lines = []
    for d in derivation:
        lines.append(
            "    step %d: %s => %s   (component %d -> %d, rule at line %d: %s, position %d)\n"
            % (
                d.step,
                d.source,
                d.result,
                d.source_component + 1,
                d.target_component + 1,
                d.rule.line,
                d.rule.text,
                d.start,
            )
        )
    return "".join(lines)


class _NoPrint:
    """Stands in for ``sys.stdout`` while a streaming callback runs."""

    def write(self, text: str) -> int:
        if text:
            raise ConfigError(
                "a callback used in streaming mode printed; use ctx.report(...) or ctx.mark(...) instead of print()"
            )
        return 0

    def flush(self) -> None:
        pass


class Context:
    """Per-callback context passed as the optional third callback argument."""

    __slots__ = ("_sim", "step", "ncomp", "component", "_enc")

    def __init__(self, sim: "Simulator"):
        self._sim = sim
        self.step = 0
        self.ncomp = sim.ncomp
        self.component = 0
        self._enc = ""

    @property
    def string(self) -> str:
        """The candidate being tested, with the real symbol names."""
        return self._sim.lexicon.decode(self._enc)

    @string.setter
    def string(self, value: str) -> None:
        self._enc = value

    def mark(self, label: str) -> None:
        """Flag the candidate being tested (independent of accepting it)."""
        self._sim._mark(self.component, self._enc, label)

    def report(self, text: str) -> None:
        """Emit a message line (queued in streaming mode and written in component order)."""
        self._sim._report(self.component, text)


def _undeclared_functions(st: Any) -> List[str]:
    """The functions of the filters and marks of the components that are not declared pure (their names, for the message)."""
    found: List[Any] = []
    for spec in (st.filters or {}).values():
        for key in ("forbid", "require"):
            found += [f for f in spec.get(key, ()) if callable(f)]
    for labels in (st.marks or {}).values():
        for entry in labels.values():
            if isinstance(entry, dict):
                items = entry.get("expected_re", ())
                items = [items] if isinstance(items, str) or callable(items) else list(items)
                found += [f for f in items if callable(f)]
    return [getattr(f, "__name__", repr(f)) for f in found if not getattr(f, "pure", False)]


class Simulator:
    """The simulation engine: contents, history, rule application and filters."""

    def __init__(
        self,
        model: Model,
        settings: Optional[Settings] = None,
        *,
        write: Optional[Callable[[str], Any]] = None,
        streaming: bool = False,
        retain: bool = False,
        max_step_candidates: Optional[int] = None,
        max_history: Optional[int] = None,
        max_step_accepted: Optional[int] = None,
        max_retained: Optional[int] = None,
        max_marks: Optional[int] = None,
        trace_best_effort: bool = False,
        no_mark_rejected: bool = False,
        retain_store: Optional[Any] = None,
    ):
        self.model = model
        self.settings = settings or settings_for_model(model)
        self.ncomp = model.ncomp
        self.rules = model.rules
        self._write = write if write is not None else (lambda text: sys.stdout.write(text))
        self.streaming = streaming
        self.retain = retain
        self.max_step_candidates = max_step_candidates
        self.max_history = max_history
        self.max_step_accepted = max_step_accepted
        self.max_retained = max_retained
        self.max_marks = max_marks
        self.trace_best_effort = trace_best_effort
        self.no_mark_rejected = no_mark_rejected

        st = self.settings
        self.lexicon = model.lexicon
        self._skip = make_matcher(st.reject_strings, self.lexicon)
        self._reject_max_len = st.reject_max_len if st.reject_max_len is not None else sys.maxsize  # None: no length limit
        self._callback = st.filter_next
        self._callback_ctx = False
        self._pure = False
        if self._callback is not None:
            self._callback_ctx = _callback_arity(self._callback)
            self._pure = bool(getattr(self._callback, "pure", False))
            if self.lexicon.active:
                # the callback sees the real symbol names, not the internal codes
                original, decode = self._callback, self.lexicon.decode

                def decoded_callback(s: str, c: int, *rest: Any, _f: Callable[..., Any] = original) -> Any:
                    return _f(decode(s), c, *rest)

                decoded_callback.pure = self._pure  # type: ignore[attr-defined]
                self._callback = decoded_callback
        if streaming:
            if st.show_detailed_application:
                raise ConfigError("streaming mode cannot be combined with show_detailed_application")
            if self._callback is not None and not self._pure:
                raise ConfigError(
                    "streaming mode requires a callback declared pure and order-independent "
                    "(set filter_next.pure = True); stateful callbacks run in the default mode"
                )
            undeclared = _undeclared_functions(st)
            if undeclared:
                raise ConfigError(
                    "streaming mode requires the functions in the filters and marks of the components to be declared pure "
                    "(pure(function) or function.pure = True): %s" % ", ".join(undeclared)
                )
        self._cfilters = self._build_component_filters()
        self._marks = self._build_marks()
        self.ctx = Context(self)

        self.cur: List[List[str]] = [list(a) for a in model.axioms]
        make_set = DigestSet if (st.history and st.hash_history) else set  # hash_history: digests instead of strings
        self.hist: List[Any] = [make_set(a) for a in model.axioms] if st.history else [set() for _ in range(self.ncomp)]
        self.hist_count = sum(len(h) for h in self.hist) if st.history else 0
        self.step_no = 0
        self._failed = False
        self.marks: List[Mark] = []
        self._queued: List[List[str]] = [[] for _ in range(self.ncomp)]
        # step -> contents; a dict, or a mapping with the same interface (SqliteRetention) to keep them out of memory
        self.retained: Any = {} if retain_store is None else retain_store
        if hasattr(self.retained, "set_lexicon"):
            self.retained.set_lexicon(model.lexicon)
        self.retained_count = 0
        self.trace_lost_from: Optional[int] = None
        self.last_candidates = 0
        self._accepted = 0  # strings accepted so far in the current step (all components)
        self._pending_marks: List[List[Mark]] = [[] for _ in range(self.ncomp)]
        self._pending_count = 0
        self.peak_strings = sum(len(c) for c in self.cur)
        if self.max_history is not None and self.hist_count > self.max_history:
            self._limit("max-history", self.max_history, 0, self.hist_count)
        if self.retain:
            self._retain(0, self.cur)

    # -- setup ---------------------------------------------------------------

    def _build_component_filters(self) -> List[Optional[Callable[[str], bool]]]:
        spec = self.settings.filters or {}
        global_specs: List[Dict[str, Any]] = []
        per: Dict[int, List[Dict[str, Any]]] = {i: [] for i in range(self.ncomp)}
        for key, value in spec.items():
            if key in (0, "all"):
                global_specs.append(value)
            elif isinstance(key, int) and 1 <= key <= self.ncomp:
                per[key - 1].append(value)
            else:
                raise ConfigError(
                    "filters for component %r: the key is not 0/'all' or a component number 1..%d" % (key, self.ncomp)
                )
        return [_build_check(global_specs + per[i], self.lexicon) for i in range(self.ncomp)]

    def _expected(self, expected_re: Sequence[Callable[[str], Any]], label: str, c: str, t: int, step_no: int) -> bool:
        """True if any 'expected_re' regex matches or any 'expected_re' function accepts the string."""
        for check in expected_re:
            try:
                if check(c):
                    return True
            except GcrsimError:
                raise
            except Exception as exc:  # user code
                raise CallbackError(
                    "%s: 'expected_re' of mark %r failed at step %d, component %d, string %s: %s: %s"
                    % (self.settings.config_name or "configuration", label, step_no, t + 1, self._q(c), type(exc).__name__, exc)
                ) from exc
        return False

    def _build_marks(self) -> List[Optional[List[Any]]]:
        spec = self.settings.marks or {}
        global_items: List[Any] = []
        per: Dict[int, List[Any]] = {i: [] for i in range(self.ncomp)}
        for key, labels in spec.items():
            items = _compile_marks(labels, "marks[%r]" % (key,), self.lexicon)
            if key in (0, "all"):
                global_items.extend(items)
            elif isinstance(key, int) and 1 <= key <= self.ncomp:
                per[key - 1].extend(items)
            else:
                raise ConfigError("marks key %r is not 0/'all' or a component number 1..%d" % (key, self.ncomp))
        return [(global_items + per[i]) or None for i in range(self.ncomp)]

    @property
    def has_filter(self) -> bool:
        return (
            self._callback is not None
            or any(f is not None for f in self._cfilters)
            or any(m is not None for m in self._marks)
        )

    # -- callback services -----------------------------------------------------

    def _mark(self, component: int, string: str, label: str, message: Any = _DEFAULT_MESSAGE, step: Optional[int] = None) -> None:
        step = self.step_no + 1 if step is None else step
        recorded = len(self.marks) + self._pending_count
        if self.max_marks is not None and recorded >= self.max_marks:
            raise LimitReached("max-marks", self.max_marks, self.step_no + 1, {"marks": recorded})
        record = Mark(step, component, self.lexicon.decode(string), label, string)
        if self.streaming:
            # committed in baseline (component) order at the end of the step
            self._pending_marks[component].append(record)
            self._pending_count += 1
        else:
            self.marks.append(record)
        if message is _DEFAULT_MESSAGE:
            text: Optional[str] = "Mark (%s): %s" % (label, string)
        elif message is None:
            text = None  # recorded, but no line is printed
        else:
            text = message.format(string=string, component=component + 1, step=step, label=label)
        if text is not None:
            self._report(component, text)

    def add_mark(self, component: int, string: str, label: str) -> None:
        """Mark a string of the current content by hand (between two steps); ``string`` has the real symbol names,
        ``component`` counts from 0. The mark belongs to the step just completed and is printed like any other."""
        encoded = self.lexicon.encode(string)
        if encoded not in self.cur[component]:
            raise GcrsimError("%r is not in component %d" % (string, component + 1))
        self._mark(component, encoded, label, step=self.step_no)

    def remove(self, component: int, string: str) -> None:
        """Take a string out of the current content, so it is not rewritten in the next step (``component`` counts from
        0). It stays in the history, so it is not produced again, and the retained contents of the steps already done are
        not changed."""
        encoded = self.lexicon.encode(string)
        if encoded not in self.cur[component]:
            raise GcrsimError("%r is not in component %d" % (string, component + 1))
        contents = list(self.cur)  # new lists, not changed ones: the retained contents of earlier steps are the old objects
        contents[component] = [t for t in contents[component] if t != encoded]
        self.cur = contents

    def _report(self, component: int, text: str) -> None:
        if self.streaming:
            self._queued[component].append(text)
        else:
            self._write(text + "\n")

    # -- one step ----------------------------------------------------------------

    def step(self) -> None:
        """Advance the simulation by one synchronous step.

        A step that fails (a limit, a callback error) leaves the history half updated, so the simulator
        refuses further steps afterwards; the contents of the last complete step stay readable.
        """
        if self._failed:
            raise GcrsimError("the simulator cannot continue: step %d did not complete" % (self.step_no + 1))
        try:
            self._step()
        except BaseException:
            self._failed = True
            raise

    def _step(self) -> None:
        n = self.ncomp
        step_no = self.step_no + 1
        self.ctx.step = step_no
        cur = self.cur
        detailed = self.settings.show_detailed_application
        history = self.settings.history
        max_c = self.max_step_candidates
        total = 0  # candidates generated in this step (counted with or without a limit)
        self._accepted = 0
        self._queued = [[] for _ in range(n)]
        self._pending_marks = [[] for _ in range(n)]
        self._pending_count = 0
        out: List[List[str]] = [[] for _ in range(n)]

        if self.streaming:
            seens = self.hist if history else [set() for _ in range(n)]
            saved_stdout = sys.stdout
            if self._callback is not None:
                # a pure streaming callback must not print: its output order would depend on generation order
                sys.stdout = _NoPrint()
            try:
                total = self._stream_generate(cur, out, seens, step_no)
            finally:
                sys.stdout = saved_stdout
            # commit queued messages and marks in baseline (component) order
            for comp in range(n):
                msgs = self._queued[comp]
                if msgs:
                    self._write("\n".join(msgs) + "\n")
                self.marks.extend(self._pending_marks[comp])
            self._queued = [[] for _ in range(n)]
            self._pending_marks = [[] for _ in range(n)]
            self._pending_count = 0
        else:
            nxt: List[List[str]] = [[] for _ in range(n)]
            for i in range(n):
                rules = self.rules[i]
                if not rules:
                    continue
                if max_c is None:
                    bound = [(self._traced(r) if detailed else r.expand, nxt[r.target].extend) for r in rules]
                    for s in cur[i]:
                        for exp, extend in bound:
                            cands = exp(s)
                            if cands:
                                total += len(cands)
                                extend(cands)
                else:
                    # the edits are small tuples: count them before building any candidate string
                    bound = [(r, nxt[r.target].extend) for r in rules]
                    for s in cur[i]:
                        for r, extend in bound:
                            cands = self._limited(r, s, total, step_no, detailed)
                            if cands:
                                total += len(cands)
                                extend(cands)
            for i in range(n):
                seen = self.hist[i] if history else set()
                self._filter(i, nxt[i], seen, out[i], step_no)
                nxt[i] = []
        self.last_candidates = total
        accepted = self._accepted
        if self.retain:
            self._retain(step_no, out)  # may raise: the step is not committed then
        self.cur = out
        self.step_no = step_no
        if accepted > self.peak_strings:
            self.peak_strings = accepted

    def _stream_generate(self, cur: List[List[str]], out: List[List[str]], seens: List[set], step_no: int) -> int:
        """Streaming mode: filter each batch as it is generated; returns the candidate count."""
        max_c = self.max_step_candidates
        total = 0
        for i in range(self.ncomp):
            rules = self.rules[i]
            if not rules:
                continue
            if max_c is None:
                bound = [(r.expand, r.target) for r in rules]
                for s in cur[i]:
                    for exp, t in bound:
                        cands = exp(s)
                        if cands:
                            total += len(cands)
                            self._filter(t, cands, seens[t], out[t], step_no)
            else:
                for s in cur[i]:
                    for r in rules:
                        cands = self._limited(r, s, total, step_no, False)
                        if cands:
                            total += len(cands)
                            self._filter(r.target, cands, seens[r.target], out[r.target], step_no)
        return total

    def _limited(self, r: Rule, s: str, total: int, step_no: int, detailed: bool) -> Sequence[str]:
        """Candidates of ``r`` on ``s`` when a candidate limit is set: stop before building too many."""
        max_c = self.max_step_candidates
        if total + r.edit_count(s) > max_c:
            self._limit("max-step-candidates", max_c, step_no, max_c + 1)
        cands = r.build(s, r.edits(s))
        if detailed and cands:
            self._write("%s => %s\n" % (s, " ".join(cands)))
        return cands

    def _traced(self, r: Rule) -> Callable[[str], Sequence[str]]:
        """``r.expand`` that also shows the application (``show_detailed_application``)."""
        write = self._write
        expand = r.expand

        def traced(s: str) -> Sequence[str]:
            res = expand(s)
            if res:
                write("%s => %s\n" % (s, " ".join(res)))
            return res

        return traced

    def _limit(self, name: str, value: int, step_no: int, count: int) -> None:
        raise LimitReached(
            name,
            value,
            step_no,
            {"count": count, "history": self.hist_count, "step": step_no},
        )

    def _filter(self, t: int, cands: Sequence[str], seen: set, out: List[str], step_no: int) -> None:
        """Dedup, length, skip regex, component conditions, callback."""
        maxlen = self._reject_max_len
        skip = self._skip
        cf = self._cfilters[t]
        mk = self._marks[t]
        cb = self._callback
        ctx = self.ctx if self._callback_ctx else None
        history = self.settings.history
        add = seen.add
        max_hist = self.max_history if history else None
        max_front = self.max_step_accepted
        nomark = self.no_mark_rejected
        accepted = self._accepted  # step-wide count; kept local inside the loop
        if ctx is not None:
            ctx.component = t
        for c in cands:
            if nomark:
                if len(c) > maxlen or (skip is not None and skip(c)) or (cf is not None and not cf(c)):
                    continue
                if c in seen:
                    continue
                add(c)
                if history:
                    self.hist_count += 1
                    if max_hist is not None and self.hist_count > max_hist:
                        self._limit("max-history", max_hist, step_no, self.hist_count)
            else:
                if c in seen:
                    continue
                add(c)
                if history:
                    # every unique insertion counts, also for candidates rejected below
                    self.hist_count += 1
                    if max_hist is not None and self.hist_count > max_hist:
                        self._limit("max-history", max_hist, step_no, self.hist_count)
                if len(c) > maxlen:
                    continue
                if skip is not None and skip(c):
                    continue
                if cf is not None and not cf(c):
                    continue
            if cb is not None:
                try:
                    if ctx is not None:
                        ctx.string = c
                        keep = cb(c, t, ctx)
                    else:
                        keep = cb(c, t)
                except GcrsimError:
                    raise
                except Exception as exc:  # user code: report where it failed instead of a bare traceback
                    raise CallbackError(
                        "%s: filter_next failed at step %d, component %d, string %s: %s: %s"
                        % (self.settings.config_name or "configuration", step_no, t + 1, self._q(c), type(exc).__name__, exc)
                    ) from exc
                if not keep:
                    continue
            if mk is not None:
                # declarative marks apply to strings that passed every filter (accepted strings)
                for label, patterns, message, expected_re in mk:
                    for rx in patterns:
                        if rx.search(c):
                            if expected_re and self._expected(expected_re, label, c, t, step_no):
                                break  # an expected string: not marked
                            self._mark(t, c, label, message)
                            break
            out.append(c)
            accepted += 1
            if max_front is not None and accepted > max_front:
                # the cap bounds the accepted strings of the whole step, over all components
                self._accepted = accepted
                self._limit("max-step-accepted", max_front, step_no, accepted)
        self._accepted = accepted

    def strings(self) -> List[List[str]]:
        """The current strings of every component, with the real symbol names (``cur`` holds the internal strings, in
        which a multi-character symbol is one private-use character)."""
        return [[self.lexicon.decode(s) for s in comp] for comp in self.cur]

    def run(self, steps: int) -> None:
        """Run ``steps`` steps (convenience for the importable API)."""
        for _ in range(steps):
            self.step()

    # -- retention ----------------------------------------------------------------

    def _retain(self, step_no: int, contents: List[List[str]]) -> None:
        count = sum(len(f) for f in contents)
        if not count:
            return  # empty steps store nothing
        if self.max_retained is not None and self.retained_count + count > self.max_retained:
            if self.trace_best_effort:
                self.retain = False
                self.trace_lost_from = step_no
                return
            raise LimitReached(
                "max-retained",
                self.max_retained,
                step_no,
                {"retained": self.retained_count + count, "history": self.hist_count},
            )
        self.retained[step_no] = contents
        self.retained_count += count

    # -- trace-back -------------------------------------------------------------------

    def find_step(self, component: int, string: str) -> Optional[int]:
        """Earliest retained step whose content holds ``string`` in ``component``."""
        first = getattr(self.retained, "first_step", None)
        if first is not None:  # a database finds it with an index
            return first(component, string)
        for k in sorted(self.retained):
            fr = self.retained[k]
            if component < len(fr) and string in fr[component]:
                return k
        return None

    def trace(self, string: str, component: int = 0, step: Optional[int] = None) -> List[DerivationStep]:
        """Derivation of ``string`` (0-based ``component``) from the axioms."""
        return self.trace_many([(component, string, step)])[0]

    def _q(self, s: str) -> str:
        """``repr`` of an internal string with the real symbol names (for messages)."""
        return repr(self.lexicon.decode(s))

    def trace_many(self, targets: Sequence[Tuple[int, str, Optional[int]]]) -> List[List[DerivationStep]]:
        """Batch trace-back with the real symbol names (targets may be given with names or internal codes)."""
        if not self.lexicon.has_lexemes:
            return self._trace_many(targets)
        encode, decode = self.lexicon.encode, self.lexicon.decode
        chains = self._trace_many([(c, encode(s), k) for c, s, k in targets])
        return [
            [
                DerivationStep(d.step, d.source_component, decode(d.source), d.rule, d.start, d.end, d.target_component, decode(d.result))
                for d in chain
            ]
            for chain in chains
        ]

    def _trace_many(self, targets: Sequence[Tuple[int, str, Optional[int]]]) -> List[List[DerivationStep]]:
        """Batch trace-back: one pass over each content level for all targets.

        ``targets`` are ``(component, string, step)``; ``step`` may be None for
        strings held by a retained content.  Parents are searched in content
        ``k-1`` in the original generation order, so each derivation is the
        first-discoverer chain (a shortest derivation).
        """
        if not self.retain and not self.retained:
            raise TraceError("tracing is not enabled (use --trace/--trace-marks or retain=True)")
        resolved: List[Tuple[int, str, int]] = []
        for comp, string, step in targets:
            if not 0 <= comp < self.ncomp:
                raise TraceError("component %d is outside 1..%d" % (comp + 1, self.ncomp))
            if step is not None and not 0 <= step <= self.step_no:
                raise TraceError("step %d is outside the simulated steps 0..%d" % (step, self.step_no))
            if step == 0 and string not in self.model.axioms[comp]:
                raise TraceError("%s is not an axiom of component %d" % (self._q(string), comp + 1))
            if step is None:
                step = self.find_step(comp, string)
                if step is None:
                    if self.trace_lost_from is not None:
                        raise TraceError(
                            "string %s not found; retention stopped at step %d (--max-retained)"
                            % (self._q(string), self.trace_lost_from)
                        )
                    raise TraceError("string %s is not in component %d of any retained step" % (self._q(string), comp + 1))
            resolved.append((comp, string, step))
        if self.trace_lost_from is not None and any(s >= self.trace_lost_from for _, _, s in resolved):
            raise TraceError("retention stopped at step %d (--max-retained); cannot trace" % self.trace_lost_from)
        pending: Dict[int, set] = {}
        for comp, string, step in resolved:
            if step > 0:
                pending.setdefault(step, set()).add((comp, string))
        found: Dict[int, Dict[Tuple[int, str], DerivationStep]] = {}
        k = max(pending) if pending else 0
        while k >= 1:
            want = pending.get(k)
            if want:
                content = self.retained.get(k - 1)
                if content is None:
                    raise TraceError("content of step %d was not retained" % (k - 1))
                got: Dict[Tuple[int, str], DerivationStep] = {}
                remaining = len(want)
                for i in range(self.ncomp):
                    if not remaining:
                        break
                    rules = self.rules[i]
                    if not rules or i >= len(content):
                        continue
                    for s in content[i]:
                        for r in rules:
                            for start, end, res in r.spans(s):
                                key = (r.target, res)
                                if key in want and key not in got:
                                    got[key] = DerivationStep(k, i, s, r, start, end, r.target, res)
                                    remaining -= 1
                                    if k - 1 >= 1:
                                        pending.setdefault(k - 1, set()).add((i, s))
                                    if not remaining:
                                        break
                            if not remaining:
                                break
                        if not remaining:
                            break
                if remaining:
                    missing = [key for key in want if key not in got]
                    raise TraceError(
                        "no derivation found for %s (component %d) at step %d" % (self._q(missing[0][1]), missing[0][0] + 1, k)
                    )
                found[k] = got
            k -= 1
        chains: List[List[DerivationStep]] = []
        for comp, string, step in resolved:
            chain: List[DerivationStep] = []
            key = (comp, string)
            for level in range(step, 0, -1):
                rec = found[level][key]
                chain.append(rec)
                key = (rec.source_component, rec.source)
            chain.reverse()
            chains.append(chain)
        return chains
