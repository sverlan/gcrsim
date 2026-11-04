r"""Lexemes (multi-character symbols), classes and the alphabet, declared in Config."""
import pytest

import gcrsim
from gcrsim import ModelError, Settings, parse_model
from conftest import EXAMPLES, legacy_model_text, run_py, write_model

NOFILTER = dict(history=False, reject_strings="", reject_max_len=1000, print_hide="", print_max_len=1000)


def model(config, axioms, rules):
    return parse_model(legacy_model_text(config, axioms, rules))


def step(m, steps=1, **kw):
    sim = gcrsim.Simulator(m, Settings(**{**NOFILTER, **kw}), write=lambda t: None)
    for _ in range(steps):
        sim.step()
    return sim


def names(sim, comp=0):
    return sorted(sim.lexicon.decode(s) for s in sim.cur[comp])


P = 'symbols = ["p1", "p2"]'


def test_a_lexeme_is_one_symbol_for_dot():
    m = model(P, "1: p1x", "{any}->Y")
    assert names(step(m)) == ["Yx", "p1Y"]  # two symbols, two candidates (not three)


def test_insertion_never_splits_a_lexeme():
    m = model(P, "1: p1", "->x")
    assert names(step(m)) == ["p1x", "xp1"]  # nothing between p and 1


def test_a_literal_lhs_is_not_found_inside_a_longer_lexeme():
    m = model('symbols = ["p1", "p12"]', "1: p12", "p1->X")
    assert names(step(m)) == []
    m = model('symbols = ["p1", "p12"]', "1: p1p12", "p1->X")
    assert names(step(m)) == ["Xp12"]


def test_longest_lexeme_wins():
    m = model('symbols = ["ab", "abc"]', "1: abcab", "{any}->X")
    assert names(step(m)) == ["Xab", "abcX"]


def test_negated_class_and_quantifier_count_symbols():
    m = model(P, "1: p1p2p1", "re([^p1])->Y")
    assert names(step(m)) == ["p1Yp1"]
    m = model(P, "1: p1p1", "re((p1){2})->Z")
    assert names(step(m)) == ["Z"]
    m = model(P, "1: p1p1p1", "re((p1){2})->Z")
    assert names(step(m)) == ["Zp1", "p1Z"]


def test_lookbehind_with_a_lexeme_context():
    m = model(P, "1: p1ab", "re((?<=p1))->x")
    assert names(step(m)) == ["p1xab"]
    m = model(P, "1: p1ab", "re((?<=.))->x")
    assert names(step(m)) == sorted(["p1xab", "p1axb", "p1abx"])


def test_backreference_matches_a_whole_lexeme():
    m = model(P, "1: p1p1p2", "re((p1|p2)\\1)->D")
    assert names(step(m)) == ["Dp2"]


def test_rhs_lexemes_and_captures():
    m = model(P, "1: p1b", "re((p1)b)->\\1p2\\1")
    assert names(step(m)) == ["p1p2p1"]


def test_classes_expand_to_character_classes():
    cfg = 'symbols = ["p1", "p2"]\n[classes]\nV = "p1 p2 a"'
    m = model(cfg, "1: p2xa", "{V}->Y")
    assert names(step(m)) == ["Yxa", "p2xY"]
    m = model(cfg, "1: p2xa", "re([{V}x]{2})->Y")
    assert names(step(m)) == ["Ya", "p2Y"]
    m = model(cfg, "1: p2xa", "re([^{V}])->Y")
    assert names(step(m)) == ["p2Ya"]


def test_class_members_declare_lexemes_without_symbols():
    m = model('[classes]\nV = "ab cd"', "1: abcd", "{V}->X")
    assert names(step(m)) == ["Xcd", "abX"]


def test_unknown_or_empty_class_is_an_error():
    with pytest.raises(ModelError, match="unknown symbol class"):
        model('[classes]\nV = "a"', "1: a", "{W}->X")
    with pytest.raises(ModelError, match="empty"):
        model('[classes]\nV = ""', "1: a", "{V}->X")
    with pytest.raises(ModelError, match="class name"):
        model('[classes]\n"bad name" = "a"', "1: a", "a->X")


def test_quantifier_braces_are_not_classes():
    m = model(P, "1: aaa", "re(a{2})->X")
    assert names(step(m)) == ["Xa", "aX"]


def test_escaped_braces_and_group_names_are_left_alone():
    cfg = '[classes]\nV = "a b"'
    m = model(cfg, "1: {W}", "re(\\{W\\})->X")  # {W} names no class: ordinary symbols (in an axiom {V} would be an error)
    assert names(step(m)) == ["X"]
    m = model('symbols = ["K1"]', "1: aa", "re((?P<K1>a)(?P=K1))->X")
    assert names(step(m)) == ["X"]


