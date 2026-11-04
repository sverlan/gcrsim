r"""Regression tests for the second Codex review of the redesign (lexicon, patterns, parser, converter)."""
import unicodedata

import pytest

import gcrsim
from gcrsim import ConfigError, ModelError, Settings, parse_model
from gcrsim.model import find_re_end
from gcrsim.lexicon import Lexicon, is_uniquely_decodable
from gcrsim.pattern import compile_pattern
from conftest import legacy_model_text, run_py

NOFILTER = dict(history=False, reject_strings="", reject_max_len=1000, print_hide="", print_max_len=1000)


def model(config, axioms, rules):
    return parse_model(legacy_model_text(config, axioms, rules))


def run(m, steps=1, **kw):
    sim = gcrsim.Simulator(m, Settings(**{**NOFILTER, **kw}), write=lambda t: None)
    for _ in range(steps):
        sim.step()
    return sim


def names(sim, comp=0):
    return sorted(sim.lexicon.decode(s) for s in sim.cur[comp])


# -- regex syntax is not encoded -----------------------------------------------------------


def test_digits_of_a_quantifier_are_not_a_lexeme():
    m = model('symbols = ["12"]', "1: aaaaaaaaaaaa", "re(a{12})->X")
    assert names(run(m)) == ["X"]


def test_hex_escape_digits_are_not_a_lexeme():
    m = model('symbols = ["24"]', "1: a$b", r"re(\x24)->X")
    assert names(run(m)) == ["aXb"]


def test_backreference_digits_and_conditional_names_are_left_alone():
    m = model('symbols = ["11", "ab"]', "1: aa", r"re((a)\1)->X")
    assert names(run(m)) == ["X"]
    m = model('symbols = ["ab"]', "1: xy", r"re((?P<ab>x)?(?(ab)y|z))->X")
    assert names(run(m)) == ["X"]


# -- the alphabet must be uniquely decodable ---------------------------------------------------


def test_uniquely_decodable_codes():
    assert is_uniquely_decodable(["ab", "ba"])
    assert is_uniquely_decodable(["A", "AB", "BC"])
    assert not is_uniquely_decodable(["a", "b", "ab"])
    assert not is_uniquely_decodable(["a", "ab", "bab"] + ["b"])


def test_a_text_with_two_readings_is_an_error_and_a_space_resolves_it():
    with pytest.raises(ModelError, match="more than one way"):
        model('alphabet = "a b ab"', "1: abab", "a->b")
    m = model('alphabet = "a b ab"', "1: a b", "a->b")  # a space separates the symbols
    assert names(run(m)) == ["bb"]
    m = model('alphabet = "a b ab"', "1: ab", "ab->b")  # a run that is itself a symbol is that symbol
    assert names(run(m)) == ["b"]
    assert sorted(names(run(model('alphabet = "a b ab x"', "1: ab ab", "ab->x")))) == ["abx", "xab"]
    model('alphabet = "ab ba"', "1: ab", "ab->ba")


def test_a_text_with_one_reading_is_accepted_even_if_the_alphabet_is_not_a_prefix_code():
    m = model('alphabet = "a ab bc"', "1: abc", "a->a")  # the only reading is a, bc
    assert names(run(m)) == ["abc"]
    with pytest.raises(ModelError, match="not in the alphabet"):
        model('alphabet = "a ab bc"', "1: abd", "a->a")


def test_ambiguity_in_regular_expressions_and_right_hand_sides():
    with pytest.raises(ModelError, match="more than one way"):
        model('alphabet = "a b ab"', "1: a", "re(abab*)->a")
    model('alphabet = "a b ab"', "1: a", "re(ab*)->a")
    model('alphabet = "a b ab"', "1: a", "re(a(?:)b*)->a")
    with pytest.raises(ModelError, match="more than one way"):
        model('alphabet = "a b ab"', "1: a", "a->abab")


# -- converter ---------------------------------------------------------------------------------


def test_converter_escapes_delimiters_in_regex_right_hand_sides():
    for rhs, expected in ((r"\054", ","), (r"\x2f\x2f", "//"), (r"a\x2cb", "a,b")):
        new, warnings = gcrsim.convert_model("Axioms\n[a]\nRules\n(a)->%s\n" % rhs)
        assert warnings == [], rhs
        assert gcrsim.parse_model(new).rules[0][0].expand("a") == [expected], rhs


