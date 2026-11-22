"""Model parser: sections, axiom lines, rule forms, comments, Config."""

import pytest

import gcrsim
from gcrsim import ModelError, parse_model
from gcrsim.model import find_re_end


def rules_of(model):
    allr = sorted((r for comp in model.rules for r in comp), key=lambda r: r.index)
    return [(r.source, r.target, r.lhs, r.rhs) for r in allr]


def expand(model_text, axiom):
    m = parse_model(model_text)
    return m.rules[0][0].expand(axiom)


def test_basic_model():
    m = parse_model("""[axioms]
1 = ["S"]

[rules]
1,S->aS,2
2,S->Sb,1
1,S->,1
""")
    assert m.axioms == [["S"], []]
    assert m.ncomp == 2
    assert rules_of(m) == [(0, 1, "S", "aS"), (1, 0, "S", "Sb"), (0, 0, "S", "")]


def test_whitespace_is_ignored_in_axiom_and_rule_lines():
    m = parse_model("""[axioms]
1 = ["a", "b"]

[rules]
 1 , a b -> c d , 1
""")
    assert m.axioms == [["a", "b"]]
    assert rules_of(m) == [(0, 0, "ab", "cd")]


def test_default_component_numbers_in_a_general_section():
    m = parse_model("""[axioms]
1 = ["a"]

[rules]
S->x
2,S->y
S->z,2
""")
    assert rules_of(m) == [(0, 0, "S", "x"), (1, 0, "S", "y"), (0, 1, "S", "z")]


def test_keywords_are_case_insensitive_whole_lines():
    m = parse_model('[AXIOMS]\n1 = ["a"]\n[rules]\na->b\n')
    assert m.axioms == [["a"]] and rules_of(m) == [(0, 0, "a", "b")]
    m = parse_model('[Axioms]\n1 = ["a"]\n[ RULES ]\na->b\n[Rules.1]\nb->c,1\n')
    assert len(m.rules[0]) == 2


# -- comments -----------------------------------------------------------------------------------


def test_a_comment_is_a_line_starting_with_hash():
    m = parse_model("""# a comment

[axioms]
1 = ["a"]

  # indented comment line

[rules]
#1,x->y
1,a->b,1
""")
    assert m.axioms == [["a"]] and rules_of(m) == [(0, 0, "a", "b")]


def test_hash_elsewhere_is_a_symbol():
    m = parse_model("""[axioms]
1 = ["a#"]

[rules]
1,a->b#c,1
 a#->#
""")
    assert m.axioms == [["a#"]]
    assert rules_of(m) == [(0, 0, "a", "b#c"), (0, 0, "a#", "#")]


def test_a_rule_that_starts_with_hash_needs_a_prefix():
    m = parse_model("""[axioms]
1 = ["#a"]

[rules]
#a->x
1,#a->y
,#a->z
""")
    assert rules_of(m) == [(0, 0, "#a", "y"), (0, 0, "#a", "z")]  # the first line is a comment


def test_slashes_are_ordinary_symbols():
    m = parse_model("""[axioms]
1 = ["a//b"]

[rules]
// -> /
re(a//b)->X
""")
    assert m.axioms == [["a//b"]]
    assert rules_of(m)[0] == (0, 0, "//", "/")


# -- axioms -------------------------------------------------------------------------------------


@pytest.mark.parametrize("value", ['"a"', "[1]", '["a", 2]', "{ a = 1 }"])
def test_axioms_must_be_a_list_of_strings(value):
    with pytest.raises(ModelError, match="list of strings"):
        parse_model("[axioms]\n1 = %s\n[rules]\na->b\n" % value)


def test_missing_component_numbers_are_empty_components():
    m = parse_model("""[axioms]
1 = ["a"]
3 = ["c"]

[rules]
1,a->b,4
""")
    assert m.axioms == [["a"], [], ["c"], []]
    assert m.ncomp == 4


