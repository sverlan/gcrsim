r"""Measures of a derivation: steps, longest form, rule use, symbols created and deleted, non-terminals, components."""
import json

import pytest

import gcrsim
from gcrsim import GcrsimError, Measures, main, measure, parse_model, replay, search
from gcrsim.measures import format_measures

# Lines 6-12 hold the rules; line numbers are part of the expected values.
TWO = """[symbols]
terminals = "a b x"
[axioms]
1 = ["S"]
[rules.1]
S -> a S b, 1
S -> a b, 1
ins(a, c, b), 1
send(), 2
[rules.2]
del(,c,), 2
sub(,a,x,), 2
"""
FORMS = ["S", "aSb", "aabb", "aacbb", "2:aacbb", "2:aabb", "2:xabb"]

NOTERM = TWO.replace('terminals = "a b x"\n', "")

SAME_TEXT = """[axioms]
1 = ["a"]
[rules]
a -> b
b -> a
a -> b
"""

MULTI = """[symbols]
alphabet = "p1 p2 S"
[run]
print_sep = " "
[axioms]
1 = ["S"]
[rules]
S -> p1 S
S -> p2 S
S ->
"""

REGEX = """[axioms]
1 = ["aaa"]
[rules]
re(a+) -> b
"""


@pytest.fixture
def files(tmp_path):
    def make(name, text):
        path = tmp_path / name
        path.write_bytes(text.encode("utf-8"))
        return str(path)
    return make


def cli(capsys, *args):
    status = main([str(a) for a in args])
    cap = capsys.readouterr()
    return status, cap.out, cap.err


def lines_of(out):
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def rules_of(m):
    return [(r["line"], r["component"], r["kind"], r["count"]) for r in m.rules]


# ---------------------------------------------------------------------------
# the fields, by hand
# ---------------------------------------------------------------------------


def test_every_field_with_all_kinds_of_rule_and_two_components():
    rep = replay(parse_model(TWO), FORMS)
    assert rep.ok
    m = rep.measures
    assert isinstance(m, Measures)
    assert m.steps == 6
    assert (m.max_len, m.max_len_step) == (5, 3)  # aacbb, first at step 3 (and again at step 4)
    assert rules_of(m) == [(6, 1, "plain", 1), (7, 1, "plain", 1), (8, 1, "ins", 1), (9, 1, "send", 1), (11, 2, "del", 1),
                           (12, 2, "sub", 1)]
    assert (m.created, m.deleted) == (7, 4)  # 3+2+1+0+0+1 and 1+1+0+0+1+1
    assert (m.max_nonterminals, m.max_nonterminals_step) == (1, 0)  # S, S, none, c, c, none, none
    assert m.components == [{"component": 1, "forms": 4}, {"component": 2, "forms": 3}]
    assert m.rules[0]["notation"] == "S->a S b,1" and m.rules[0]["name"] is None


def test_to_dict_has_the_documented_fields():
    d = replay(parse_model(TWO), FORMS).measures.to_dict()
    assert list(d) == ["steps", "max_len", "max_len_step", "rules", "created", "deleted", "max_nonterminals",
                       "max_nonterminals_step", "components"]
    assert set(d["rules"][0]) == {"line", "component", "notation", "name", "kind", "bindings", "count"}
    json.dumps(d)


def test_terminals_not_declared_leave_the_peak_out():
    m = replay(parse_model(NOTERM), FORMS).measures
    assert m.max_nonterminals is None and m.max_nonterminals_step is None
    assert m.to_dict()["max_nonterminals"] is None
    assert "non-terminal" not in format_measures(m)
    assert m.steps == 6 and m.created == 7


def test_peak_of_nonterminals_is_the_first_step_that_reaches_it():
    model = parse_model('[symbols]\nterminals = "a"\n[axioms]\n1 = ["S"]\n[rules]\nS -> S S\nS -> a\n')
    rep = replay(model, ["S", "SS", "SSS", "aSS", "aaS", "aaa"])
    m = rep.measures
    assert (m.max_nonterminals, m.max_nonterminals_step) == (3, 2)
    assert (m.max_len, m.max_len_step) == (3, 2)


