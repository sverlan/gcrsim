"""Declarative .toml configurations and the gate on executable .py ones."""
import gcrsim
from conftest import write_model, EXAMPLES, run_py

MODEL = """[axioms]
1 = ["a"]

[rules]
a->ab
"""


def test_toml_matches_python_declarative_config():
    py = gcrsim.load_config(str(EXAMPLES / "ins_b_110200_declarative.py"))
    tm = gcrsim.load_config(str(EXAMPLES / "ins_b_110200_declarative.toml"), allow_python=False)
    assert tm.filters == py.filters
    assert tm.marks == py.marks
    assert (tm.print_max_len, tm.reject_max_len, tm.history) == (py.print_max_len, py.reject_max_len, py.history)


def test_toml_runs_without_the_flag_and_rejects_callbacks(tmp_path):
    write_model(tmp_path / "m.txt", MODEL)
    (tmp_path / "c.toml").write_text("[model]\nreject_max_len = 3\n[model.components.1.filters]\nforbid = ['bb']\n")
    r = run_py(["m.txt", "4", "--config", "c.toml"], tmp_path, trusted=False)
    assert r.returncode == 0, r.stderr
    assert "abbb" not in r.stdout
    (tmp_path / "bad.toml").write_text("[model]\nfilter_next = 'x'\n")
    r = run_py(["m.txt", "2", "--config", "bad.toml"], tmp_path, trusted=False)
    assert r.returncode != 0 and "filter_next" in r.stderr


def test_a_configuration_is_used_only_when_it_is_named(tmp_path):
    write_model(tmp_path / "mod.txt", MODEL)
    (tmp_path / "mod_conf.toml").write_text("[model]\nreject_max_len = 2\n")
    r = run_py(["mod.txt", "4"], tmp_path, trusted=False)
    assert r.returncode == 0, r.stderr
    assert "mod_conf.toml" not in r.stdout and "abbb" in r.stdout  # next to the model, but not named: not used
    r = run_py(["mod.txt", "4", "--config", "mod_conf.toml"], tmp_path, trusted=False)
    assert r.returncode == 0, r.stderr
    assert "Configuration: model + mod_conf.toml" in r.stdout and "abbb" not in r.stdout


def test_python_code_runs_only_with_python_filter(tmp_path):
    write_model(tmp_path / "m.txt", MODEL)
    (tmp_path / "c.py").write_text("open(\"ran.txt\", \"w\").write(\"x\")" + chr(10))
    r = run_py(["m.txt", "2", "--config", "c.py"], tmp_path)
    assert r.returncode != 0 and "--python-filter" in r.stderr
    assert not (tmp_path / "ran.txt").exists()
    assert run_py(["m.txt", "2", "--python-filter", "c.py"], tmp_path).returncode == 0
    assert (tmp_path / "ran.txt").exists()


def test_a_python_file_is_never_found_by_name(tmp_path):
    write_model(tmp_path / "m.txt", MODEL)
    for name in ("m_conf.py", "gcrsim_config.py"):
        (tmp_path / name).write_text("open(\"ran.txt\", \"w\").write(\"x\")" + chr(10))
    r = run_py(["m.txt", "2"], tmp_path, trusted=False)
    assert r.returncode == 0 and not (tmp_path / "ran.txt").exists()


def test_keep_is_the_filter_function(tmp_path):
    write_model(tmp_path / "m.txt", MODEL)
    (tmp_path / "f.py").write_text("def keep(s, component):" + chr(10) + "    return len(s) < 3" + chr(10))
    r = run_py(["m.txt", "4", "--python-filter", "f.py"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "abb" not in r.stdout
