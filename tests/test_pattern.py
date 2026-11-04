"""The shared pattern preprocessing: ``$`` is always a literal, anchors are \\A and \\Z."""
import re

import pytest

import gcrsim
from conftest import parse_old
from gcrsim.pattern import compile_pattern, literal_dollar


@pytest.mark.parametrize(
    "pattern, expected",
    [
        ("a$", r"a\$"),
        (r"a\$", r"a\$"),  # already escaped: unchanged
        (r"a\\$", r"a\\\$"),  # an escaped backslash, then a real $
        ("[$AB]", r"[\$AB]"),
        (r"[\]$]", r"[\]\$]"),
        ("(?P<n>a$)", r"(?P<n>a\$)"),
        ("no dollar", "no dollar"),
        ("$$", r"\$\$"),
        ("a\\", "a\\"),  # a trailing lone backslash is left to re to reject
    ],
)
def test_literal_dollar_uses_backslash_parity(pattern, expected):
    assert literal_dollar(pattern) == expected


def test_dollar_matches_only_the_symbol():
    rx = compile_pattern("A$")
    assert rx.search("xA$y") and not rx.search("xA")
    assert compile_pattern(r"\AA\Z").search("A")
    assert not compile_pattern(r"\AA\Z").search("AA")


def test_start_and_end_anchors():
    assert compile_pattern(r"\Aab").search("abab").start() == 0
    assert compile_pattern(r"ab\Z").search("abab").start() == 2
    assert compile_pattern(r"\Aab\Z").search("ab") and not compile_pattern(r"\Aab\Z").search("aba")


def test_verbose_flag_is_rejected():
    with pytest.raises(ValueError):
        compile_pattern("(?x)#A")
    with pytest.raises(ValueError):
        compile_pattern("(?x: a )")  # scoped, still verbose inside - flags report it only for global use
    # the plain non-verbose pattern with a literal hash is fine
    assert compile_pattern("#A").search("x#Ay")


def test_hyphen_inside_a_character_class_is_a_range():
    assert compile_pattern("[a-c]").search("b") and not compile_pattern("[a-c]").search("d")


def _model(rules):
    return gcrsim.parse_model("""[axioms]
1 = ["A$B"]

[rules]
""" + rules + "\n")


def test_a_dollar_in_a_rule_lhs_is_a_symbol_not_an_anchor():
    model = _model("A$->X")
    sim = gcrsim.Simulator(model, gcrsim.Settings(), write=lambda text: None)
    sim.step()
    assert sim.cur[0] == ["XB"]


def test_escaped_dollar_in_a_rule_lhs_is_still_a_symbol():
    model = _model(r"re(A\$)->X")
    sim = gcrsim.Simulator(model, gcrsim.Settings(), write=lambda text: None)
    sim.step()
    assert sim.cur[0] == ["XB"]


def test_dollar_in_a_class_of_a_rule_lhs():
    model = _model("re([$#]B)->Y")
    sim = gcrsim.Simulator(model, gcrsim.Settings(), write=lambda text: None)
    sim.step()
    assert sim.cur[0] == ["AY"]


def test_verbose_flag_in_a_rule_lhs_is_a_model_error():
    with pytest.raises(gcrsim.ModelError):
        _model("re((?x)#A)->B")


def test_config_regexes_use_the_same_rules():
    st = gcrsim.Settings(marks={1: {"t": r"\A[A$B]+\Z"}})
    model = _model("B->A")
    sim = gcrsim.Simulator(model, st, write=lambda text: None)
    sim.step()
    assert any(m.label == "t" for m in sim.marks)
    with pytest.raises(gcrsim.ConfigError):
        gcrsim.Simulator(model, gcrsim.Settings(marks={1: {"t": "(?x)#A"}}), write=lambda text: None)
