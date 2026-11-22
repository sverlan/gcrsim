"""Every model of examples/cookbook generates what its header says, and the plain ones pass --cross-check."""
import os
from pathlib import Path

import pytest

import gcrsim
from conftest import ROOT, run_py

COOK = Path(ROOT) / "examples" / "cookbook"
FEAT = Path(ROOT) / "examples" / "features"


def run(name, steps, filters=True, folder=COOK):
    model = gcrsim.parse_model_file(str(folder / name))
    st = gcrsim.settings.settings_for_model(model)
    if not filters:
        st.filters = {}
    st.reject_strings, st.print_hide, st.reject_max_len, st.print_max_len = "", "", 60, 1000
    sim = gcrsim.Simulator(model, st, write=lambda t: None)
    per_step = []
    for _ in range(steps):
        sim.step()
        per_step.append(sim.strings())
    return sim, per_step


def strings(per_step, component=None):
    out = set()
    for fr in per_step:
        for c, comp in enumerate(fr):
            if component is None or c == component - 1:
                out.update(comp)
    return out


def anbn(n):
    return "a" * n + "b" * n


def terminals(found):
    return {s for s in found if s.islower() or s == ""}


def test_01_context_free():
    _, ps = run("01_context_free.txt", 6)
    assert terminals(strings(ps)) == {anbn(n) for n in range(6)}


@pytest.mark.parametrize("name", ["02_insdel.txt", "03_marcus_internal.txt"])
def test_02_03_insdel_and_internal_contextual(name):
    _, ps = run(name, 5)
    assert strings(ps) == {anbn(n) for n in range(2, 7)}


def test_04_external_contextual():
    _, ps = run("04_marcus_external.txt", 6)
    assert strings(ps, 1) == {anbn(n) for n in (2, 3, 4)}
    assert all(s.count("a") == s.count("b") + 1 for s in strings(ps, 2))


def test_05_evolutionary_operations():
    _, ps = run("05_evolutionary_processors.txt", 1)
    assert set(ps[0][0]) == {"bY", "XaY", "a"}


def test_06_network_of_processors():
    _, ps = run("06_network_of_processors.txt", 4)
    assert strings(ps, 2) == {"bbb"}


def test_07_graph_controlled():
    _, ps = run("07_graph_controlled.txt", 6)
    assert strings(ps, 2) == {anbn(n) for n in range(6)}


