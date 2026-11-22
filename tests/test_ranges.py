r"""Ranges: ``[symbols.ranges]``, the references ``{:X}``, and the rules, symbols and axioms they expand."""
import json
import re
from pathlib import Path

import pytest

import gcrsim
from gcrsim import ModelError, describe, main, parse_model, replay, search

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ROOT / "examples" / "features"


def run(capsys, *args):
    status = main([str(a) for a in args])
    cap = capsys.readouterr()
    return status, cap.out, cap.err


def objs(out):
    return [json.loads(line) for line in out.splitlines() if line.strip()]


@pytest.fixture
def files(tmp_path):
    def make(name, text):
        path = tmp_path / name
        path.write_bytes(text.encode("utf-8"))
        return str(path)
    return make


def sig(model):
    """What a model is, without where its rules came from: axioms, alphabet, classes and every rule's notation and wiring."""
    lex = model.lexicon
    return (
        [[lex.decode(a) for a in comp] for comp in model.axioms],
        lex.alphabet_order,
        {k: list(v) for k, v in lex.classes.items()},
        [[(r.kind, r.notation, r.source, r.target, r.permit, r.forbid, r.any_of) for r in comp] for comp in model.rules],
    )


def same(expanded, handwritten):
    a, b = parse_model(expanded), parse_model(handwritten)
    assert sig(a) == sig(b)
    return a, b


def csv_of(capsys, text, files, steps):
    path = files("m_%d.txt" % abs(hash(text)), text)
    status, out, _ = run(capsys, path, steps, "--format", "csv", "--quiet")
    assert status == 0
    return out


def notations(text, comp=0):
    return [r.notation for r in parse_model(text).rules[comp]]


HEAD = '[symbols]\nalphabet = "A{:X} B{:X} a b S"\n[symbols.ranges]\nX = "1..3"\n[axioms]\n1 = ["S"]\n[rules]\n'


# ---------------------------------------------------------------- expansion equals the handwritten model


def test_simple_rule_expands_in_order():
    ex = HEAD + "A{:X} -> B{:X}\n"
    hw = HEAD.replace("{:X}", "").replace('[symbols.ranges]\nX = "1..3"\n', "") + "A1->B1\nA2->B2\nA3->B3\n"
    hw = '[symbols]\nalphabet = "A1 A2 A3 B1 B2 B3 a b S"\n[axioms]\n1 = ["S"]\n[rules]\nA1->B1\nA2->B2\nA3->B3\n'
    same(ex, hw)


def test_declarations_in_any_order():
    text = '[rules]\nA{:X} -> B{:X}\n[axioms]\n1 = ["A1"]\n[symbols.ranges]\nX = "1..2"\n[symbols]\nalphabet = "A{:X} B{:X}"\n'
    m = parse_model(text)
    assert [r.notation for r in m.rules[0]] == ["A1->B1", "A2->B2"]
    assert m.lexicon.alphabet_order == ("A1", "A2", "B1", "B2")


def test_correlated_versus_independent_matches():
    text = '[symbols]\nalphabet = "A1 A2 a"\nterminals = "a"\n[symbols.ranges]\nX = "1..2"\n[symbols.classes]\nA = "A{:X}"\n' \
           '[axioms]\n1 = ["A1 A2", "A1 A1"]\n[rules]\n'
    corr = parse_model(text + "A{:X}A{:X} -> a\n")
    indep = parse_model(text + "{A}{A} -> a\n")
    assert [r.notation for r in corr.rules[0]] == ["A1A1->a", "A2A2->a"]
    assert len(indep.rules[0]) == 1
    enc = corr.lexicon.encode
    assert [list(r.expand(enc("A1A2"))) for r in corr.rules[0]] == [[], []]  # unequal indices: no instance matches
    assert [len(r.expand(enc("A1A1"))) for r in corr.rules[0]] == [1, 0]
    assert len(indep.rules[0][0].expand(enc("A1A2"))) == 1  # the class matches A1 A2 as well


def test_class_from_a_range_is_a_runtime_class():
    m = parse_model('[symbols]\nalphabet = "A{:X} b"\n[symbols.ranges]\nX = "1..3"\n[symbols.classes]\nP = "A{:X}"\n[rules]\n{P}->b\n')
    assert m.lexicon.classes["P"] == ["A1", "A2", "A3"]
    assert len(m.rules[0]) == 1 and m.rules[0][0].bindings is None


def test_cartesian_product_and_binding_order():
    text = '[symbols.ranges]\nI = "0..1"\nJ = "5..6"\n[rules]\nD{:I}{:J} -> D{:J}{:I}\n'
    m = parse_model(text)
    assert [r.notation for r in m.rules[0]] == ["D05->D50", "D06->D60", "D15->D51", "D16->D61"]
    assert [r.bindings for r in m.rules[0]] == [{"I": 0, "J": 5}, {"I": 0, "J": 6}, {"I": 1, "J": 5}, {"I": 1, "J": 6}]
    assert list(m.rules[0][0].bindings) == ["I", "J"]
    # the order is the order of first appearance in the line, not of the declarations
    swapped = parse_model(text.replace("D{:I}{:J} -> D{:J}{:I}", "D{:J}{:I} -> x"))
    assert [r.bindings for r in swapped.rules[0]][:2] == [{"J": 5, "I": 0}, {"J": 5, "I": 1}]


@pytest.mark.parametrize("expr,values", [
    ("X", [1, 2, 3]), ("X+1", [2, 3, 4]), ("X-1", [0, 1, 2]), ("1-X+2", [2, 1, 0]), ("2*X", [2, 4, 6]), ("X*2", [2, 4, 6]),
    ("(X+1)%2", [0, 1, 0]), ("X%2+1", [2, 1, 2]), ("-X+5", [4, 3, 2]), ("(X-2)%3", [2, 0, 1]), (" X + 1 ", [2, 3, 4]),
    ("7", [7, 7, 7]), ("2*(X+1)-1", [3, 5, 7]),
])
def test_arithmetic(expr, values):
    text = '[symbols.ranges]\nX = "1..3"\n[rules]\nq{:%s} -> r\n' % expr
    m = parse_model(text)
    got = [r.notation for r in m.rules[0]]
    if "X" in expr:
        assert got == ["q%d->r" % v for v in values]
    else:
        assert got == ["q7->r"] and m.rules[0][0].bindings is None


