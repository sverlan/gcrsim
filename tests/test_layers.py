"""Settings layers: defaults < the model's own sections < the --config files."""
import pytest

import gcrsim
from gcrsim import ConfigError, ModelError, Settings, parse_model, resolve_config
from conftest import run_py

MODEL = '[model]\nreject_max_len = 5\n\n[run]\nprint_max_len = 7\n\n[model.components.1.filters]\nforbid = [\'bb\']\n[model.components.2.filters]\nforbid = [\'aa\']\n[model.components.1.marks]\nterminal = \'\\Aa+\\Z\'\n\n[axioms]\n1 = ["a"]\n\n[rules]\na->ab,2\na->aa\n'


def test_model_config_is_applied_without_a_conf_file(tmp_path):
    (tmp_path / "m.txt").write_bytes(MODEL.encode("utf-8"))
    model = gcrsim.parse_model_file(str(tmp_path / "m.txt"))
    st = resolve_config(model, cwd=str(tmp_path))
    assert st.reject_max_len == 5 and st.print_max_len == 7
    assert set(st.filters) == {1, 2} and set(st.marks) == {1}
    r = run_py(["m.txt", "2", "--quiet"], tmp_path)
    assert r.returncode == 0, r.stderr


def test_conf_file_overrides_and_merges_by_component(tmp_path):
    (tmp_path / "m.txt").write_bytes(MODEL.encode("utf-8"))
    (tmp_path / "over.toml").write_text("[model]\nreject_max_len = 9\n[model.components.2.filters]\nforbid = ['ab']\n")
    model = gcrsim.parse_model_file(str(tmp_path / "m.txt"))
    st = resolve_config(model, "over.toml", cwd=str(tmp_path))
    assert st.reject_max_len == 9 and st.print_max_len == 7  # a key the file does not set keeps the model's value
    assert st.filters[1] == {"forbid": ["bb"]}  # component 1 untouched
    assert st.filters[2] == {"forbid": ["ab"]}  # component 2 replaced
    assert st.config_name == "model + over.toml"


def test_a_file_next_to_the_model_is_not_found_by_name(tmp_path):
    (tmp_path / "m.txt").write_bytes(MODEL.encode("utf-8"))
    (tmp_path / "m_conf.toml").write_text("[model]\nreject_max_len = 9\n")
    (tmp_path / "gcrsim_config.toml").write_text("[model]\nreject_max_len = 9\n")
    model = gcrsim.parse_model_file(str(tmp_path / "m.txt"))
    st = resolve_config(model, cwd=str(tmp_path))
    assert st.reject_max_len == 5 and st.config_name == "model"


def test_config_options_layer_in_order(tmp_path):
    (tmp_path / "m.txt").write_bytes(MODEL.encode("utf-8"))
    (tmp_path / "one.toml").write_text("[run]\nprint_max_len = 3\n[model]\nreject_max_len = 8\n")
    (tmp_path / "two.toml").write_text("[run]\nprint_max_len = 4\n")
    model = gcrsim.parse_model_file(str(tmp_path / "m.txt"))
    st = resolve_config(model, ["one.toml", "two.toml"], cwd=str(tmp_path))
    assert st.print_max_len == 4 and st.reject_max_len == 8  # the later file wins, the earlier one still counts
    r = run_py(["m.txt", "1", "--config", "one.toml", "--config", "two.toml"], tmp_path)
    assert r.returncode == 0 and "Configuration: model + one.toml + two.toml" in r.stdout


def test_explicit_config_option_layers_the_same_way(tmp_path):
    (tmp_path / "m.txt").write_bytes(MODEL.encode("utf-8"))
    (tmp_path / "other.toml").write_text("[run]\nprint_max_len = 3\n")
    model = gcrsim.parse_model_file(str(tmp_path / "m.txt"))
    st = resolve_config(model, "other.toml", cwd=str(tmp_path))
    assert st.print_max_len == 3 and st.reject_max_len == 5