def test_repeated_or_zero_component_number_is_an_error():
    with pytest.raises(ModelError, match="Cannot overwrite|duplicate|already"):
        parse_model('[axioms]\n1 = ["a"]\n1 = ["b"]\n[rules]\na->b\n')
    with pytest.raises(ModelError, match="from 1 to"):
        parse_model('[axioms]\n0 = ["a"]\n[rules]\na->b\n')


def test_at_least_one_component():
    assert parse_model("""[rules]
""").ncomp == 1


# -- rule lines -----------------------------------------------------------------------------------


def test_numbered_rules_section_requires_the_target():
    m = parse_model("""[axioms]
1 = ["a"]

[rules.2]
b->c,1
[rules]
x->y
""")
    assert rules_of(m) == [(1, 0, "b", "c"), (0, 0, "x", "y")]
    with pytest.raises(ModelError, match="needs its target"):
        parse_model("""[axioms]
1 = ["a"]

[rules.2]
b->c
""")


def test_numbered_section_prefix_must_equal_the_section():
    m = parse_model("""[axioms]
1 = ["a"]

[rules.2]
2,b->c,1
,#d->e,1
""")
    assert [(r[0], r[2]) for r in rules_of(m)] == [(1, "b"), (1, "#d")]
    with pytest.raises(ModelError, match="starts with component 3"):
        parse_model("""[axioms]
1 = ["a"]

[rules.2]
3,b->c,1
""")


def test_sections_may_come_in_any_order():
    m = parse_model("""[axioms]
1 = ["a"]

[rules]
a->b
""")
    assert m.axioms == [["a"]] and rules_of(m) == [(0, 0, "a", "b")]


def test_trailing_text_after_the_target_is_an_error():
    with pytest.raises(ModelError, match="unexpected text"):
        parse_model("""[axioms]
1 = ["a"]

[rules]
1,a->b,2,3
""")
    with pytest.raises(ModelError, match="unexpected text"):
        parse_model("""[axioms]
1 = ["a"]

[rules]
1,a->b,2junk
""")


def test_malformed_rule_reports_file_and_line():
    with pytest.raises(ModelError) as exc:
        parse_model('[axioms]\n1 = ["a"]\n\n[rules]\nnot a rule\n', path="m.txt")
    assert "m.txt:5" in str(exc.value)


def test_component_zero_rejected():
    with pytest.raises(ModelError):
        parse_model("""[axioms]
1 = ["a"]

[rules]
0,a->b
""", path="m.txt")


def test_rule_records_line_number_and_text():
    m = parse_model('[axioms]\n1 = ["a"]\n\n\n[rules]\n\n1,a->b,1\n')
    r = m.rules[0][0]
    assert r.line == 7 and r.notation == "1,a->b,1"


def test_crlf_and_missing_final_newline():
    m = parse_model('[axioms]\r\n1 = ["a"]\r\n[rules]\r\n1,a->b,1')
    assert rules_of(m) == [(0, 0, "a", "b")]


def test_a_line_before_any_section_is_an_error():
    with pytest.raises(ModelError, match="unknown section"):
        parse_model('alphabet = "a"\n[axioms]\n1 = ["a"]\n[rules]\na->b\n')
    with pytest.raises(ModelError):
        parse_model('1: a\n[rules]\na->b\n')


def test_a_config_section_is_refused_with_a_hint():
    with pytest.raises(ModelError, match=r"no \[config\] section"):
        parse_model('[config]\nsteps = 3\n[axioms]\n1 = ["a"]\n[rules]\na->b\n')


# -- the rule forms ---------------------------------------------------------------------------------


def model_with(rule, axiom="ab"):
    return """[axioms]
1 = ["%s"]

[rules]
%s
""" % (axiom, rule)


def test_plain_rules_are_literal():
    assert expand(model_with("a.->X", "a.b"), "a.b") == ["Xb"]
    assert expand(model_with("a+*->X", "a+*"), "a+*") == ["X"]
    assert expand(model_with("$->X", "a$"), "a$") == ["aX"]
    assert expand(model_with("\\->X", "a\\b"), "a\\b") == ["aXb"]
    assert expand(model_with("a->$@\"%'#x", "ab"), "ab") == ["$@\"%'#xb"]