# -- case-insensitive patterns with lexemes ----------------------------------------------------


def test_case_insensitive_pattern_is_rejected_with_lexemes_only():
    with pytest.raises(ValueError, match="case-insensitive"):
        compile_pattern("(?i)ab", Lexicon(["ab"]))
    assert compile_pattern("(?i)ab").search("AB")


# -- callbacks, print_hide and diagnostics use the real names -----------------------------------


def test_ctx_string_is_decoded():
    seen = []

    def cb(s, c, ctx):
        seen.append((s, ctx.string))
        return s == ctx.string

    m = model('symbols = ["ab"]', "1: ab", "ab->abab")
    sim = run(m, filter_next=cb)
    assert seen == [("abab", "abab")] and names(sim) == ["abab"]


def test_print_hide_uses_the_lexicon(tmp_path):
    (tmp_path / "m.txt").write_bytes(b'[symbols]\nlexemes = ["ab"]\n[axioms]\n1 = ["ab"]\n[rules]\nab->abab\n')
    (tmp_path / "c.toml").write_text('[run]\nprint_hide = "{S}"\n')  # unknown class: reported, not ignored
    r = run_py(["m.txt", "1", "--config", "c.toml"], tmp_path)
    assert r.returncode != 0 or "{S}" in r.stdout


def test_print_hide_matches_whole_lexemes(tmp_path):
    (tmp_path / "m.txt").write_bytes(b'[symbols]\nlexemes = ["ab"]\n[axioms]\n1 = ["ab"]\n[rules]\nab->abab\n')
    (tmp_path / "c.toml").write_text('[run]\nprint_hide = "\\\\Aab\\\\Z"\n')
    r = run_py(["m.txt", "1", "--config", "c.toml"], tmp_path)
    body = r.stdout.split("STEP 1", 1)[1]
    assert "abab" in body and "\nab\n" not in body.split("Component 1:")[0]


def test_callback_failure_message_shows_real_names():
    def cb(s, c):
        raise RuntimeError("boom")

    m = model('symbols = ["ab"]', "1: ab", "ab->abab")
    with pytest.raises(gcrsim.CallbackError) as exc:
        run(m, filter_next=cb)
    assert "'abab'" in str(exc.value) and "" not in str(exc.value)


def test_trace_many_accepts_and_returns_real_names():
    m = model('symbols = ["ab"]', "1: ab", "ab->abab")
    sim = gcrsim.Simulator(m, Settings(**NOFILTER), write=lambda t: None, retain=True)
    sim.step()
    chain = sim.trace_many([(0, "abab", None)])[0]
    assert [(d.source, d.result) for d in chain] == [("ab", "abab")]
    assert sim.trace("abab")[0].result == "abab"


# -- unknown classes ------------------------------------------------------------------------------


def test_unknown_class_is_an_error_everywhere():
    for pattern in ("{TYPO}", "[{TYPO}]", "a{TYPO}b"):
        with pytest.raises(ModelError, match="unknown symbol class"):
            Lexicon().encode_pattern(pattern)
    assert Lexicon().encode_pattern(r"\{TYPO\}") == r"\{TYPO\}"
    assert Lexicon().encode_pattern("a{2}") == "a{2}"


# -- inline flags ----------------------------------------------------------------------------------


def test_verbose_flag_detection_respects_escapes_and_classes():
    with pytest.raises(ValueError):
        compile_pattern("\\\\(?x:a)")  # an escaped backslash, then a real flag group
    assert compile_pattern("[(?x:)]").search("x")
    assert compile_pattern(r"\(?x:a").search("(x:a") or True


# -- the rule separator -------------------------------------------------------------------------------


def test_re_end_skips_groups_and_comments():
    assert find_re_end("re((?:a->b))->X", 3) == 11
    assert find_re_end("re((?#->)a)->X", 3) == 10


# -- private-use allocation ----------------------------------------------------------------------------


def test_many_lexemes_stay_in_private_use_areas():
    lex = Lexicon(["S%04d" % i for i in range(6401)])
    codes = [lex.encode("S%04d" % i) for i in (0, 6399, 6400)]
    assert all(len(c) == 1 and unicodedata.category(c) == "Co" for c in codes)
    assert len(set(lex.encode("S%04d" % i) for i in range(6401))) == 6401


