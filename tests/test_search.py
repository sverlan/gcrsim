r"""Search: breadth-first search for a word, with pruning by the terminals, outcomes, limits and the time limit."""
import json
import re
from pathlib import Path

import pytest

import gcrsim
from gcrsim import GcrsimError, Simulator, main, parse_model, replay, search
from gcrsim import _search, operations
from gcrsim.timelimit import describe, parse_duration
from conftest import ROOT

PY = ROOT / "examples" / "python"

# a^n b^n: S is the only non-terminal
ANBN = """
[symbols]
alphabet = "a b c d S"
terminals = "a b"
[axioms]
1 = ["S"]
[rules]
S -> a S b
S ->
"""

# every word over {a, b}: the number of strings doubles with every step
FREE = """
[symbols]
alphabet = "a b S"
terminals = "a b"
[axioms]
1 = ["S"]
[rules]
ins(, a, )
ins(, b, )
del(, S, )
"""

# the witness of ab needs two non-terminals at once
PEAK = """
[symbols]
alphabet = "a b S X Y"
terminals = "a b"
[axioms]
1 = ["S"]
[rules]
S -> X Y
X -> a
Y -> b
"""

INSDEL = """
[symbols]
alphabet = "a b"
terminals = "a b"
[axioms]
1 = ["ab"]
[rules]
ins(a, ab, b)
"""

# three components: the words are built in 1, sent to 2 and 3, and component 3 inserts b after an a
CHAIN = """
[symbols]
alphabet = "a b S"
terminals = "a b"
[axioms]
1 = ["S"]
[rules.1]
S -> a S, 1
S -> b S, 1
S ->, 2
[rules.2]
send(), 3
[rules.3]
ins(a, b, ), 3
"""

CLASSES = """
[symbols]
alphabet = "a b c S"
terminals = "a b c"
[symbols.classes]
V = "a b"
[axioms]
1 = ["S"]
[rules]
S -> a S
S -> b S
S ->
ins({V}, c, )
"""

MULTI = """
[symbols]
alphabet = "p1 p2 S"
terminals = "p1 p2"
[run]
print_sep = " "
[axioms]
1 = ["S"]
[rules]
S -> p1 S
S -> p2 S
S ->
"""


def model_of(text):
    return parse_model(text)


def with_rule(base, rule):
    return base.rstrip("\n") + "\n" + rule + "\n"


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