def test_ins_del_sub_forms():
    assert expand(model_with("ins(a,X,b)"), "ab") == ["aXb"]
    assert expand(model_with("ins(,X,)"), "ab") == ["Xab", "aXb", "abX"]
    assert expand(model_with("del(a,b,)"), "ab") == ["a"]
    assert expand(model_with("sub(a,b,X,)"), "ab") == ["aX"]
    assert expand(model_with("sub(,a,X,b)"), "ab") == ["Xb"]


def test_forms_take_the_target_and_clauses():
    m = parse_model("""[axioms]
1 = ["ab"]

[rules]
ins(a,X,b),2;permit:a;forbid:z
""")
    r = m.rules[0][0]
    assert r.target == 1 and r.permit == ("a",) and r.forbid == ("z",)
    assert m.ncomp == 2


def test_operand_counts_are_checked():
    for bad in ("ins(a,b)", "ins(a,b,c,d)", "sub(a,b,c)", "del(a)"):
        with pytest.raises(ModelError, match="comma-separated operands"):
            parse_model(model_with(bad))
    with pytest.raises(ModelError, match="missing"):
        parse_model(model_with("ins(a,b,c"))


def test_send_passes_the_string_unchanged():
    m = parse_model("""[axioms]
1 = ["ab"]

[rules]
send(),2
send(),1;forbid:b
""")
    assert [list(r.expand("ab")) for r in m.rules[0]] == [["ab"], []]
    assert m.rules[0][0].target == 1


def test_regex_rules_use_re():
    assert expand(model_with("re(a.)->X"), "ab") == ["X"]
    assert expand(model_with("re((a)(b))->\\2\\1"), "ab") == ["ba"]
    assert expand(model_with("re([a-b])->X"), "ab") == ["Xb", "aX"]
    assert expand(model_with("re(a{1,2})->X"), "aab") == ["Xb", "aXb"]
    assert expand(model_with("re(\\Aa)->X"), "ab") == ["Xb"]


def test_re_rhs_escapes():
    assert expand(model_with("re(a)->x\\\\y"), "ab") == ["x\\yb"]
    assert expand(model_with("re(a)->\\x2c\\u0041"), "ab") == [",Ab"]
    assert expand(model_with("re((a))->\\g<1>0"), "ab") == ["a0b"]
    assert expand(model_with("re((?P<n>a))->\\g<n>\\g<n>"), "ab") == ["aab"]
    for bad in ("x\\", "\\q", "\\2", "\\g<3>", "\\g<zz>", "\\g", "\\x2", "\\u00"):
        with pytest.raises(ModelError):
            parse_model(model_with("re((a))->%s" % bad))


def test_syntax_characters_are_not_allowed_in_plain_operands():
    for bad in ("a{->b", "a}->b", "a(->b", "a)->b", "a->b{", "a->b(", "a->b)", "ins(a,x{,b)"):
        with pytest.raises(ModelError):
            parse_model(model_with(bad))
    with pytest.raises(ModelError, match="re\\(\\.\\.\\.\\)"):
        parse_model(model_with("a(b)->x"))


def test_re_form_errors():
    with pytest.raises(ModelError, match="missing"):
        parse_model(model_with("re(a->x"))
    with pytest.raises(ModelError, match="followed by"):
        parse_model(model_with("re(a)x"))


def test_closing_parenthesis_of_re_skips_groups_classes_and_comments():
    assert find_re_end("re((?:a->b))->X", 3) == 11
    assert find_re_end("re([)]a)->X", 3) == 7
    assert find_re_end("re((?#x)a)->X", 3) == 9
    assert find_re_end("re(a", 3) == -1


