"""Unicode text: models and configs are UTF-8, one code point is one symbol."""
import io

import pytest

import gcrsim
from conftest import old_to_new, parse_old, run_py

GAMMA = "Γ"
SIGMA = "Σ"
ALPHA_FRAKTUR = "\U0001d538"  # outside the Basic Multilingual Plane
E_ACUTE = "é"


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_bytes((old_to_new(text) if name.endswith(".txt") else text).encode("utf-8"))
    return p


def content(text, steps=1, **settings):
    model = gcrsim.parse_model(text)
    sim = gcrsim.Simulator(model, gcrsim.Settings(**settings), write=lambda t: None)
    for _ in range(steps):
        sim.step()
    return sim.cur


def test_greek_symbols_run_and_print(tmp_path):
    write(tmp_path, "m.txt", "Axioms\n[%s]\nRules\n%s->%s%s\n" % (GAMMA, GAMMA, GAMMA, SIGMA))
    r = run_py(["m.txt", "2"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert GAMMA + SIGMA + SIGMA in r.stdout


def test_dot_matches_one_code_point_even_outside_the_bmp():
    text = """[axioms]
1 = ["%sb"]

[rules]
re(.)->X
""" % ALPHA_FRAKTUR
    assert sorted(content(text)[0]) == sorted(["Xb", ALPHA_FRAKTUR + "X"])


def test_word_class_is_unicode_aware():
    text = '[axioms]\n1 = ["%s"]\n\n[rules]\nre(\\w)->X\n' % E_ACUTE
    assert content(text)[0] == ["X"]


def test_lengths_count_code_points():
    text = """[axioms]
1 = ["%s"]

[rules]
%s->%s%s%s
""" % (GAMMA, GAMMA, GAMMA, GAMMA, GAMMA)
    assert content(text, reject_max_len=3)[0] == [GAMMA * 3]  # 3 symbols, though 6 bytes
    assert content(text, reject_max_len=2)[0] == []


def test_utf8_bom_is_accepted(tmp_path):
    p = tmp_path / "m.txt"
    p.write_bytes(b"\xef\xbb\xbf" + ("""[axioms]
1 = ["%s"]

[rules]
%s->x
""" % (GAMMA, GAMMA)).encode("utf-8"))
    model = gcrsim.parse_model_file(str(p))
    assert model.axioms[0] == [GAMMA]


def test_invalid_utf8_is_a_clear_model_error(tmp_path):
    p = tmp_path / "m.txt"
    p.write_bytes(b"Axioms\n[\xe9]\nRules\n\xe9->x\n")  # latin-1 bytes, not UTF-8
    with pytest.raises(gcrsim.ModelError, match="UTF-8"):
        gcrsim.parse_model_file(str(p))
    r = run_py(["m.txt", "1"], tmp_path)
    assert r.returncode == 2 and "UTF-8" in r.stderr and "Traceback" not in r.stderr


def test_output_is_utf8_bytes():
    class Raw:
        def __init__(self):
            self.buffer = io.BytesIO()

        def flush(self):
            pass

    raw = Raw()
    out = gcrsim.Output(raw)
    out.write("caf%s\n" % E_ACUTE)
    out.flush()
    assert raw.buffer.getvalue() == ("caf%s\n" % E_ACUTE).encode("utf-8")


def test_python_config_can_use_unicode_literals(tmp_path):
    write(tmp_path, "m.txt", "Axioms\n[%s]\nRules\n%s->%s\n" % (GAMMA, GAMMA, SIGMA))
    write(tmp_path, "c.py", "# -*- coding: utf-8 -*-\nreject_strings = lit('%s')\nreject_max_len = 50\nprint_max_len = 50\n" % SIGMA)
    r = run_py(["m.txt", "1", "--python-filter", "c.py"], tmp_path)
    assert r.returncode == 0, r.stderr
    body = r.stdout.split("STEP 1", 1)[1]
    assert SIGMA not in body  # the only candidate contains the skipped symbol


def test_toml_config_with_unicode_symbols(tmp_path):
    write(tmp_path, "m.txt", "Axioms\n[%s]\nRules\n%s->%s%s\n" % (GAMMA, GAMMA, GAMMA, SIGMA))
    write(tmp_path, "c.toml", "[model.components.1.filters]\nforbid = ['%s%s']\n" % (SIGMA, SIGMA))
    r = run_py(["m.txt", "3", "--config", "c.toml"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert GAMMA + SIGMA in r.stdout and GAMMA + SIGMA + SIGMA not in r.stdout


def test_combining_marks_are_separate_symbols():
    # NFD "e + combining acute" is two code points: not equal to the precomposed character
    nfd = "é"
    text = """[axioms]
1 = ["%s"]

[rules]
%s->X
""" % (nfd, E_ACUTE)
    assert content(text)[0] == []  # no normalisation: the precomposed lhs does not match
