"""Declarative marks: the ``marks`` setting (regex -> label, applied to accepted strings)."""

import pytest

import gcrsim
from gcrsim import ConfigError, LimitReached, Settings
from conftest import write_model, parse_old, EXAMPLES, run_py

NOFILTER = dict(reject_strings="(?!)", reject_max_len=1000, print_hide="(?!)", print_max_len=1000)
ANBN = """[axioms]
1 = ["S"]

[rules]
S->aS,2
2,S->Sb
S->
"""


def sim_of(text=ANBN, *, marks=None, filters=None, callback=None, **kw):
    settings = Settings(**NOFILTER)
    settings.marks = marks or {}
    settings.filters = filters or {}
    settings.filter_next = callback
    out = []
    sim = gcrsim.Simulator(gcrsim.parse_model(text), settings, write=out.append, **kw)
    sim.out = out
    return sim


def records(sim):
    return [(m.step, m.component, m.string, m.label) for m in sim.marks]


def test_a_mark_is_recorded_for_matching_accepted_strings():
    sim = sim_of(marks={1: {"terminal": r"\A[ab]*\Z"}})
    sim.run(5)
    assert records(sim) == [(1, 0, "", "terminal"), (3, 0, "ab", "terminal"), (5, 0, "aabb", "terminal")]
    assert "".join(sim.out) == "Mark (terminal): \nMark (terminal): ab\nMark (terminal): aabb\n"


def test_default_message_for_other_labels():
    sim = sim_of(marks={1: {"done": r"\Aab\Z"}})
    sim.run(3)
    assert "".join(sim.out) == "Mark (done): ab\n"


def test_only_strings_that_passed_every_filter_are_marked():
    # "ab" is rejected by the component condition, so it is never marked (the Perl callbacks print after rejecting)
    sim = sim_of(marks={1: {"terminal": r"\A[ab]*\Z"}}, filters={0: {"forbid": [r"\Aab\Z"]}})
    sim.run(5)
    assert [m.string for m in sim.marks] == ["", "aabb"]


def test_a_string_rejected_by_the_callback_is_not_marked():
    sim = sim_of(marks={1: {"t": r"\A[ab]*\Z"}}, callback=lambda s, c: s != "ab")
    sim.run(5)
    assert [m.string for m in sim.marks] == ["", "aabb"]


def test_marks_only_apply_to_their_component():
    sim = sim_of(marks={2: {"t": r"^a"}})
    sim.run(3)
    assert records(sim) == [(1, 1, "aS", "t"), (3, 1, "aaSb", "t")]


def test_the_key_zero_or_all_applies_to_every_component():
    for key in (0, "all"):
        sim = sim_of(marks={key: {"t": r"^a"}})
        sim.run(3)
        assert {m.component for m in sim.marks} == {0, 1}


def test_several_labels_and_several_patterns():
    marks = {1: {"even": [r"\Aaabb\Z", r"\A\Z"], "any_a": r"a"}}
    sim = sim_of(marks=marks)
    sim.run(5)
    labels = [(m.string, m.label) for m in sim.marks]
    assert ("", "even") in labels and ("aabb", "even") in labels and ("ab", "any_a") in labels
    assert ("ab", "even") not in labels


def test_one_label_is_recorded_once_per_string_even_with_several_matching_patterns():
    sim = sim_of(marks={1: {"t": [r"\Aab\Z", r"\Aa.\Z"]}})  # both patterns match "ab"
    sim.run(3)
    assert records(sim) == [(3, 0, "ab", "t")]


def test_custom_message_and_suppressed_message():
    marks = {1: {"t": {"pattern": r"\Aab\Z", "message": "found {string} in {component} at step {step} ({label})"}}}
    sim = sim_of(marks=marks)
    sim.run(3)
    assert "".join(sim.out) == "found ab in 1 at step 3 (t)\n"
    sim = sim_of(marks={1: {"t": {"pattern": r"\Aab\Z", "message": None}}})
    sim.run(3)
    assert len(sim.marks) == 1 and sim.out == []  # recorded, but silent


def test_marks_are_unique_with_history_and_repeat_without():
    text = """[axioms]
1 = ["a"]

[rules]
b->b
a->b
b->a
"""
    on = sim_of(text, marks={1: {"t": r"b"}})
    on.run(4)
    assert [m.step for m in on.marks] == [1]
    off_settings = Settings(**NOFILTER, history=False)
    off_settings.marks = {1: {"t": r"b"}}
    off = gcrsim.Simulator(gcrsim.parse_model(text), off_settings, write=lambda t: None)
    off.run(4)
    assert [m.step for m in off.marks] == [1, 2, 3, 4]  # b is rediscovered at every step