def test_classes_and_boundaries_in_plain_forms():
    cfg = """[symbols.classes]
V = "a b"

[axioms]
1 = ["abc"]

[rules]
"""
    assert sorted(parse_model(cfg + "{V}->X\n").rules[0][0].expand("abc")) == ["Xbc", "aXc"]
    assert parse_model(cfg + "ins({start},X,)\n").rules[0][0].expand("abc") == ["Xabc"]
    assert parse_model(cfg + "ins(,X,{end})\n").rules[0][0].expand("abc") == ["abcX"]
    assert parse_model(cfg + "{start}a->X\n").rules[0][0].expand("abc") == ["Xbc"]
    assert parse_model(cfg + "sub(a,{any},X,)\n").rules[0][0].expand("abc") == ["aXc"]
    assert parse_model(cfg + "del(,{V},c)\n").rules[0][0].expand("abc") == ["ac"]
    with pytest.raises(ModelError, match="unknown symbol class"):
        parse_model(cfg + "{W}->X\n")
    with pytest.raises(ModelError, match="class reference"):
        parse_model(cfg + "{->X\n")
    with pytest.raises(ModelError):
        parse_model(cfg + "a->{V}\n")  # classes only match, they cannot be produced


def test_reserved_class_names():
    with pytest.raises(ModelError, match="reserved"):
        parse_model("""[symbols.classes]
start = "a"

[axioms]
1 = ["a"]

[rules]
a->b
""")


# -- Config -------------------------------------------------------------------------------------


def test_settings_sections_are_parsed_as_toml():
    text = (
        "[model]\nreject_max_len = 5\n[model.components.0.filters]\nforbid = ['aa']\n"
        '[axioms]\n1 = ["a"]\n[rules]\na->b\n'
    )
    m = parse_model(text)
    assert m.config == {"reject_max_len": 5, "components": {"0": {"filters": {"forbid": ["aa"]}}}}


def test_sections_may_follow_the_rules_and_keep_toml_comments():
    m = parse_model('[rules]\na->b\n\n[axioms]\n1 = ["a"]\n\n[run]\n# a TOML comment\nsteps = 1 # trailing\n')
    assert m.config == {"steps": 1} and rules_of(m) == [(0, 0, "a", "b")]


def test_section_errors():
    base = '[axioms]\n1 = ["a"]\n[rules]\na->b\n'
    with pytest.raises(ModelError, match="at line"):
        parse_model("[model]\nhistory = \n" + base)
    with pytest.raises(ModelError, match="multi-line"):
        parse_model("[model]\nreject_strings = " + chr(39) * 3 + "a\nb" + chr(39) * 3 + "\n" + base)
    with pytest.raises(ModelError, match="Cannot|twice|duplicate"):
        parse_model("[model]\nhistory = true\n[model]\nhistory = false\n" + base)
    with pytest.raises(ModelError, match="unknown setting 'bogus' in .run."):
        parse_model("[run]\nbogus = 1\n" + base)
    with pytest.raises(ModelError, match="'steps' belongs in .run., not in .model."):
        parse_model("[model]\nsteps = 1\n" + base)
    with pytest.raises(ModelError, match="unknown section .other."):
        parse_model("[other]\nx = 1\n" + base)
    with pytest.raises(ModelError, match="exclusive"):
        parse_model('[symbols]\nalphabet = "a"\nlexemes = "p1"\n' + base)
    with pytest.raises(ModelError, match="rules.N"):
        parse_model("[axioms]\n[rules.x]\na->b\n")
    with pytest.raises(ModelError, match="start at 1"):
        parse_model("[axioms]\n[rules.0]\na->b,1\n")


def test_a_rules_block_ends_at_the_next_header():
    m = parse_model('[rules]\na->b\n[run]\nsteps = 2\n[axioms]\n1 = ["a"]\n')
    assert rules_of(m) == [(0, 0, "a", "b")] and m.config == {"steps": 2}


def test_bom_at_the_start_of_the_text_is_ignored():
    m = parse_model(chr(0xFEFF) + '[axioms]\n1 = ["a"]\n[rules]\na->b\n')
    assert m.axioms == [["a"]]


