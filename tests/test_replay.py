r"""Replay: checking that a sequence of forms is a derivation of a model."""
import json
import time
from pathlib import Path

import pytest

import gcrsim
from gcrsim import GcrsimError, Simulator, parse_model, replay
from conftest import ROOT, EXAMPLES, run_py

FEATURES = ROOT / "examples" / "features"
COOKBOOK = ROOT / "examples" / "cookbook"

TWO = """
[axioms]
1 = ["S"]
[rules]
S -> a S, 2
2, S -> S b, 1
S ->
"""

GUARDS = """
[axioms]
1 = ["ab"]
[rules]
a -> c, 1; forbid: b
a -> d, 1; permit: b
a -> e, 2
"""

ALPHABET = """
[symbols]
alphabet = "a b ab"
[axioms]
1 = ["a b"]
[rules]
a -> ab, 1
"""


def cli(args, cwd, stdin=None):
    args = [str(a) for a in args]
    if "--format" not in args and "--help" not in args:
        args += ["--format", "text"]
    return run_py(args, cwd, stdin=stdin, trusted=False)


def write(path: Path, text: str) -> str:
    path.write_bytes(text.encode("utf-8"))
    return str(path)


def lines_of(model, steps, settings=None):
    """Run the simulator and write the derivation of the longest string of the last step as lines of a replay file."""
    st = settings or gcrsim.settings.settings_for_model(model)
    sim = Simulator(model, st, write=lambda t: None, retain=True)
    sim.run(steps)
    found = [(len(s), c, s) for c, comp in enumerate(sim.cur) for s in comp]
    assert found, "the run produced nothing"
    _, c, s = max(found)
    chain = sim._trace_many([(c, s, sim.step_no)])[0]
    lex = model.lexicon
    show = (lambda x: lex.decode_spaced(x, " ")) if lex.has_lexemes else lex.decode
    forms = []
    if chain:
        forms.append("%d: %s" % (chain[0].source_component + 1, show(chain[0].source)))
    for d in chain:
        forms.append("%d: %s" % (d.target_component + 1, show(d.result)))
    return forms


# ---------------------------------------------------------------------------
# the core
# ---------------------------------------------------------------------------


def test_a_legal_derivation_with_components_and_the_empty_word():
    r = replay(parse_model(TWO), ["S", "2: aS", "1: aSb"])
    assert r.ok and len(r.steps) == 2
    r = replay(parse_model(TWO), ["1: S", "1:"])  # S -> (empty), the empty word of component 1
    assert r.ok
    assert r.steps[0].result == "" and r.steps[0].source == "S"


def test_report_fields():
    r = replay(parse_model(TWO), ["# derivation", "", "S", "2: aS", "  1 : aSb"])
    assert r.ok and not r.fragment and r.failure is None
    first = r.steps[0]
    assert (first.index, first.lines, first.source_component, first.target_component) == (1, (3, 4), 0, 1)
    assert (first.source, first.result, first.rule.line, first.start, first.end, first.ways) == ("S", "aS", 5, 0, 1, 1)
    assert r.steps[1].lines == (4, 5) and r.steps[1].rule.notation.startswith("2,S->S b")


def test_first_form_must_be_an_axiom_unless_fragment():
    m = parse_model(TWO)
    r = replay(m, ["aS", "2: aS"])
    assert not r.ok and r.failure.step == 0 and r.failure.line == 1
    assert r.failure.reason == "not an axiom of component 1"
    r = replay(m, ["2: aS", "1: aSb"], fragment=True)
    assert r.ok and r.fragment and len(r.steps) == 1
    r = replay(m, ["2: S"])  # S is an axiom of component 1 only
    assert not r.ok and r.failure.reason == "not an axiom of component 2"


def test_a_guard_that_forbids_the_step_rejects_it():
    m = parse_model(GUARDS)
    assert not replay(m, ["ab", "cb"]).ok  # a -> c would give it, but b is forbidden
    r = replay(m, ["ab", "db"])
    assert r.ok and r.steps[0].rule.notation.startswith("a->d")
    r = replay(m, ["ab", "ab"])  # nothing produces the same string
    assert not r.ok