def test_rules_with_the_same_text_on_different_lines_are_different():
    rep = replay(parse_model(SAME_TEXT), ["a", "b", "a", "b"])
    assert rep.ok
    # a -> b is on lines 4 and 6; the replay takes the first rule in the order of the model (line 4) both times
    assert rules_of(rep.measures) == [(4, 1, "plain", 2), (5, 1, "plain", 1)]
    sim = gcrsim.Simulator(parse_model(SAME_TEXT), gcrsim.settings.settings_for_model(parse_model(SAME_TEXT)), write=lambda t: None,
                           retain=True)
    for _ in range(3):
        sim.step()
    chain = sim.trace("b")
    m = measure(chain)
    assert sum(r["count"] for r in m.rules) == m.steps


def test_multicharacter_symbols_count_as_one():
    model = parse_model(MULTI)
    rep = replay(model, ["S", "p1 S", "p1 p2 S", "p1 p2"])
    m = rep.measures
    assert (m.steps, m.max_len, m.max_len_step) == (3, 3, 2)
    assert (m.created, m.deleted) == (2 + 2 + 0, 1 + 1 + 1)


def test_regex_rule():
    rep = replay(parse_model(REGEX), ["aaa", "b"])
    m = rep.measures
    assert rep.ok and m.steps == 1
    assert rules_of(m) == [(4, 1, "re", 1)]
    assert (m.created, m.deleted) == (1, 3)
    assert m.max_len == 3 and m.max_len_step == 0


def test_axiom_only_derivation_and_the_empty_word():
    model = parse_model(TWO)
    rep = replay(model, ["S"])
    m = rep.measures
    assert (m.steps, m.max_len, m.max_len_step, m.rules, m.created, m.deleted) == (0, 1, 0, [], 0, 0)
    assert (m.max_nonterminals, m.max_nonterminals_step) == (1, 0)
    assert m.components == [{"component": 1, "forms": 1}]
    assert "rules: none" in format_measures(m)
    empty = parse_model('[axioms]\n1 = [""]\n[rules]\na -> b\n')
    m = measure([], model=empty, first=[])
    assert (m.steps, m.max_len) == (0, 0)


def test_format_measures_text():
    m = replay(parse_model(TWO), FORMS).measures
    assert format_measures(m) == (
        "    measures: 6 steps, longest form 5 symbols (step 3), at most 1 non-terminal (step 0), 7 symbols created, 4 deleted\n"
        "    rules: S->a S b,1 (line 6) (component 1) x1, S->a b,1 (line 7) (component 1) x1, ins(a,c,b),1 (line 8) (component 1) x1, "
        "send(),2 (line 9) (component 1) x1, del(,c,),2 (line 11) (component 2) x1, sub(,a,x,),2 (line 12) (component 2) x1; components: 1 (4 forms), 2 (3 forms)\n")
    one = replay(parse_model(NOTERM), ["S", "aSb"]).measures
    assert format_measures(one) == (
        "    measures: 1 step, longest form 3 symbols (step 1), 3 symbols created, 1 deleted\n"
        "    rules: S->a S b,1 (line 5) x1; components: 1 (2 forms)\n")


def test_failed_replay_measures_the_checked_prefix():
    rep = replay(parse_model(TWO), ["S", "aSb", "aaSbb", "x"])
    assert not rep.ok
    assert rep.measures.steps == 2
    bad_start = replay(parse_model(TWO), ["aSb"])
    assert not bad_start.ok and bad_start.measures is None
    frag = replay(parse_model(TWO), ["aSb", "aabb"], fragment=True)
    assert frag.ok and frag.measures.steps == 1 and frag.measures.max_len == 4


# ---------------------------------------------------------------------------
# the same derivation by replay, trace, search
# ---------------------------------------------------------------------------


def test_replay_and_trace_of_the_same_derivation_agree(files):
    model = parse_model(TWO)
    sim = gcrsim.Simulator(model, gcrsim.settings.settings_for_model(model), write=lambda t: None, retain=True)
    for _ in range(6):
        sim.step()
    chain = sim.trace("xabb", 1)
    from_trace = measure(chain, model=model)
    forms = ["S"] + [("%d:%s" % (d.target_component + 1, d.result)) for d in chain]
    rep = replay(model, forms)
    assert rep.ok
    assert from_trace == rep.measures
    assert measure(rep.steps, model=model) == rep.measures


def test_search_found_gives_the_measures():
    model = parse_model('[symbols]\nterminals = "a b"\n[axioms]\n1 = ["S"]\n[rules]\nS -> a S b\nS -> a b\n')
    res = search(model, "aabb")
    assert res.found
    m = res.measures
    assert m.steps == 2 and (m.max_len, m.max_len_step) == (4, 2)
    assert (m.max_nonterminals, m.max_nonterminals_step) == (1, 0)
    assert rules_of(m) == [(6, 1, "plain", 1), (7, 1, "plain", 1)]
    assert m == measure(res.derivation, model=model)
    assert search(model, "ab", max_steps=0).measures is None  # not found


