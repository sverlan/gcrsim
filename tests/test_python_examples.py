"""The examples of examples/python/: a model and the Python file that goes with it, run from the command line."""
import itertools
import re
from pathlib import Path

from conftest import ROOT, run_py

PY = Path(ROOT) / "examples" / "python"


def marked(stdout, label):
    return [m.group(1) for m in re.finditer(r"Mark \(%s\): (.*)" % label, stdout)]


def anbn(n):
    return "a" * n + "b" * n


def test_a_function_in_expected_re_checks_against_an_infinite_language():
    r = run_py([str(PY / "anbn_with_mistake.txt"), "6", "--python-filter", str(PY / "check_infinite.py")], PY)
    assert r.returncode == 0, r.stderr
    words = marked(r.stdout, "unexpected")
    assert "ba" in words and "abab" in words
    assert not any(w == anbn(len(w) // 2) for w in words)      # the words a^n b^n are expected, whatever n is


def test_a_file_of_expected_words_gives_the_same_marks_up_to_its_length():
    a = run_py([str(PY / "anbn_with_mistake.txt"), "6", "--python-filter", str(PY / "check_infinite.py")], PY)
    b = run_py([str(PY / "anbn_with_mistake.txt"), "6", "--python-filter", str(PY / "check_from_file.py")], PY)
    assert marked(a.stdout, "unexpected") == marked(b.stdout, "unexpected")      # n = 3 at step 6 is within the 20 of the file


def test_the_valence_gate_lets_through_the_words_with_as_many_a_as_b():
    r = run_py([str(PY / "valence.txt"), "12", "--python-filter", str(PY / "valence.py")], PY)
    assert r.returncode == 0, r.stderr
    words = set(marked(r.stdout, "terminal"))
    balanced = {"".join(w) for k in range(5) for w in itertools.product("ab", repeat=k) if w.count("a") == w.count("b")}
    assert words == balanced                   # all of length up to 4 at 12 steps, and no other word


def balanced(limit):
    return {"".join(w) for k in range(limit + 1) for w in itertools.product("ab", repeat=k) if w.count("a") == w.count("b")}


def test_the_valence_gate_as_the_filter_function_keep_gives_the_same_words():
    for extra in ([], ["--streaming"]):     # keep.pure = True and pure(...) allow streaming
        r = run_py([str(PY / "valence.txt"), "12", "--python-filter", str(PY / "valence_keep.py"), *extra], PY)
        assert r.returncode == 0, r.stderr
        assert set(marked(r.stdout, "terminal")) == balanced(4)
        r = run_py([str(PY / "valence.txt"), "12", "--python-filter", str(PY / "valence.py"), *extra], PY)
        assert r.returncode == 0, r.stderr
        assert set(marked(r.stdout, "terminal")) == balanced(4)


def test_ctx_mark_flags_the_words_that_keep_cuts():
    r = run_py([str(PY / "anbn_with_mistake.txt"), "6", "--python-filter", str(PY / "mark_what_is_cut.py")], PY)
    assert r.returncode == 0, r.stderr
    cut = marked(r.stdout, "too_long")
    assert cut and all(len(w) > 7 for w in cut)


def test_a_beam_keeps_three_strings_per_component_and_step_and_streaming_refuses_it():
    r = run_py([str(PY / "anbn_with_mistake.txt"), "5", "--python-filter", str(PY / "beam.py"), "--format", "csv"], PY)
    assert r.returncode == 0, r.stderr
    rows = [line.split("\t") for line in r.stdout.strip().split("\n")[1:]]
    per = {}
    for step, component, _ in rows:
        per[(step, component)] = per.get((step, component), 0) + 1
    assert max(per.values()) == 3
    r = run_py([str(PY / "anbn_with_mistake.txt"), "5", "--python-filter", str(PY / "beam.py"), "--streaming"], PY)
    assert r.returncode == 2 and "declared pure" in r.stderr


def test_streaming_refuses_a_function_in_the_components_that_is_not_declared_pure(tmp_path):
    (tmp_path / "m.txt").write_bytes(b'[axioms]\n1 = ["a"]\n[rules]\na->a\n')
    (tmp_path / "c.py").write_text("components = {1: {'filters': {'forbid': [lambda s: False]}}}\n")
    r = run_py(["m.txt", "1", "--python-filter", "c.py", "--streaming"], tmp_path)
    assert r.returncode == 2 and "declared pure" in r.stderr and "<lambda>" in r.stderr
    (tmp_path / "c.py").write_text("components = {1: {'filters': {'forbid': [pure(lambda s: False)]}}}\n")
    assert run_py(["m.txt", "1", "--python-filter", "c.py", "--streaming"], tmp_path).returncode == 0
    (tmp_path / "c.py").write_text("components = {1: {'marks': {'t': {'pattern': 'a', 'expected_re': [lambda s: False]}}}}\n")
    assert run_py(["m.txt", "1", "--python-filter", "c.py", "--streaming"], tmp_path).returncode == 2


def test_the_infinite_check_is_pure_and_works_with_streaming():
    a = run_py([str(PY / "anbn_with_mistake.txt"), "5", "--python-filter", str(PY / "check_infinite.py")], PY)
    b = run_py([str(PY / "anbn_with_mistake.txt"), "5", "--python-filter", str(PY / "check_infinite.py"), "--streaming"], PY)
    assert b.returncode == 0, b.stderr
    assert marked(a.stdout, "unexpected") == marked(b.stdout, "unexpected")