def jsonl(out):
    return [json.loads(line) for line in out.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# outcomes
# ---------------------------------------------------------------------------


def test_found_with_the_shortest_derivation():
    res = search(model_of(ANBN), "aabb")
    assert (res.outcome, res.reason, res.found, res.step, res.status) == ("found", "found", True, 3, 0)
    assert [d.step for d in res.derivation] == [1, 2, 3]
    assert [d.result for d in res.derivation] == ["aSb", "aaSbb", "aabb"]


def test_not_found_because_no_strings_remain():
    res = search(model_of(ANBN), "ba")
    assert (res.outcome, res.reason, res.status, res.limit) == ("not_found", "frontier_exhausted", 6, None)
    assert res.step == 2 and not res.found and res.derivation == []


def test_not_found_because_the_depth_bound_was_reached():
    res = search(model_of(ANBN), "aaaabbbb", max_steps=2)
    assert (res.outcome, res.reason, res.step, res.status) == ("not_found", "depth_bound", 2, 6)
    assert res.bounds["max_steps"] == 2


def test_the_depth_bound_does_not_hide_a_word_found_exactly_at_it():
    assert search(model_of(ANBN), "aabb", max_steps=3).found
    assert not search(model_of(ANBN), "aabb", max_steps=2).found


def test_without_pruning_the_same_outcome_is_reached_the_long_way():
    res = search(model_of(ANBN), "ba", max_steps=6, pruning=False)
    assert (res.outcome, res.reason) == ("not_found", "depth_bound")
    assert res.pruning is False and "switched off" in res.pruning_note


@pytest.mark.parametrize("name,kwargs,limit", [
    ("candidates", {"max_step_candidates": 3}, "max-step-candidates"),
    ("history", {"max_history": 20}, "max-history"),
    ("accepted", {"max_step_accepted": 5}, "max-step-accepted"),
    ("retained", {"max_retained": 6}, "max-retained"),
])
def test_a_limit_makes_the_search_inconclusive(name, kwargs, limit):
    res = search(model_of(FREE), "abbaabba", **kwargs)
    assert (res.outcome, res.reason, res.limit, res.status, res.found) == ("inconclusive", "limit", limit, 3, False)
    assert res.derivation == []
    assert res.step < 8


def test_the_time_limit_makes_the_search_inconclusive():
    res = search(model_of(FREE), "abbaabbaabbaabbaab", max_time=0.3, pruning=False)
    assert (res.outcome, res.reason, res.limit, res.status) == ("inconclusive", "time", None, 3)
    assert res.bounds["max_time"] == 0.3 and 1 <= res.step < 19


def test_the_time_limit_is_checked_while_a_step_is_generated():
    import time
    # one step of this search has hundreds of thousands of candidates: the limit must stop it long before the step ends
    started = time.monotonic()
    res = search(model_of(FREE), "ab" * 9, max_time=0.2, pruning=False)
    assert res.reason == "time" and time.monotonic() - started < 2.0


def test_an_interruption_is_an_outcome():
    def keep(s, component):
        raise KeyboardInterrupt

    res = search(model_of(ANBN), "aabb", keep=keep)
    assert (res.outcome, res.reason, res.status, res.step, res.limit) == ("inconclusive", "interrupted", 3, 0, None)


def test_a_partial_exploration_is_never_not_found():
    for kwargs in ({"max_history": 5}, {"max_step_accepted": 2}, {"max_time": 1e-9}, {"max_retained": 3}):
        assert search(model_of(FREE), "abbbaabb", **kwargs).outcome == "inconclusive"


def test_the_word_may_be_an_axiom_or_empty():
    res = search(model_of(ANBN), "S")
    assert (res.outcome, res.step, res.derivation) == ("found", 0, [])
    res = search(model_of(ANBN), "")
    assert (res.found, res.step) == (True, 1) and res.derivation[0].result == ""
    res = search(model_of(with_rule(ANBN.replace('["S"]', '["S", ""]'), "")), "")
    assert (res.found, res.step) == (True, 0)


def test_the_word_may_hold_non_terminals():
    res = search(model_of(ANBN), "aaSbb")
    assert (res.found, res.step) == (True, 2)
    assert search(model_of(ANBN), "bSa").reason == "frontier_exhausted"


def test_the_component_counts_from_1():
    model = model_of(CHAIN)
    assert search(model, "ab", component=3).found
    assert search(model, "ab", component=3).derivation[-1].target_component == 2
    assert search(model, "ab", component=2).found      # the word passes through component 2
    with pytest.raises(GcrsimError, match="between 1 and 3"):
        search(model, "ab", component=4)
    with pytest.raises(GcrsimError, match="between 1 and 3"):
        search(model, "ab", component=0)


def test_the_result_fields_and_the_dictionary():
    res = search(model_of(ANBN), "aabb", max_steps=9, max_nonterminals=2, max_time=60, keep=gcrsim.settings.declare_pure(lambda s, c: True))
    assert res.explored >= 3 and res.pruning is True and res.pruning_note is None
    assert res.bounds == {"max_steps": 9, "max_nonterminals": 2, "max_len": None, "max_time": 60.0}
    assert res.conditional == ["python_filter", "max_nonterminals"]
    d = res.to_dict()
    assert list(d) == ["status", "steps", "outcome", "reason", "limit", "explored", "bounds", "pruning", "conditional"]
    assert d["pruning"] == {"on": True, "reason": None} and d["steps"] == 3 and d["status"] == 0
    json.dumps(d)


def test_the_bounds_name_the_length_bound_of_the_model():
    res = search(model_of(ANBN.replace("[axioms]", "[model]\nreject_max_len = 9\n[axioms]")), "aabb")
    assert res.bounds["max_len"] == 9 and res.conditional == ["max_len"]


def test_hash_history_is_a_condition():
    model = model_of(ANBN)
    st = gcrsim.settings.settings_for_model(model)
    st.hash_history = True
    assert search(model, "ba", settings=st).conditional == ["hash_history"]
    assert st.hash_history and search(model, "ba").conditional == []


# ---------------------------------------------------------------------------
# terminals
# ---------------------------------------------------------------------------


def test_terminals_must_be_declared():
    model = model_of(ANBN.replace('terminals = "a b"\n', ""))
    with pytest.raises(GcrsimError, match="terminals are not declared.*--terminals"):
        search(model, "aabb")
    assert search(model, "aabb", terminals="a b").found
    assert search(model, "aabb", terminals=["a", "b"]).found
    assert search(model_of(ANBN), "aabb", terminals="a b").found


def test_an_unknown_terminal_is_an_error():
    with pytest.raises(GcrsimError, match="'z' is not a symbol of the model"):
        search(model_of(ANBN), "aabb", terminals="a z")
    with pytest.raises(GcrsimError, match="'ab' is not a symbol"):
        search(model_of(ANBN), "aabb", terminals=["ab"])
    with pytest.raises(GcrsimError, match="not a symbol"):
        search(model_of(ANBN.replace('terminals = "a b"', 'terminals = "a q"')), "aabb")


def test_the_option_wins_over_the_setting():
    model = model_of(with_rule(ANBN, "b -> c"))        # a rule rewrites the terminal b of the setting
    assert search(model, "aabb").pruning is False
    assert search(model, "aabb", terminals="a").pruning is True


def test_terminals_must_be_a_string_in_the_model():
    with pytest.raises(GcrsimError, match="terminals must be a string"):
        model_of(ANBN.replace('terminals = "a b"', "terminals = 3"))


def test_the_setting_terminals_is_ignored_by_a_run_and_a_replay(files, capsys):
    model = files("m.txt", ANBN)
    status, out, err = cli(capsys, model, 3, "--format", "csv")
    assert status == 0 and "aSb" in out
    forms = files("d.txt", "S\naSb\n")
    assert cli(capsys, model, "--replay", forms, "--format", "text")[0] == 0


def test_the_setting_belongs_to_the_model_not_to_a_configuration(files, capsys):
    model = files("m.txt", ANBN)
    cfg = files("c.toml", '[symbols]\nterminals = "a"\n')
    status, out, err = cli(capsys, model, 2, "--config", cfg)
    assert status == 2 and "[symbols]" in err


# ---------------------------------------------------------------------------
# the condition for pruning
# ---------------------------------------------------------------------------


def obstacle(extra, terminals="a b"):
    model = model_of(with_rule(ANBN, extra))
    return _search.pruning_obstacle(model, _search.terminal_chars(model, terminals.split()))


@pytest.mark.parametrize("rule,words", [
    ("a -> c", "a->c (line 10) rewrites the terminal a"),
    ("S b -> S", "rewrites the terminal b"),
    ("sub(, b, c, )", "rewrites the terminal b"),
    ("del(, a, )", "deletes the terminal a"),
    ("del(a, b, )", "deletes the terminal b"),
])
def test_a_rule_that_rewrites_or_deletes_a_terminal_turns_pruning_off(rule, words):
    note = obstacle(rule)
    assert note is not None and "rule " in note and "(line " in note and words in note.replace(" ", " ")
    res = search(model_of(with_rule(ANBN, rule)), "aabb")
    assert res.pruning is False and res.pruning_note == note and res.found


@pytest.mark.parametrize("rule,words", [
    ("del(, {any}, )", "{any} in the part it replaces: cannot be checked"),
    ("{V} -> c", "a class in the part it replaces: cannot be checked"),
    ("re(c+) -> c", "regular-expression rule: cannot be checked"),
])
def test_a_class_any_or_a_regular_expression_cannot_be_checked(rule, words):
    text = with_rule(ANBN.replace('[axioms]', '[symbols.classes]\nV = "S c"\n[axioms]'), rule)
    model = model_of(text)
    note = _search.pruning_obstacle(model, _search.terminal_chars(model, ["a", "b"]))
    assert note is not None and words in note
    res = search(model, "aabb")
    assert res.pruning is False and res.found


@pytest.mark.parametrize("rule", [
    "ins(a, b, )",             # an insertion
    "ins({V}, b, {V})",        # a class in the context
    "del(a, S, b)",            # the context holds terminals, the part deleted does not
    "S -> a S, 1; forbid: b",  # a guard
    "send(), 1",
    "{start} S -> S",
    "c -> d",                  # not a terminal
])
def test_what_cannot_remove_a_terminal_leaves_pruning_on(rule):
    text = ANBN.replace('[axioms]', '[symbols.classes]\nV = "a b"\n[axioms]')
    model = model_of(with_rule(text, rule))
    assert _search.pruning_obstacle(model, _search.terminal_chars(model, ["a", "b"])) is None
    assert search(model, "aabb").pruning is True


def test_the_first_offending_rule_is_named_with_its_line_and_text():
    text = with_rule(with_rule(ANBN, "S -> a"), "a -> c")
    assert obstacle("S -> a") is None
    note = _search.pruning_obstacle(model_of(text), "ab")
    assert note.startswith("rule a->c (line 11)")


def test_the_note_is_written_at_the_start(files, capsys):
    model = files("m.txt", with_rule(ANBN, "a -> c"))
    status, out, err = cli(capsys, model, "--search", "aabb")
    assert status == 0 and "gcrsim: note: pruning is off: rule a->c (line 10) rewrites the terminal a" in err
    assert "pruning off (rule a->c (line 10)" in out
    status, out, err = cli(capsys, model, "--search", "aabb", "--format", "jsonl")
    msgs = [o for o in jsonl(out) if o["type"] == "message"]
    assert any("pruning is off: rule a->c (line 10)" in m["text"] for m in msgs)
    end = jsonl(out)[-1]
    assert end["pruning"]["on"] is False and "rewrites the terminal a" in end["pruning"]["reason"]


def test_no_pruning_is_said_in_the_outcome_but_is_not_a_note(files, capsys):
    status, out, err = cli(capsys, files("m.txt", ANBN), "--search", "aabb", "--no-pruning")
    assert status == 0 and "note:" not in err and "pruning off (switched off by the user)" in out


# ---------------------------------------------------------------------------
# soundness
# ---------------------------------------------------------------------------

CASES = [
    (ANBN, "aabb", 1), (ANBN, "aaabbb", 1), (ANBN, "ba", 1), (ANBN, "abab", 1), (ANBN, "aSb", 1), (ANBN, "aaSbb", 1),
    (INSDEL, "aaabbb", 1), (INSDEL, "abab", 1), (INSDEL, "aabbab", 1), (INSDEL, "aab", 1),
    (CHAIN, "ab", 3), (CHAIN, "aabb", 3), (CHAIN, "bba", 3), (CHAIN, "abb", 2), (CHAIN, "bab", 3),
    (CLASSES, "acb", 1), (CLASSES, "acacb", 1), (CLASSES, "ca", 1), (CLASSES, "abc", 1),
    (PEAK, "ab", 1), (PEAK, "ba", 1), (PEAK, "XY", 1),
    (FREE, "abba", 1), (FREE, "baab", 1),
]


def plain_step(model, word, component, bound):
    """The step of a plain run (no pruning, no search) in which the word first appears in the component, or None."""
    sim = Simulator(model, write=lambda t: None)
    target = model.lexicon.encode(word)
    if target in sim.cur[component - 1]:
        return 0
    for _ in range(bound):
        sim.step()
        if target in sim.cur[component - 1]:
            return sim.step_no
    return None


@pytest.mark.parametrize("text,word,component", CASES)
def test_pruned_and_unpruned_searches_agree(text, word, component):
    model = model_of(text)
    bound = 7
    pruned = search(model, word, component=component, max_steps=bound)
    plain = search(model, word, component=component, max_steps=bound, pruning=False)
    assert pruned.pruning and not plain.pruning
    assert pruned.outcome == plain.outcome
    assert pruned.step == plain.step or not pruned.found
    assert pruned.explored <= plain.explored
    expected = plain_step(model, word, component, bound)
    assert (pruned.step if pruned.found else None) == expected      # breadth first: the step of a plain run
    if pruned.found and pruned.derivation:
        lex = model.lexicon
        first = pruned.derivation[0]
        forms = ["%d: %s" % (first.source_component + 1, first.source)]
        forms += ["%d: %s" % (d.target_component + 1, d.result) for d in pruned.derivation]
        assert replay(model, forms).ok
        assert len(pruned.derivation) == pruned.step


def test_pruning_explores_fewer_strings_when_it_can():
    model = model_of(FREE)
    pruned = search(model, "abbabaab")
    plain = search(model, "abbabaab", pruning=False)
    assert pruned.step == plain.step == 9
    assert pruned.explored * 3 < plain.explored


def test_the_cap_on_non_terminals_excludes_a_witness_that_needs_more():
    model = model_of(PEAK)
    assert search(model, "ab").step == 3
    capped = search(model, "ab", max_nonterminals=1)
    assert (capped.outcome, capped.reason) == ("not_found", "frontier_exhausted")
    assert capped.conditional == ["max_nonterminals"] and capped.bounds["max_nonterminals"] == 1
    found = search(model, "ab", max_nonterminals=2)
    assert found.found and found.step == 3 and found.conditional == ["max_nonterminals"]


def test_the_cap_applies_when_pruning_is_off():
    model = model_of(PEAK)
    res = search(model, "ab", max_nonterminals=1, pruning=False)
    assert res.outcome == "not_found" and not res.pruning
    assert search(model, "ab", max_nonterminals=2, pruning=False).found


def test_the_pruner_counts_what_is_not_a_terminal_as_a_non_terminal():
    pruner = _search.Pruner("ab", "abab", 1)
    assert pruner(["ab", "aSb", "aSSb", "ba", "abab", "aabab", "X"]) == ["ab", "aSb", "ba", "abab", "X"]
    assert _search.Pruner("ab", None, None)(["ba", "zzz"]) == ["ba", "zzz"]
    assert _search.Pruner("ab", "ab", None)(["a\n", "ba\n"]) == ["a\n"]      # other characters are not terminals


def test_the_filter_runs_after_the_pruning():
    seen = []

    def keep(s, component):
        seen.append(s)
        return True

    keep.pure = True

    res = search(model_of(FREE), "abab", keep=keep)
    assert res.found and res.conditional == ["python_filter"]
    assert seen
    for s in seen:
        projection = s.replace("S", "")
        it = iter("abab")
        assert all(ch in it for ch in projection), s      # nothing that the pruning drops reaches the filter


def test_the_filter_can_reject_what_the_pruning_keeps():
    res = search(model_of(ANBN), "aabb", keep=lambda s, c: s != "aaSbb")
    assert res.outcome == "not_found" and res.conditional == ["python_filter"]


def test_a_search_can_be_given_the_settings_of_a_run():
    model = model_of(ANBN)
    st = gcrsim.settings.settings_for_model(model)
    st.reject_max_len = 3
    res = search(model, "aabb", settings=st)
    assert res.outcome == "not_found" and res.bounds["max_len"] == 3
    assert gcrsim.settings.settings_for_model(model).reject_max_len is None


# ---------------------------------------------------------------------------
# multi-character symbols and how a word is written
# ---------------------------------------------------------------------------


def test_multi_character_symbols():
    model = model_of(MULTI)
    res = search(model, "p1p2")
    assert res.found and res.step == 3
    assert search(model, "p1 p2", word_sep=" ").found
    assert [d.result for d in res.derivation][-1] == "p1p2"


def test_the_word_is_read_with_the_alphabet_and_word_sep():
    model = model_of(MULTI)
    with pytest.raises(GcrsimError, match="not in the alphabet"):
        search(model, "p1q")
    with pytest.raises(GcrsimError, match="word_sep"):
        search(model, "p1p2", word_sep="p")
    assert search(model, "p1|p2", word_sep="|").found


def test_print_sep_in_the_text_output(files, capsys):
    status, out, err = cli(capsys, files("m.txt", MULTI), "--search", "p1p2")
    assert status == 0
    assert "step 3: p1 p2 S => p1 p2" in out
    assert "search: found 'p1 p2' in component 1 at step 3" in out
    status, out, err = cli(capsys, files("m.txt", MULTI), "--search", "p1|p2", "--word-sep", "|", "--format", "jsonl")
    obj = jsonl(out)
    assert obj[0]["word"] == ["p1", "p2"] and obj[0]["word_string"] == "p1 p2"


# ---------------------------------------------------------------------------
# the command line
# ---------------------------------------------------------------------------


def test_the_two_spellings_select_search():
    assert operations.select(["m.txt", "--search", "ab"])[0].name == "search"
    assert operations.select(["m.txt", "--mode", "search", "ab"])[0].name == "search"
    assert operations.select(["m.txt", "--mode=search", "ab"])[1] == ["m.txt", "ab"]
    with pytest.raises(GcrsimError, match="more than one mode"):
        operations.select(["m.txt", "--search", "ab", "--replay", "f"])


def test_text_output_of_a_found_word(files, capsys):
    status, out, err = cli(capsys, files("m.txt", ANBN), "--search", "aabb")
    assert status == 0
    lines = out.splitlines()
    assert lines[0].startswith("gcrsim ") and lines[1] == "1 component, 2 rules"
    assert "Derivation of 'aabb' (component 1), first appearing at step 3:" in out
    assert "    step 3: aaSbb => aabb   (component 1 -> 1, rule at line 9: S->, position 2)" in out
    assert out.rstrip().splitlines()[-1].startswith("        explored ")
    assert "search: found 'aabb' in component 1 at step 3" in out
    assert "step 1\n" not in out and "STEP" not in out          # the strings of the steps are not listed


def test_the_second_argument_and_the_option_are_the_same(files, capsys):
    m = files("m.txt", ANBN)
    b = cli(capsys, m, "--search", "aabb")
    c = cli(capsys, "--mode", "search", m, "aabb")
    assert b == c and b[0] == 0
    assert cli(capsys, "--mode", "search", m, "aabb", "--search", "aabb")[0] == 2
    status, out, err = cli(capsys, "--mode", "search", m)
    assert status == 2 and "no word" in err


def test_not_found_and_the_exit_statuses(files, capsys):
    m = files("m.txt", ANBN)
    status, out, err = cli(capsys, m, "--search", "ba")
    assert status == 6 and "search: not found: no strings remain after step 2" in out
    status, out, err = cli(capsys, m, "--search", "aaaabbbb", "--max-steps", "2")
    assert status == 6 and "search: not found: no derivation of at most 2 steps" in out
    assert "bounds: at most 2 steps" in out
    status, out, err = cli(capsys, m, "--search", "zz")
    assert status == 2 and "not in the alphabet" in err


def test_the_limits_make_the_outcome_inconclusive(files, capsys):
    m = files("m.txt", FREE)
    for option, value in (("--max-history", 50), ("--max-step-candidates", 5), ("--max-step-accepted", 4), ("--max-retained", 9)):
        status, out, err = cli(capsys, m, "--search", "abbaabba", option, value)
        assert status == 3, option
        assert "search: inconclusive: the limit %s (%d) stopped step" % (option[2:], value) in out, out
        assert "last complete step" in out
    status, out, err = cli(capsys, m, "--search", "abbaabba", "--max-history", 50, "--format", "jsonl")
    end = jsonl(out)[-1]
    assert (end["status"], end["outcome"], end["reason"], end["limit"]) == (3, "inconclusive", "limit", "max-history")


def test_the_time_limit_on_the_command_line(files, capsys):
    m = files("m.txt", FREE)
    status, out, err = cli(capsys, m, "--search", "ab" * 9, "--no-pruning", "--max-time", "0.2s")
    assert status == 3 and "search: inconclusive: the time limit (0.2s) stopped step" in out
    assert "time limit 0.2s" in out
    status, out, err = cli(capsys, m, "--search", "ab" * 9, "--no-pruning", "--max-time", "0.2", "--format", "jsonl")
    end = jsonl(out)[-1]
    assert (end["status"], end["reason"], end["limit"], end["bounds"]["max_time"]) == (3, "time", None, 0.2)
    assert cli(capsys, m, "--search", "abab", "--max-time", "0")[0] == 2


def test_an_interruption_on_the_command_line(files, capsys):
    m = files("m.txt", ANBN)
    f = files("stop.py", "def keep(s, component):\n    raise KeyboardInterrupt\n")
    status, out, err = cli(capsys, m, "--search", "aabb", "--python-filter", f)
    assert status == 3 and "search: inconclusive: interrupted during step 1; last complete step 0" in out
    status, out, err = cli(capsys, m, "--search", "aabb", "--python-filter", f, "--format", "jsonl")
    end = jsonl(out)[-1]
    assert (end["status"], end["outcome"], end["reason"]) == (3, "inconclusive", "interrupted")
    assert end["conditional"] == ["python_filter"]


def test_a_negative_answer_names_its_conditions(files, capsys):
    f = files("f.py", "def keep(s, component):\n    return True\n")
    m = files("m.txt", PEAK)
    status, out, err = cli(capsys, m, "--search", "ab", "--max-nonterminals", 1, "--python-filter", f)
    assert status == 6
    assert "the answer holds only under: the Python filter; the cap on non-terminals" in out
    assert "bounds: at most 1 non-terminals" in out
    status, out, err = cli(capsys, m, "--search", "ab", "--max-nonterminals", 1, "--python-filter", f, "--format", "jsonl")
    assert jsonl(out)[-1]["conditional"] == ["python_filter", "max_nonterminals"]


def test_quiet_and_progress(files, capsys):
    m = files("m.txt", ANBN)
    status, out, err = cli(capsys, m, "--search", "aabb", "--quiet", "--progress")
    assert status == 0 and out.startswith("search: found 'aabb'") and "Derivation" not in out
    assert [l[:7] for l in err.splitlines()] == ["step 1:", "step 2:", "step 3:"]


def test_only_the_formats_text_and_jsonl(files, capsys):
    m = files("m.txt", ANBN)
    for fmt in ("perl", "csv"):
        with pytest.raises(SystemExit) as exc:
            main([m, "--search", "aabb", "--format", fmt])
        assert exc.value.code == 2
        capsys.readouterr()


def test_options_of_other_modes_are_refused(files, capsys):
    m = files("m.txt", ANBN)
    for extra in (["--trace", "aabb"], ["--stop-on-found"], ["--print-all"], ["-i"]):
        with pytest.raises(SystemExit) as exc:
            main([m, "--search", "aabb", *extra])
        assert exc.value.code == 2
        capsys.readouterr()


def test_a_bad_component_or_bound_is_an_error(files, capsys):
    m = files("m.txt", ANBN)
    assert cli(capsys, m, "--search", "ab", "--component", 2)[0] == 2
    assert cli(capsys, m, "--search", "ab", "--max-steps", -1)[0] == 2
    assert cli(capsys, m, "--search", "ab", "--max-nonterminals", -1)[0] == 2
    assert cli(capsys, files("t.txt", ANBN.replace('terminals = "a b"\n', "")), "--search", "ab")[0] == 2
    status, out, err = cli(capsys, files("t.txt", ANBN.replace('terminals = "a b"\n', "")), "--search", "aabb", "--terminals", "a b")
    assert status == 0


def test_terminals_option_wins_on_the_command_line(files, capsys):
    m = files("m.txt", with_rule(ANBN, "b -> c"))
    status, out, err = cli(capsys, m, "--search", "aabb")
    assert "pruning off (rule b->c (line" in out
    status, out, err = cli(capsys, m, "--search", "aabb", "--terminals", "a")
    assert "pruning on" in out and "note:" not in err


# ---------------------------------------------------------------------------
# jsonl
# ---------------------------------------------------------------------------


def test_jsonl_output(files, capsys):
    status, out, err = cli(capsys, files("m.txt", ANBN), "--search", "aabb", "--format", "jsonl", "--max-steps", 5)
    objs = jsonl(out)
    assert status == 0
    assert [o["type"] for o in objs] == ["header", "derivation", "derivation_step", "derivation_step", "derivation_step", "end"]
    head = objs[0]
    assert head["mode"] == "search" and head["word"] == ["a", "a", "b", "b"] and head["word_string"] == "aabb" and head["component"] == 1
    assert not any(o["type"] == "step" for o in objs)
    deriv = objs[1]
    assert (deriv["word_string"], deriv["component"], deriv["found_at"], deriv["steps"]) == ("aabb", 1, 3, 3)
    assert [o["after_string"] for o in objs[2:5]] == ["aSb", "aaSbb", "aabb"]
    end = objs[-1]
    assert list(end) == ["type", "status", "steps", "outcome", "reason", "limit", "explored", "bounds", "pruning", "conditional"]
    assert end["bounds"] == {"max_steps": 5, "max_nonterminals": None, "max_len": None, "max_time": None}
    assert end["pruning"] == {"on": True, "reason": None} and end["conditional"] == [] and end["explored"] >= 3


def test_jsonl_and_text_agree(files, capsys):
    m = files("m.txt", CHAIN)
    status, text, err = cli(capsys, m, "--search", "bab", "--component", 3)
    status2, data, err = cli(capsys, m, "--search", "bab", "--component", 3, "--format", "jsonl")
    objs = jsonl(data)
    assert status == status2 == 0
    end = objs[-1]
    assert "found 'bab' in component 3 at step %d" % end["steps"] in text
    assert "explored %d strings" % end["explored"] in text
    steps = [o for o in objs if o["type"] == "derivation_step"]
    for o in steps:
        assert "step %d: %s => %s" % (o["step"], o["before_string"], o["after_string"]) in text


def test_jsonl_of_a_word_that_is_an_axiom_has_no_steps(files, capsys):
    status, out, err = cli(capsys, files("m.txt", ANBN), "--search", "S", "--format", "jsonl")
    objs = jsonl(out)
    assert [o["type"] for o in objs] == ["header", "derivation", "end"]
    assert objs[1]["steps"] == 0 and objs[2]["steps"] == 0 and objs[2]["outcome"] == "found"
    status, out, err = cli(capsys, files("m.txt", ANBN), "--search", "S")
    assert "(axiom: no derivation steps)" in out and "at step 0" in out


def test_the_empty_word_on_the_command_line(files, capsys):
    status, out, err = cli(capsys, files("m.txt", ANBN), "--search", "")
    assert status == 0 and "found the empty word in component 1 at step 1" in out


def test_messages_stay_messages_in_jsonl(files, capsys):
    f = files("noisy.py", "def keep(s, component):\n    print('hello')\n    return True\n")
    status, out, err = cli(capsys, files("m.txt", ANBN), "--search", "aabb", "--python-filter", f, "--format", "jsonl")
    objs = jsonl(out)
    assert status == 0 and {"type": "message", "text": "hello"} in objs


def test_a_retention_file_can_be_used(files, capsys, tmp_path):
    status, out, err = cli(capsys, files("m.txt", ANBN), "--search", "aabb", "--retain-file", tmp_path / "r.db")
    assert status == 0 and "step 3: aaSbb => aabb" in out


# ---------------------------------------------------------------------------
# the time limit in every mode
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text,seconds", [("90", 90.0), ("90s", 90.0), ("1.5m", 90.0), ("2h", 7200.0), (".5", 0.5), ("1.", 1.0),
                                          (" 3 ", 3.0), ("0.25h", 900.0), ("10m", 600.0)])
