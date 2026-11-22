"""The operations of the command line and the choice between them.

``gcrsim MODEL STEPS`` runs a model; that is the operation ``run``, the default. Other operations are selected with ``--mode NAME``
or with the shorter option of the operation (``--replay FILE`` for ``replay``). The selector may stand anywhere before a ``--``
terminator and must be written in full. Each operation has its own parser, so it accepts only its own arguments.

Adding an operation is one entry in ``operations()``: a name, a function that builds its parser, a handler and, if it has one,
the option that selects it.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from ._meta import CHECK_FAILED_STATUS, __version__
from .errors import GcrsimError, TimeLimitReached
from .listing import Jsonl
from .measures import format_measures, model_terminals
from .output import Output
from .timelimit import Deadline, parse_duration
from .wordsep import warn_print_sep
from ._replay import ReplayReport, check_forms, check_replay_word_sep, parse_forms, read_lines

MODE_OPTION = "--mode"
DEFAULT_MODE = "run"


class Operation:
    """An operation: ``build_parser()`` gives its argparse parser, ``handler(args, out, stdin)`` does it and returns the exit
    status, ``alias`` is the option that selects it (``None`` if only ``--mode`` does) and ``summary`` is one line for the help."""

    __slots__ = ("name", "build_parser", "handler", "alias", "summary", "operand")

    def __init__(self, name: str, build_parser: Callable[[], Any], handler: Callable[[Any, Output, Any], int],
                 alias: Optional[str], summary: str, operand: str = "FILE"):
        self.operand = operand  # what follows the model on the command line
        self.name = name
        self.build_parser = build_parser
        self.handler = handler
        self.alias = alias
        self.summary = summary


def operations() -> List[Operation]:
    """The table of the operations, the default first."""
    from . import cli

    return [
        Operation("run", build_run_parser, cli.run_cli, None, "run the model for a number of steps (the default)"),
        Operation("replay", build_replay_parser, run_replay, "--replay",
                  "check that the forms in FILE are a derivation of the model"),
        Operation("search", build_search_parser, run_search, "--search",
                  "search for the word WORD, breadth first, and print a derivation of it", "WORD"),
    ]


def _modes_note(table: Sequence[Operation]) -> str:
    parts = ["Modes: without a selector the program runs the model for STEPS steps (mode run, the default). Another mode is "
             "selected with --mode NAME or with the shorter option of the mode, written in full:"]
    for op in table:
        if op.name != DEFAULT_MODE:
            short = " (or %s %s)" % (op.alias, op.operand) if op.alias else ""
            parts.append("--mode %s MODEL %s%s: %s." % (op.name, op.operand, short, op.summary))
    parts.append("'gcrsim --mode NAME --help' shows the options of a mode.")
    return " ".join(parts)


def build_run_parser() -> Any:
    """The parser of ``run``: the parser of the command line, with a note about the other modes."""
    from . import cli

    parser = cli._build_parser()
    parser.epilog = _modes_note(operations()) + "\n\n" + (parser.epilog or "")
    return parser


def build_replay_parser() -> Any:
    import argparse

    p = argparse.ArgumentParser(
        prog="gcrsim --mode replay",
        description="Check that a sequence of forms is a derivation of a model. FILE (- for the standard input) has one form per "
                    "line, [N:] WORD, where N is the component (default: --component) and the symbols of WORD are written together "
                    "or separated by white space or by the word_sep setting (--word-sep). Blank lines and lines that start with # are ignored. The first form "
                    "must be an axiom unless --fragment is given. Filters and the history are not checked, and a word with a space as one of its symbols (which a regular-expression rule can produce) cannot be written. Exit status: 0 if every "
                    "step is legal, 4 if one is not, 2 for an error.",
        epilog="The file can be given as the second argument or with --replay FILE (not both).",
        allow_abbrev=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("input_file", nargs="?", metavar="MODEL", help="the model file")
    p.add_argument("file", nargs="?", metavar="FILE", help="the file of forms, or - for the standard input")
    p.add_argument("--replay", dest="replay_file", metavar="FILE", help="the file of forms (the same as the second argument)")
    p.add_argument("--component", type=int, default=1, metavar="N", help="component of the forms without a prefix N: (default 1)")
    p.add_argument("--word-sep", metavar="TEXT",
                   help="TEXT also separates the symbols of a word, as white space does (overrides the setting word_sep); "
                        "TEXT must not occur in a symbol of the model")
    p.add_argument("--fragment", action="store_true", help="the first form need not be an axiom")
    p.add_argument("--explain", action="store_true", help="in the text format, show the rule, the position and the number of ways of every step")
    p.add_argument("--format", choices=("text", "jsonl"), default="text",
                   help="text: a short header, the steps with --explain and a final line (default); "
                        "jsonl: one JSON object per line (header, one per legal step, end)")
    p.add_argument("--quiet", action="store_true", help="in the text format, print only the final line")
    p.add_argument("--max-time", metavar="T",
                   help="stop (exit status 3) when the elapsed time of the program passes T: seconds, or a number with the suffix s, m or h "
                        "(90, 90s, 1.5m, 2h); checked between the steps")
    p.add_argument("--config", metavar="FILE", action="append", default=[],
                   help="configuration (.toml) applied over the model's own settings; repeatable, later files win; "
                        "only print_sep (how --explain writes the words) and word_sep (how the words are read) matter here")
    p.add_argument("--python-filter", metavar="FILE.py",
                   help="run FILE.py (it executes code!) for its settings (print_sep, word_sep); its filters are not applied")
    p.add_argument("--version", action="version", version="gcrsim %s" % __version__)
    return p


# ---------------------------------------------------------------------------
# Choosing the operation
# ---------------------------------------------------------------------------


def _value_options(parsers: Sequence[Any]) -> Tuple[Set[str], Set[str]]:
    """The options that take a value, and all the long options, of the parsers."""
    value: Set[str] = set()
    longs: Set[str] = set()
    for parser in parsers:
        for action in parser._actions:
            for name in action.option_strings:
                if name.startswith("--"):
                    longs.add(name)
                if action.nargs != 0:
                    value.add(name)
    return value, longs


def select(argv: Sequence[str], table: Optional[Sequence[Operation]] = None) -> Tuple[Operation, List[str]]:
    """The operation chosen by ``argv`` and the arguments that remain for its parser (the ``--mode NAME`` tokens are removed).

    The selectors are ``--mode NAME``, ``--mode=NAME`` and the alias of an operation (``--replay FILE``, which stays in the
    arguments of the operation). Only these exact spellings count, only before a ``--``, and not where an option takes
    them as its value (``--trace --mode``). More than one selector is an error, even when they agree."""
    table = list(table) if table is not None else operations()
    by_name: Dict[str, Operation] = {op.name: op for op in table}
    by_alias: Dict[str, Operation] = {op.alias: op for op in table if op.alias}
    value_opts, long_opts = _value_options([op.build_parser() for op in table])
    for alias in by_alias:  # selectors, not ordinary options
        value_opts.discard(alias)
    names = ", ".join(op.name for op in table)
    chosen: List[Operation] = []
    selectors: List[str] = []
    drop: Set[int] = set()
    args = list(argv)
    i = 0
    while i < len(args):
        tok = args[i]
        if tok == "--":
            break
        if tok == MODE_OPTION:
            if i + 1 >= len(args) or args[i + 1] == "--":
                raise GcrsimError("%s needs a mode name (%s)" % (MODE_OPTION, names))
            name = args[i + 1]
            drop.update((i, i + 1))
            i += 2
        elif tok.startswith(MODE_OPTION + "="):
            name = tok[len(MODE_OPTION) + 1:]
            drop.add(i)
            i += 1
        else:
            alias = tok.split("=", 1)[0]
            if alias in by_alias:
                chosen.append(by_alias[alias])
                selectors.append(alias)
                i = i + 1 if "=" in tok else _after_value(args, i)  # the next token is its value
            elif tok.startswith("--") and "=" not in tok and (tok in value_opts or _abbreviates_value_option(tok, long_opts, value_opts)):
                i = _after_value(args, i)
            else:
                i += 1
            continue
        if name not in by_name:
            raise GcrsimError("unknown mode %r: the modes are %s" % (name, names))
        chosen.append(by_name[name])
        selectors.append("%s %s" % (MODE_OPTION, name))
    if len(selectors) > 1:
        raise GcrsimError("more than one mode selector (%s): give one" % ", ".join(selectors))
    rest = [t for k, t in enumerate(args) if k not in drop]
    return (chosen[0] if chosen else by_name[DEFAULT_MODE]), rest


def _after_value(args: Sequence[str], i: int) -> int:
    """The index after the option at ``i`` and its value; a ``--`` is never a value, it ends the scan."""
    return i + 1 if i + 1 < len(args) and args[i + 1] == "--" else i + 2


def _abbreviates_value_option(token: str, long_opts: Set[str], value_opts: Set[str]) -> bool:
    """argparse lets ``--comp`` stand for ``--component``: such a token takes the next one as its value too."""
    matching = [o for o in long_opts if o.startswith(token)]
    return len(matching) == 1 and matching[0] in value_opts


# ---------------------------------------------------------------------------
# replay
# ---------------------------------------------------------------------------


def _shown(text: str) -> str:
    return text if text else "(empty word)"


def run_replay(args: Any, out: Output, stdin: Any) -> int:
    from . import cli
    from .model import parse_model_file

    deadline = Deadline(parse_duration(args.max_time)) if args.max_time is not None else None
    if args.file is not None and args.replay_file is not None:
        raise GcrsimError("the file of forms is given twice (as an argument and with --replay)")
    path = args.file if args.file is not None else args.replay_file
    if path is None:
        raise GcrsimError("no file of forms: give it after the model, or with --replay FILE")
    if not os.path.exists(args.input_file):
        raise GcrsimError("cannot read the model %s: no such file" % args.input_file)
    model = parse_model_file(args.input_file)
    settings, loaded = cli.load_settings_captured(model, args, args.format == "jsonl")  # printed while loading: a message in jsonl
    plain: Callable[[str], str] = cli.make_show(model, settings)  # a string of symbols, with print_sep
    where = "standard input" if path == "-" else path
    check_replay_word_sep(model, settings.word_sep)
    warn_print_sep(model, settings.print_sep)
    forms = parse_forms(model, read_lines(path, stdin), args.component, where, settings.word_sep, checked=True)
    out.decode = None
    jsonl = Jsonl(out.write, model.lexicon.decode, sys.stderr.write, plain, model.lexicon.tokens) if args.format == "jsonl" else None
    quiet = args.quiet and jsonl is None
    if jsonl is not None:
        jsonl.header(__version__, "replay", args.input_file, settings.config_name, settings.description, file=where,
                     fragment=bool(args.fragment))
        jsonl.text(loaded)
    elif not quiet:
        cli._text_header(out, args.input_file, settings, model)
    timed_out = None
    try:
        report = check_forms(model, forms, args.fragment, deadline)
    except TimeLimitReached as exc:  # the steps checked before the time ran out are still reported
        timed_out = exc
        report = ReplayReport(False, list(getattr(exc, "steps", [])), None, bool(args.fragment), len(forms),
                              forms[0][2], forms[0][1], model_terminals(model))
    status = 0 if report.ok else (3 if timed_out is not None else CHECK_FAILED_STATUS)
    for st in report.steps:
        if jsonl is not None:
            jsonl.derivation_step(st)
        elif args.explain and not quiet:
            before, after = plain(st.internal_source), plain(st.internal_result)
            out.write("step %d (lines %d-%d): %s => %s   (component %d -> %d, %s, position %d%s)\n" % (
                st.index, st.lines[0], st.lines[1], _shown(before), _shown(after), st.source_component + 1,
                st.target_component + 1, st.rule.describe(), st.start,
                ", %d ways" % st.ways if st.ways > 1 else ""))
    if args.explain and not quiet and jsonl is None and report.measures is not None:
        out.write(format_measures(report.measures, ""))
    fail = report.failure
    if jsonl is not None:
        failure = None
        if fail is not None:
            failure = {"line": fail.line, "step": fail.step, "component": fail.source_component + 1,
                       "target": None if fail.target_component is None else fail.target_component + 1,
                       "before": model.lexicon.tokens(fail.internal_source), "before_string": plain(fail.internal_source),
                       "after": None if fail.internal_target is None else model.lexicon.tokens(fail.internal_target),
                       "after_string": None if fail.internal_target is None else plain(fail.internal_target),
                       "reason": fail.reason}
        measures = None if report.measures is None else report.measures.to_dict()
        if timed_out is not None:
            jsonl.end(len(report.steps), status, ok=False, failure=None, reason="time", measures=measures,
                      measures_partial=measures is not None)
        else:
            jsonl.end(len(report.steps), status, ok=report.ok, failure=failure, measures=measures,
                      measures_partial=measures is not None and not report.ok)
    elif timed_out is not None:
        out.write("replay of %s: stopped by the time limit (%s) after %d step%s checked; the rest was not checked\n" % (
            where, deadline, len(report.steps), "" if len(report.steps) == 1 else "s"))
    else:
        out.write(_final_line(where, report, plain))
    out.flush()
    return status


def _final_line(where: str, report: ReplayReport, plain: Callable[[str], str]) -> str:
    fail = report.failure
    if fail is None:
        n = len(report.steps)
        note = "filters and the history are not checked"
        if report.fragment:
            note = "the first form is not required to be an axiom; " + note
        return "replay of %s: %d step%s, all legal (%s)\n" % (where, n, "" if n == 1 else "s", note)
    if fail.step == 0:
        return ("replay of %s: line %d: the first form is %s: '%s' (use --fragment to check a derivation that does not start from "
                "an axiom)\n" % (where, fail.line, fail.reason, plain(fail.internal_source)))
    return "replay of %s: step %d (line %d) is not legal: %s: '%s' => '%s'\n" % (
        where, fail.step, fail.line, fail.reason, _shown(plain(fail.internal_source)), _shown(plain(fail.internal_target)))


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def build_search_parser() -> Any:
    import argparse

    p = argparse.ArgumentParser(
        prog="gcrsim --mode search",
        description="Search for a word in a component of a model, breadth first, and print a shortest derivation of it. The terminals "
                    "must be declared (the setting terminals in [symbols], or --terminals). The symbols of WORD are written together, "
                    "or separated by --word-sep or the setting word_sep. Without --max-steps the search runs until the word appears, "
                    "no string remains, or a limit stops it. Exit status: 0 found, 6 not found (everything within the bounds was "
                    "explored), 3 inconclusive (a limit, the time limit or an interruption), 2 for an error.",
        epilog="The word can be given as the second argument or with --search WORD (not both).",
        allow_abbrev=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("input_file", nargs="?", metavar="MODEL", help="the model file")
    p.add_argument("word", nargs="?", metavar="WORD", help="the word to search for")
    p.add_argument("--search", dest="search_word", metavar="WORD", help="the word to search for (the same as the second argument)")
    p.add_argument("--component", type=int, default=1, metavar="N", help="the component in which WORD must appear (default 1)")
    p.add_argument("--word-sep", metavar="TEXT",
                   help="TEXT also separates the symbols of WORD (overrides the setting word_sep); TEXT must not occur in a symbol of the model")
    p.add_argument("--terminals", metavar="SYMBOLS",
                   help="the terminal symbols, separated by white space, for example \"a b\" (overrides the setting terminals)")
    p.add_argument("--max-steps", type=int, metavar="N", help="the depth bound: search at most N steps")
    p.add_argument("--max-nonterminals", type=int, metavar="K",
                   help="drop the strings with more than K non-terminals (a restriction: a negative answer holds only within it)")
    p.add_argument("--no-pruning", action="store_true", help="do not drop the strings whose terminals cannot lead to WORD")
    lim = p.add_argument_group("limits (the search is then inconclusive, exit status 3)")
    lim.add_argument("--max-time", metavar="T",
                     help="elapsed time of the whole run, from the start of the program (seconds, or a number with the suffix s, m or h: "
                          "90, 90s, 1.5m, 2h)")
    lim.add_argument("--max-step-candidates", type=int, metavar="N", help="candidates generated in one step")
    lim.add_argument("--max-history", type=int, metavar="N", help="strings inserted into the history")
    lim.add_argument("--max-step-accepted", type=int, metavar="N", help="strings accepted in one step, over all components")
    lim.add_argument("--max-retained", type=int, metavar="N", help="cap on strings retained for the derivation")
    p.add_argument("--retain-file", metavar="FILE", help="keep the retained strings in this SQLite file instead of in memory")
    p.add_argument("--format", choices=("text", "jsonl"), default="text",
                   help="text: a short header, the derivation and the outcome (default); jsonl: one JSON object per line "
                        "(header, the derivation, messages, end)")
    p.add_argument("--quiet", action="store_true", help="in the text format, print only the outcome")
    p.add_argument("--progress", action="store_true", help="write one summary line per step to stderr")
    p.add_argument("--config", metavar="FILE", action="append", default=[],
                   help="configuration (.toml) applied over the model's own settings; repeatable, later files win")
    p.add_argument("--python-filter", metavar="FILE.py",
                   help="run FILE.py (it executes code!): its function keep(s, component[, ctx]) rejects strings, after the built-in "
                        "pruning (a negative answer is then conditional on it), and its settings apply")
    p.add_argument("--version", action="version", version="gcrsim %s" % __version__)
    return p


def _run_search(args: Any, out: Output, state: Dict[str, Any]) -> int:
    import time

    from . import cli
    from ._search import Search, check_options, declared_terminals, outcome_text, read_target, terminal_chars
    from .engine import format_derivation
    from .model import parse_model_file
    from .retention import SqliteRetention, refuse_protected
    from .timelimit import Deadline, parse_duration
    from .wordsep import check_word_sep

    deadline = Deadline(parse_duration(args.max_time)) if args.max_time is not None else None
    if args.word is not None and args.search_word is not None:
        raise GcrsimError("the word is given twice (as an argument and with --search)")
    text = args.word if args.word is not None else args.search_word
    if text is None:
        raise GcrsimError("no word: give it after the model, or with --search WORD")
    if not os.path.exists(args.input_file):
        raise GcrsimError("cannot read the model %s: no such file" % args.input_file)
    model = parse_model_file(args.input_file)
    jsonl_format = args.format == "jsonl"
    settings, loaded = cli.load_settings_captured(model, args, jsonl_format)
    check_options(model, args.component, args.max_steps, args.max_nonterminals)
    terminals = terminal_chars(model, declared_terminals(model, args.terminals))
    check_word_sep(model, settings.word_sep)
    warn_print_sep(model, settings.print_sep)
    target = read_target(model, text, settings.word_sep)
    plain: Callable[[str], str] = cli.make_show(model, settings)
    if jsonl_format:
        out.decode = None
        fmt: Any = Jsonl(out.write, model.lexicon.decode, sys.stderr.write, plain, model.lexicon.tokens)
        say: Any = cli._LineSink(fmt.text)
        sys.stdout = say  # callbacks that print() end up in the messages
    else:
        fmt = None
        out.decode = cli.make_decode(model, settings)
        say = out
    quiet = args.quiet and fmt is None
    state["fmt"] = fmt
    if args.retain_file:
        refuse_protected(args.retain_file, [args.input_file, args.python_filter, *args.config])
    search = Search(model, settings, target, args.component, terminals, max_steps=args.max_steps,
                    max_nonterminals=args.max_nonterminals, deadline=deadline, pruning=not args.no_pruning, write=say.write,
                    max_step_candidates=args.max_step_candidates, max_history=args.max_history,
                    max_step_accepted=args.max_step_accepted, max_retained=args.max_retained,
                    retain_store=SqliteRetention(args.retain_file) if args.retain_file else None)
    if fmt is not None:
        fmt.header(__version__, "search", args.input_file, settings.config_name, settings.description,
                   word=model.lexicon.tokens(target), word_string=plain(target), component=args.component)
        state["header"] = True
        fmt.text(loaded)
    elif not quiet:
        cli._text_header(out, args.input_file, settings, model)
    if search.obstacle is not None:
        note = "note: pruning is off: " + search.obstacle
        if fmt is not None:
            fmt.text(note)
        else:
            out.flush()
            sys.stderr.write("gcrsim: %s\n" % out.text(note))
    out.flush()
    started = time.perf_counter()

    def progress(sim: Any) -> None:
        if args.progress:
            sys.stderr.write(cli._progress_line(sim, started))
            sys.stderr.flush()

    result = search.run(progress)
    shown = plain(target)
    if fmt is not None:
        say.flush()
        if result.found:
            fmt.derivation(target, args.component - 1, result.step, result.derivation, None, result.measures)
        fmt.record({"type": "end", **result.to_dict()})
    else:
        derived = result.found and not quiet
        if derived:  # the header ends with a blank line
            out.write("Derivation of %s (component %d), first appearing at step %d:\n" % (
                "'%s'" % shown if shown else "the empty word", args.component, result.step)
                      + format_derivation(result.derivation, plain, result.measures))
        out.write(("\n" if derived else "") + outcome_text(result, shown))
    out.flush()
    return result.status


def run_search(args: Any, out: Output, stdin: Any) -> int:
    """The search operation. An interruption at any point, also while the settings are loaded, is the outcome ``inconclusive``
    (``interrupted``), written in the format asked for, with the status 3."""
    state: Dict[str, Any] = {}
    try:
        return _run_search(args, out, state)
    except KeyboardInterrupt:
        from ._search import SearchResult, outcome_text
        from .timelimit import parse_duration

        try:
            seconds: Optional[float] = parse_duration(args.max_time) if args.max_time is not None else None
        except GcrsimError:
            seconds = None
        result = SearchResult("inconclusive", "interrupted", 0, 0, [],
                              {"max_steps": args.max_steps, "max_nonterminals": args.max_nonterminals, "max_len": None,
                               "max_time": seconds},
                              False, "interrupted before the search started", [], component=args.component)
        if args.format == "jsonl":
            fmt = state.get("fmt") or Jsonl(out.write, lambda text: text, sys.stderr.write)
            if not state.get("header"):
                fmt.header(__version__, "search", args.input_file, "", "", component=args.component)
            fmt.record({"type": "end", **result.to_dict()})
        else:
            out.write(outcome_text(result, ""))
        out.flush()
        return result.status