def test_values_above_the_range_are_checked_by_the_alphabet():
    base = '[symbols]\nalphabet = "A{:X}"\n[symbols.ranges]\nX = "1..3"\n[rules]\nA{:X} -> A{:X+1}\n'
    with pytest.raises(ModelError, match=r"A4.*not in the alphabet.*X=3|X=3.*A4"):
        parse_model(base)
    ok = base.replace('"A{:X}"', '"A{:X} A4"')
    assert [r.notation for r in parse_model(ok).rules[0]] == ["A1->A2", "A2->A3", "A3->A4"]
    wrap = base.replace("A{:X+1}", "A{:X%3+1}")
    assert [r.notation for r in parse_model(wrap).rules[0]] == ["A1->A2", "A2->A3", "A3->A1"]


def test_negative_value_is_an_error_naming_line_and_binding():
    with pytest.raises(ModelError, match=r":6: .*X-2.*-1.*X=1.*negative"):
        parse_model('[symbols.ranges]\nX = "1..3"\n\n\n[rules]\nq{:X-2} -> r\n')
    # a negative intermediate value that comes back to a non-negative result is fine
    assert [r.notation for r in parse_model('[symbols.ranges]\nX = "0..2"\n[rules]\nq{:(X-1)%3} -> r\n').rules[0]] == ["q2->r", "q0->r", "q1->r"]


@pytest.mark.parametrize("expr,message", [
    ("X%0", "positive constant"), ("X%X", "constant divisor"), ("X*X", "constant operand"), ("X%(1-1)", "positive constant"),
    ("X%-2", "positive constant"), ("", "empty"), ("X+", "expected"), ("(X", "missing"), ("X Y", "unexpected"), ("X$", "unexpected character"),
    ("01", "leading zero"), ("X/2", "unexpected character"), ("1.5", "unexpected"),
])
def test_invalid_expressions(expr, message):
    with pytest.raises(ModelError, match=message):
        parse_model('[symbols.ranges]\nX = "1..3"\n[rules]\nq{:%s} -> r\n' % expr)


def test_modulo_error_is_found_even_when_the_rule_would_not_matter():
    with pytest.raises(ModelError, match=":5: "):
        parse_model('[symbols.ranges]\nX = "1..1"\n[rules]\n#\nq{:X%0} -> r\n')


def test_unclosed_reference():
    with pytest.raises(ModelError, match="not closed"):
        parse_model('[symbols.ranges]\nX = "1..3"\n[rules]\nq{:X -> r\n')


def test_undeclared_range():
    with pytest.raises(ModelError, match=r":4: .*range Y is not declared"):
        parse_model('[symbols.ranges]\nX = "1..3"\n[rules]\nq{:Y} -> r\n')
    with pytest.raises(ModelError, match="range X is not declared"):
        parse_model('[symbols]\nalphabet = "A{:X}"\n')
    with pytest.raises(ModelError, match="range X is not declared"):
        parse_model('[axioms]\n1 = ["a{:X}"]\n')


@pytest.mark.parametrize("decl", ['"3..1"', '"1-3"', '3', '"a..b"', '"01..3"', '"-1..3"', '"1..3..5"'])
def test_bad_range_declaration(decl):
    with pytest.raises(ModelError, match="range X"):
        parse_model("[symbols.ranges]\nX = %s\n" % decl)
    assert parse_model('[symbols.ranges]\nX = " 0 .. 0 "\n').ranges == {"X": (0, 0)}


def test_bad_range_name():
    with pytest.raises(ModelError, match="bad range name"):
        parse_model('[symbols.ranges]\n"1x" = "1..3"\n')


def test_limit_on_generated_rules():
    text = '[symbols.ranges]\nX = "1..10"\nY = "1..10"\n[rules]\na -> b\nq{:X}{:Y} -> r\n'
    assert len(parse_model(text).rules[0]) == 101
    with pytest.raises(ModelError, match=r":8: .*100 rules.*max_expanded_rules"):
        parse_model('[model]\nmax_expanded_rules = 99\n' + text)
    assert len(parse_model('[model]\nmax_expanded_rules = 100\n' + text).rules[0]) == 101
    with pytest.raises(ModelError, match=r":8: .*10 rules"):  # the second line takes the total over the limit
        parse_model('[model]\nmax_expanded_rules = 105\n[symbols.ranges]\nX = "1..10"\nY = "1..10"\n[rules]\nq{:X}{:Y} -> r\nu{:X} -> r\n')


def test_limit_default_and_status(files, capsys):
    path = files("big.txt", '[symbols.ranges]\nX = "1..400"\nY = "1..400"\n[rules]\nq{:X}{:Y} -> r\n')
    status, out, err = run(capsys, path, "1")
    assert status == 2 and "max_expanded_rules" in err and "160000" in err
    path = files("big2.txt", '[model]\nmax_expanded_rules = 200000\n[symbols.ranges]\nX = "1..400"\nY = "1..400"\n[rules]\nq{:X}{:Y} -> r\n')
    assert len(parse_model(Path(path).read_text()).rules[0]) == 160000


def test_limit_setting_must_be_positive_and_is_model_only(files, capsys):
    with pytest.raises(ModelError, match="max_expanded_rules"):
        parse_model("[model]\nmax_expanded_rules = 0\n")
    with pytest.raises(ModelError, match="max_expanded_rules"):
        parse_model('[model]\nmax_expanded_rules = "5"\n')
    model = files("m.txt", '[axioms]\n1 = ["a"]\n[rules]\na -> b\n')
    cfg = files("c.toml", "[model]\nmax_expanded_rules = 5\n")
    status, out, err = run(capsys, model, "1", "--config", cfg)
    assert status == 2 and "max_expanded_rules" in err