def test_durations_are_read(text, seconds):
    assert parse_duration(text) == seconds


@pytest.mark.parametrize("text", ["", " ", "0", "0s", "-1", "abc", "1x", "1e3", "inf", "nan", "1_0", "5 m", "m", "1.5.2", "2hours", "+3"])
def test_bad_durations_are_refused(text):
    with pytest.raises(GcrsimError, match="bad time limit"):
        parse_duration(text)


def test_durations_are_written_back():
    assert [describe(x) for x in (7200, 90, 60, 0.5, 120, 5400, 1.5)] == ["2h", "90s", "1m", "0.5s", "2m", "90m", "1.5s"]


def test_a_run_stops_at_the_time_limit(files, capsys):
    status, out, err = cli(capsys, files("m.txt", FREE), 30, "--format", "csv", "--max-time", "0.3")
    assert status == 3
    assert "the time limit (0.3s) was reached during step" in err and "that step is incomplete" in err
    assert out.startswith("step\tcomponent\tstring")        # the output was flushed


def test_a_run_accepts_a_suffix_and_refuses_a_bad_value(files, capsys):
    m = files("m.txt", ANBN)
    assert cli(capsys, m, 3, "--max-time", "1h", "--format", "csv")[0] == 0
    status, out, err = cli(capsys, m, 3, "--max-time", "soon")
    assert status == 2 and "bad time limit 'soon'" in err


