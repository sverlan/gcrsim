"""Symbol boundaries (``Symbols`` directive) and permitting/forbidding words."""

import pytest

import gcrsim
from conftest import parse_old
from gcrsim import ModelError, Settings

NOFILTER = dict(reject_strings="(?!)", reject_max_len=1000, print_hide="(?!)", print_max_len=1000, history=False)


def run(text, steps=1, **cfg):
    settings = Settings(**{**NOFILTER, **cfg})
    sim = gcrsim.Simulator(gcrsim.parse_model(text), settings, write=lambda t: None)
    sim.run(steps)
    return [sorted(c) for c in sim.cur]


def first_step(text, **cfg):
    return run(text, 1, **cfg)[0]


# -- symbol boundaries ---------------------------------------------------------












def test_rules_without_symbols_or_conditions_are_unchanged():
    model = gcrsim.parse_model("""[axioms]
1 = ["a"]

[rules]
a->b
""")
    assert model.rules[0][0].guarded is False


# -- permitting and forbidding words -----------------------------------------------

def test_permit_requires_every_word():
    base = """[axioms]
1 = ["ABC"]

[rules]
A->X,1;permit:B,C
"""
    assert first_step(base) == ["XBC"]
    base = """[axioms]
1 = ["AB"]

[rules]
A->X,1;permit:B,C
"""
    assert first_step(base) == []


def test_forbid_blocks_on_any_word():
    assert first_step("""[axioms]
1 = ["AB"]

[rules]
A->X,1;forbid:C,D
""") == ["XB"]
    assert first_step("""[axioms]
1 = ["ABD"]

[rules]
A->X,1;forbid:C,D
""") == []
    assert first_step("""[axioms]
1 = ["ABC"]

[rules]
A->X,1;forbid:C,D
""") == []


def test_permit_and_forbid_together():
    model = """[axioms]
1 = ["AB"]

[rules]
A->X,1;permit:B;forbid:C
"""
    assert first_step(model) == ["XB"]
    model = """[axioms]
1 = ["ABC"]

[rules]
A->X,1;permit:B;forbid:C
"""
    assert first_step(model) == []


def test_words_are_contiguous_substrings():
    assert first_step("""[axioms]
1 = ["AxBy"]

[rules]
A->X,1;permit:AB
""") == []
    assert first_step("""[axioms]
1 = ["ABxy"]

[rules]
A->X,1;permit:AB
""") == ["XBxy"]


def test_condition_is_tested_on_the_source_string_not_the_result():
    # the rule itself inserts the forbidden word: still applies, the source had none
    assert first_step("""[axioms]
1 = ["A"]

[rules]
A->AF,1;forbid:F
""") == ["AF"]
    # and the result contains the permitted word only after the rule: not applicable
    assert first_step("""[axioms]
1 = ["A"]

[rules]
A->AP,1;permit:P
""") == []


def test_cap_of_two_copies_via_forbid():
    model = """[axioms]
1 = ["A"]

[rules]
A->Ap1,1;forbid:p1p1
"""
    assert run(model, 1) == [["Ap1"]]
    assert run(model, 2) == [["Ap1p1"]]
    assert run(model, 3) == [[]]  # the source already holds two copies


def test_word_with_special_symbols():
    model = """[axioms]
1 = ["A$#"]

[rules]
A->X,1;permit:$#
"""
    assert first_step(model) == ["X$#"]



def test_multiple_clauses_of_the_same_kind_accumulate():
    model = """[axioms]
1 = ["ABC"]

[rules]
A->X,1;permit:B;permit:C
"""
    assert first_step(model) == ["XBC"]
    model = """[axioms]
1 = ["AB"]

[rules]
A->X,1;permit:B;permit:C
"""
    assert first_step(model) == []


def test_rule_line_keeps_target_component_before_clause():
    model = """[axioms]
1 = ["A"]

[rules]
A->B,2;permit:A
"""
    assert run(model, 1) == [[], ["B"]]


def test_empty_word_is_an_error():
    with pytest.raises(ModelError):
        gcrsim.parse_model("""[axioms]
1 = ["A"]

[rules]
A->B,1;permit:
""")
    with pytest.raises(ModelError):
        gcrsim.parse_model("""[axioms]
1 = ["A"]

[rules]
A->B,1;forbid:X,,Y
""")


def test_clause_works_with_regex_rules():
    model = '[axioms]\n1 = ["ab"]\n\n[rules]\nre(([ab]))->\\1\\1,1;forbid:ba\n'
    assert first_step(model) == ["aab", "abb"]
    model = '[axioms]\n1 = ["ba"]\n\n[rules]\nre(([ab]))->\\1\\1,1;forbid:ba\n'
    assert first_step(model) == []