def test_08_matrix():
    _, ps = run("08_matrix.txt", 14)
    done = strings(ps, 8)
    assert {"abc", "aabbcc"} <= done
    assert all(len(s) % 3 == 0 and s == "a" * (len(s) // 3) + "b" * (len(s) // 3) + "c" * (len(s) // 3) for s in done)


def test_08_matrix_with_the_first_rules_in_component_1():
    _, ps = run("08_matrix_direct.txt", 14)
    done = {s for s in strings(ps, 1) if s.islower()}  # component 1 also holds the sentential forms
    assert {"abc", "aabbcc", "aaabbbccc"} <= done
    assert all(len(s) % 3 == 0 and s == "a" * (len(s) // 3) + "b" * (len(s) // 3) + "c" * (len(s) // 3) for s in done)


def test_09_programmed_with_failure_field():
    _, ps = run("09_programmed.txt", 4)
    assert ps[3][2] == ["xbb"] and strings(ps, 3) == {"xbb"}


def test_10_time_varying():
    _, ps = run("10_time_varying.txt", 8)
    done = strings(ps, 3)
    assert done == {"ab" * n for n in (1, 2, 3, 4)}


def test_11_regular_control():
    _, ps = run("11_regular_control.txt", 8)
    assert strings(ps, 3) == {anbn(n) for n in range(4)}


def test_12_random_context():
    _, ps = run("12_random_context.txt", 16)
    assert {s for s in strings(ps) if s.islower()} == {"a" * n + "b" * n + "c" * n for n in (1, 2, 3)}


def test_13_semi_conditional():
    _, ps = run("13_semi_conditional.txt", 8)
    assert terminals(strings(ps)) == {anbn(n) for n in range(4)}
    assert not any("bbbb" in s for s in strings(ps))


def test_14_context_conditional():
    _, ps = run("14_context_conditional.txt", 1)
    assert set(ps[0][0]) == {"Yab", "Yba"}


def test_15_ordered():
    _, ps = run("15_ordered.txt", 3)
    assert ps[0][0] == ["aB"] and ps[1][0] == ["ab"] and ps[2][0] == []


def test_16_finite_index():
    _, free = run("16_finite_index.txt", 5, filters=False)
    assert any(s.count("S") > 2 for s in strings(free))
    _, limited = run("16_finite_index.txt", 5)
    assert all(s.count("S") <= 2 for s in strings(limited))


def test_checking_marks_the_unexpected_terminal_strings():
    sim, _ = run("checking_an_bn.txt", 5, folder=FEAT)
    marked = {m.string for m in sim.marks}
    assert "ba" in marked and "abab" in marked
    assert not marked & {"", "ab", "aabb", "aaabbb"}


def test_17_counter_machine():
    _, ps = run("17_counter_machine.txt", 8)
    assert strings(ps, 3) == {"|bbbbb"}


def test_symbols_and_classes():
    _, ps = run("symbols_and_classes.txt", 1, folder=FEAT)
    assert set(ps[0][0]) == {"Xap2", "p1aX"}


def test_overlapping_symbols():
    _, ps = run("overlapping_symbols.txt", 2, folder=FEAT)
    assert set(ps[0][0]) == {"abab"}
    assert set(ps[1][0]) == {"Tab", "abS"}


TAG = {"a": "bc", "b": "a", "c": "aaa"}


def tag_words(word):
    """The words of the Post tag system (deletion number 2, productions a -> bc, b -> a, c -> aaa), computed on the side."""
    out = [word]
    while len(word) >= 2:
        word = word[2:] + TAG[word[0]]
        out.append(word)
    return out


def test_19_post_tag_system_with_regular_expression_rules():
    words = tag_words("aaa")
    assert len(words) == 25 and words[-1] == "a"
    sim, ps = run("19_post_tag_system.txt", len(words) - 1)
    assert [set(step[0]) for step in ps] == [{w} for w in words[1:]]
    assert [(m.label, m.string, m.step) for m in sim.marks] == [("halt", "a", len(words) - 1)]   # the halting word


def test_19_post_tag_system_with_left_right_insertion_deletion_rules():
    words = tag_words("aaa")
    sim, ps = run("19_post_left_right.txt", 2 * (len(words) - 1))
    assert [set(ps[2 * k - 1][0]) for k in range(1, len(words))] == [{w} for w in words[1:]]
    assert [(m.label, m.string, m.step) for m in sim.marks] == [("halt", "a", 2 * (len(words) - 1))]


def test_01_monotone_anbncn():
    _, ps = run("01_monotone_anbncn.txt", 14)
    found = {s for s in strings(ps) if s.islower()}
    assert found == {"a" * n + "b" * n + "c" * n for n in (1, 2, 3)}


def test_01_type0_powers_of_two():
    model = gcrsim.parse_model_file(str(COOK / "01_type0_powers_of_two.txt"))
    st = gcrsim.settings.settings_for_model(model)
    assert st.steps == 54
    st.reject_strings, st.print_hide, st.print_max_len = "", "", 1000
    sim = gcrsim.Simulator(model, st, write=lambda t: None, max_step_candidates=5_000_000)
    found = set()
    for _ in range(st.steps):
        sim.step()
        found |= {s for s in sim.strings()[0] if s.islower()}
    assert found == {"a" * 2 ** n for n in (1, 2, 3, 4)}


def terminal_words(sim_states, component):
    import re as _re
    return {s for s in strings(sim_states, component) if _re.fullmatch("[a-z]+", s)}


def run_with_conf(name, max_step_candidates=5_000_000):
    """The model with its own settings, for the number of steps it asks for."""
    model = gcrsim.parse_model_file(str(COOK / name))
    st = gcrsim.settings.settings_for_model(model)
    st.print_hide = ""
    sim = gcrsim.Simulator(model, st, write=lambda t: None, max_step_candidates=max_step_candidates)
    out = []
    for _ in range(st.steps):
        sim.step()
        out.append(sim.strings())
    return out


def test_07_graph_controlled_with_appearance_checking():
    ps = run_with_conf("07_graph_controlled_appearance_checking.txt")
    assert terminal_words(ps, 4) == {"a" * 2 ** n for n in range(4)}   # a, a^2, a^4, a^8


def test_08_matrix_with_appearance_checking():
    ps = run_with_conf("08_matrix_appearance_checking.txt")
    assert terminal_words(ps, 15) == {"a" * 2 ** n for n in range(4)}
    assert not any("#" in w for step in ps for comp in step for w in comp)   # the dead words were rejected


def test_08_matrix_with_appearance_checking_makes_dead_words_when_not_rejected():
    model = gcrsim.parse_model_file(str(COOK / "08_matrix_appearance_checking.txt"))
    sim = gcrsim.Simulator(model, gcrsim.Settings(reject_max_len=40), write=lambda t: None)
    seen = set()
    for _ in range(14):
        sim.step()
        seen |= {w for comp in sim.strings() for w in comp}
    assert any("#" in w for w in seen)       # the trap symbol appears: an appearance-checked rule that has to be applied


def test_ac_examples_pass_verify_without_their_configuration():
    from gcrsim.verify import Verifier
    for name in ("07_graph_controlled_appearance_checking.txt", "08_matrix_appearance_checking.txt"):
        model = gcrsim.parse_model_file(str(COOK / name))
        sim = gcrsim.Simulator(model, gcrsim.Settings(reject_max_len=40), write=lambda t: None)
        verifier = Verifier(sim)
        for _ in range(12):
            sim.step()
            verifier.check_step()


def test_20_valence_grammar_accepts_the_words_with_as_many_a_as_b():
    import itertools
    sim, _ = run("20_valence.txt", 13)
    marked = {m.string.rstrip("|") for m in sim.marks if m.label == "terminal"}
    balanced = {"".join(w) for k in range(7) for w in itertools.product("ab", repeat=k) if w.count("a") == w.count("b")}
    assert marked == balanced      # all of them up to length 6, and no other word


def test_18_scattered_context_with_regular_expressions():
    _, ps = run("18_scattered_context.txt", 8)
    found = {s for s in strings(ps) if s.islower()}
    assert found == {"a" * n + "b" * n + "c" * n for n in range(1, 8)}


def test_18_scattered_choices_lazy_and_greedy_cover_two_but_not_three():
    _, ps = run("18_scattered_context_choices.txt", 1)
    assert set(ps[0][0]) == {"xyB", "xBy"}
    text = "[axioms]\n1 = [\"A B B B\"]\n\n[rules]\nre(A(.*?)B) -> x\\1y\nre(A(.*)B) -> x\\1y\n"
    model = gcrsim.parse_model(text)
    sim = gcrsim.Simulator(model, gcrsim.Settings(), write=lambda t: None)
    sim.step()
    assert set(sim.strings()[0]) == {"xyBB", "xBBy"}   # the choice "the middle B" (xByB) is not produced


def test_16_bounded_index_with_a_class():
    import re as _re
    model = gcrsim.parse_model_file(str(COOK / "16_bounded_index_classes.txt"))

    def words(limit):
        st = gcrsim.settings.settings_for_model(model)
        st.filters = {0: {"max_count": {"class": {"N": limit}}}}
        sim = gcrsim.Simulator(model, st, write=lambda t: None)
        seen = set()
        for _ in range(8):
            sim.step()
            seen |= {w for w in sim.strings()[0] if _re.fullmatch("[a-z]+", w)}
        return seen

    assert words(1) == set()
    two = words(2)
    assert {"ab", "aab", "abb", "aabb"} <= two and all(_re.fullmatch("a+b+", w) for w in two)


PLAIN = [
    "01_context_free", "02_insdel", "03_marcus_internal", "04_marcus_external", "05_evolutionary_processors",
    "06_network_of_processors", "07_graph_controlled", "08_matrix", "08_matrix_direct", "19_post_left_right", "09_programmed", "10_time_varying",
    "11_regular_control", "12_random_context", "13_semi_conditional", "14_context_conditional", "15_ordered",
    "17_counter_machine", "20_valence", "01_monotone_anbncn", "01_type0_powers_of_two",
]


@pytest.mark.parametrize("name", PLAIN)
def test_plain_cookbook_models_pass_verify(name):
    r = run_py([str(COOK / (name + ".txt")), "10", "--quiet", "--cross-check"], COOK)
    assert r.returncode == 0, r.stderr


def test_the_cookbook_document_contains_every_model_as_written():
    text = (Path(ROOT) / "docs" / "grammars.md").read_text(encoding="utf-8")
    doc = "\n".join(l for l in text.split("\n") if not l.startswith("#"))
    for path in sorted(COOK.glob("*.txt")):
        body = "\n".join(l for l in path.read_text(encoding="utf-8").split("\n") if not l.startswith("#")).strip()
        assert body in doc, path.name
    assert not list(COOK.glob("*_conf.toml"))  # the settings are in the models


TERMINAL_MARKS = {   # model -> the component that holds the words of its language, marked 'terminal' in the model file
    "01_context_free": 1, "01_monotone_anbncn": 1, "02_insdel": 1, "03_marcus_internal": 1, "04_marcus_external": 1,
    "06_network_of_processors": 2, "07_graph_controlled": 2, "08_matrix": 8, "08_matrix_direct": 1, "09_programmed": 3,
    "10_time_varying": 3, "11_regular_control": 3, "12_random_context": 1, "13_semi_conditional": 1, "15_ordered": 1,
    "16_bounded_index_classes": 1, "16_finite_index": 1, "18_scattered_context": 1,
}


@pytest.mark.parametrize("stem", sorted(TERMINAL_MARKS))
def test_the_terminal_mark_flags_exactly_the_words_of_the_language(stem):
    sim, ps = run(stem + ".txt", 12)
    component = TERMINAL_MARKS[stem]
    marked = {m.string for m in sim.marks if m.label == "terminal" and m.component == component - 1}
    assert marked == terminal_words(ps, component) | ({""} if "" in strings(ps, component) else set())
    assert all(m.component == component - 1 for m in sim.marks if m.label == "terminal")