def test_a_run_with_streaming_stops_at_the_time_limit(files, capsys):
    status, out, err = cli(capsys, files("m.txt", FREE), 30, "--format", "csv", "--streaming", "--max-time", "0.3")
    assert status == 3 and "time limit" in err


def test_the_limit_counts_from_the_start_of_the_program(files, capsys):
    status, out, err = cli(capsys, files("m.txt", ANBN), 3, "--max-time", "0.000001")
    assert status == 3 and "time limit" in err


def test_replay_stops_at_the_time_limit(files, capsys):
    m = files("m.txt", ANBN)
    d = files("d.txt", "S\naSb\naaSbb\naabb\n")
    assert cli(capsys, m, "--replay", d, "--max-time", "1h")[0] == 0
    status, out, err = cli(capsys, m, "--replay", d, "--max-time", "0.000001")
    assert status == 3 and "stopped by the time limit" in out
    assert cli(capsys, m, "--replay", d, "--max-time", "0")[0] == 2


def test_the_time_limit_is_in_the_help():
    from gcrsim.cli import _build_parser
    assert "--max-time" in _build_parser().format_help()
    assert "--max-time" in operations.build_replay_parser().format_help()
    assert "--max-time" in operations.build_search_parser().format_help()


def test_a_python_deadline_for_the_simulator():
    from gcrsim.timelimit import Deadline

    sim = Simulator(model_of(FREE), write=lambda t: None, deadline=Deadline(0.2))
    with pytest.raises(gcrsim.LimitReached) as exc:
        sim.run(40)
    assert exc.value.limit == "max-time" and exc.value.exit_code == 3


