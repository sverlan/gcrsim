"""Section headers: the fixed words of the format are case-insensitive, names chosen by the user keep their case."""
import pytest

from gcrsim import parse_model
from gcrsim.sections import header_words


def test_header_words_lower_the_fixed_words_only():
    assert header_words("symbols", ["CLASSES", "V"]) == ["classes", "V"]
    assert header_words("model", ["Components", "ALL", "Marks", "MyLabel"]) == ["components", "all", "marks", "MyLabel"]
    assert header_words("model", ["FILTERS"]) == ["filters"]
    assert header_words("model", ["components", "1", "FILTERS", "FORBID"]) == ["components", "1", "filters", "forbid"]
    assert header_words("symbols", ["Ranges"]) == ["ranges"]


MODEL = """
[SYMBOLS]
alphabet = "a b c"
[Symbols.Classes]
V = "a b"
v = "c"
[symbols.ranges]
Kk = "1..2"
[MODEL.FILTERS]
forbid = ['cc']
[Model.Components.ALL.Marks]
any = 'a'
[model.components.1.marks.MyLabel]
pattern = 'b'
[AXIOMS]
1 = ["ab"]
[RULES]
{V} -> c
[RULES.2]
c -> a, 1
"""


def test_headers_in_any_case_parse():
    model = parse_model(MODEL)
    assert model.ncomp == 2 and len(model.rules[0]) == 1 and len(model.rules[1]) == 1


def test_user_names_keep_their_case():
    from gcrsim.settings import resolve_config
    model = parse_model(MODEL)
    assert set(model.ranges) == {"Kk"}
    marks = resolve_config(model, []).marks
    assert marks[0] == {"any": "a"} and list(marks[1]) == ["MyLabel"]


def test_classes_V_and_v_are_distinct():
    text = """[symbols]
alphabet = "a b c"
[SYMBOLS.CLASSES]
V = "a"
v = "b c"
[axioms]
1 = ["a"]
[rules]
{v} -> a
{V} -> b
"""
    model = parse_model(text)
    assert [r.describe() for r in model.rules[0]] == ["rule at line 9: {v}->a", "rule at line 10: {V}->b"]


def test_a_unknown_fixed_word_is_still_an_error():
    from gcrsim import ModelError
    with pytest.raises(ModelError, match="Klasses|unknown"):
        parse_model('[symbols]\nalphabet = "a"\n[Symbols.Klasses]\nV = "a"\n[axioms]\n1 = ["a"]\n')


QUOTED = """[axioms]
1 = ["a"]
[rules]
a -> b
[MODEL.COMPONENTS.1.MARKS."My.Label"]
pattern = 'b'
"""


def test_a_quoted_label_with_a_dot_keeps_its_spelling_after_the_rules():
    from gcrsim.settings import resolve_config
    marks = resolve_config(parse_model(QUOTED), []).marks
    assert list(marks[1]) == ["My.Label"] and marks[1]["My.Label"]["pattern"] == "b"


def test_max_count_class_subtable_in_any_case_filters_in_a_run(tmp_path):
    import subprocess
    import sys
    text = """[symbols]
alphabet = "a b"
[symbols.classes]
N = "a"
[MODEL.COMPONENTS.ALL.FILTERS.MAX_COUNT.CLASS]
N = 2
[axioms]
1 = ["a"]
[rules]
a -> a a
"""
    model = tmp_path / "m.txt"
    model.write_text(text, encoding="utf-8")
    out = subprocess.run([sys.executable, "-m", "gcrsim", str(model), "3", "--quiet", "--run-empty", "--format", "jsonl"],
                         capture_output=True, text=True, timeout=60).stdout
    steps = [line for line in out.splitlines() if line.startswith('{"type": "step"')]
    assert '"components_string": [["aa"]]' in steps[1] and '"components_string": [[]]' in steps[2]