def test_the_api_uses_the_model_config_by_default():
    model = parse_model(MODEL)
    sim = gcrsim.Simulator(model, write=lambda t: None)
    assert sim.settings.reject_max_len == 5


def test_lexicon_keys_are_refused_outside_the_model(tmp_path):
    (tmp_path / "m.txt").write_bytes(b'[axioms]\n1 = ["a"]\n[rules]\na->b\n')
    (tmp_path / "c.toml").write_text('[symbols]\nlexemes = ["ab"]\n')
    r = run_py(["m.txt", "1", "--config", "c.toml"], tmp_path)
    assert r.returncode == 2 and "belongs to the model" in r.stderr


def test_a_model_cannot_bring_a_filter_function():
    with pytest.raises(ModelError, match="unknown setting 'filter_next'"):
        parse_model('[model]\nfilter_next = "x"\n[axioms]\n1 = ["a"]\n[rules]\na->b\n')


def test_unknown_settings_are_reported_not_ignored(tmp_path):
    (tmp_path / "m.txt").write_bytes(b'[axioms]\n1 = ["a"]\n[rules]\na->b\n')
    (tmp_path / "c.toml").write_text("[run]\nprint_max_lenn = 3\n")
    r = run_py(["m.txt", "1", "--config", "c.toml"], tmp_path)
    assert r.returncode == 2 and "unknown setting 'print_max_lenn'" in r.stderr
    with pytest.raises(ModelError, match="unknown setting 'bogus'"):
        parse_model('[model]\nbogus = 1\n[axioms]\n1 = ["a"]\n[rules]\na->b\n')


def test_derivation_any_only():
    st = Settings()
    gcrsim.settings.apply_settings(st, {"derivation": "any"}, "test")
    with pytest.raises(ConfigError, match="not supported yet"):
        gcrsim.settings.apply_settings(st, {"derivation": "leftmost"}, "test")


def test_components_tables_and_the_shortcuts():
    body = '[axioms]\n1 = ["a"]\n[rules]\na->b\n'
    m = parse_model('[model.components.2.filters]\nforbid = ["x"]\n[model.components.2.marks]\nt = "a"\n[model.filters]\nrequire = ["a"]\n[model.marks]\nu = "b"\n' + body)
    assert m.config["components"] == {
        "2": {"filters": {"forbid": ["x"]}, "marks": {"t": "a"}},
        "0": {"filters": {"require": ["a"]}},   # [model.filters]: every component
        "1": {"marks": {"u": "b"}},             # [model.marks]: component 1
    }
    st = gcrsim.settings.settings_for_model(m)
    assert set(st.filters) == {0, 2} and set(st.marks) == {1, 2}
    m = parse_model('[model.components.all.filters]\nforbid = ["x"]\n' + body)  # "all" is 0
    assert set(gcrsim.settings.settings_for_model(m).filters) == {0}


@pytest.mark.parametrize("text, message", [
    ('[model.filters]\nforbid = ["x"]\n[model.components.0.filters]\nforbid = ["y"]\n', "component 0 has its filters twice"),
    ('[model.components.x.filters]\nforbid = ["x"]\n', "a component is a number"),
    ('[model.components.1.other]\nforbid = ["x"]\n', "unknown setting 'other'"),
    ('[model]\ncomponents = 3\n', "must be a table"),
    ('[model]\nfilters = 3\n', "must be a table"),
])
def test_components_tables_errors(text, message):
    with pytest.raises(ModelError, match=message):
        parse_model(text + '[axioms]\n1 = ["a"]\n[rules]\na->b\n')