def test_marks_and_callback_marks_coexist_in_order():
    def cb(s, c, ctx):
        if s == "ab":
            ctx.mark("from-callback")
        return True

    sim = sim_of(marks={1: {"declared": r"\Aab\Z"}}, callback=cb)
    sim.run(3)
    assert [m.label for m in sim.marks] == ["from-callback", "declared"]  # the callback runs first


def test_marks_are_traceable():
    sim = sim_of(marks={1: {"terminal": r"\Aaabb\Z"}}, retain=True)
    sim.run(5)
    (m,) = sim.marks
    chain = sim.trace(m.string, m.component, m.step)
    assert [d.result for d in chain] == ["aS", "aSb", "aaSb", "aaSbb", "aabb"]


def test_max_marks_applies_to_declarative_marks():
    sim = sim_of(marks={0: {"t": r"."}}, max_marks=1)
    with pytest.raises(LimitReached) as exc:
        sim.run(3)
    assert exc.value.limit == "max-marks"


def test_streaming_mark_records_and_messages_equal_baseline():
    text = """[axioms]
1 = ["S"]

[rules]
S->A,2
S->B
"""
    results = []
    for streaming in (False, True):
        sim = sim_of(text, marks={0: {"t": r"."}}, streaming=streaming)
        sim.step()
        results.append((records(sim), "".join(sim.out)))
    assert results[0] == results[1]
    assert results[0][0] == [(1, 0, "B", "t"), (1, 1, "A", "t")]


def test_marks_make_the_filter_function_header_say_yes():
    assert sim_of(marks={1: {"t": r"a"}}).has_filter
    assert not sim_of().has_filter


# -- validation ----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "marks",
    [
        {9: {"t": "a"}},  # no such component
        {"x": {"t": "a"}},  # bad key
        {1: {}},  # no labels
        {1: ["a"]},  # not a dict
        {1: {"": "a"}},  # empty label
        {1: {"t": "("}},  # bad regex
        {1: {"t": 5}},  # not a pattern
        {1: {"t": []}},  # no pattern
        {1: {"t": {"message": "x"}}},  # no pattern key
        {1: {"t": {"pattern": "a", "color": "red"}}},  # unknown key
        {1: {"t": {"pattern": "a", "message": "{nope}"}}},  # unknown field
        {1: {"t": {"pattern": "a", "message": "{"}}},  # malformed template
        {1: {"t": {"pattern": "a", "message": 3}}},  # not a string
    ],
)
def test_invalid_marks_are_config_errors(marks):
    with pytest.raises(ConfigError):
        sim_of(marks=marks)


# -- configuration file and command line ------------------------------------------------------------------------------------


def test_components_setting_must_be_a_dict(tmp_path):
    (tmp_path / "c.py").write_text("components = ['x']\n")
    with pytest.raises(ConfigError, match="components must be a table"):
        gcrsim.load_config(str(tmp_path / "c.py"))


def test_cli_marks_without_any_callback(tmp_path):
    write_model(tmp_path / "m.txt", ANBN)
    (tmp_path / "c.py").write_text("components = {1: {'marks': {'terminal': r'\\A[ab]*\\Z'}}}\n")
    r = run_py(["m.txt", "5", "--python-filter", "c.py", "--trace-marks"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "Filter function used: yes" in r.stdout
    assert "Mark (terminal): aabb" in r.stdout
    assert "Mark [terminal] at step 5, component 1: aabb" in r.stdout
    assert "step 5: aaSbb => aabb" in r.stdout
    assert "Marks (3, 3 distinct):" in r.stdout
    plain = run_py(["m.txt", "5", "--python-filter", "c.py"], tmp_path).stdout
    assert "Mark [terminal]" not in plain and "Mark (terminal): aabb" in plain


def test_cli_stop_on_mark_and_streaming_with_declarative_marks(tmp_path):
    write_model(tmp_path / "m.txt", ANBN)
    (tmp_path / "c.py").write_text("components = {1: {'marks': {'terminal': r'\\Aab\\Z'}}}\n")
    r = run_py(["m.txt", "20", "--python-filter", "c.py", "--stop-on-mark"], tmp_path)
    assert "STEP 3" in r.stdout and "STEP 4" not in r.stdout
    a = run_py(["m.txt", "6", "--python-filter", "c.py", "--trace-marks"], tmp_path)
    b = run_py(["m.txt", "6", "--python-filter", "c.py", "--trace-marks", "--streaming"], tmp_path)
    assert a.returncode == b.returncode == 0, b.stderr
    assert a.stdout == b.stdout


def test_the_all_example_configs_load():
    for model in ("ins_a_110200", "ins_b_110200", "ins_c_211110", "ins_222"):
        st = gcrsim.load_config(str(EXAMPLES / (model + "_declarative.py")))
        gcrsim.Simulator(gcrsim.parse_model("""[axioms]
1 = ["a"]
2 = []
3 = []
4 = []
5 = []

[rules]
a->b
"""), st, write=lambda t: None)
