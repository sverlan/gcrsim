"""Command line interface: argument parsing, header, listings, `main`."""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from ._meta import CHECK_FAILED_STATUS, __version__
from .engine import DerivationStep, Mark, Simulator, format_derivation
from . import listing, stepper
from .errors import GcrsimError, LimitReached, TraceError
from .pattern import make_matcher
from .model import parse_model_file
from .output import Output, format_conf
from .retention import SqliteRetention
from .verify import Verifier
from .settings import Settings, apply_settings, read_config_data, resolve_config


# ---------------------------------------------------------------------------
# Command line interface
# ---------------------------------------------------------------------------


def _build_parser() -> "argparse.ArgumentParser":
    import argparse

    p = argparse.ArgumentParser(
        prog="gcrsim",
        description="Graph Controlled string Rewriting SIMulator (successor of the Perl gcrsim.pl).",
        epilog="Other programs: 'gcrsim-convert OLD_MODEL [-o NEW_MODEL]' translates a Perl-era model and its .cfg; "
        "'gcrsim-retention FILE ...' shows, searches and traces a file written with --retain-file. "
        "Use --help with them for their options.",
    )
    p.add_argument("input_file", nargs="?", metavar="MODEL", help="the model file (without it this help is shown)")
    p.add_argument("steps", nargs="?", help="number of steps to run (or the setting 'steps' of the configuration)")
    p.add_argument("-i", "--interactive", action="store_true", help="step by step, waiting for a command after each step (formats text and perl only)")
    p.add_argument("--format", choices=("text", "perl", "csv", "jsonl"), default="text",
                   help="text: a short header and the strings of each step (default); perl: the layout of the Perl simulator; "
                        "csv: only the strings, one row each; jsonl: one JSON object per line (header, one per step, messages, end)")
    p.add_argument("--csv-sep", metavar="CHAR", default="tab",
                   help="separator of the csv format: one character (for example , or ;) or tab (the default)")
    p.add_argument("--version", action="version", version="gcrsim %s" % __version__)
    p.add_argument("--config", metavar="FILE", action="append", default=[],
                   help="configuration (.toml with [model] and [run]) applied over the model's own settings; repeatable, later files win")
    p.add_argument("--python-filter", metavar="FILE.py",
                   help="run FILE.py (it executes code!): a Python function keep(s, component[, ctx]) that rejects strings, "
                        "and any other setting, applied on top of the configuration")
    p.add_argument("--quiet", action="store_true", help="no header, step banners or listings (callback output stays)")
    p.add_argument("--progress", action="store_true", help="write one summary line per step to stderr")
    p.add_argument("--no-mark-summary", action="store_true", help="do not list the marks at the end of the run")
    p.add_argument("--print-all", action="store_true", help="ignore print_hide/print_max_len (list every accepted string)")
    p.add_argument("--run-empty", action="store_true", help="keep running steps after all components are empty")
    p.add_argument("--streaming", action="store_true", help="filter candidates as they are generated (pure callbacks only)")
    p.add_argument("--cross-check", action="store_true",
                   help="run an independent reference interpreter next to the engine and compare every step (plain fragment only)")
    p.add_argument("--no-mark-rejected", action="store_true", help="do not record strings rejected by pure conditions in the history")
    t = p.add_argument_group("trace-back")
    t.add_argument("--trace", metavar="STRING", help="print the derivation of STRING when it first appears")
    t.add_argument("--component", type=int, default=1, metavar="N", help="component of --trace STRING (default 1)")
    t.add_argument("--trace-marks", action="store_true", help="retain the strings of every step and print a derivation for every mark")
    t.add_argument("--trace-mark-label", action="append", default=[], metavar="LABEL",
                   help="derivations only for marks with this label (repeatable; implies --trace-marks)")
    t.add_argument("--stop-on-mark-label", action="append", default=[], metavar="LABEL",
                   help="stop after the step in which a mark with this label was recorded (repeatable)")
    t.add_argument("--fail-on-mark", action="append", default=[], metavar="LABEL",
                   help="exit with status 4 if a mark with this label was recorded; '*' means any label (repeatable)")
    t.add_argument("--stop-on-found", action="store_true", help="stop after the step in which --trace STRING appeared")
    t.add_argument("--stop-on-mark", action="store_true", help="stop after the step in which a callback marked a string")
    t.add_argument("--max-retained", type=int, metavar="N", help="cap on strings retained for trace-back")
    t.add_argument("--retain-file", metavar="FILE", help="keep the retained strings in this SQLite file instead of in memory (for long traces)")
    t.add_argument("--trace-best-effort", action="store_true", help="when --max-retained is hit, continue without tracing")
    lim = p.add_argument_group("limits (stop the run with status 3; the last step is incomplete)")
    lim.add_argument("--max-step-candidates", type=int, metavar="N", help="candidates generated in one step (a per-step limit)")
    lim.add_argument("--max-history", type=int, metavar="N", help="strings inserted into the history (whole run)")
    lim.add_argument("--max-step-accepted", type=int, metavar="N", help="strings accepted in one step, over all components (a per-step limit)")
    lim.add_argument("--max-marks", type=int, metavar="N", help="marks recorded (whole run)")
    return p