def test_ranges_must_not_reach_a_configuration_file(files, capsys):
    model = files("m.txt", '[axioms]\n1 = ["a"]\n[rules]\na -> b\n')
    cfg = files("c.toml", '[symbols.ranges]\nX = "1..2"\n')
    status, out, err = run(capsys, model, "1", "--config", cfg)
    assert status == 2 and "symbols" in err


# ---------------------------------------------------------------- where ranges are allowed


def test_alphabet_lexemes_terminals_classes_axioms():
    text = ('[symbols]\nlexemes = "p{:X} q{:X}"\nterminals = "a p{:X}"\n[symbols.classes]\nP = "p{:X}"\nQ = ["q{:X}", "z"]\n'
            '[symbols.ranges]\nX = "1..3"\n[axioms]\n1 = ["p{:X} a", "b"]\n2 = ["q{:X}"]\n[rules]\n{P}->z\n')
    m = parse_model(text)
    assert m.config["terminals"] == "a p1 p2 p3"
    assert m.lexicon.classes == {"P": ["p1", "p2", "p3"], "Q": ["q1", "q2", "q3", "z"]}
    assert [[m.lexicon.decode(a) for a in comp] for comp in m.axioms] == [["p1a", "p2a", "p3a", "b"], ["q1", "q2", "q3"], []][:len(m.axioms)]
    assert m.lexicon.lexemes == ["p1", "p2", "p3", "q1", "q2", "q3"]
    assert gcrsim.search is not None


def test_alphabet_list_value_expands_each_entry():
    m = parse_model('[symbols]\nalphabet = ["A{:X}", "b"]\n[symbols.ranges]\nX = "1..2"\n')
    assert m.lexicon.alphabet_order == ("A1", "A2", "b")


def test_words_expand_in_place_and_axioms_per_binding():
    m = parse_model('[symbols]\nalphabet = "S a{:X} b{:X} c"\n[symbols.ranges]\nX = "1..2"\n[axioms]\n1 = ["S a{:X} b{:X}", "c"]\n')
    assert m.lexicon.alphabet_order == ("S", "a1", "a2", "b1", "b2", "c")
    assert [m.lexicon.tokens(a) for a in m.axioms[0]] == [["S", "a1", "b1"], ["S", "a2", "b2"], ["c"]]


def test_declarations_do_not_count_against_the_rule_limit():
    m = parse_model('[model]\nmax_expanded_rules = 1\n[symbols]\nalphabet = "A{:X}"\n[symbols.ranges]\nX = "1..2"\n')
    assert m.lexicon.alphabet_order == ("A1", "A2")
    with pytest.raises(ModelError, match="more than 1000000 words"):  # only a sanity bound for one word of a declaration
        parse_model('[symbols]\nalphabet = "A{:X}{:Y}"\n[symbols.ranges]\nX = "1..2000"\nY = "1..2000"\n')


@pytest.mark.parametrize("key", ["alphabet", "lexemes", "terminals"])
def test_spaces_inside_a_reference_in_string_declarations(key):
    m = parse_model('[symbols]\n%s = "a A{: X + 1 } b"\n[symbols.ranges]\nX = "1..2"\n' % key)
    value = m.config.get("symbols" if key == "lexemes" else key)
    assert value == "a A2 A3 b"
    c = parse_model('[symbols]\nalphabet = "A2 A3 B"\n[symbols.classes]\nP = "A{: X + 1 } B"\n[symbols.ranges]\nX = "1..2"\n')
    assert c.lexicon.classes["P"] == ["A2", "A3", "B"]


def test_description_and_other_text_is_not_expanded():
    m = parse_model('[model]\ndescription = "uses {:X} here"\n[symbols.ranges]\nX = "1..2"\n')
    assert m.config["description"] == "uses {:X} here"


def test_range_in_a_rule_name_clause_is_an_error():
    with pytest.raises(ModelError, match="name of a rule"):
        parse_model('[symbols.ranges]\nX = "1..2"\n[rules]\nq{:X} -> r, 1; name: g{:X}\n')


def test_permit_forbid_words_use_the_same_binding():
    m = parse_model('[symbols.ranges]\nX = "1..2"\n[rules]\nq{:X} -> r{:X}, 1; permit: a{:X}; forbid: b{:X}\n')
    assert [r.notation for r in m.rules[0]] == ["q1->r1,1;permit:a1;forbid:b1", "q2->r2,1;permit:a2;forbid:b2"]
    assert m.rules[0][1].permit == ("a2",) and m.rules[0][1].forbid == ("b2",)


def test_ins_del_sub_forms_and_contexts():
    m = parse_model('[symbols.ranges]\nX = "1..2"\n[rules]\nins(a{:X},b{:X},c{:X+1})\ndel(,a{:X},)\nsub(,a{:X},b,)\n')
    assert [r.notation for r in m.rules[0]] == ["ins(a1,b1,c2)", "ins(a2,b2,c3)", "del(,a1,)", "del(,a2,)", "sub(,a1,b,)", "sub(,a2,b,)"]
    assert [r.kind for r in m.rules[0]] == ["ins", "ins", "del", "del", "sub", "sub"]


# ---------------------------------------------------------------- component numbers


def test_component_numbers_in_the_general_section():
    m = parse_model('[symbols.ranges]\nX = "1..3"\n[rules]\n{:X}, A{:X} -> B, {:X+1}\n')
    assert m.ncomp == 4
    assert [[(r.notation, r.source, r.target) for r in comp] for comp in m.rules] == [
        [("1,A1->B,2", 0, 1)], [("2,A2->B,3", 1, 2)], [("3,A3->B,4", 2, 3)], []]
    assert m.rules[1][0].bindings == {"X": 2}


def test_component_number_must_not_be_zero_after_expansion():
    with pytest.raises(ModelError, match=r"component numbers start at 1.*X=0|X=0.*component numbers start at 1|X=0"):
        parse_model('[symbols.ranges]\nX = "0..2"\n[rules]\n{:X}, A -> B, 1\n')