def test_search_for_an_axiom_has_empty_measures():
    model = parse_model('[symbols]\nterminals = "a b"\n[axioms]\n1 = ["ab"]\n[rules]\na -> b\n')
    res = search(model, "ab")
    assert res.found and res.derivation == []
    m = res.measures
    assert (m.steps, m.max_len, m.max_nonterminals) == (0, 2, 0)
    assert measure([], model=model, first=["a", "b"]) == m
    assert measure([], model=model, first="ab") == m


# ---------------------------------------------------------------------------
# the Python function
# ---------------------------------------------------------------------------


def test_measure_terminals_argument_overrides_the_model():
    model = parse_model(TWO)
    steps = replay(model, FORMS).steps
    assert measure(steps).max_nonterminals is None  # no model, no terminals
    assert measure(steps, terminals="a b x c S").max_nonterminals == 0
    m = measure(steps, terminals=["a"], model=model)  # only a is a terminal: aacbb has three other symbols
    assert (m.max_nonterminals, m.max_nonterminals_step) == (3, 3)
    assert measure(steps, model=model).max_nonterminals == 1


def test_measure_needs_the_first_form_for_an_empty_derivation():
    with pytest.raises(GcrsimError):
        measure([])
    with pytest.raises(GcrsimError):
        measure([], first="ab")  # no model to read it with


def test_measure_in_the_package():
    assert gcrsim.measure is measure and "measure" in gcrsim.__all__ and "Measures" in gcrsim.__all__


# ---------------------------------------------------------------------------
# the command line: text and jsonl agree
# ---------------------------------------------------------------------------

CLI_MODEL = """[symbols]
terminals = "a b"
[axioms]
1 = ["S"]
[rules]
S -> a S b
S -> a b
"""


def test_trace_prints_the_measures_and_jsonl_has_them(files, capsys):
    path = files("m.txt", CLI_MODEL)
    status, out, _ = cli(capsys, path, "5", "--trace", "aabb")
    assert status == 0
    assert ("    measures: 2 steps, longest form 4 symbols (step 2), at most 1 non-terminal (step 0), 5 symbols created, "
            "2 deleted\n    rules: S->a S b (line 6) x1, S->a b (line 7) x1; components: 1 (3 forms)\n") in out
    status, out, _ = cli(capsys, path, "5", "--trace", "aabb", "--format", "jsonl")
    derivation = [o for o in lines_of(out) if o["type"] == "derivation"][0]
    m = derivation["measures"]
    assert m["steps"] == 2 == derivation["steps"] and m["created"] == 5 and m["deleted"] == 2
    assert m["max_nonterminals"] == 1 and m["max_nonterminals_step"] == 0 and m["max_len_step"] == 2
    assert m["components"] == [{"component": 1, "forms": 3}]
    assert [(r["line"], r["count"]) for r in m["rules"]] == [(6, 1), (7, 1)]


def test_trace_of_an_axiom_has_measures(files, capsys):
    path = files("m.txt", CLI_MODEL)
    status, out, _ = cli(capsys, path, "2", "--trace", "S")
    assert "(axiom: no derivation steps)" in out
    assert "measures: 0 steps, longest form 1 symbol (step 0), at most 1 non-terminal (step 0), 0 symbols created, 0 deleted" in out


def test_trace_marks_print_the_measures(files, capsys):
    text = CLI_MODEL.replace("[axioms]", "[model.marks]\nterminal = '\\A[a-z]*\\Z'\n[axioms]")
    path = files("m.txt", text)
    status, out, _ = cli(capsys, path, "3", "--trace-marks")
    assert status == 0 and out.count("    measures: ") == 3  # ab, aabb, aaabbb
    status, out, _ = cli(capsys, path, "3", "--trace-marks", "--format", "jsonl")
    ds = [o for o in lines_of(out) if o["type"] == "derivation"]
    assert [d["measures"]["steps"] for d in ds] == [1, 2, 3]