class _LineSink:
    """A stand-in for ``sys.stdout`` that passes whole lines to ``emit`` (``print`` writes a line in pieces)."""

    def __init__(self, emit: Callable[[str], Any]):
        self._emit = emit
        self._pending = ""

    def write(self, text: str) -> int:
        self._pending += text
        head, newline, self._pending = self._pending.rpartition("\n")
        if newline:
            self._emit(head + "\n")
        return len(text)

    def flush(self) -> None:
        if self._pending:
            self._emit(self._pending + "\n")
            self._pending = ""


def _header(out: Output, model_path: str, st: Settings, has_filter: bool) -> None:
    w = out.write
    w("\n\n========================================\n")
    w("gcrsim simulator v.%s\n" % __version__)
    w("Program configuration:\n")
    w("Input file: %s\n" % model_path)
    w("Configuration: %s\n" % st.config_name)
    if st.description:
        w("Description: %s\n" % st.description)
    w('Print_hide = "%s"; Print_max_len=%s;\n' % (st.print_hide, "unlimited" if st.print_max_len is None else st.print_max_len))
    w('Reject_strings = "%s"; Reject_max_len=%s\n' % (st.reject_strings, "unlimited" if st.reject_max_len is None else st.reject_max_len))
    w("Filter function used: %s, History: %s\n" % ("yes" if has_filter else "no", "yes" if st.history else "no"))
    w("========================================\n")
    w("The initial configuration (at STEP 0):\n\n")


def _non_default(st: Settings) -> List[str]:
    """The settings of a run that differ from the defaults, for the header of the text format."""
    d = Settings()
    items: List[str] = []
    if st.print_hide != d.print_hide:
        items.append('print_hide "%s"' % st.print_hide)
    if st.print_max_len != d.print_max_len:
        items.append("print_max_len %s" % st.print_max_len)
    if st.reject_strings != d.reject_strings:
        items.append('reject_strings "%s"' % st.reject_strings)
    if st.reject_max_len != d.reject_max_len:
        items.append("reject_max_len %s" % st.reject_max_len)
    if st.history != d.history:
        items.append("history off")
    if st.show_detailed_application:
        items.append("detailed application")
    if st.print_sep:
        items.append('print_sep "%s"' % st.print_sep)
    if st.hash_history:
        items.append("hash_history")
    for what, table in (("filters", st.filters), ("marks", st.marks)):
        if table:
            items.append("%s for %d component%s" % (what, len(table), "" if len(table) == 1 else "s"))
    if st.filter_next is not None:
        items.append("filter function")
    return items


def _text_header(out: Output, model_path: str, st: Settings, model: Any) -> None:
    """The header of the text format: what was run, and only what differs from the defaults."""
    w = out.write
    w("gcrsim %s   %s\n" % (__version__, model_path))
    if st.description:
        w(st.description + "\n")
    rules = sum(len(r) for r in model.rules)
    line = "%d component%s, %d rule%s" % (model.ncomp, "" if model.ncomp == 1 else "s", rules, "" if rules == 1 else "s")
    if st.config_name != "model":
        line += "; settings: " + st.config_name
    w(line + "\n")
    items = _non_default(st)
    if items:
        w(", ".join(items) + "\n")
    w("\n")