def test_range_in_a_section_header_is_an_error():
    with pytest.raises(ModelError, match=r":3: .*section header"):
        parse_model('[symbols.ranges]\nX = "1..2"\n[rules.{:X}]\nA -> B, 1\n')


def test_rules_section_with_range_keeps_the_target_required():
    m = parse_model('[symbols.ranges]\nX = "1..2"\n[rules.2]\nA{:X} -> B, {:X}\n')
    assert [(r.source, r.target) for r in m.rules[1]] == [(1, 0), (1, 1)]


# ---------------------------------------------------------------- regular expressions


def test_regex_rule_with_ranges_quantifiers_and_backreferences():
    text = ('[symbols]\nalphabet = "A{:X} B{:X} c"\n[symbols.ranges]\nX = "1..2"\n[symbols.classes]\nC = "A{:X} c"\n'
            '[rules]\nre(({C})A{:X}{2})->\\1B{:X}\n')
    m = parse_model(text)
    assert len(m.rules[0]) == 2 and all(r.kind == "re" for r in m.rules[0])
    r1, r2 = m.rules[0]
    assert r1.notation == "re(({C})A1{2})->\\1B1" and r2.notation == "re(({C})A2{2})->\\1B2"
    enc = m.lexicon.encode
    assert list(r1.expand(enc("cA1A1"))) == [enc("cB1")]
    assert list(r1.expand(enc("cA2A2"))) == [] and list(r2.expand(enc("cA2A2"))) == [enc("cB2")]


def test_regex_literal_range_start_is_written_with_a_backslash():
    text = '[symbols.ranges]\nX = "1..2"\n[rules]\nre(a\\{:b)->c\nre(a\\\\{:X})->c\n'
    m = parse_model(text)
    assert m.rules[0][0].notation == "re(a\\{:b)->c" and m.rules[0][0].bindings is None
    assert [r.notation for r in m.rules[0][1:]] == ["re(a\\\\1)->c", "re(a\\\\2)->c"]  # an even number of backslashes: a reference


def test_regex_literal_works_without_declared_ranges():
    m = parse_model('[rules]\nre(a\\{:b)->c\n')
    assert m.rules[0][0].expand("a{:b") == ["c"]


def test_range_syntax_outside_a_regex_always_starts_a_reference():
    with pytest.raises(ModelError, match="range"):
        parse_model('[rules]\na{:b} -> c\n')
    with pytest.raises(ModelError, match="range"):
        parse_model('[rules]\n1, re(a{:Y})->c\n')


def test_regex_with_component_range_prefix():
    m = parse_model('[symbols.ranges]\nX = "1..2"\n[rules]\n{:X}, re(a{:X})->b, {:X}\n')
    assert [r.notation for comp in m.rules for r in comp] == ["1,re(a1)->b,1", "2,re(a2)->b,2"]


# ---------------------------------------------------------------- unchanged models


def test_model_without_ranges_is_unchanged():
    m = parse_model('[axioms]\n1 = ["S"]\n[rules]\nS -> a S b, 1; name: g\nS -> a, 1\n')
    assert [(r.line, r.name, r.bindings, r.source_notation) for r in m.rules[0]] == [(4, "g", None, None), (5, None, None, None)]
    assert m.ranges == {}
    assert [r.index for r in m.rules[0]] == [0, 1]


def test_ranges_declared_but_unused():
    m = parse_model('[symbols.ranges]\nX = "1..3"\n[axioms]\n1 = ["S"]\n[rules]\nS -> a\n')
    assert len(m.rules[0]) == 1 and m.ranges == {"X": (1, 3)}


def test_rules_keep_the_order_of_the_file_and_the_line_numbers():
    m = parse_model('[symbols.ranges]\nX = "1..2"\n[rules]\na -> b\nq{:X} -> r\n\nc -> d\n')
    assert [(r.notation, r.line, r.index) for r in m.rules[0]] == [("a->b", 4, 0), ("q1->r", 5, 1), ("q2->r", 5, 2), ("c->d", 7, 3)]


# ---------------------------------------------------------------- names and provenance


NAMED = ('[symbols]\nalphabet = "A{:X} B{:X} S"\nterminals = "B1"\n[symbols.ranges]\nX = "1..2"\n[axioms]\n1 = ["A1 A2"]\n[rules]\n'
         'A{:X} -> B{:X}, 1; name: grow\nB{:X} -> A{:X}\n')


def test_names_bindings_and_source_notation_are_separate():
    m = parse_model(NAMED)
    g1, g2, u1, u2 = m.rules[0]
    assert (g1.name, g1.bindings, g1.line, g1.notation, g1.source_notation) == ("grow", {"X": 1}, 9, "A1->B1,1", "A{:X}->B{:X},1")
    assert g2.bindings == {"X": 2} and g2.name == "grow"
    assert (u1.name, u1.bindings, u1.source_notation, u1.line) == (None, {"X": 1}, "B{:X}->A{:X}", 10)
    assert g1.label == "grow[X=1]" and u2.label == "B{:X}->A{:X}[X=2]"
    assert g1.provenance(m.lexicon)["bindings"] == {"X": 1}
    assert g1.provenance(m.lexicon)["source_notation"] == "A{:X}->B{:X},1"
    assert g1.provenance(m.lexicon)["notation"] == "A1->B1,1"
    plain = parse_model('[rules]\na -> b\n')
    assert "source_notation" not in plain.rules[0][0].provenance(plain.lexicon)


def test_two_source_lines_cannot_share_a_name():
    with pytest.raises(ModelError, match=r"'grow' is used by the rules at lines 9 and 10"):
        parse_model(NAMED.replace("B{:X} -> A{:X}", "B{:X} -> A{:X}, 1; name: grow"))


def test_expansions_of_one_name_do_not_clash():
    assert len(parse_model(NAMED).rules[0]) == 4


