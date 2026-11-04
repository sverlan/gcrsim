"""Pattern and replacement semantics.

Every case is checked against its expected result and, when Perl is
available, against the original simulator.
"""

import pytest

import gcrsim
from conftest import parse_old, needs_perl, perl_cfg, perl_contents, python_contents

# (id, axiom string, rule line, expected content after one step or None)
CASES = [
    ("group-ref", "ab", "(a)->$1$1", ["aab"]),
    ("double-dollar-group", "ab", "(a)->$$1x", ["axb"]),
    ("missing-group", "ab", "(a)(b)->$2$1$3", ["ba"]),
    ("group-beyond-count", "ab", "(a)->$10", ["b"]),
    ("literal-dollar-end", "ab", "a->$", ["$b"]),
    ("literal-dollar-mid", "ab", "a->x$y", ["x$yb"]),
    ("double-dollar-literal", "ab", "a->$$x", ["$$xb"]),
    ("dollar-then-double-group", "ab", "(a)->$$$1", ["$ab"]),
    ("dollar-without-group", "ab", "a->$$$1", ["$b"]),
    ("at-name-breaks-rule", "ab", "a->x@y", []),
    ("at-end-literal", "ab", "a->x@", ["x@b"]),
    ("at-digit-vanishes", "ab", "a->x@1y", ["xyb"]),
    ("at-punct-literal", "ab", "a->x@.y", ["x@.yb"]),
    ("at-at-breaks", "ab", "a->x@@y", []),
    ("quote-breaks-rule", "ab", 'a->x"y', []),
    ("escaped-quote", "ab", 'a->x\\"y', ['x"yb']),
    ("trailing-backslash-breaks", "ab", "a->x\\", []),
    ("unknown-escape-passes-through", "ab", "a->x\\qy", ["xqyb"]),
    ("escaped-dollar-breaks", "ab", "a->\\$", []),
    ("hex-escape", "ab", "a->\\x41", ["Ab"]),
    ("hex-braces", "ab", "a->x\\x{42}y", ["xByb"]),
    ("hex-dollar-is-literal", "ab", "a->\\x24", ["$b"]),
    ("hex-two-digits-only", "ab", "a->\\x4Bz", ["Kzb"]),
    ("octal-escape", "ab", "a->\\101", ["Ab"]),
    ("percent-hash-quote", "ab", "a->x%y#z'w", ["x%y#z'wb"]),
    ("braces-literal", "ab", "a->x{y}", ["x{y}b"]),
    ("empty-lhs", "ab", "->x", ["xab", "axb", "abx"]),
    ("empty-rhs", "ab", "a->", ["b"]),
    ("overlap-literal", "aaa", "aa->b", ["ba", "ab"]),  # every occurrence, overlapping included (Perl: only "ba")
    ("multiple-matches", "abab", "a->x", ["xbab", "abxb"]),
    ("zero-width-star", "axxb", "x*->y", None),
    ("lookahead", "aa", "(?=a)->x", None),
    ("named-group", "ab", "(?P<n>a)->$1$1", None),  # Python syntax: Perl rejects it, so no Perl comparison
    ("caret-anchor", "aab", "^a->X", ["Xab"]),
    ("dollar-lhs-is-literal", "a$b@c%d#e'f", "$->X", ["aXb@c%d#e'f"]),
    ("at-lhs-is-literal", "a$b@c%d#e'f", "@->X", ["a$bXc%d#e'f"]),
    ("percent-lhs-is-literal", "a$b@c%d#e'f", "%->X", ["a$b@cXd#e'f"]),
    ("hash-lhs-is-literal", "a$b@c%d#e'f", "1,#->X", ["a$b@c%dXe'f"]),
    ("quote-lhs-is-literal", "a$b@c%d#e'f", "'->X", ["a$b@c%d#eXf"]),
    ("dollar-in-class", "a$b", "[$]->X", ["aXb"]),
    ("dollar-never-anchors", "ab", "b$->X", []),
    ("alternation", "abc", "b|c->X", ["aXc", "abX"]),
    ("backreference-lhs", "abab", "(ab)\\1->X", ["X"]),
]


# cases where overlapping occurrences make the result a superset of Perl's
OVERLAPPING = {"overlap-literal", "zero-width-star"}


def model_text(axiom, rule):
    return "Axioms\n[%s]\nRules\n%s\n" % (axiom, rule)


def python_one_step(axiom, rule):
    settings = gcrsim.Settings(history=False, reject_strings="(?!)", reject_max_len=1000, print_hide="(?!)", print_max_len=1000)
    return python_contents(model_text(axiom, rule), steps=1, settings=settings)[1][0]


WITH_EXPECTED = [c for c in CASES if c[3] is not None]   # the other cases are only compared with Perl


@pytest.mark.parametrize("name, axiom, rule, expected", WITH_EXPECTED, ids=[c[0] for c in WITH_EXPECTED])
def test_expected_result(name, axiom, rule, expected):
    assert python_one_step(axiom, rule) == expected


@needs_perl
@pytest.mark.perl
@pytest.mark.parametrize("name, axiom, rule, expected", CASES, ids=[c[0] for c in CASES])
def test_matches_perl(name, axiom, rule, expected, tmp_path):
    cfg = perl_cfg(history=0, reject_strings="(?!)", reject_max_len=1000, print_hide="(?!)", print_max_len=1000)
    perl = perl_contents(model_text(axiom, rule), cfg, 1, tmp_path)
    ours = python_one_step(axiom, rule)
    if name in OVERLAPPING:
        # by design every occurrence counts here; Perl's non-overlapping /g finds a subset
        assert set(perl[1][0]) <= set(ours)
    else:
        assert perl[1][0] == ours


def test_perl_newline_escape_converts_to_a_hex_escape():
    new, warnings = gcrsim.convert_model(model_text("ab", "a->x\\ny"))
    assert warnings == [] and "\\x0a" in new
    assert gcrsim.parse_model(new).rules[0][0].expand("ab") == ["x\nyb"]


def test_unsupported_constructs_are_reported_by_the_converter():
    for rule in ("a->$0", "a->x@-y", "a->x\\xy"):
        new, warnings = gcrsim.convert_model(model_text("ab", rule))
        assert len(warnings) == 1 and "not converted" in warnings[0], rule


def test_bad_lhs_regex_reports_line():
    with pytest.raises(gcrsim.ModelError) as exc:
        gcrsim.parse_model("""[axioms]
1 = ["ab"]

[rules]
(a->x
""", "m.txt")
    assert "m.txt:5" in str(exc.value)
    _, warnings = gcrsim.convert_model(model_text("ab", "(a->x"))
    assert len(warnings) == 1 and "does not compile" in warnings[0]


def test_expand_matches_spans_for_all_cases():
    """The hot-path expansion and the tracing spans must agree."""
    for name, axiom, rule, _ in CASES:
        model = parse_old(model_text(axiom, rule))
        for comp in model.rules:
            for r in comp:
                for s in (axiom, "", "ab", "aab", "abab"):
                    assert list(r.expand(s)) == [res for _, _, res in r.spans(s)], (name, s)