def _print_text_conf(out: Output, contents: Sequence[Sequence[str]], skip: Optional[Callable[[str], Any]], plen: Optional[int]) -> None:
    """The strings of each component in the text format: a heading, one string per line, a blank line. An empty component
    is just the heading and the blank line; the empty word is written (empty word)."""
    for c, comp in enumerate(listing.visible(contents, skip, plen)):
        out.write("component %d\n" % (c + 1))
        for string in comp:
            out.write((string or "(empty word)") + "\n")
        out.write("\n")


def _print_conf(out: Output, contents: Sequence[Sequence[str]], skip: Optional[Callable[[str], Any]], plen: Optional[int]) -> None:
    for chunk in format_conf(contents, skip, plen):
        out.write(chunk)


def _print_marks_block(out: Output, sim: Simulator, new_marks: Sequence[Mark], retain: bool) -> None:
    if not new_marks or not retain:
        return  # without retention the inline mark line (and the final summary) is all there is
    derivs: List[Optional[List[DerivationStep]]] = [None] * len(new_marks)
    note = ""
    try:
        chains = sim._trace_many([(m.component, m.encoded, m.step) for m in new_marks])
        derivs = list(chains)
    except TraceError as exc:
        note = "    (derivation unavailable: %s)\n" % exc
    for m, d in zip(new_marks, derivs):
        out.write("\nMark [%s] at step %d, component %d: %s\n" % (m.label, m.step, m.component + 1, m.encoded))
        if d is not None:
            out.write(format_derivation(d))
        else:
            out.write(note)


def _print_marks_summary(out: Output, marks: Sequence[Mark], retain: bool) -> None:
    if not marks:
        return
    groups: Dict[Tuple[int, str, str], List[int]] = {}
    for m in marks:
        groups.setdefault((m.component, m.encoded, m.label), []).append(m.step)
    out.write("\nMarks (%d, %d distinct):\n" % (len(marks), len(groups)))
    for (comp, string, label), steps in groups.items():
        out.write("  [%s] component %d: %s  (steps %s)\n" % (label, comp + 1, string, ", ".join(map(str, steps))))
    if not retain:
        out.write("  (run with --trace-marks to see how each was derived)\n")


def _progress_line(sim: Simulator, started: float) -> str:
    sizes = ",".join(str(len(c)) for c in sim.cur)
    return "step %d: strings per component [%s], candidates %d, history %d, retained %d, elapsed %.2fs\n" % (
        sim.step_no,
        sizes,
        sim.last_candidates,
        sim.hist_count,
        sim.retained_count,
        time.perf_counter() - started,
    )