def test_search_refuses_a_bad_max_time():
    for bad in (0, -1, True, "5"):
        with pytest.raises(GcrsimError, match="max_time"):
            search(model_of(ANBN), "aabb", max_time=bad)


# ---------------------------------------------------------------------------
# a plain run is not slowed down
# ---------------------------------------------------------------------------


def test_a_plain_run_never_calls_the_pruning_code(monkeypatch):
    def boom(self, cands):
        raise AssertionError("the pruning code ran in a plain run")

    monkeypatch.setattr(_search.Pruner, "__call__", boom)
    sim = Simulator(model_of(FREE), write=lambda t: None)
    assert sim._prune is None and sim.deadline is None
    sim.run(4)
    assert sim.step_no == 4
    sim = Simulator(model_of(FREE), write=lambda t: None, streaming=True)
    sim.run(3)


# ---------------------------------------------------------------------------
# the example
# ---------------------------------------------------------------------------

WORD = "abbabaababbaabbaba"


def trace_step(capsys, *extra):
    status, out, err = cli(capsys, PY / "target_pruning.txt", 19, "--python-filter", PY / "target_pruning.py", "--trace", WORD,
                           "--stop-on-found", "--quiet", *extra)
    assert status == 0, err
    return int(re.search(r"first appearing at step (\d+)", out).group(1))