def test_empty_lhs_insertion_with_conditions():
    model = """[axioms]
1 = ["ab"]

[rules]
->X,1;permit:a
"""
    assert first_step(model) == sorted(["Xab", "aXb", "abX"])


def test_conditions_do_not_change_other_rules():
    model = """[axioms]
1 = ["AB"]

[rules]
A->X,1;forbid:B
B->Y
"""
    assert first_step(model) == ["AY"]


def test_bounded_expansion_honours_conditions():
    model = """[axioms]
1 = ["AB"]

[rules]
A->X,1;forbid:B
B->Y
"""
    sim = gcrsim.Simulator(gcrsim.parse_model(model), Settings(**NOFILTER), write=lambda t: None, max_step_candidates=5)
    sim.run(1)
    assert sim.cur == [["AY"]]


def test_streaming_matches_default_with_conditions_and_symbols():
    model = """[symbols]
lexemes = ["p1"]

[axioms]
1 = ["Ap1"]

[rules]
A->Ap1,1;forbid:p1p1
->Z
"""
    out = []
    for streaming in (False, True):
        sim = gcrsim.Simulator(gcrsim.parse_model(model), Settings(**NOFILTER), write=lambda t: None, streaming=streaming)
        sim.run(3)
        out.append(sorted(sim.cur[0]))
    assert out[0] == out[1]


# -- a complete random-context grammar -------------------------------------------------

def test_random_context_grammar_generates_exactly_anbncn():
    import os
    path = os.path.join(os.path.dirname(__file__), "fixtures", "examples", "rc_anbncn.txt")
    settings = Settings(**{**NOFILTER, "history": True})
    sim = gcrsim.Simulator(gcrsim.parse_model_file(path), settings, write=lambda t: None)
    terminal = set()
    for _ in range(16):
        sim.step()
        terminal.update(s for s in sim.cur[0] if s.isalpha() and s.islower())
    assert terminal == {"a" * n + "b" * n + "c" * n for n in (1, 2, 3)}




# -- parser edge cases ----------------------------------------------------------------

def test_clause_text_in_lhs_or_rhs_is_literal():
    assert first_step("""[axioms]
1 = ["A"]

[rules]
A->;forbid:B,1
""") == [";forbid:B"]
    assert first_step("""[axioms]
1 = ["A;permit:B"]

[rules]
A;permit:B->X,1
""") == ["X"]


def test_clause_without_explicit_target_is_an_error():
    with pytest.raises(ModelError):
        gcrsim.parse_model("""[axioms]
1 = ["A"]

[rules]
A->X;permit:B
""")


def test_target_may_be_empty_before_a_clause():
    assert first_step("""[axioms]
1 = ["AB"]

[rules]
A->X,1;permit:B
""") == ["XB"]


def test_comment_after_clause():
    assert first_step("""[axioms]
1 = ["ABF"]

[rules]
# not with F
A->X,1;forbid:F
""") == []
    assert first_step("""[axioms]
1 = ["AB"]

[rules]
# not with F
A->X,1;forbid:F
""") == ["XB"]


def test_trailing_semicolon_makes_an_empty_word():
    with pytest.raises(ModelError):
        gcrsim.parse_model("""[axioms]
1 = ["A"]

[rules]
A->B,1;permit:X,
""")


def test_other_text_after_the_target_is_still_ignored():
    assert first_step("""[axioms]
1 = ["A"]

[rules]
A->X
""") == ["X"]


# -- symbol pattern details ---------------------------------------------------------------




# -- bounded expansion, tracing and broken rules ---------------------------------------------

def test_guarded_rule_stops_at_candidate_limit():
    model = """[axioms]
1 = ["aaaaaa"]

[rules]
a->b,1;permit:a
"""
    sim = gcrsim.Simulator(gcrsim.parse_model(model), Settings(**NOFILTER), write=lambda t: None, max_step_candidates=2)
    with pytest.raises(gcrsim.LimitReached):
        sim.step()


def test_failed_condition_produces_no_candidates_under_a_limit():
    model = """[axioms]
1 = ["aaaaaa"]

[rules]
a->b,1;permit:z
"""
    sim = gcrsim.Simulator(gcrsim.parse_model(model), Settings(**NOFILTER), write=lambda t: None, max_step_candidates=2)
    sim.step()
    assert sim.cur == [[]]


def test_guarded_detailed_trace_lists_results():
    out = []
    model = """[axioms]
1 = ["ab"]

[rules]
a->x,1;permit:b
"""
    settings = Settings(**{**NOFILTER, "show_detailed_application": True})
    sim = gcrsim.Simulator(gcrsim.parse_model(model), settings, write=out.append)
    sim.step()
    assert any("ab => xb" in line for line in out)


# -- symbol pattern validation (second review) ----------------------------------------------

