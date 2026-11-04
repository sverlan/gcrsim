"""Checking a grammar: expected terminal strings, everything else is flagged and traced."""

import pytest

import gcrsim
from gcrsim import CallbackError, ConfigError, Settings
from conftest import write_model, parse_old, EXAMPLES, run_py

NOFILTER = dict(reject_strings="(?!)", reject_max_len=1000, print_hide="(?!)", print_max_len=1000)
GOOD = """[axioms]
1 = ["S"]

[rules]
S->aS,2
2,S->Sb
S->
"""
BAD = GOOD + "1,S->bb,1\n"
EXPECTED = {"a" * n + "b" * n for n in range(30)}


def sim_of(text, marks, **kw):
    settings = Settings(**NOFILTER)
    settings.marks = marks
    return gcrsim.Simulator(gcrsim.parse_model(text), settings, write=lambda t: None, **kw)


def flagged(sim):
    return [m.string for m in sim.marks]


def test_expected_terminal_strings_are_not_marked_and_the_rest_are():
    marks = {1: {"unexpected": {"pattern": r"\A[ab]*\Z", "expected": EXPECTED}}}
    good = sim_of(GOOD, marks)
    good.run(10)
    assert flagged(good) == []  # nothing deviates from the plan
    bad = sim_of(BAD, marks)
    bad.run(8)
    assert flagged(bad) == ["bb", "abbb", "aabbbb", "aaabbbbb"]


def test_nonterminal_strings_are_never_flagged():
    sim = sim_of(BAD, {1: {"unexpected": {"pattern": r"\A[ab]*\Z", "expected": EXPECTED}}})
    sim.run(4)
    assert all(set(s) <= set("ab") for s in flagged(sim))


def test_expected_accepts_any_collection_of_strings():
    for collection in (["x"], ("x",), {"x"}, frozenset({"x"}), (s for s in ["x"])):
        sim = sim_of("""[axioms]
1 = ["a"]

[rules]
a->x
a->y
""", {1: {"u": {"pattern": r".", "expected": collection}}})
        sim.step()
        assert flagged(sim) == ["y"]


def test_empty_expected_set_flags_every_matching_string():
    sim = sim_of("""[axioms]
1 = ["a"]

[rules]
a->x
""", {1: {"u": {"pattern": r".", "expected": set()}}})
    sim.step()
    assert flagged(sim) == ["x"]


@pytest.mark.parametrize("bad", ["abc", b"abc", 5, None, [1, 2], ["a", 3]])
def test_expected_must_be_a_collection_of_strings(bad):
    with pytest.raises(ConfigError):
        sim_of(GOOD, {1: {"u": {"pattern": r".", "expected": bad}}})


def test_expected_re_with_a_regex_a_function_or_a_list():
    def anbn(s):
        n = len(s) // 2
        return s == "a" * n + "b" * n

    for expected_re in (r"\A(?:ab|aabb|aaabbb|)\Z", anbn, [r"\A\Z", anbn], [anbn, r"\Aab\Z"]):
        sim = sim_of(BAD, {1: {"unexpected": {"pattern": r"\A[ab]*\Z", "expected_re": expected_re}}})
        sim.run(7)
        assert flagged(sim) == ["bb", "abbb", "aabbbb", "aaabbbbb"], expected_re


def test_expected_and_expected_re_can_be_combined():
    marks = {1: {"u": {"pattern": r"\A[ab]*\Z", "expected": {"ab"}, "expected_re": r"\Abb\Z"}}}
    sim = sim_of(BAD, marks)
    sim.run(6)
    assert flagged(sim) == ["", "abbb", "aabb", "aabbbb"]  # the empty word and aabb are not in this small set


def test_a_failing_predicate_is_reported_with_its_location():
    def boom(s):
        raise ValueError("no")

    sim = sim_of(GOOD, {1: {"u": {"pattern": r".*", "expected_re": boom}}})
    sim.config_name = None
    with pytest.raises(CallbackError, match="'expected_re' of mark 'u' failed at step 1"):
        sim.step()


@pytest.mark.parametrize("expected_re", [5, [], [5], ("(",), "("])
def test_invalid_expected_re_is_a_config_error(expected_re):
    with pytest.raises(ConfigError):
        sim_of(GOOD, {1: {"u": {"pattern": r".", "expected_re": expected_re}}})