def test_permit_and_forbid_words_use_lexemes():
    m = model(P, "1: p1p2", "p2->X,1;permit:p1")
    assert names(step(m)) == ["p1X"]
    # "p12" is read as the two symbols p1, 2: the symbol 2 can be rewritten, the lexeme p1 is present
    m = model(P, "1: p12", "2->X,1")
    assert names(step(m)) == ["p1X"]
    m = model(P, "1: p12", "2->X,1;permit:p1")
    assert names(step(m)) == ["p1X"]
    m = model(P, "1: p12", "2->X,1;forbid:p1")  # p1 occurs as a symbol, so the rule is blocked
    assert names(step(m)) == []
    m = model(P, "1: p12", "2->X,1;forbid:p2")  # p2 does not occur: '1' and '2' are not the lexeme p2
    assert names(step(m)) == ["p1X"]


def test_lexeme_validation():
    for bad in ('["a.b"]', '["a b"]', '["a,b"]', '["a->"]', '["(x)"]'):
        with pytest.raises(ModelError, match="cannot be a lexeme"):
            model("symbols = %s" % bad, "1: a", "a->b")


def test_private_use_characters_in_the_model_are_never_reused():
    m = model('symbols = ["ab"]', "1: ab", "ab->X")
    assert names(step(m)) == ["X"]


def test_alphabet_is_checked_in_axioms_and_right_hand_sides():
    cfg = 'alphabet = "a b p1"'
    model(cfg, "1: abp1", "a->b")  # fine
    with pytest.raises(ModelError, match="not in the alphabet"):
        model(cfg, "1: abz", "a->b")
    with pytest.raises(ModelError, match="not in the alphabet"):
        model(cfg, "1: ab", "a->z")
    with pytest.raises(ModelError, match="not in the alphabet"):
        model(cfg, "1: ab", "a->b,1;permit:z")


def test_alphabet_error_shows_how_the_text_was_read():
    cfg = 'alphabet = ["p1", "q2"]'
    with pytest.raises(ModelError, match="symbols read as: p1 q"):
        model(cfg, "1: p1q", "p1->p1")


def test_alphabet_includes_class_members():
    cfg = 'alphabet = "a"\n[classes]\nV = "a K1"'
    model(cfg, "1: K1a", "a->a")