def test_trace_text_shows_names_and_bindings(files, capsys):
    path = files("m.txt", NAMED)
    status, out, _ = run(capsys, path, "3", "--trace", "B1B2")
    assert status == 0
    assert "rule grow[X=1] at line 9: A1->B1,1" in out
    assert "rule grow[X=2] at line 9: A2->B2,1" in out
    path = files("m2.txt", NAMED.replace('["A1 A2"]', '["B1 B2"]'))
    status, out, _ = run(capsys, path, "3", "--trace", "A1B2")
    assert "rule at line 10: B{:X}->A{:X}[X=1]" in out
    assert "rules: " in out and "B{:X}->A{:X}[X=1] (line 10) x1" in out


def test_error_messages_name_the_binding():
    with pytest.raises(ModelError, match=r"A3.*X=3"):
        parse_model('[symbols]\nalphabet = "A1 A2 B"\n[symbols.ranges]\nX = "1..3"\n[rules]\nA{:X} -> B\n')


def test_measures_entries_have_bindings(files, capsys):
    path = files("m.txt", NAMED)
    status, out, _ = run(capsys, path, "3", "--trace", "B1B2", "--format", "jsonl")
    rules = [o for o in objs(out) if o["type"] == "derivation"][0]["measures"]["rules"]
    assert [(r["name"], r["bindings"], r["line"], r["notation"]) for r in rules] == [
        ("grow", {"X": 1}, 9, "A1->B1,1"), ("grow", {"X": 2}, 9, "A2->B2,1")]
    assert rules[0]["source_notation"] == "A{:X}->B{:X},1"
    steps = [o for o in objs(out) if o["type"] == "derivation_step"]
    assert steps[0]["rule"]["bindings"] == {"X": 1} and steps[0]["rule"]["source_notation"] == "A{:X}->B{:X},1"
    assert steps[0]["rule"]["name"] == "grow" and steps[0]["rule"]["notation"] == "A1->B1,1"


def test_measures_text_tells_expansions_apart():
    sim = gcrsim.Simulator(parse_model(NAMED), retain=True)
    sim.run(3)
    steps = sim.trace("B1B2")
    text = gcrsim.format_derivation(steps, measures=gcrsim.measure(steps, first="A1A2"))
    assert "grow[X=1] (line 9) x1, grow[X=2] (line 9) x1" in text


def test_python_provenance():
    sim = gcrsim.Simulator(parse_model(NAMED), retain=True)
    sim.run(3)
    st = sim.trace("B1B2")[0]
    assert st.name == "grow" and st.bindings == {"X": 1} and st.rule.bindings == {"X": 1} and st.rule_line == 9
    assert st.provenance["source_notation"] == "A{:X}->B{:X},1"
    assert st.to_dict()["rule"]["bindings"] == {"X": 1}
    plain = gcrsim.Simulator(parse_model('[axioms]\n1 = ["a"]\n[rules]\na->b\n'), retain=True)
    plain.run(1)
    step = plain.trace("b")[0]
    assert step.bindings is None and "source_notation" not in step.provenance


def test_replay_explain_shows_bindings(files, capsys):
    path = files("m.txt", NAMED)
    good = files("good.txt", "A1A2\nB1A2\nB1B2\n")
    status, out, _ = run(capsys, path, "--mode", "replay", good, "--explain")
    assert status == 0
    assert "rule grow[X=1] at line 9: A1->B1,1" in out and "rule grow[X=2] at line 9: A2->B2,1" in out
    assert "grow[X=1] (line 9) x1, grow[X=2] (line 9) x1" in out
    report = replay(parse_model(NAMED), ["A1A2", "B1A2"])
    assert report.steps[0].provenance["bindings"] == {"X": 1} and report.steps[0].rule.name == "grow"
    status, out, _ = run(capsys, path, "--mode", "replay", good, "--format", "jsonl")
    steps = [o for o in objs(out) if o["type"] == "derivation_step"]
    assert [s["rule"]["bindings"] for s in steps] == [{"X": 1}, {"X": 2}]


def test_search_shows_bindings_and_notes(files, capsys):
    path = files("m.txt", NAMED)
    status, out, err = run(capsys, path, "--mode", "search", "B1B2", "--terminals", "B1 B2")
    assert status == 0 and "rule grow[X=1] at line 9" in out and "rule grow[X=2] at line 9" in out
    m = parse_model('[symbols]\nalphabet = "A{:X} B"\nterminals = "A1"\n[symbols.ranges]\nX = "1..2"\n[rules]\nA{:X} -> B\n')
    note = gcrsim._search.pruning_obstacle(m, m.lexicon.encode("A1"))
    assert note.startswith("rule A{:X}->B[X=1] (line 7)") and "rewrites the terminal A1" in note


def test_search_with_declared_terminals_from_a_range():
    m = parse_model('[symbols]\nalphabet = "S a{:X}"\nterminals = "a{:X}"\n[symbols.ranges]\nX = "1..2"\n[axioms]\n1 = ["S"]\n[rules]\nS -> a{:X} S\nS ->\n')
    res = search(m, "a2a1", max_steps=4)
    assert res.found and [s.bindings for s in res.derivation][:2] == [{"X": 2}, {"X": 1}]


# ---------------------------------------------------------------- describe


def test_describe_text_and_dict():
    d = describe(parse_model(NAMED))
    out = d.text()
    assert "4 rules" in out and "ranges: X=1..2" in out
    assert "line 9: A{:X}->B{:X},1;name:grow (X=1..2): 2 rules" in out
    assert "    grow[X=1]  A1->B1,1" in out and "    [X=2]  B2->A2" in out
    exp = d.to_dict()["expansions"]
    assert [g["line"] for g in exp] == [9, 10]
    assert exp[0] == {"line": 9, "notation": "A{:X}->B{:X},1", "name": "grow", "ranges": {"X": [1, 2]}, "rules": [
        {"notation": "A1->B1,1", "bindings": {"X": 1}, "component": 1, "target": 1},
        {"notation": "A2->B2,1", "bindings": {"X": 2}, "component": 1, "target": 1}]}
    assert d.to_dict()["ranges"] == {"X": [1, 2]}
    assert d.to_dict()["rules"]["count"] == 4


def test_describe_without_ranges_has_no_expansion_section():
    d = describe(parse_model('[rules]\na -> b\n'))
    assert d.to_dict()["expansions"] == [] and "ranges" not in d.text()