def test_streaming_flags_the_same_strings_in_the_same_order():
    marks = {0: {"u": {"pattern": r"\A[ab]*\Z", "expected": EXPECTED}}}
    a, b = sim_of(BAD, marks), sim_of(BAD, marks, streaming=True)
    a.run(8)
    b.run(8)
    assert [(m.step, m.component, m.string) for m in a.marks] == [(m.step, m.component, m.string) for m in b.marks]


# -- command line: the checking workflow ------------------------------------------------------------------------


def test_example_check_flags_the_deviations_and_exits_with_status_4():
    r = run_py(["an_bn_check.txt", "8", "--trace-mark-label", "unexpected", "--fail-on-mark", "unexpected"], EXAMPLES)
    assert r.returncode == 4, r.stderr
    assert "Mark (unexpected): abbb" in r.stdout
    assert "Mark [unexpected] at step 3, component 1: abbb" in r.stdout
    assert "step 3: aSb => abbb" in r.stdout  # the derivation of the deviating string
    assert "Marks (4, 4 distinct):" in r.stdout
    assert "check failed: 4 mark(s) with label(s) unexpected (first: step 1, component 1, 'bb')" in r.stderr
    assert "Mark (unexpected): aabb\n" not in r.stdout  # expected strings stay silent


def test_a_correct_grammar_passes_the_check(tmp_path):
    write_model(tmp_path / "m.txt", GOOD)
    (tmp_path / "m_conf.py").write_text(
        "components = {1: {'marks': {'unexpected': {'pattern': r'\\A[ab]*\\Z', 'expected': {'a'*n + 'b'*n for n in range(30)}}}}}\n"
    )
    r = run_py(["m.txt", "10", "--fail-on-mark", "unexpected"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "Mark (" not in r.stdout and "Marks (" not in r.stdout


def test_fail_on_mark_label_selection_and_wildcard(tmp_path):
    write_model(tmp_path / "m.txt", GOOD)
    (tmp_path / "c.py").write_text("components = {1: {'marks': {'info': r'\\Aab\\Z', 'bad': r'\\Azzz\\Z'}}}\n")
    assert run_py(["m.txt", "4", "--python-filter", "c.py", "--fail-on-mark", "bad"], tmp_path).returncode == 0
    r = run_py(["m.txt", "4", "--python-filter", "c.py", "--fail-on-mark", "info"], tmp_path)
    assert r.returncode == 4 and "label(s) info" in r.stderr
    assert run_py(["m.txt", "4", "--python-filter", "c.py", "--fail-on-mark", "*"], tmp_path).returncode == 4
    assert run_py(["m.txt", "4", "--python-filter", "c.py", "--fail-on-mark", "bad", "--fail-on-mark", "info"], tmp_path).returncode == 4


def test_a_limit_stop_keeps_its_own_status_over_the_check_status(tmp_path):
    write_model(tmp_path / "m.txt", BAD)
    (tmp_path / "c.py").write_text("components = {1: {'marks': {'u': r'\\Abb\\Z'}}}\n")
    r = run_py(["m.txt", "9", "--python-filter", "c.py", "--fail-on-mark", "u", "--max-history", "3"], tmp_path)
    assert r.returncode == 3


def test_trace_mark_label_restricts_the_derivations(tmp_path):
    write_model(tmp_path / "m.txt", GOOD)
    (tmp_path / "c.py").write_text("components = {1: {'marks': {'info': r'\\Aab\\Z', 'other': r'\\A\\Z'}}}\n")
    r = run_py(["m.txt", "4", "--python-filter", "c.py", "--trace-mark-label", "info"], tmp_path)
    assert "Mark [info] at step 3, component 1: ab" in r.stdout
    assert "Mark [other]" not in r.stdout  # recorded and listed in the summary, but not traced
    assert "[other] component 1:" in r.stdout


def test_stop_on_mark_label(tmp_path):
    write_model(tmp_path / "m.txt", GOOD)
    (tmp_path / "c.py").write_text("components = {1: {'marks': {'info': r'\\A\\Z', 'bad': r'\\Aab\\Z'}}}\n")
    r = run_py(["m.txt", "20", "--python-filter", "c.py", "--stop-on-mark-label", "bad"], tmp_path)
    assert "STEP 3" in r.stdout and "STEP 4" not in r.stdout  # the empty word (info) at step 1 did not stop the run