def run_cli(args: "argparse.Namespace", out: Output, stdin: Any) -> int:
    interactive = args.interactive
    input_file = args.input_file
    run_steps = 0
    if args.steps is not None:
        if interactive:
            raise GcrsimError("-i and a number of steps exclude each other")
        try:
            run_steps = int(args.steps)
        except ValueError:
            raise GcrsimError("Bad number of steps: %s !" % args.steps)
        if run_steps < 0:
            raise GcrsimError("Bad number of steps: %d !" % run_steps)
    layout = args.format
    human = layout in ("text", "perl")  # the formats written by this module (the others are in listing.py)
    if interactive and not human:
        raise GcrsimError("-i works with --format text or perl only")
    try:
        sep = listing.separator(args.csv_sep)
    except ValueError as exc:
        raise GcrsimError(str(exc))
    if not os.path.exists(input_file):
        raise GcrsimError("cannot read the model %s: no such file" % input_file)

    model = parse_model_file(input_file)
    trace_target = model.lexicon.encode(args.trace) if args.trace is not None else None
    settings = resolve_config(model, args.config)
    if args.python_filter:
        if not os.path.isfile(args.python_filter):
            raise GcrsimError("Python filter file not found: %s" % args.python_filter)
        apply_settings(settings, read_config_data(args.python_filter, True), args.python_filter)
        settings.config_name += " + " + args.python_filter
    if args.steps is None and not interactive:
        if settings.steps is None:  # the number of steps may come from the configuration
            raise GcrsimError("no number of steps: give it after the model, set `steps` in the configuration, or use -i")
        run_steps = settings.steps
    if settings.print_sep and model.lexicon.has_lexemes:
        lex, psep = model.lexicon, settings.print_sep
        decode: Optional[Callable[[str], str]] = lambda text: lex.decode_spaced(text, psep)
    else:
        decode = model.lexicon.decode if model.lexicon.active else None
    plain = decode or (lambda text: text)
    if human:
        out.decode = decode
        say: Any = out
        fmt: Any = None
    else:  # csv, jsonl: the data are written already decoded; what is not data goes to the format
        out.decode = None
        fmt = (listing.Jsonl(out.write, plain, sys.stderr.write) if args.format == "jsonl"
               else listing.Csv(out.write, plain, sys.stderr.write, sep))
        say = _LineSink(fmt.text)
        sys.stdout = say  # callbacks that print() end up in the same place as the marks
    if args.trace is not None and not (1 <= args.component <= model.ncomp):
        raise GcrsimError("--component must be between 1 and %d" % model.ncomp)
    if args.stop_on_found and args.trace is None:
        raise GcrsimError("--stop-on-found needs --trace STRING")
    retain = args.trace is not None or bool(args.trace_marks) or bool(args.trace_mark_label)
    trace_labels = set(args.trace_mark_label)  # empty: derivations for every mark
    stop_labels = set(args.stop_on_mark_label)
    fail_labels = set(args.fail_on_mark)
    sim = Simulator(
        model,
        settings,
        write=say.write,
        streaming=args.streaming,
        retain=retain or interactive,
        max_step_candidates=args.max_step_candidates,
        max_history=args.max_history,
        max_step_accepted=args.max_step_accepted,
        max_retained=args.max_retained,
        max_marks=args.max_marks,
        trace_best_effort=args.trace_best_effort,
        no_mark_rejected=args.no_mark_rejected,
        retain_store=SqliteRetention(args.retain_file) if (retain and args.retain_file) else None,
    )
    verifier = Verifier(sim) if args.cross_check else None
    skip = make_matcher(settings.print_hide, model.lexicon)
    plen: Optional[int] = settings.print_max_len
    if args.print_all:
        skip, plen = None, None
    quiet = args.quiet and human
    started = time.perf_counter()

    if not human:
        fmt.start(__version__, input_file, settings.config_name, sim.cur, skip, plen, settings.description)
    elif not quiet:
        if layout == "perl":
            _header(out, input_file, settings, sim.has_filter)
            _print_conf(out, sim.cur, skip, plen)
        else:
            _text_header(out, input_file, settings, model)
            out.write("step 0\n")
            _print_text_conf(out, sim.cur, skip, plen)
    out.flush()

    trace_found = False
    trace_comp = args.component - 1

    def check_trace() -> bool:
        """Report the derivation the first time the traced string is in its content."""
        nonlocal trace_found
        if args.trace is None or trace_found or trace_target not in sim.cur[trace_comp]:
            return False
        trace_found = True
        say.write(
            "\nTrace of %r (component %d), first appearing at step %d:\n" % (args.trace, args.component, sim.step_no)
        )
        try:
            say.write(format_derivation(sim._trace_many([(trace_comp, trace_target, sim.step_no)])[0]))
        except TraceError as exc:  # e.g. retention was exhausted with --trace-best-effort
            say.write("    (derivation unavailable: %s)\n" % exc)
        return True

    shown_marks = 0
    step = 1

    def run_one_step() -> bool:
        """Do one step and print it; True if a stop option asks to end the run after it."""
        nonlocal shown_marks, step
        if human and not quiet:
            out.write("\n\n============\nSTEP %d\n============\n\n" % step if layout == "perl" else "step %d\n" % step)
        step += 1
        sim.step()
        if verifier is not None:
            verifier.check_step()
        if not human:
            fmt.step(sim.step_no, sim.cur, skip, plen)
        elif not quiet:
            (_print_conf if layout == "perl" else _print_text_conf)(out, sim.cur, skip, plen)
        new_marks = sim.marks[shown_marks:]
        shown_marks = len(sim.marks)
        _print_marks_block(say, sim, [m for m in new_marks if not trace_labels or m.label in trace_labels], retain)
        check_trace()
        out.flush()
        if args.progress:
            sys.stderr.write(_progress_line(sim, started))
            sys.stderr.flush()
        return bool(
            (args.stop_on_found and trace_found)
            or (args.stop_on_mark and new_marks)
            or (stop_labels and any(m.label in stop_labels for m in new_marks))
        )

    def _mark_shown() -> None:
        nonlocal shown_marks
        shown_marks = len(sim.marks)

    check_trace()  # the string may already be an axiom (step 0)
    status = 0
    try:
        if interactive:
            session = stepper.Session(sim, out, stdin, skip, plen, layout, _mark_shown, lambda: _print_marks_summary(out, sim.marks, True))
            if not (args.stop_on_found and trace_found):
                while True:
                    count = session.next_count()
                    if count == 0:
                        break
                    stopped = False
                    for _ in range(count):
                        if run_one_step():
                            stopped = True
                            break
                    if stopped:
                        break
        else:
            run_loop = run_steps > 0 and not (args.stop_on_found and trace_found)
            while run_loop:
                if run_one_step():
                    break
                if run_steps < step:
                    break
                if not args.run_empty and not any(sim.cur):
                    sys.stderr.write("gcrsim: no strings remain at step %d; stopping (use --run-empty to continue)\n" % sim.step_no)
                    break
    except LimitReached as exc:
        out.flush()
        sys.stderr.write("gcrsim: %s\n" % out.text(str(exc)))
        status = exc.exit_code
    except KeyboardInterrupt:
        out.flush()
        sys.stderr.write("gcrsim: interrupted during step %d; output of that step may be partial\n" % step)
        status = 130
    if verifier is not None and status == 0:
        sys.stderr.write("gcrsim: verified %d step(s) against the reference interpreter\n" % verifier.steps)
    if args.trace is not None and not trace_found and status == 0:
        say.write("\nTrace of %r (component %d): not found in the steps run\n" % (args.trace, args.component))
    if not quiet and not args.no_mark_summary:
        _print_marks_summary(say, sim.marks, retain or interactive)
    if not human:
        say.flush()
    out.flush()
    if fail_labels and status == 0:
        failing = [m for m in sim.marks if "*" in fail_labels or m.label in fail_labels]
        if failing:
            sys.stderr.write(
                "gcrsim: check failed: %d mark(s) with label(s) %s (first: step %d, component %d, %r)\n"
                % (len(failing), ", ".join(sorted({m.label for m in failing})), failing[0].step,
                   failing[0].component + 1, model.lexicon.decode(failing[0].encoded))
            )
            status = CHECK_FAILED_STATUS
    if not human:
        fmt.end(sim.step_no, status)
        out.flush()
    return status


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Command line entry point; returns the process exit status."""
    if argv is None:
        argv = sys.argv[1:]
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.input_file is None:
        parser.print_help()   # started without a model: show how to use the program
        return 2
    for stream in (sys.stderr,):
        try:
            stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass
    real_stdout = sys.stdout
    out = Output(real_stdout)
    sys.stdout = out  # callbacks that print() stay in order with simulator output
    try:
        return run_cli(args, out, sys.stdin)
    except GcrsimError as exc:
        out.flush()
        sys.stderr.write("gcrsim: %s\n" % out.text(str(exc)))
        return exc.exit_code
    except BrokenPipeError:
        _silence_stdout()
        return 1
    except KeyboardInterrupt:
        try:
            out.flush()
        except BrokenPipeError:
            pass
        sys.stderr.write("gcrsim: interrupted\n")
        return 130
    finally:
        try:
            out.flush()
        except BrokenPipeError:
            _silence_stdout()
        finally:
            sys.stdout = real_stdout


def _silence_stdout() -> None:
    """After a closed pipe, point stdout at the null device (no exit-time error)."""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.__stdout__.fileno())
    except (OSError, ValueError, AttributeError):
        pass