def test_the_target_component_must_match():
    m = parse_model(GUARDS)
    assert replay(m, ["ab", "2: eb"]).ok
    r = replay(m, ["ab", "1: eb"])
    assert not r.ok
    assert r.failure.reason == "no rule of component 1 gives this string in component 1"
    assert (r.failure.step, r.failure.line, r.failure.source, r.failure.target) == (1, 2, "ab", "eb")
    assert (r.failure.source_component, r.failure.target_component) == (0, 0)


def test_the_first_illegal_step_is_reported_and_the_steps_before_it_kept():
    r = replay(parse_model(TWO), ["S", "2: aS", "1: aSb", "1: aaSb", "1: x"])
    assert not r.ok and len(r.steps) == 2
    assert r.failure.step == 3 and r.failure.line == 4


def test_ways_counts_every_rule_and_position():
    m = parse_model('[axioms]\n1 = ["x"]\n[rules]\nins(,x,)\nre(x) -> xx\n')
    r = replay(m, ["x", "xx"])
    assert r.ok and r.steps[0].ways == 3  # the insertion before x, the insertion after x, and the regular expression
    assert r.steps[0].rule.notation == "ins(,x,)"


def test_an_identical_pair_is_legal_only_if_a_rule_produces_it():
    m = parse_model('[axioms]\n1 = ["a"]\n[rules]\nsend()\n')
    assert replay(m, ["a", "a"]).ok
    assert not replay(parse_model(TWO), ["S", "S"]).ok


def test_default_component_and_prefix_forms():
    m = parse_model(TWO)
    assert replay(m, ["S", "aS"], component=1, fragment=True).failure is not None
    assert replay(m, ["2: S"], component=2, fragment=True).ok
    r = replay(m, ["aS", "1: aSb"], component=2, fragment=True)  # lines without a prefix are in component 2
    assert r.ok
    r = replay(m, [(1, "S"), (2, "aS")])  # pairs, components from 1
    assert r.ok


def test_words_written_together_or_separated():
    m = parse_model((FEATURES / "symbols_and_classes.txt").read_text(encoding="utf-8"))
    for second in ("X a p2", "Xap2", "X  a   p2"):
        r = replay(m, ["p1 a p2", second])
        assert r.ok, second
        assert (r.steps[0].source, r.steps[0].result) == ("p1ap2", "Xap2")


def test_words_are_separated_by_white_space_only():
    m = parse_model('[symbols]\nalphabet = "a b ab"\n[run]\nprint_sep = "|"\n[axioms]\n1 = ["a b"]\n[rules]\na -> ab, 1\n')
    assert replay(m, ["a b", "ab b"]).ok
    with pytest.raises(GcrsimError, match="not in the alphabet"):
        replay(m, ["a|b"])  # print_sep is for the output of a run, not for reading words


def test_overlapping_symbols_with_a_space_printed_between_them():
    m = parse_model((FEATURES / "overlapping_symbols.txt").read_text(encoding="utf-8"))
    r = replay(m, ["S", "ab a b", "ab S"])
    assert r.ok
    assert replay(m, ["S", "ab a b"]).steps[0].result == "abab"
    with pytest.raises(GcrsimError, match=r"more than one way"):
        replay(m, ["S", "aba b"])
    with pytest.raises(GcrsimError, match=r"more than one way"):
        replay(m, ["S", "abab"], source="f.txt")


