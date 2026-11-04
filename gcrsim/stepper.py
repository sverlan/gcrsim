"""The commands of the step-by-step mode (``gcrsim MODEL -i``), described in docs/interactive.md."""

from __future__ import annotations

import shlex
from typing import Any, Callable, List, Optional

from .engine import Simulator, format_derivation
from .errors import GcrsimError
from .listing import visible

HELP = """\
commands (components count from 1; quote a string that holds spaces):
  Enter, n [K]          do the next step (or K steps)
  show [C]              list the strings of the current step (of component C)
  find STRING           where a string appeared first, and whether it is in the current step
  trace STRING [C]      the derivation of a string in component C (default 1)
  marks                 list the marks recorded so far
  mark C STRING LABEL   mark a string of the current step by hand
  remove C STRING       take a string out of the current step (it is not rewritten in the next one)
  stats                 the counters of the run
  help                  this list
  q                     quit
"""


class Session:
    """Reads commands until one of them asks for steps or for the end of the run."""

    def __init__(
        self,
        sim: Simulator,
        out: Any,
        stdin: Any,
        skip: Optional[Callable[[str], Any]],
        limit: Optional[int],
        layout: str,
        on_mark: Callable[[], None],
        marks_summary: Callable[[], None],
    ):
        self.sim = sim
        self.out = out
        self.stdin = stdin
        self.skip = skip
        self.limit = limit
        self.layout = layout  # text or perl: how `show` lists a component
        self.on_mark = on_mark  # called after a mark made by hand, so that the next step does not announce it again
        self.marks_summary = marks_summary
        self.commands = {
            "n": self.cmd_next, "next": self.cmd_next,
            "q": self.cmd_quit, "quit": self.cmd_quit, "exit": self.cmd_quit,
            "h": self.cmd_help, "help": self.cmd_help, "?": self.cmd_help,
            "show": self.cmd_show, "find": self.cmd_find, "trace": self.cmd_trace, "marks": self.cmd_marks,
            "mark": self.cmd_mark, "remove": self.cmd_remove, "stats": self.cmd_stats,
        }

    def say(self, text: str) -> None:
        self.out.write(text + "\n")

    def next_count(self) -> int:
        """Run commands until the user asks for steps; returns how many (0: the end)."""
        while True:
            self.out.write("step %d> " % self.sim.step_no)
            self.out.flush()
            line = self.stdin.readline()
            if not line:  # the end of the input: quit
                self.out.write("\n")
                return 0
            try:
                words = shlex.split(line)
            except ValueError as exc:
                self.say("cannot read the command: %s" % exc)
                continue
            if not words:
                return 1
            handler = self.commands.get(words[0].lower())
            if handler is None:
                self.say("unknown command %r (help lists the commands)" % words[0])
                continue
            try:
                result = handler(words[1:])
            except GcrsimError as exc:
                self.say(str(exc))
                continue
            if result is not None:
                return result

    # -- helpers ---------------------------------------------------------------------

    def component(self, text: str) -> int:
        try:
            number = int(text)
        except ValueError:
            number = 0
        if not 1 <= number <= self.sim.ncomp:
            raise GcrsimError("a component is a number from 1 to %d, not %r" % (self.sim.ncomp, text))
        return number - 1

    @staticmethod
    def arguments(args: List[str], low: int, high: int, usage: str) -> None:
        if not low <= len(args) <= high:
            raise GcrsimError("usage: " + usage)

    # -- commands ------------------------------------------------------------------------

    def cmd_next(self, args: List[str]) -> int:
        self.arguments(args, 0, 1, "n [K]")
        try:
            count = int(args[0]) if args else 1
        except ValueError:
            count = 0
        if count < 1:
            raise GcrsimError("usage: n [K]  (K is a number of steps, at least 1)")
        return count

    def cmd_quit(self, args: List[str]) -> int:
        return 0

    def cmd_help(self, args: List[str]) -> None:
        self.out.write(HELP)

    def cmd_show(self, args: List[str]) -> None:
        self.arguments(args, 0, 1, "show [C]")
        comps = [self.component(args[0])] if args else list(range(self.sim.ncomp))
        text = self.layout == "text"
        for c in comps:
            self.say("component %d" % (c + 1) if text else "Component %d:" % (c + 1))
            for s in visible([self.sim.cur[c]], self.skip, self.limit)[0]:
                self.say((s or "(empty word)") if text else s)
            self.say("")

    def cmd_find(self, args: List[str]) -> None:
        self.arguments(args, 1, 1, "find STRING")
        sim = self.sim
        encoded = sim.lexicon.encode(args[0])
        found = False
        for c in range(sim.ncomp):
            first = sim.find_step(c, encoded)
            if first is not None:
                found = True
                now = "it is in the current step" if encoded in sim.cur[c] else "it is not in the current step"
                self.say("component %d: first at step %d; %s" % (c + 1, first, now))
        if not found:
            self.say("%r has not appeared in any component (steps 0 to %d)" % (args[0], sim.step_no))

    def cmd_trace(self, args: List[str]) -> None:
        self.arguments(args, 1, 2, "trace STRING [C]")
        c = self.component(args[1]) if len(args) == 2 else 0
        derivation = self.sim.trace(args[0], component=c)
        self.say("Trace of %r (component %d):" % (args[0], c + 1))
        self.out.write(format_derivation(derivation))

    def cmd_marks(self, args: List[str]) -> None:
        self.arguments(args, 0, 0, "marks")
        if self.sim.marks:
            self.marks_summary()
        else:
            self.say("no marks so far")

    def cmd_mark(self, args: List[str]) -> None:
        self.arguments(args, 3, 3, "mark C STRING LABEL")
        self.sim.add_mark(self.component(args[0]), args[1], args[2])
        self.on_mark()

    def cmd_remove(self, args: List[str]) -> None:
        self.arguments(args, 2, 2, "remove C STRING")
        self.sim.remove(self.component(args[0]), args[1])
        self.say("removed %r from component %s" % (args[1], args[0]))

    def cmd_stats(self, args: List[str]) -> None:
        self.arguments(args, 0, 0, "stats")
        sim = self.sim
        self.say("step %d; strings per component: %s" % (sim.step_no, ", ".join(str(len(c)) for c in sim.cur)))
        self.say("candidates of the last step: %d; strings in the history: %d; strings retained: %d; marks: %d"
                 % (sim.last_candidates, sim.hist_count, sim.retained_count, len(sim.marks)))
