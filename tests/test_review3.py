r"""Regression tests for the third Codex review (rule forms, settings layers, verify, converter)."""
import tracemalloc

import pytest

import gcrsim
from gcrsim import ConfigError, LimitReached, ModelError, Settings, parse_model
from gcrsim.settings import apply_settings
from gcrsim.verify import Verifier
from conftest import run_py

NOFILTER = dict(reject_strings="", reject_max_len=2000, print_hide="", print_max_len=2000, history=False)


def test_an_escaped_code_point_cannot_collide_with_a_lexeme_code():
    bs = chr(92)
    text = '[symbols]\nalphabet = ["a", "K1"]\n\n[axioms]\n1 = ["a"]\n\n[rules]\nre(a)->\\ue000\n'
    with pytest.raises(ModelError, match="reserved for a lexeme"):
        parse_model(text)
    ok = parse_model('[symbols]\nlexemes = ["K1"]\n\n[axioms]\n1 = ["a"]\n\n[rules]\nre(a)->\\ue001\n')  # an unused private-use character
    assert ok.rules[0][0].expand("a") == [chr(0xE001)]


@pytest.mark.parametrize("streaming, detailed", [(False, False), (False, True), (True, False)])   # streaming and detailed tracing do not combine
def test_regex_candidate_limit_does_not_build_the_replacements(streaming, detailed):
    model = parse_model('[axioms]\n1 = ["%s"]\n\n[rules]\nre((a+))->\x01\x01\n' % ("a" * 1000))
    settings = Settings(**NOFILTER, show_detailed_application=detailed)
    sim = gcrsim.Simulator(model, settings, write=lambda t: None, max_step_candidates=1, streaming=streaming)
    tracemalloc.start()
    try:
        with pytest.raises(LimitReached):
            sim.step()
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < 300_000, peak  # building the 1000 replacements would take about 1 MB


def test_equivalent_global_keys_override_across_layers():
    st = Settings()
    apply_settings(st, {"components": {"all": {"filters": {"forbid": ["b"]}, "marks": {"t": "a"}}}}, "model", from_model=True)
    apply_settings(st, {"components": {"0": {"filters": {"forbid": ["a"]}}, 0: {"marks": {"u": "b"}}}}, "conf")
    assert st.filters == {0: {"forbid": ["a"]}}
    assert st.marks == {0: {"u": "b"}}


def test_a_regex_comment_may_contain_an_escaped_parenthesis():
    m = parse_model('[axioms]\n1 = ["a"]\n\n[rules]\nre((?#\\))a)->X\n')
    assert m.rules[0][0].expand("a") == ["X"]


def test_verify_refuses_no_mark_rejected(tmp_path):
    (tmp_path / "m.txt").write_bytes(b'[axioms]\n1 = ["a"]\n[rules]\na->bb\n')
    r = run_py(["m.txt", "2", "--cross-check", "--no-mark-rejected"], tmp_path)
    assert r.returncode == 2 and "no-mark-rejected" in r.stderr


def test_no_length_limit_with_none():
    sim = gcrsim.Simulator(parse_model("""[axioms]
1 = ["a"]

[rules]
a->aaaaaaaaaaaaaaaaaaaaaaaa
"""), Settings(reject_max_len=None, print_max_len=100), write=lambda t: None)
    sim.step()
    assert len(sim.cur[0][0]) == 24


def test_a_failed_step_makes_the_simulator_refuse_to_continue():
    import gcrsim
    model = parse_model("""[axioms]
1 = ["aaaa"]

[rules]
1,a->b,1
""")
    sim = gcrsim.Simulator(model, Settings(), write=lambda t: None, max_step_candidates=2)
    with pytest.raises(gcrsim.LimitReached):
        sim.step()
    with pytest.raises(gcrsim.GcrsimError, match="cannot continue"):
        sim.step()
    assert sim.step_no == 0