def test_the_filter_of_the_example_and_the_built_in_options_agree(capsys):
    model = str(PY / "target_pruning.txt")
    status, out, err = cli(capsys, model, "--search", WORD, "--format", "jsonl")
    end = jsonl(out)[-1]
    assert status == 0 and end["outcome"] == "found" and end["pruning"]["on"] is True
    assert trace_step(capsys) == end["steps"] == 19
    assert trace_step(capsys, "--streaming") == 19      # keep is pure


def test_pruning_rescues_the_search_of_the_example(capsys):
    model = str(PY / "target_pruning.txt")
    status, out, err = cli(capsys, model, "--search", WORD, "--no-pruning", "--max-history", 300000)
    assert status == 3 and "the limit max-history (300000) stopped step" in out
    status, out, err = cli(capsys, model, "--search", WORD, "--max-history", 300000)
    assert status == 0 and "explored 9" in out


def test_the_example_filter_can_be_added_to_the_search(capsys):
    model = str(PY / "target_pruning.txt")
    status, out, err = cli(capsys, model, "--search", WORD, "--python-filter", PY / "target_pruning.py", "--format", "jsonl")
    end = jsonl(out)[-1]
    assert status == 0 and end["steps"] == 19 and end["conditional"] == ["python_filter", "max_len"]


# ---------------------------------------------------------------------------
# review round: witnesses, purity, deadlines, files, regular expressions, interruption
# ---------------------------------------------------------------------------

AMBIGUOUS = """
[symbols]
alphabet = "S a b ab"
terminals = "a"
[axioms]
1 = ["S"]
[rules]
S -> ab
S -> a b
"""


