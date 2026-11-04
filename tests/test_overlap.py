"""Every occurrence of a left-hand side counts, overlapping ones included."""
import pytest

import gcrsim
from conftest import parse_old, python_contents

NOFILTER = dict(history=False, reject_strings="", reject_max_len=1000, print_hide="", print_max_len=1000)


def step(axiom, rule):
    text = "Axioms\n[%s]\nRules\n%s\n" % (axiom, rule)
    return python_contents(text, steps=1, settings=gcrsim.Settings(**NOFILTER))[1][0]


@pytest.mark.parametrize(
    "axiom, rule, expected",
    [
        ("aaa", "aa->b", ["ba", "ab"]),
        ("aaaa", "aa->b", ["baa", "aba", "aab"]),
        ("aba", "aba->X", ["X"]),
        ("ababa", "aba->X", ["Xba", "abX"]),
        ("aaa", "(aa)->b", ["ba", "ab"]),  # a regex left-hand side too
        ("aaaa", "a+->X", ["X", "aX", "aaX", "aaaX"]),  # one match per start, each the leftmost-longest there
        ("ab", "x*->y", ["yab", "ayb", "aby"]),  # zero-width matches: once per position
        ("aab", "a*->y", ["yb", "ayb", "aayb", "aaby"]),
    ],
)
def test_overlapping_occurrences(axiom, rule, expected):
    assert sorted(step(axiom, rule)) == sorted(expected)


def test_insertion_with_a_lookbehind_context_sees_all_positions():
    # insert x after every "aa": positions 2, 3 and 4 of "aaaa"
    assert sorted(step("aaaa", "(?<=aa)->x")) == sorted(["aaxaa", "aaaxa", "aaaax"])


def test_candidate_count_never_exceeds_length_plus_one():
    for axiom, rule in (("aaaa", "->x"), ("aaaa", "re(a*)->y"), ("aaaa", "re((?=a))->x"), ("abab", "re((?:ab)*)->z")):
        text = """[axioms]
1 = ["%s"]

[rules]
%s
""" % (axiom, rule)
        r = gcrsim.parse_model(text).rules[0][0]
        assert len(r.expand(axiom)) <= len(axiom) + 1


def test_guarded_rules_use_the_same_semantics():
    text = "Axioms\n[aaa]\nRules\naa->b,1;permit:a\n"
    out = python_contents(text, steps=1, settings=gcrsim.Settings(**NOFILTER))[1][0]
    assert sorted(out) == ["ab", "ba"]


def test_build_from_edits_matches_expand():
    r = gcrsim.parse_model("""[axioms]
1 = ["aaaa"]

[rules]
aa->b
""").rules[0][0]
    assert r.build("aaaa", r.edits("aaaa")) == list(r.expand("aaaa"))
    assert r.edits("aaaa") == [(0, 2, "b"), (1, 3, "b"), (2, 4, "b")]


def test_spans_report_overlapping_matches():
    r = gcrsim.parse_model("""[axioms]
1 = ["aaa"]

[rules]
aa->b
""").rules[0][0]
    assert [(a, b) for a, b, _ in r.spans("aaa")] == [(0, 2), (1, 3)]