def test_a_python_configuration_uses_the_nesting_of_the_toml_tables(tmp_path):
    (tmp_path / "m.txt").write_bytes(b'[axioms]\n1 = ["a"]\n[rules]\na->b\n')
    (tmp_path / "c.py").write_text("components = {0: {'filters': {'forbid': ['x']}}, 1: {'marks': {'t': 'b'}}}\n")
    r = run_py(["m.txt", "1", "--python-filter", "c.py"], tmp_path)
    assert r.returncode == 0 and "Terminal?" not in r.stdout and "Mark (t): b" in r.stdout
    (tmp_path / "bad.py").write_text("components = {1: {'other': {}}}\n")
    r = run_py(["m.txt", "1", "--python-filter", "bad.py"], tmp_path)
    assert r.returncode == 2 and "unknown setting 'other'" in r.stderr


def test_max_count_counts_symbols_classes_and_patterns_in_one_dictionary():
    body = '[symbols.classes]\nN = "S A"\n[axioms]\n1 = ["a"]\n[rules]\na->a\n'
    m = parse_model('[model.filters]\nmax_count = { a = 2, class.N = 2, re."p." = 2 }\n' + body)
    chk = gcrsim.filters._build_check([m.config["components"]["0"]["filters"]], m.lexicon)
    assert chk("aap1ap2ap1") is False                        # three a
    assert chk("p1ap2ap1") and not chk("p1p1p1")             # the pattern: each token separately
    assert not chk("SSA") and chk("SS")                      # the class: the symbols together
    with pytest.raises(gcrsim.ConfigError, match="only the keys 'class' and 're'"):
        gcrsim.filters._build_check([{"max_count": {"x": {"a": 1}}}])
    with pytest.raises(gcrsim.ConfigError, match="empty string"):
        gcrsim.filters._build_check([{"max_count": {"re": {"p*": 2}}}])


def test_re_counts_every_symbol_of_a_class_separately_and_class_counts_them_together():
    body = """[symbols.classes]
XY = "X00 Y10"
[axioms]
1 = ["a"]
[rules]
a->a
"""
    each = parse_model('[model.filters]' + chr(10) + 'max_count.re."{XY}" = 1' + chr(10) + body)
    together = parse_model('[model.filters]' + chr(10) + 'max_count.class.XY = 1' + chr(10) + body)
    listed = parse_model('[model.filters]' + chr(10) + 'max_count = { X00 = 1, Y10 = 1 }' + chr(10) + body)
    ok = {}
    for name, m in (("each", each), ("together", together), ("listed", listed)):
        chk = gcrsim.filters._build_check([m.config["components"]["0"]["filters"]], m.lexicon)
        ok[name] = [chk(m.lexicon.encode(w)) for w in ("X00", "X00 Y10", "X00 X00", "Y10 a Y10")]
    assert ok["each"] == ok["listed"] == [True, True, False, False]
    assert ok["together"] == [True, False, False, False]


def test_forbid_and_require_accept_functions_that_see_the_real_symbol_names():
    m = parse_model('[symbols]\nlexemes = ["p1"]\n[axioms]\n1 = ["a"]\n[rules]\na->a\n')
    seen = []
    chk = gcrsim.filters._build_check(
        [{"forbid": [lambda s: seen.append(s) or s.count("p1") > 1, r"zz"], "require": [lambda s: s.startswith("a")]}], m.lexicon)
    assert chk("ap1") and not chk("ap1p1") and not chk("bp1") and not chk("azz")
    assert seen[0] == "ap1"                                   # the function got the name p1, not the internal character
    with pytest.raises(gcrsim.ConfigError, match="regular expression or a function"):
        gcrsim.filters._build_check([{"forbid": [3]}])


def test_a_python_file_can_put_a_function_in_the_filters_of_a_component(tmp_path):
    (tmp_path / "m.txt").write_bytes(b'[axioms]\n1 = ["a"]\n[rules]\na->aa\na->ab\n')
    (tmp_path / "c.py").write_text("components = {1: {'filters': {'require': [lambda s: len(s) % 2 == 0]}}}\n")
    r = run_py(["m.txt", "2", "--python-filter", "c.py"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "aa" in r.stdout and "aaa" not in r.stdout.replace("aaaa", "")