def forms_of(result, sep="|"):
    first = result.derivation[0]
    return ["%d: %s" % (first.source_component + 1, sep.join(first.before))] + [
        "%d: %s" % (d.target_component + 1, sep.join(d.after)) for d in result.derivation]


def test_the_witness_is_for_the_word_that_was_asked_for():
    model = model_of(AMBIGUOUS)
    res = search(model, "a|b", word_sep="|")
    assert res.found and res.derivation[-1].after == ["a", "b"]
    assert replay(model, forms_of(res), word_sep="|").ok
    only = model_of(AMBIGUOUS.replace("S -> ab\n", ""))
    res = search(only, "a|b", word_sep="|")          # this raised TraceError after the word was found
    assert res.found and res.derivation[-1].after == ["a", "b"]
    res = search(model, "ab")
    assert res.found and res.derivation[-1].after == ["ab"]


def test_the_witness_on_the_command_line(files, capsys):
    status, out, err = cli(capsys, files("m.txt", AMBIGUOUS), "--search", "a|b", "--word-sep", "|", "--format", "jsonl")
    steps = [o for o in jsonl(out) if o["type"] == "derivation_step"]
    assert status == 0 and steps[-1]["after"] == ["a", "b"]


STATEFUL = """
[symbols]
alphabet = "a b S"
terminals = "a b"
[axioms]
1 = ["S"]
[rules]
S -> b
S -> a
"""


def stateful_keep():
    seen = set()

    def keep(s, component):          # accepts a only after it has seen b
        if s == "b":
            seen.add("b")
        return s != "a" or "b" in seen

    return keep


def test_a_filter_that_is_not_pure_switches_the_pruning_off():
    model = model_of(STATEFUL)
    res = search(model, "a", keep=stateful_keep(), pruning=False)
    assert res.found                                      # what the answer is without pruning
    res = search(model, "a", keep=stateful_keep())
    assert res.found and res.pruning is False and "not declared pure" in res.pruning_note
    assert res.conditional == ["python_filter"]


def test_a_pure_filter_keeps_the_pruning_on():
    keep = stateful_keep()
    keep.pure = True
    res = search(model_of(STATEFUL), "a", keep=keep)
    assert res.pruning is True and not res.found            # pure is a promise of the user's: the order is theirs to answer for


def test_a_function_in_the_filters_of_a_component_counts_too():
    from gcrsim import Settings

    def f(s):
        return True

    assert "not declared pure" in _search.order_obstacle(Settings(filters={1: {"forbid": [f]}}))
    f.pure = True
    assert _search.order_obstacle(Settings(filters={1: {"forbid": [f]}})) is None
    assert _search.order_obstacle(Settings(filters={1: {"forbid": ["x"]}})) is None


def test_the_cap_still_applies_when_a_filter_switches_the_pruning_off():
    res = search(model_of(PEAK), "ab", keep=lambda s, c: True, max_nonterminals=1)
    assert res.pruning is False and res.outcome == "not_found"


def test_the_note_about_an_impure_filter_is_written_at_the_start(files, capsys):
    f = files("f.py", "def keep(s, component):\n    return True\n")
    status, out, err = cli(capsys, files("m.txt", ANBN), "--search", "aabb", "--python-filter", f)
    assert status == 0 and "note: pruning is off: the filter function keep is not declared pure" in err
    f = files("g.py", "def keep(s, component):\n    return True\nkeep.pure = True\n")
    status, out, err = cli(capsys, files("m.txt", ANBN), "--search", "aabb", "--python-filter", f)
    assert "note:" not in err and "pruning on" in out


ONE = """
[symbols]
alphabet = "a S"
terminals = "a"
[axioms]
1 = ["S"]
[rules]
S -> a
"""


def test_an_expired_time_limit_never_gives_a_definitive_answer():
    import time

    def slow(s, component):
        time.sleep(0.045)
        return False

    res = search(model_of(ONE), "aa", keep=slow, max_time=0.01)
    assert (res.outcome, res.reason, res.status) == ("inconclusive", "time", 3)
    for word, kwargs in (("S", {}), ("a", {}), ("aa", {"max_steps": 0}), ("aa", {"max_steps": 5})):
        res = search(model_of(ONE), word, max_time=1e-9, **kwargs)
        assert (res.outcome, res.reason) == ("inconclusive", "time"), (word, kwargs)
        assert res.derivation == []


def test_the_clock_of_the_python_api_starts_before_the_model_is_read(monkeypatch, tmp_path):
    import time

    path = tmp_path / "m.txt"
    path.write_bytes(ONE.encode())
    real = _search.parse_model_file

    def slow_read(p):
        time.sleep(0.15)
        return real(p)

    monkeypatch.setattr(_search, "parse_model_file", slow_read)
    res = search(str(path), "S", max_time=0.05)
    assert (res.outcome, res.reason) == ("inconclusive", "time")


def test_the_pruner_looks_at_the_clock_while_it_works():
    calls = []
    pruner = _search.Pruner("a", "a", None)
    pruner.check = lambda: calls.append(1)
    assert pruner(["a"] * 3000) == ["a"] * 3000
    assert len(calls) == 3


def test_a_run_whose_time_is_up_never_reports_success(files, capsys):
    m = files("m.txt", ANBN)
    status, out, err = cli(capsys, m, 0, "--max-time", "0.000001", "--format", "csv")
    assert status == 0                  # a run that completed its steps keeps its status: nothing stopped it
    status, out, err = cli(capsys, m, "--search", "S", "--max-time", "0.000001")
    assert status == 3 and "search: inconclusive: the time limit" in out
    status, out, err = cli(capsys, m, "--search", "ba", "--max-steps", 0, "--max-time", "0.000001")
    assert status == 3
    one = files("one.txt", "S\n")
    status, out, err = cli(capsys, m, "--replay", one, "--max-time", "0.000001")
    assert status == 3


def test_the_trace_back_looks_at_the_clock():
    from gcrsim.timelimit import Deadline

    sim = Simulator(model_of(FREE), write=lambda t: None, retain=True)
    sim.run(5)
    target = sim.cur[0][0]
    sim.deadline = Deadline(1e-9)
    with pytest.raises(gcrsim.LimitReached):
        sim._trace_many([(0, target, 5)])


class _CountingDeadline:
    """A deadline that is up from the third look on."""

    def __init__(self, seconds):
        self.seconds = seconds
        self.looks = 0

    def expired(self):
        self.looks += 1
        return self.looks >= 3

    def __str__(self):
        return "1s"