def test_describe_jsonl(files, capsys):
    path = files("m.txt", NAMED)
    status, out, _ = run(capsys, path, "--describe", "--format", "jsonl")
    assert status == 0
    body = [o for o in objs(out) if o["type"] == "description"][0]
    assert body["ranges"] == {"X": [1, 2]}
    assert [(g["line"], [r["bindings"] for r in g["rules"]]) for g in body["expansions"]] == [
        (9, [{"X": 1}, {"X": 2}]), (10, [{"X": 1}, {"X": 2}])]


# ---------------------------------------------------------------- the examples


def lines_of(path):
    return Path(path).read_text(encoding="utf-8")


RANGES_EXPANDED = '''[symbols]
alphabet = "S a b C1 C2 C3 D00 D01 D10 D11"
terminals = "a b"
[symbols.classes]
D = "D00 D01 D10 D11"
[axioms]
1 = ["S C1", "S C2", "S C3"]
[rules]
ins(S,D00,)
ins(S,D01,)
ins(S,D10,)
ins(S,D11,)
D00->D01,1;name:x
D01->D11,1
D10->D00,1
D11->D10,1
C1->C2,1
C2->C3,1
D00D00->,1
D01D01->,1
D10D10->,1
D11D11->,1
{D}{D}->a,1
S->a b,1
'''


def test_example_ranges_equals_its_handwritten_expansion(capsys, files):
    ex = parse_model(lines_of(FEATURES / "ranges.txt"))
    hw = parse_model(RANGES_EXPANDED.replace(";name:x", ""))
    strip = lambda m: [[(r.kind, re.sub(r";name:\w+", "", r.notation), r.target) for r in comp] for comp in m.rules]
    assert strip(ex) == strip(hw)
    assert ex.lexicon.alphabet_order == hw.lexicon.alphabet_order and ex.lexicon.classes == hw.lexicon.classes
    assert [ex.lexicon.tokens(a) for a in ex.axioms[0]] == [hw.lexicon.tokens(a) for a in hw.axioms[0]]
    assert ex.config["terminals"] == hw.config["terminals"]
    names = [r.name for r in ex.rules[0]]
    assert [names.count(n) for n in ("step", "count", "cancel", "any_pair")] == [4, 2, 4, 1]
    # the same strings, step by step
    a = csv_of(capsys, lines_of(FEATURES / "ranges.txt"), files, 4)
    b = csv_of(capsys, RANGES_EXPANDED.replace(";name:x", ""), files, 4)
    assert a == b and len(a.splitlines()) > 20


def test_example_ranges_components_equals_its_handwritten_expansion(capsys, files):
    hw = ('[symbols]\nalphabet = "S c1 c2 c3 c4"\n[axioms]\n1 = ["S"]\n[rules]\n'
          '1, S -> c1 S, 2\n2, S -> c2 S, 3\n3, S -> c3 S, 4\n4, S -> c4 S, 1\n')
    ex = parse_model(lines_of(FEATURES / "ranges_components.txt"))
    h = parse_model(hw)
    assert sig(ex)[0] == sig(h)[0] and sig(ex)[1] == sig(h)[1]
    assert [[(r.kind, r.notation.replace(";name:walk", ""), r.source, r.target) for r in comp] for comp in ex.rules] == \
           [[(r.kind, r.notation, r.source, r.target) for r in comp] for comp in h.rules]
    assert csv_of(capsys, lines_of(FEATURES / "ranges_components.txt"), files, 8) == csv_of(capsys, hw, files, 8)
    last = csv_of(capsys, lines_of(FEATURES / "ranges_components.txt"), files, 8).splitlines()[-1]
    assert last.split("\t")[:2] == ["8", "1"] and last.split("\t")[2].replace(" ", "") == "c1c2c3c4c1c2c3c4S"


def test_example_descriptions_list_their_expansions(capsys):
    for name, count in (("ranges.txt", 14), ("ranges_components.txt", 4)):
        d = describe(FEATURES / name)
        assert sum(len(g["rules"]) for g in d.expansions) == count
        assert d.text().count("[") >= count


# ---------------------------------------------------------------- review fixes


RX = '[symbols.ranges]\nX = "1..2"\n[rules]\n'
BS = chr(92)


def test_section_header_check_only_looks_at_the_component_field():
    with pytest.raises(ModelError, match="section header"):
        parse_model('[symbols.ranges]\nX = "1..2"\n[rules.{:X}]\na -> b, 1\n')
    m = parse_model('[symbols.ranges]\nX = "1..2"\n[rules.1] # document {:X}\na -> b, 1\n')
    assert [r.notation for r in m.rules[0]] == ["a->b,1"]
    m = parse_model('[symbols.ranges]\nX = "1..2"\n[rules] # {:X}\na -> b, 1\n')
    assert len(m.rules[0]) == 1
    m = parse_model(RX + "[rules]{:X}->b\n")  # a rule line, not a header
    assert [r.notation for r in m.rules[0]] == ["[rules]1->b", "[rules]2->b"]


def test_regex_text_that_looks_like_a_clause_is_not_a_clause():
    m = parse_model(RX + 're(;name:p)->b{:X}\n')
    assert [r.notation for r in m.rules[0]] == ["re(;name:p)->b1", "re(;name:p)->b2"]
    assert m.rules[0][0].source_notation == "re(;name:p)->b{:X}"
    m = parse_model(RX + 're(;name:p)->a,1;permit:q{:X}\n')
    assert m.rules[0][0].source_notation == "re(;name:p)->a,1;permit:q{:X}"
    assert m.rules[0][1].permit == ("q2",)
    m = parse_model(RX + 're(;name:p)->a,1;permit:q{:X};name:n\n')
    assert m.rules[0][0].name == "n" and m.rules[0][0].source_notation == "re(;name:p)->a,1;permit:q{:X}"