def test_input_errors_name_the_file_and_the_line():
    m = parse_model(ALPHABET)
    with pytest.raises(GcrsimError, match=r"f\.txt, line 3: .*'c'.*not in the alphabet"):
        replay(m, ["a b", "a b", "c"], source="f.txt")
    with pytest.raises(GcrsimError, match=r"f\.txt, line 2: the component 3 does not exist"):
        replay(m, ["a b", "3: a"], source="f.txt")
    with pytest.raises(GcrsimError, match=r"f\.txt: no forms"):
        replay(m, ["# nothing", "   ", ""], source="f.txt")
    with pytest.raises(GcrsimError, match="between 1 and 1"):
        replay(m, ["a"], component=2)
    assert replay(m, ["a b", "ab b"]).ok


def test_a_word_that_starts_with_digits_needs_a_prefix():
    m = parse_model('[axioms]\n1 = ["12:a"]\n[rules]\n12:a -> 12:b, 1\n')
    with pytest.raises(GcrsimError, match="does not exist"):
        replay(m, ["12:a"])
    assert replay(m, ["1: 12:a", "1: 12:b"]).ok


def test_a_hash_inside_a_word_is_a_symbol():
    m = parse_model('[axioms]\n1 = ["a#"]\n[rules]\na# -> b#, 1\n')
    assert replay(m, ["a#", "b#"]).ok
    r = replay(m, ["1: #", "# comment"], fragment=True)  # '#' after a prefix is a word; the second line is a comment
    assert r.ok and r.forms == 1