def test_a_timed_out_replay_keeps_the_steps_it_checked(files, capsys, monkeypatch):
    m = files("m.txt", ANBN)
    d = files("d.txt", "S\naSb\naaSbb\naabb\n")
    monkeypatch.setattr(operations, "Deadline", _CountingDeadline)
    status, out, err = cli(capsys, m, "--replay", d, "--max-time", "1", "--format", "jsonl")
    objs = jsonl(out)
    assert status == 3
    assert [o["type"] for o in objs] == ["header", "derivation_step", "derivation_step", "end"]
    assert (objs[-1]["status"], objs[-1]["steps"], objs[-1]["reason"]) == (3, 2, "time")
    status, out, err = cli(capsys, m, "--replay", d, "--max-time", "1", "--explain")
    assert status == 3 and "step 1 (lines 1-2)" in out and "step 2 (lines 2-3)" in out and "step 3" not in out
    assert "stopped by the time limit (1s) after 2 steps checked" in out


def test_retain_file_cannot_be_the_model_or_a_configuration(files, capsys, tmp_path):
    import os

    m = files("m.txt", ANBN)
    cfg = files("c.toml", "[run]\nprint_max_len = 9\n")
    alias = os.path.join(str(tmp_path), ".", "m.txt")
    for args in ((m, 3, "--trace", "aSb", "--retain-file", m), (m, 3, "--trace", "aSb", "--retain-file", alias),
                 (m, "--search", "aabb", "--retain-file", m), (m, "--search", "aabb", "--retain-file", alias),
                 (m, 3, "--trace", "aSb", "--config", cfg, "--retain-file", cfg),
                 (m, "--search", "aabb", "--config", cfg, "--retain-file", cfg)):
        status, out, err = cli(capsys, *args)
        assert status == 2 and "would be deleted" in err, args
        assert os.path.exists(m) and os.path.exists(cfg)
    f = files("f.py", "def keep(s, component):\n    return True\n")
    assert cli(capsys, m, "--search", "aabb", "--python-filter", f, "--retain-file", f)[0] == 2
    assert os.path.exists(f)


def test_a_model_with_regular_expression_rules_can_be_searched():
    model = model_of('[symbols]\nterminals = "a"\n[axioms]\n1 = ["S"]\n[rules]\nre(S) -> a\n')
    res = search(model, "a")
    assert res.found and res.step == 1
    assert res.pruning is False and "regular-expression rule" in res.pruning_note


def test_an_interruption_while_the_settings_are_loaded(files, capsys, monkeypatch):
    from gcrsim import cli as cli_module

    def interrupt(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli_module, "load_settings_captured", interrupt)
    m = files("m.txt", ANBN)
    status, out, err = cli(capsys, m, "--search", "aabb")
    assert status == 3 and "search: inconclusive: interrupted" in out
    status, out, err = cli(capsys, m, "--search", "aabb", "--format", "jsonl")
    objs = jsonl(out)
    assert status == 3 and [o["type"] for o in objs] == ["header", "end"]
    assert (objs[-1]["outcome"], objs[-1]["reason"], objs[-1]["status"]) == ("inconclusive", "interrupted", 3)
    assert main([m, "2"]) == 130                       # a run keeps its status


def test_every_outcome_lists_its_conditions(files, capsys):
    f = files("f.py", "def keep(s, component):\n    return True\n")
    m = files("m.txt", ANBN)
    status, out, err = cli(capsys, m, "--search", "aabb", "--python-filter", f)
    assert status == 0 and "conditions: the Python filter" in out
    status, out, err = cli(capsys, m, "--search", "aabb", "--python-filter", f, "--max-history", 3)
    assert status == 3 and "conditions: the Python filter" in out


def test_explored_without_a_history_counts_the_candidates():
    model = model_of(ANBN.replace("[axioms]", "[model]\nhistory = false\n[axioms]"))
    res = search(model, "aabb")
    assert res.found and res.explored >= 3


def test_a_limit_reached_by_the_axioms_is_step_0(files, capsys):
    res = search(model_of(ANBN), "aabb", max_history=0)
    assert (res.outcome, res.reason, res.limit, res.step, res.limit_step) == ("inconclusive", "limit", "max-history", 0, 0)
    status, out, err = cli(capsys, files("m.txt", ANBN), "--search", "aabb", "--max-history", 0)
    assert status == 3 and "was reached by the axioms (step 0)" in out


def test_terminals_validation():
    model = model_of(ANBN)
    for empty in ("", "  ", []):
        with pytest.raises(GcrsimError, match="declares no terminals"):
            search(model, "aabb", terminals=empty)
    with pytest.raises(GcrsimError, match="declares no terminals"):
        search(model_of(ANBN.replace('terminals = "a b"', 'terminals = ""')), "aabb")
    with pytest.raises(GcrsimError, match="not declared"):
        search(model_of(ANBN.replace('terminals = "a b"\n', "")), "aabb")
    with pytest.raises(GcrsimError, match="'a b' is not a symbol"):
        search(model, "aabb", terminals=["a b"])
    multi = model_of(MULTI)
    code = multi.lexicon.encode("p1")
    assert len(code) == 1 and code != "p1"
    with pytest.raises(GcrsimError, match="not a symbol"):
        search(multi, "p1", terminals=[code])
    assert search(multi, "p1p2", terminals=["p1", "p2"]).found


def test_the_first_offending_rule_is_the_first_in_the_file():
    text = """
[symbols]
alphabet = "a b c S"
terminals = "a b"
[axioms]
1 = ["S"]
[rules.2]
a -> c, 1
[rules.1]
b -> c, 2
S -> a S, 1
"""
    note = _search.pruning_obstacle(model_of(text), "ab")
    assert note.startswith("rule a->c,1 (line 8)")


def test_the_cap_does_not_apply_to_the_axioms():
    model = model_of('[symbols]\nalphabet = "a S"\nterminals = "a"\n[axioms]\n1 = ["S S"]\n[rules]\nS -> a\n')
    assert search(model, "SS", max_nonterminals=0).found
    assert search(model, "SS", max_nonterminals=0).step == 0
    assert search(model, "aa", max_nonterminals=1).found
    assert search(model, "aa", max_nonterminals=0).outcome == "not_found"      # the strings derived are tested