def test_output_shows_the_real_names(tmp_path):
    text = """[symbols]
lexemes = ["p1", "p2"]

[axioms]
1 = ["p1"]

[rules]
p1->p1p2
"""
    (tmp_path / "m.txt").write_bytes(text.encode("utf-8"))
    r = run_py(["m.txt", "2"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "p1p2p2" in r.stdout and "" not in r.stdout


def test_error_messages_and_traces_use_real_names(tmp_path):
    text = """[symbols]
lexemes = ["p1", "p2"]

[axioms]
1 = ["p1"]

[rules]
p1->p1p2
"""
    (tmp_path / "m.txt").write_bytes(text.encode("utf-8"))
    r = run_py(["m.txt", "3", "--trace", "p1p2p2"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "p1p2p2" in r.stdout and "step 2: p1p2 => p1p2p2" in r.stdout


def test_callbacks_and_marks_see_real_names(tmp_path):
    seen = []

    def cb(s, c):
        seen.append(s)
        return True

    m = parse_model("""[symbols]
lexemes = ["p1"]

[axioms]
1 = ["p1"]

[rules]
p1->p1p1
""")
    sim = gcrsim.Simulator(m, Settings(**NOFILTER, filter_next=cb), write=lambda t: None)
    sim.step()
    assert seen == ["p1p1"]
    marks = {1: {"t": {"pattern": r"\A(?:p1)+\Z", "expected": {"p1p1"}}}}
    sim = gcrsim.Simulator(m, Settings(**NOFILTER, marks=marks), write=lambda t: None)
    sim.step()
    assert sim.marks == []  # the expected string is given with real names


def test_filters_use_lexemes():
    m = model(P, "1: p1", "p1->p1p2\np1->p1p1")
    settings = Settings(**NOFILTER, filters={0: {"forbid": [r"p2"], "max_count": {"p1": 2}}})
    sim = gcrsim.Simulator(m, settings, write=lambda t: None)
    sim.step()
    assert names(sim) == ["p1p1"]


def test_ins_b_110200_with_lexemes_equals_the_filter_version():
    """p0..p5 as lexemes give the strings of the old p\\d\\d / f\\d\\d filters (66,907 strings at depth 20)."""
    steps = 20
    base = (EXAMPLES / "ins_b_110200.txt").read_text(encoding="utf-8")
    old_settings = gcrsim.load_config(str(EXAMPLES / "ins_b_110200_declarative.py"))
    old = gcrsim.Simulator(parse_model(base), old_settings, write=lambda t: None)
    cfg = """[symbols]
lexemes = ["p0", "p1", "p2", "p3", "p4", "p5"]

[symbols.classes]
P = "p0 p1 p2 p3 p4 p5"
"""
    new_settings = gcrsim.load_config(str(EXAMPLES / "ins_b_110200_declarative.py"))
    new_settings.filters = {0: {"forbid": [r"({P}).*\1.*\1", r"(f.).*\1.*\1"]}}
    new = gcrsim.Simulator(parse_model(cfg + base), new_settings, write=lambda t: None)
    for _ in range(steps):
        old.step()
        new.step()
        assert [sorted(c) for c in old.cur] == [sorted(new.lexicon.decode(s) for s in c) for c in new.cur]
    assert sum(len(h) for h in new.hist) == sum(len(h) for h in old.hist) == 66907


def test_lookbehind_syntax_is_not_read_as_a_lexeme():
    m = parse_model("""[symbols]
lexemes = ["<=", "a1"]

[axioms]
1 = ["a1<="]

[rules]
re((?<=a1)<=)->X
""")
    assert m.rules[0][0].expand(m.axioms[0][0]) == [m.lexicon.encode("a1") + "X"]


def test_patterns_cannot_name_internal_codes():
    bs = chr(92)
    lex = parse_model("""[symbols]
lexemes = ["p1"]

[axioms]
1 = ["p1"]

[rules]
p1->p1
""").lexicon
    code = lex.encode("p1")
    from gcrsim.pattern import compile_pattern
    with pytest.raises(ValueError, match="reserved"):
        compile_pattern(code, lex)
    with pytest.raises(ValueError, match="reserved"):
        compile_pattern(bs + "u%04x" % ord(code), lex)
    compile_pattern(bs + "ue0ff", lex) if ord(code) != 0xE0FF else None


def test_print_sep_separates_lexemes_in_the_listing(tmp_path):
    text = '[symbols]\nlexemes = ["p1"]\n\n[run]\nprint_sep = " "\n\n[axioms]\n1 = ["p1a"]\n\n[rules]\n1,a->ap1,1\n'
    (tmp_path / "m.txt").write_bytes(text.encode("utf-8"))
    r = run_py(["m.txt", "1"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "p1 a p1" in r.stdout
    plain = text.replace("print_sep = " + chr(34) + " " + chr(34) + chr(10), "")
    (tmp_path / "n.txt").write_bytes(plain.encode("utf-8"))
    assert "p1ap1" in run_py(["n.txt", "1"], tmp_path).stdout


def test_a_space_between_symbols_stops_a_lexeme_from_being_read_across_it():
    cfg = '[symbols]\nlexemes = ["ab", "abc"]\n[axioms]\n1 = ["%s"]\n[rules]\nX->Y\n'

    def tokens(axiom):
        m = parse_model(cfg % axiom)
        return m.lexicon.tokens(m.axioms[0][0])

    assert tokens("abcab") == ["abc", "ab"]        # no space: longest match
    assert tokens("ab c ab") == ["ab", "c", "ab"]  # spaces: the symbols are read as written
    assert tokens("abc ab") == ["abc", "ab"]
    assert tokens("a bc") == ["a", "b", "c"]       # a lexeme is not read across a space


def test_spaces_in_rules_and_words_separate_lexemes_too():
    text = (
        """[symbols]
lexemes = ["ab", "abc"]

[axioms]
1 = ["ab c ab"]

[rules]
ab c -> X , 1 ; permit: ab c , ab ; forbid: abc
"""
    )
    m = parse_model(text)
    rule = m.rules[0][0]
    assert list(rule.expand(m.axioms[0][0])) == [m.lexicon.encode("X") + m.lexicon.encode("ab")]
    assert chr(0) not in rule.text and "ab c" in rule.text   # the rule is shown as it was written
    assert list(rule.expand(m.lexicon.encode("abc ab".replace(" ", "")))) == []   # forbid: abc blocks it


def test_spaces_do_nothing_without_lexemes():
    a = parse_model("""[axioms]
1 = ["a b c"]

[rules]
a b -> c d , 1
""")
    b = parse_model("""[axioms]
1 = ["abc"]

[rules]
ab->cd,1
""")
    assert a.axioms == b.axioms and [r.lhs for r in a.rules[0]] == [r.lhs for r in b.rules[0]] == ["ab"]