@pytest.mark.parametrize(
    "path, steps",
    [
        (COOKBOOK / "07_graph_controlled.txt", 6),
        (COOKBOOK / "02_insdel.txt", 5),
        (COOKBOOK / "20_valence.txt", 6),
        (COOKBOOK / "17_counter_machine.txt", 6),
        (COOKBOOK / "05_evolutionary_processors.txt", 5),
        (FEATURES / "symbols_and_classes.txt", 2),
        (FEATURES / "overlapping_symbols.txt", 3),
        (EXAMPLES / "an_bn_2comp.txt", 6),
        (EXAMPLES / "rc_anbncn.txt", 5),
    ],
    ids=lambda v: v.name if isinstance(v, Path) else str(v),
)
def test_a_derivation_found_by_the_simulator_replays(path, steps, tmp_path):
    model = gcrsim.parse_model_file(str(path))
    forms = lines_of(model, steps)
    assert len(forms) >= 2
    report = replay(model, forms)
    assert report.ok, (forms, report.failure)
    assert len(report.steps) == len(forms) - 1
    f = write(tmp_path / "d.txt", "\n".join(forms) + "\n")
    r = cli([str(path), "--mode", "replay", f], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "all legal" in r.stdout and "%d steps" % (len(forms) - 1) in r.stdout
    # a corrupted form is refused at its line (a symbol outside the alphabet would be an input error, so use a rule-less change)
    bad = list(forms)
    k = len(bad) - 1
    comp, _, word = bad[k].partition(": ")
    bad[k] = "%s: %s" % (comp, word + " " + word)
    r = cli([str(path), "--replay", write(tmp_path / "bad.txt", "\n".join(bad) + "\n")], tmp_path)
    assert r.returncode == 4, (bad, r.stdout, r.stderr)
    assert "step %d (line %d) is not legal" % (k, k + 1) in r.stdout


def test_the_long_derivation_replays_quickly():
    n = 3000
    m = parse_model('[axioms]\n1 = ["a"]\n[rules]\nins(a, b, )\nins(, c, )\nsub(x, y, z, w)\n' + "".join(
        "%s -> %s\n" % (chr(0x4E00 + i), chr(0x4E00 + (i + 1) % 300)) for i in range(300)))
    forms = ["a"]
    word = "a"
    for i in range(n):  # grow by one symbol: insert a b at the end, as ins(a, b, ) does
        word = word + "b"
        forms.append(word)
    started = time.perf_counter()
    report = replay(m, forms)
    elapsed = time.perf_counter() - started
    assert report.ok and len(report.steps) == n
    assert elapsed < 20, elapsed  # a smoke test, not a benchmark
    cycle = [chr(0x4E00 + i % 300) for i in range(n + 1)]
    started = time.perf_counter()
    report = replay(m, cycle, fragment=True)
    assert report.ok and len(report.steps) == n
    assert time.perf_counter() - started < 20


# ---------------------------------------------------------------------------
# the command
# ---------------------------------------------------------------------------


def test_text_output_with_explain(tmp_path):
    m = write(tmp_path / "m.txt", TWO)
    f = write(tmp_path / "d.txt", "S\n2: aS\n1: aSb\n")
    r = cli([m, "--mode", "replay", f, "--explain"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "step 1 (lines 1-2): S => aS   (component 1 -> 2, rule at line 5: S->a S,2, position 0)" in r.stdout
    assert r.stdout.rstrip().endswith("replay of %s: 2 steps, all legal (filters and the history are not checked)" % f)
    r = cli([m, "--mode", "replay", f, "--quiet"], tmp_path)
    assert r.stdout.count("\n") == 1 and r.stdout.startswith("replay of")
    r = cli([m, "--mode", "replay", f], tmp_path)  # the header, no step lines
    assert "gcrsim " in r.stdout and "step 1" not in r.stdout


def test_explain_shows_the_number_of_ways(tmp_path):
    m = write(tmp_path / "m.txt", '[axioms]\n1 = ["x"]\n[rules]\nins(,x,)\n')
    f = write(tmp_path / "d.txt", "x\nxx\n")
    r = cli([m, "--replay", f, "--explain"], tmp_path)
    assert "position 0, 2 ways)" in r.stdout


def test_illegal_derivation_exits_4(tmp_path):
    m = write(tmp_path / "m.txt", TWO)
    f = write(tmp_path / "d.txt", "S\n2: aS\n1: aSbb\n")
    r = cli([m, "--replay", f], tmp_path)
    assert r.returncode == 4
    assert "step 2 (line 3) is not legal: no rule of component 2 gives this string in component 1: 'aS' => 'aSbb'" in r.stdout
    r = cli([m, "--replay", write(tmp_path / "e.txt", "aS\n")], tmp_path)
    assert r.returncode == 4 and "not an axiom of component 1" in r.stdout and "--fragment" in r.stdout
    r = cli([m, "--replay", write(tmp_path / "e.txt", "aS\n"), "--fragment"], tmp_path)
    assert r.returncode == 0 and "0 steps" in r.stdout


def test_input_errors_exit_2(tmp_path):
    m = write(tmp_path / "m.txt", ALPHABET)
    f = write(tmp_path / "d.txt", "a b\n\nc\n")
    r = cli([m, "--replay", f], tmp_path)
    assert r.returncode == 2 and ("%s, line 3:" % f) in r.stderr and "alphabet" in r.stderr
    r = cli([m, "--replay", write(tmp_path / "e.txt", "# only a comment\n")], tmp_path)
    assert r.returncode == 2 and "no forms" in r.stderr
    r = cli([m, "--replay", str(tmp_path / "nothing.txt")], tmp_path)
    assert r.returncode == 2 and "cannot read" in r.stderr
    r = cli([str(tmp_path / "nomodel.txt"), "--replay", f], tmp_path)
    assert r.returncode == 2
    r = cli([m, "--replay", f, "--component", "5"], tmp_path)
    assert r.returncode == 2


def test_component_option_and_stdin(tmp_path):
    m = write(tmp_path / "m.txt", TWO)
    r = cli([m, "--mode", "replay", "-", "--component", "2", "--fragment"], tmp_path, stdin="aS\n1: aSb\n")
    assert r.returncode == 0 and "standard input" in r.stdout and "1 step," in r.stdout
    r = cli([m, "--replay", "-"], tmp_path, stdin="S\r\n2: aS\r\n")
    assert r.returncode == 0 and "1 step," in r.stdout


def test_print_sep_words_from_a_run_can_be_pasted_back(tmp_path):
    m = write(tmp_path / "m.txt", (FEATURES / "overlapping_symbols.txt").read_text(encoding="utf-8"))
    run = cli([m, "2", "--print-all"], tmp_path)
    assert "ab a b" in run.stdout
    f = write(tmp_path / "d.txt", "S\nab a b\nTa b\n")
    r = cli([m, "--replay", f, "--explain"], tmp_path)
    assert r.returncode == 0 and "step 2 (lines 2-3): ab a b => Ta b" in r.stdout, r.stdout


def test_jsonl_output(tmp_path):
    m = write(tmp_path / "m.txt", TWO)
    f = write(tmp_path / "d.txt", "S\n2: aS\n1: aSb\n1: x\n")
    r = cli([m, "--replay", f, "--format", "jsonl"], tmp_path)
    assert r.returncode == 4
    rows = [json.loads(line) for line in r.stdout.splitlines()]
    assert [x["type"] for x in rows] == ["header", "derivation_step", "derivation_step", "end"]
    assert rows[0]["mode"] == "replay" and rows[0]["model"] == m
    step = rows[1]
    assert step == {"type": "derivation_step", "step": 1, "lines": [1, 2], "component": 1, "target": 2, "before": ["S"],
                    "before_string": "S", "after": ["a", "S"], "after_string": "aS",
                    "rule": {"line": 5, "kind": "plain", "notation": "S->a S,2", "name": None, "u": None, "x": ["S"],
                             "y": ["a", "S"], "v": None}, "start": 0, "end": 1, "removed": ["S"], "inserted": ["a", "S"], "ways": 1}
    end = rows[3]
    assert (end["status"], end["ok"], end["steps"]) == (4, False, 2)
    assert end["failure"]["step"] == 3 and end["failure"]["line"] == 4 and end["failure"]["after"] == ["x"] and end["failure"]["after_string"] == "x"
    f = write(tmp_path / "ok.txt", "S\n2: aS\n")
    r = cli([m, "--replay", f, "--format", "jsonl"], tmp_path)
    rows = [json.loads(line) for line in r.stdout.splitlines()]
    assert r.returncode == 0 and rows[-1]["ok"] is True and rows[-1]["failure"] is None


def test_jsonl_has_decoded_symbols(tmp_path):
    m = write(tmp_path / "m.txt", (FEATURES / "symbols_and_classes.txt").read_text(encoding="utf-8"))
    f = write(tmp_path / "d.txt", "p1 a p2\nX a p2\n")
    r = cli([m, "--replay", f, "--format", "jsonl"], tmp_path)
    row = json.loads(r.stdout.splitlines()[1])
    assert (row["before"], row["after"]) == (["p1", "a", "p2"], ["X", "a", "p2"])


def test_only_text_and_jsonl(tmp_path):
    m = write(tmp_path / "m.txt", TWO)
    f = write(tmp_path / "d.txt", "S\n")
    assert cli([m, "--replay", f, "--format", "csv"], tmp_path).returncode == 2
    assert cli([m, "--replay", f, "--format", "perl"], tmp_path).returncode == 2


# ---------------------------------------------------------------------------
# print_sep, internal characters, long words, stdin, guards, filters
# ---------------------------------------------------------------------------


def test_print_sep_never_changes_a_word():
    m = parse_model('[symbols]\nalphabet = "a b xy"\n[run]\nprint_sep = "ab"\n[axioms]\n1 = ["ab"]\n[rules]\na ->\n')
    r = replay(m, ["ab", "b"])
    assert r.ok and r.steps[0].source == "ab"
    m = parse_model('[symbols]\nlexemes = ["xy"]\n[run]\nprint_sep = "-"\n[axioms]\n1 = ["xya"]\n[rules]\na -> b\n')
    assert replay(m, ["xya", "xyb"]).ok and replay(m, ["xy a", "xy  b"]).ok
    m = parse_model('[run]\nprint_sep = "|"\n[axioms]\n1 = ["a"]\n[rules]\nre(a) -> \\x7c\n')
    assert replay(m, ["a", "|"]).ok


def test_trace_reads_the_argument_literally(tmp_path):
    m = write(tmp_path / "m.txt", '[axioms]\n1 = ["a"]\n[rules]\nre(a) -> a\\x20b\n')
    r = cli([m, "1", "--trace", "a b"], tmp_path)
    assert r.returncode == 0 and "first appearing at step 1" in r.stdout


def test_internal_characters_are_refused():
    m = parse_model('[symbols]\nalphabet = "a b ab"\n[axioms]\n1 = ["ab"]\n[rules]\nsend()\n')
    code = next(iter(m.lexicon.names()))
    for bad in (code, "a\x00b", "ab" + code):
        with pytest.raises(GcrsimError, match=r"f\.txt, line 1: .*internal character"):
            replay(m, [bad, "ab"], source="f.txt")


def test_internal_characters_are_refused_on_the_command_line(tmp_path):
    m = write(tmp_path / "m.txt", TWO)
    r = cli([m, "--replay", "-"], tmp_path, stdin="S\x00\n")
    assert r.returncode == 2 and "internal character" in r.stderr and "line 1" in r.stderr


def test_a_long_word_with_an_alphabet_replays(tmp_path):
    word = "aX" * 1500
    m = write(tmp_path / "m.txt", (FEATURES / "symbols_and_classes.txt").read_text(encoding="utf-8"))
    r = cli([m, "--replay", "-", "--fragment"], tmp_path, stdin=word + "\n")
    assert r.returncode == 0, r.stderr


def test_a_huge_component_prefix_is_an_input_error(tmp_path):
    m = parse_model(TWO)
    with pytest.raises(GcrsimError, match="line 1: the component"):
        replay(m, ["9" * 5000 + ": a"])
    with pytest.raises(GcrsimError, match="does not exist"):
        replay(m, ["0: a"])
    assert replay(m, ["0001: S"]).ok


def test_stdin_and_file_are_read_alike(tmp_path):
    m = write(tmp_path / "m.txt", TWO)
    text = "﻿# bom\nS\r\n2: aS\n".encode("utf-8")
    (tmp_path / "d.txt").write_bytes(text)
    a = cli([m, "--replay", "d.txt", "--quiet"], tmp_path)
    import subprocess, sys
    from conftest import CLI_ENV
    p = subprocess.run([sys.executable, "-m", "gcrsim", m, "--replay", "-", "--quiet", "--format", "text"], cwd=str(tmp_path),
                       env=CLI_ENV, input=text, capture_output=True)
    b = p.stdout.decode("utf-8")
    assert a.returncode == p.returncode == 0
    assert a.stdout.split(": ", 1)[1] == b.split(": ", 1)[1]  # the same report, whatever the name of the input
    bad = subprocess.run([sys.executable, "-m", "gcrsim", m, "--replay", "-", "--format", "text"], cwd=str(tmp_path), env=CLI_ENV,
                         input=b"S\n\xff\n", capture_output=True)
    assert bad.returncode == 2 and b"not UTF-8" in bad.stderr


def test_a_guarded_send_to_another_component():
    m = parse_model('[axioms]\n1 = ["ab"]\n[rules]\nsend(), 2; permit: b\n')
    assert replay(m, ["ab", "2: ab"]).ok
    assert not replay(m, ["ab", "1: ab"]).ok
    m = parse_model('[axioms]\n1 = ["ab"]\n[rules]\nsend(), 2; forbid: b\n')
    assert not replay(m, ["ab", "2: ab"]).ok


def test_filters_are_not_applied_by_replay():
    text = '[model]\nreject_max_len = 2\n[axioms]\n1 = ["a"]\n[rules]\nins(,a,)\n'
    m = parse_model(text)
    st = gcrsim.settings.settings_for_model(m)
    sim = Simulator(m, st, write=lambda t: None)
    sim.run(3)
    assert "aaaa" not in sim.strings()[0]  # the simulator drops what is longer than 2
    assert replay(m, ["a", "aa", "aaa", "aaaa"]).ok