def test_an_escaped_space_in_a_regex_is_not_stripped():
    bs = chr(92)
    model = parse_model('[axioms]\n1 = ["ab"]\n\n[rules]\n1,re(a\\ b)->X,1\n')
    assert model.rules[0][0].pattern.pattern == "a" + bs + " b"
    model = parse_model("""[axioms]
1 = ["ab"]

[rules]
re( a  b )->X
""")
    assert model.rules[0][0].pattern.pattern == "ab"


def test_dollar_as_anchor_is_an_error_when_the_model_has_no_dollar():
    with pytest.raises(ModelError, match="end anchor"):
        parse_model("""[axioms]
1 = ["ab"]

[rules]
re(b$)->X
""")
    # a model that really uses the symbol keeps it literal
    assert parse_model("""[axioms]
1 = ["a$"]

[rules]
re(a$)->X
""").rules[0][0].expand("a$") == ["X"]
    sim_model = parse_model("""[axioms]
1 = ["ab"]

[rules]
1,a->b,1
""")
    with pytest.raises(gcrsim.GcrsimError, match="end anchor"):
        gcrsim.Simulator(sim_model, Settings(marks={0: {"t": "^[ab]+$"}}), write=lambda t: None)


def test_empty_target_and_absurd_component_numbers_are_errors():
    with pytest.raises(ModelError, match="target component number"):
        parse_model("""[axioms]
1 = ["a"]

[rules]
a->b,
""")
    with pytest.raises(ModelError, match="target component number"):
        parse_model("""[axioms]
1 = ["a"]

[rules]
a->b,;permit:a
""")
    for text in ("""[axioms]
99999999 = ["a"]
""", """[axioms]
1 = ["a"]

[rules.99999999]
a->b,1
""", """[axioms]
1 = ["a"]

[rules]
a->b,99999999
""",
                 """[axioms]
1 = ["a"]

[rules]
99999999,a->b,1
"""):
        with pytest.raises(ModelError, match="larger than the limit|from 1 to|at most 10000"):
            parse_model(text)


def test_api_returns_real_symbol_names():
    model = parse_model("""[symbols]
lexemes = ["p1"]

[axioms]
1 = ["p1"]

[rules]
1,p1->p1p1,1
""")
    sim = gcrsim.Simulator(model, Settings(marks={0: {"x": "p1p1"}}), write=lambda t: None)
    sim.step()
    assert sim.strings() == [["p1p1"]]
    assert sim.marks[0].string == "p1p1"


def test_settings_are_typed():
    from gcrsim.settings import apply_settings
    for bad in ({"history": "false"}, {"print_hide": ["a"]}, {"print_max_len": True}, {"print_max_len": 1.5}, {"print_max_len": -1}):
        with pytest.raises(ConfigError):
            apply_settings(Settings(), bad, "test")


def test_load_config_can_include_the_model_layer(tmp_path):
    model = parse_model("""[model]
history = false

[run]
print_max_len = 5

[axioms]
1 = ["a"]

[rules]
1,a->b,1
""")
    (tmp_path / "c.toml").write_text("[run]\nprint_max_len = 9\n")
    st = gcrsim.load_config(str(tmp_path / "c.toml"), model=model)
    assert st.print_max_len == 9 and st.history is False
    assert gcrsim.load_config(str(tmp_path / "c.toml")).history is True


def test_permit_any_needs_one_word():
    m = parse_model("""[axioms]
1 = ["ab"]

[rules]
a->X,1;permit-any:b,z
b->Y,1;permit-any:c,z
""")
    assert list(m.rules[0][0].expand("ab")) == ["Xb"] and list(m.rules[0][1].expand("ab")) == []
    with pytest.raises(ModelError, match="empty word"):
        parse_model("""[axioms]
1 = ["ab"]

[rules]
a->X,1;permit-any:
""")


def test_guard_example_of_the_documentation_blocks_a_forbidden_word():
    m = parse_model("""[axioms]
1 = ["ABC", "ABCF"]

[rules]
# applies only if B and C both occur and none of D, E, F does
1,A->aD,1;permit:B,C;forbid:D,E,F
""")
    rule = m.rules[0][0]
    assert list(rule.expand("ABC")) == ["aDBC"] and list(rule.expand("ABCF")) == []