def test_a_literal_private_use_character_in_the_line():
    for ch in (chr(0xFDD0), chr(0xE000)):
        m = parse_model(RX + "a" + ch + "{:X} -> b\n")
        assert [r.notation for r in m.rules[0]] == ["a" + ch + "1->b", "a" + ch + "2->b"]
        assert m.rules[0][1].source_notation == "a" + ch + "{:X}->b"


def test_regex_escape_depends_on_the_pattern_only():
    m = parse_model('[symbols.ranges]\nX = "1..1"\n[rules]\n1{:X},re(' + BS + '{:)->b,1\n')
    assert m.rules[10][0].notation == "11,re(" + BS + "{:)->b,1"
    # an odd number of backslashes is never a reference: outside a pattern the ordinary parser says what it says on any model
    with pytest.raises(ModelError, match="cannot be used in a plain rule"):
        parse_model(RX + 're(a)->b,1;permit:' + BS + '{:X}' + chr(10))
    with pytest.raises(ModelError, match="cannot be used in a plain rule"):
        parse_model('[rules]' + chr(10) + 're(a)->b,1;permit:' + BS + '{:X}' + chr(10))
    # an escaped space of the pattern is kept in the source notation, whatever the component field looks like
    m = parse_model(RX + '{:X},re(a' + BS + ' )->q{:X},1\n')
    assert m.rules[0][0].source_notation == "{:X},re(a" + BS + " )->q{:X},1"
    assert m.rules[0][0].notation == "1,re(a" + BS + " )->q1,1"
    # an even number of backslashes before {: leaves the reference
    m = parse_model(RX + 're(a' + BS * 2 + '{:X})->c\n')
    assert [r.notation for r in m.rules[0]] == ["re(a" + BS * 2 + "1)->c", "re(a" + BS * 2 + "2)->c"]
    # a reference in a character class of the pattern
    m = parse_model(RX + 're([a{:X}])->c\n')
    assert [r.notation for r in m.rules[0]] == ["re([a1])->c", "re([a2])->c"]


def test_range_in_a_name_is_still_refused_after_a_regex():
    with pytest.raises(ModelError, match="name of a rule"):
        parse_model(RX + 're(a)->b,1;name:g{:X}\n')
    with pytest.raises(ModelError, match="name of a rule"):
        parse_model(RX + 'a->b,1;permit:c; name : g{:X}\n')


def test_diagnostic_order_declarations_first():
    with pytest.raises(ModelError, match="must be written"):
        parse_model('[symbols.ranges]\nX = "broken"\n[rules]\nq{:X-9} -> r\n')
    with pytest.raises(ModelError, match="range Y is not declared"):
        parse_model('[symbols]\nalphabet = "A{:Y}"\n[symbols.ranges]\nX = "1..2"\n[rules]\nq{:X-9} -> r\n')
    with pytest.raises(ModelError, match="negative"):
        parse_model('[symbols.ranges]\nX = "1..2"\n[rules]\nq{:X-9} -> r\n')
    with pytest.raises(ModelError, match="empty"):
        parse_model('[symbols.ranges]\nX = "9..1"\n[rules]\nq{:X%0} -> r\n')


def test_long_expressions_and_huge_numbers_are_model_errors(files, capsys):
    long = "+".join(["X"] * 1100)
    with pytest.raises(ModelError, match=r":4: .*too long"):
        parse_model(RX + "q{:%s} -> r\n" % long)
    with pytest.raises(ModelError, match=r":4: .*too deeply"):
        parse_model(RX + "q{:%sX%s} -> r\n" % ("(" * 100, ")" * 100))
    with pytest.raises(ModelError, match=r":4: .*digits"):
        parse_model(RX + "q{:%s} -> r\n" % ("9" * 100))
    with pytest.raises(ModelError, match="digits"):
        parse_model('[symbols.ranges]\nX = "1..%s"\n' % ("9" * 4400))
    path = files("long.txt", RX + "q{:%s} -> r\n" % long)
    status, out, err = run(capsys, path, "1")
    assert status == 2 and "too long" in err and "Traceback" not in err
    assert len(parse_model(RX + "q{:%s} -> r\n" % "+".join(["X"] * 100)).rules[0]) == 2


def test_negative_message_names_the_rule():
    with pytest.raises(ModelError, match=r"negative.*\(rule grow\)"):
        parse_model('[symbols.ranges]\nX = "1..3"\n[rules]\nq{:X-2} -> r, 1; name: grow\n')


def test_constant_only_reference_is_an_ordinary_rule():
    m = parse_model('[model]\nmax_expanded_rules = 1\n[rules]\nq{:7} -> r\nq{:2*3} -> r\n')
    assert [r.notation for r in m.rules[0]] == ["q7->r", "q6->r"]
    assert all(r.bindings is None and r.source_notation is None for r in m.rules[0])
    assert describe(m).to_dict()["expansions"] == []


# ---------------------------------------------------------------- the line is read by the ordinary parser, with markers


def pair(ranges_text, ex_line, hw_lines):
    """The model with a line that uses a range, and the handwritten one: the same rules; returns both models."""
    ex = parse_model(ranges_text + ex_line + "\n")
    hw = parse_model("".join(hw_lines))
    assert [(r.kind, r.notation, r.name, r.target, r.permit, r.forbid) for r in ex.rules[0]] == \
           [(r.kind, r.notation, r.name, r.target, r.permit, r.forbid) for r in hw.rules[0]]
    return ex, hw


def test_pattern_with_a_comment_and_a_bracket_then_a_name():
    m = parse_model(RX + "re(a( ?# [)b)->b{:X},1;name:grow\n")
    assert [r.notation for r in m.rules[0]] == ["re(a(?#[)b)->b1,1", "re(a(?#[)b)->b2,1"]
    assert [r.name for r in m.rules[0]] == ["grow", "grow"]
    assert m.rules[0][0].source_notation == "re(a(?#[)b)->b{:X},1"
    hw = parse_model('[rules]\nre(a( ?# [)b)->b1,1;name:grow\n')
    assert hw.rules[0][0].notation == m.rules[0][0].notation


