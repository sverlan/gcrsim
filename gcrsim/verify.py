"""``--cross-check``: run the reference interpreter next to the engine and compare every step.

Only the plain fragment can be verified (see SPEC.md): rules without regular expressions, permit/forbid
words, the history and length filters.  Anything that changes which strings are accepted but is outside
the fragment (a regex rule, ``reject_strings``, ``filters``, a filter function) is refused up front.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple
from . import _reference as ref
from .errors import ConfigError, GcrsimError
from .rules import ANY, END, START, SendRule, SubRule


class VerificationError(GcrsimError):
    """The engine and the reference interpreter disagree."""

    exit_code = 5


def _fragment_problems(sim: Any) -> List[str]:
    st = sim.settings
    problems = []
    for comp in sim.rules:
        for r in comp:
            if not isinstance(r, (SubRule, SendRule)):
                problems.append("line %d is a regular-expression rule" % r.line)
    if st.reject_strings:
        problems.append("reject_strings is set")
    if st.filters:
        problems.append("filters are set")
    if st.filter_next is not None:
        problems.append("a filter function is used")
    if sim.no_mark_rejected:
        problems.append("--no-mark-rejected is set (it changes the history)")
    return problems


class Verifier:
    """Keeps the reference state and compares it with the engine after each step."""

    def __init__(self, sim: Any):
        problems = _fragment_problems(sim)
        if problems:
            raise ConfigError(
                "--cross-check checks the plain fragment only (no regex rules, reject_strings, filters or filter "
                "function): " + "; ".join(problems[:3])
            )
        self.sim = sim
        lex = sim.lexicon
        self.use_history = sim.settings.history
        self.max_len: Optional[int] = sim.settings.reject_max_len
        self.rules = [self._convert(r, lex) for comp in sim.rules for r in comp]
        self.contents = [[tuple(lex.tokens(s)) for s in comp] for comp in sim.model.axioms]
        self.history: Optional[List[set]] = [set(f) for f in self.contents] if self.use_history else None
        self.steps = 0
        self.check_contents(0)

    @staticmethod
    def _convert(r: Any, lex: Any) -> "ref.Rule":
        permit = tuple(tuple(lex.tokens(w)) for w in r.permit)
        forbid = tuple(tuple(lex.tokens(w)) for w in r.forbid)
        any_of = tuple(tuple(lex.tokens(w)) for w in r.any_of)
        if isinstance(r, SendRule):
            return ref.Rule("send", r.source, r.target, permit=permit, forbid=forbid, permit_any=any_of)

        def item(it: Any) -> Any:
            if it is START:
                return ref.START
            if it is END:
                return ref.END
            if it is ANY:
                return ref.ANY
            if isinstance(it, frozenset):
                return frozenset(lex.decode(c) for c in it)
            return lex.decode(it)

        return ref.Rule(
            "sub", r.source, r.target,
            tuple(item(i) for i in r.U), tuple(item(i) for i in r.Y), tuple(lex.tokens(r.x)), tuple(item(i) for i in r.V),
            permit, forbid, any_of,
        )

    def check_contents(self, step: int) -> None:
        lex = self.sim.lexicon
        got = [[tuple(lex.tokens(s)) for s in comp] for comp in self.sim.cur]
        if got != self.contents:
            for c, (a, b) in enumerate(zip(got, self.contents)):
                if a != b:
                    raise VerificationError(
                        "step %d, component %d: the engine has %s, the reference interpreter has %s"
                        % (step, c + 1, _show(a), _show(b))
                    )

    def check_step(self) -> None:
        """Call after ``sim.step()``: advance the reference one step and compare."""
        self.steps += 1
        self.contents, self.history, raw = ref.step(self.contents, self.history, self.rules, self.use_history, self.max_len)
        self.check_contents(self.steps)
        if raw != self.sim.last_candidates:
            raise VerificationError(
                "step %d: the engine generated %d candidates, the reference interpreter %d" % (self.steps, self.sim.last_candidates, raw)
            )


def _show(content: Sequence[Tuple[str, ...]]) -> str:
    return "[" + ", ".join("".join(w) or "''" for w in content[:6]) + (", ..." if len(content) > 6 else "") + "]"