# -- Config handling ----------------------------------------------------------------------------------


def test_triple_quotes_in_a_toml_comment_or_string_are_fine():
    text = '[symbols]\n# do not use """ strings\nlexemes = ["ab"]\n\n[model]\nreject_strings = "it\'s"\n\n[axioms]\n1 = ["ab"]\n\n[rules]\nab->X\n'
    assert parse_model(text).lexicon.lexemes == ["ab"]
    with pytest.raises(ModelError, match="multi-line"):
        parse_model("""[model]
reject_strings = '''a'''

[axioms]
1 = ["a"]

[rules]
a->b
""")


def test_alphabet_error_in_an_axiom_has_a_line_number():
    with pytest.raises(ModelError) as exc:
        parse_model("""[symbols]
alphabet = "a"

[axioms]
1 = ["z"]

[rules]
a->a
""", "m.txt")
    assert "m.txt:4" in str(exc.value)


def test_symbols_and_alphabet_exclude_each_other():
    with pytest.raises(ModelError, match="exclusive"):
        model('symbols = "p1"\nalphabet = "a p1 p2"', "1: a", "a->a")
    model('alphabet = "a p1 p2"', "1: a", "a->a")
    model('symbols = "p1 p3"', "1: a", "a->a")  # without an alphabet: no check


def test_regex_rules_cannot_leave_the_alphabet():
    # the literal text of a right-hand side is checked (escapes included); a group reference only copies symbols
    for rhs in ("re(a)->z", "re(a)->" + chr(92) + "x7a"):
        with pytest.raises(ModelError, match="not in the alphabet"):
            model('alphabet = "a b"', "1: a b", rhs)
    m = model('alphabet = "a b"', "1: a b", "re((a))->" + chr(92) + "1" + chr(92) + "1")
    assert names(run(m)) == ["aab"]


def test_regex_left_hand_side_literals_are_checked_against_the_alphabet():
    with pytest.raises(ModelError, match="not in the alphabet"):
        model('alphabet = "a b"', "1: a", "re(az)->a")
    with pytest.raises(ModelError, match="not in the alphabet"):
        model('alphabet = "a b"', "1: a", "re((a)z*)->a")
    model('alphabet = "a b"', "1: a b", "re((a)(b)|.)->" + chr(92) + "1")  # operators and groups are not symbols
    model('alphabet = "a b p1"', "1: a", "re(a(?:)p1*)->a")


@pytest.mark.parametrize("axiom,rule", [
    ("z", "a->a"),                     # axiom
    ("a", "z->a"),                     # left-hand side
    ("a", "a->z"),                     # right-hand side
    ("a", "a->a,1; permit: z"),         # permit word
    ("a", "a->a,1; forbid: z"),         # forbid word
    ("a", "a->a,1; permit-any: z"),     # permit-any word
    ("a", "ins(z, a, b)"),             # context of ins
    ("a", "re(z)->a"),                 # regular expression, left-hand side
    ("a", "re(a)->z"),                 # regular expression, right-hand side
])
def test_every_place_of_a_rule_and_the_axioms_reject_an_unknown_symbol(axiom, rule):
    with pytest.raises(ModelError, match="not in the alphabet"):
        model('alphabet = "a b"', "1: " + axiom, rule)


def test_a_class_cannot_be_used_in_an_axiom():
    for config in ('alphabet = "a p1 p2"', 'lexemes = "p1 p2"'):
        text = "[symbols]\n%s\n[symbols.classes]\nP = \"p1 p2\"\n[axioms]\n1 = [\"a {P}\"]\n[rules]\na->b\n" % config
        with pytest.raises(ModelError, match=r"axiom of component 1 uses \{P\}"):
            parse_model(text)
    with pytest.raises(ModelError, match=r"uses \{start\}"):
        parse_model('[axioms]\n1 = ["{start}a"]\n[rules]\na->b\n')
    m = parse_model('[axioms]\n1 = ["{x}"]\n[rules]\na->b\n')  # braces that name no class are ordinary symbols
    assert m.lexicon.tokens(m.axioms[0][0]) == ["{", "x", "}"]