def test_a_reference_in_a_regex_comment_is_expanded_like_any_other():
    m = parse_model(RX + "re(a(?#note {:X}))->b\n")
    assert [r.notation for r in m.rules[0]] == ["re(a(?#note1))->b", "re(a(?#note2))->b"]


def test_clause_text_before_the_real_clauses():
    # the ordinary parser reads the first ;name: of a plain rule as part of the left-hand side; so does a line with a range
    ordinary = parse_model("[rules]\na;name:b1->c,1;name:real\n")
    ranged = parse_model(RX + "a;name:b{:X}->c,1;name:real\n")
    assert [r.notation for r in ranged.rules[0]] == ["a;name:b1->c,1", "a;name:b2->c,1"]
    assert ordinary.rules[0][0].notation == ranged.rules[0][0].notation and ranged.rules[0][1].name == "real"
    m = parse_model(RX + "re(a)->b,1;name:q;permit:p{:X}\n")
    assert m.rules[0][0].name == "q" and m.rules[0][0].source_notation == "re(a)->b,1;permit:p{:X}"
    assert m.rules[0][1].permit == ("p2",)
    with pytest.raises(ModelError, match="name of a rule"):
        parse_model(RX + "re(a)->b,1;name:q{:X}\n")


def test_lines_the_ordinary_parser_reads_in_an_odd_way_are_read_the_same():
    o = parse_model("[rules]\nre(a)->b;name:q\n")
    r = parse_model(RX + "re(a)->b;name:q{:X}\n")
    assert [x.notation for x in o.rules[0]] == ["re(a)->b;name:q"]  # no target: the text is part of the replacement
    assert [x.notation for x in r.rules[0]] == ["re(a)->b;name:q1", "re(a)->b;name:q2"]
    # after the pattern of a re rule white space is dropped, also inside the word name
    o = parse_model("[rules]\nre(a)->b,1;n a m e:g1\n")
    assert o.rules[0][0].name == "g1"
    r = parse_model(RX + "re(a)->b,1;n a m e:g;permit:p{:X}\n")
    assert [x.name for x in r.rules[0]] == ["g", "g"] and r.rules[0][0].permit == ("p1",)
    with pytest.raises(ModelError, match="name of a rule"):
        parse_model(RX + "re(a)->b,1;n a m e:g{:X}\n")


def test_thousands_of_references_in_one_line():
    m = parse_model('[symbols.ranges]\nX = "1..1"\n[rules]\nq' + "{:X}" * 6401 + "->r\n")
    assert m.rules[0][0].notation == "q" + "1" * 6401 + "->r"


def test_huge_component_numbers_and_repetitions_are_model_errors(files, capsys):
    with pytest.raises(ModelError, match=r":4: .*too many digits"):
        parse_model(RX + "1" * 4399 + ",a->b,1\n")
    with pytest.raises(ModelError, match=r":2: .*too many digits"):
        parse_model("[rules]\na->b," + "1" * 4399 + "\n")
    with pytest.raises(ModelError, match=r":4: "):
        parse_model(RX + "re(a{100000000000000})->b\n")
    path = files("rep.txt", RX + "re(a{100000000000000})->b{:X}\n")
    status, out, err = run(capsys, path, "1")
    assert status == 2 and "Traceback" not in err


def test_the_digit_cap_is_in_the_message():
    with pytest.raises(ModelError, match="up to 15 digits"):
        parse_model(RX + "q{:%s} -> r\n" % ("9" * 20))


# ---------------------------------------------------------------- an escaped {: is left to the ordinary parser


def test_escaped_text_is_not_masked_so_the_structure_stays_visible():
    m = parse_model(RX + "re(a(?#" + BS + "{:(X)}b)->b{:X}\n")
    assert [r.notation for r in m.rules[0]] == ["re(a(?#" + BS + "{:(X)}b)->b1", "re(a(?#" + BS + "{:(X)}b)->b2"]
    hw = parse_model("[rules]\nre(a(?#" + BS + "{:(X)}b)->b1\n")
    assert hw.rules[0][0].notation == m.rules[0][0].notation


def test_escaped_text_with_spaces_compiles_like_the_handwritten_pattern():
    ex = parse_model('[symbols.ranges]\nX = "1..1"\n[rules]\nre(a' + BS + '{: X })->b{:X}\n')
    hw = parse_model("[rules]\nre(a" + BS + "{: X })->b1\n")
    assert ex.rules[0][0].notation == hw.rules[0][0].notation
    s = "a{:X}"
    assert list(ex.rules[0][0].expand(s)) == list(hw.rules[0][0].expand(s)) == ["b1"]


def test_escaped_reference_outside_a_pattern_is_what_the_ordinary_parser_says():
    nb = chr(0xA0)
    text = "a" + BS + "{:" + nb + "X}->b\n"
    with pytest.raises(ModelError) as ordinary:
        parse_model("[rules]\n" + text)
    with pytest.raises(ModelError) as ranged:
        parse_model(RX + text)
    assert str(ordinary.value).split(": ", 2)[2] == str(ranged.value).split(": ", 2)[2]


def test_expression_white_space_is_ascii_space_and_tab():
    assert [r.notation for r in parse_model(RX + "q{: " + chr(9) + "X + 1 } -> r\n").rules[0]] == ["q2->r", "q3->r"]
    with pytest.raises(ModelError, match="unexpected character"):
        parse_model(RX + "q{:" + chr(0xA0) + "X} -> r\n")


def test_component_numbers_are_checked_after_substitution():
    m = parse_model('[symbols.ranges]\nX = "0..0"\n[rules]\na->b,1000{:X}\n')
    assert m.ncomp == 10000 and m.rules[0][0].target == 9999
    assert parse_model("[rules]\na->b,10000\n").ncomp == 10000
    with pytest.raises(ModelError, match=r":4: .*10001.*X=1"):
        parse_model('[symbols.ranges]\nX = "1..1"\n[rules]\na->b,1000{:X}\n')
    with pytest.raises(ModelError, match=r"component numbers start at 1.*X=0"):
        parse_model('[symbols.ranges]\nX = "0..0"\n[rules]\n{:X},a->b,1\n')