def test_search_text_and_jsonl(files, capsys):
    path = files("m.txt", CLI_MODEL)
    status, out, _ = cli(capsys, path, "--mode", "search", "aabb")
    assert status == 0
    assert "    measures: 2 steps, longest form 4 symbols (step 2), at most 1 non-terminal (step 0)" in out
    status, out, _ = cli(capsys, path, "--mode", "search", "aabb", "--format", "jsonl")
    d = [o for o in lines_of(out) if o["type"] == "derivation"][0]
    assert d["measures"] == search(parse_model(CLI_MODEL), "aabb").measures.to_dict()
    status, out, _ = cli(capsys, path, "--mode", "search", "ba")
    assert "measures:" not in out


def test_search_terminals_option_gives_the_peak(files, capsys):
    path = files("m.txt", CLI_MODEL.replace('terminals = "a b"\n', ""))
    status, out, _ = cli(capsys, path, "--mode", "search", "aabb", "--terminals", "a b")
    assert "at most 1 non-terminal (step 0)" in out
    res = search(parse_model(CLI_MODEL), "aabb", terminals="a")  # b counts as a non-terminal
    assert (res.measures.max_nonterminals, res.measures.max_nonterminals_step) == (2, 1)  # S, aSb (S and b), aabb (b b)


def test_replay_explain_and_jsonl(files, capsys):
    path = files("m.txt", CLI_MODEL)
    good = files("good.txt", "S\naSb\naabb\n")
    status, out, _ = cli(capsys, path, "--mode", "replay", good, "--explain")
    assert status == 0
    assert "measures: 2 steps, longest form 4 symbols (step 2), at most 1 non-terminal (step 0), 5 symbols created, 2 deleted" in out
    assert "rules: S->a S b (line 6) x1, S->a b (line 7) x1; components: 1 (3 forms)" in out
    status, out, _ = cli(capsys, path, "--mode", "replay", good, "--format", "jsonl")
    end = lines_of(out)[-1]
    assert end["type"] == "end" and end["measures_partial"] is False
    assert end["measures"]["steps"] == 2 and end["measures"]["created"] == 5
    # a trace of the same derivation gives the same object
    status, tout, _ = cli(capsys, path, "5", "--trace", "aabb", "--format", "jsonl")
    assert [o for o in lines_of(tout) if o["type"] == "derivation"][0]["measures"] == end["measures"]
    bad = files("bad.txt", "S\naSb\nxx\n")
    status, out, _ = cli(capsys, path, "--mode", "replay", bad, "--format", "jsonl")
    end = lines_of(out)[-1]
    assert status != 0 and end["measures_partial"] is True and end["measures"]["steps"] == 1
    notaxiom = files("na.txt", "aSb\n")
    status, out, _ = cli(capsys, path, "--mode", "replay", notaxiom, "--format", "jsonl")
    end = lines_of(out)[-1]
    assert end["measures"] is None and end["measures_partial"] is False


def test_interactive_trace_and_retention_trace_print_the_measures(files, tmp_path, capsys):
    from conftest import run_py
    from gcrsim.retention import trace
    path = files("m.txt", CLI_MODEL)
    expected = ("    measures: 2 steps, longest form 4 symbols (step 2), at most 1 non-terminal (step 0), 5 symbols created, "
                "2 deleted\n    rules: S->a S b (line 6) x1, S->a b (line 7) x1; components: 1 (3 forms)")
    r = run_py([path, "-i", "--quiet"], tmp_path, stdin="n 3\ntrace aabb\ntrace S\nq\n")
    assert r.returncode == 0, r.stderr
    assert expected in r.stdout
    assert "measures: 0 steps, longest form 1 symbol (step 0)" in r.stdout
    db = str(tmp_path / "r.db")
    assert cli(capsys, path, "5", "--trace", "aabb", "--retain-file", db, "--quiet")[0] == 0
    lines = []
    assert trace(db, path, "aabb", 1, write=lines.append) == 0
    assert expected in "\n".join(lines)


def test_search_counts_the_first_form_in_its_own_component():
    model = parse_model('[symbols]\nterminals = "a b"\n[axioms]\n1 = ["aaa"]\n[rules.1]\nsend(), 2\n[rules.2]\nre(a+) -> b, 2\n')
    res = search(model, "b", component=2)
    assert res.found and res.derivation[0].source_component == 0
    assert res.measures.components == [{"component": 1, "forms": 1}, {"component": 2, "forms": 2}]
    rep = replay(model, ["aaa", "2:aaa", "2:b"])
    assert rep.ok and rep.measures == res.measures
    sim = gcrsim.Simulator(model, gcrsim.settings.settings_for_model(model), write=lambda t: None, retain=True)
    sim.step(); sim.step()
    assert measure(sim.trace("b", 1), model=model) == res.measures
