r"""word_sep: reading typed words (--trace, replay) with a separator, and the checks around it."""
from pathlib import Path

import pytest

from gcrsim import GcrsimError, parse_model, replay
from conftest import run_py


def cli(args, cwd):
    args = [str(a) for a in args]
    if "--format" not in args:
        args += ["--format", "text"]
    return run_py(args, cwd, trusted=False)


def write(path: Path, text: str) -> str:
    path.write_bytes(text.encode("utf-8"))
    return str(path)


LEXEME = '[symbols]\nlexemes = ["xy"]\n{run}[axioms]\n1 = ["xya"]\n[rules]\na -> b\n'


def lexeme_model(run=""):
    return LEXEME.format(run=run)


def test_alphabet_symbol_with_the_separator_is_refused(tmp_path):
    m = write(tmp_path / "m.txt", '[symbols]\nalphabet = "a b ab"\n[axioms]\n1 = ["a"]\n[rules]\na -> b\n')
    f = write(tmp_path / "d.txt", "a\nb\n")
    r = cli([m, "--replay", f, "--word-sep", "b"], tmp_path)
    assert r.returncode == 2 and "'b'" in r.stderr and "word_sep" in r.stderr, r.stderr
    r = cli([m, "1", "--trace", "b", "--word-sep", "b"], tmp_path)
    assert r.returncode == 2 and "word_sep" in r.stderr


def test_a_character_of_the_separator_in_a_symbol_is_refused(tmp_path):
    m = parse_model('[symbols]\nalphabet = "a b xy"\n[axioms]\n1 = ["a"]\n[rules]\na -> b\n')
    with pytest.raises(GcrsimError, match="'a'"):
        replay(m, ["a"], word_sep="ab")


def test_lexeme_model_without_alphabet_accepts_a_dash(tmp_path):
    m = write(tmp_path / "m.txt", lexeme_model('[run]\nword_sep = "-"\n'))  # the arrow is not a symbol
    f = write(tmp_path / "d.txt", "xy-a\nxy-b\n")
    r = cli([m, "--replay", f], tmp_path)
    assert r.returncode == 0 and "1 step," in r.stdout, r.stdout + r.stderr
    r = cli([m, "2", "--trace", "xy-b"], tmp_path)
    assert r.returncode == 0 and "first appearing at step 1" in r.stdout, r.stdout + r.stderr
    assert 'word_sep "-"' in r.stdout  # listed in the header


def test_the_separator_stops_a_symbol_from_being_read_across_it():
    m = parse_model(lexeme_model())
    assert replay(m, ["xya", "xyb"]).ok
    assert replay(m, ["x-ya"], word_sep="-").failure.reason.startswith("not an axiom")  # x and y, not the lexeme xy
    assert replay(m, ["xy-a", "xy b"], word_sep="-").ok  # white space still separates


def test_regex_rule_gives_a_warning(tmp_path, capfd):
    m = write(tmp_path / "m.txt", '[axioms]\n1 = ["a"]\n[rules]\nre(a) -> \\x7c\n')
    r = cli([m, "1", "--trace", "|", "--word-sep", "|"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "warning" in r.stderr and "regular-expression" in r.stderr and "'|'" in r.stderr
    assert "not found" in r.stdout  # the traced word is empty: the separator is cut away


def test_trace_without_word_sep_keeps_a_literal_space(tmp_path):
    m = write(tmp_path / "m.txt", '[axioms]\n1 = ["a"]\n[rules]\nre(a) -> a\\x20b\n')
    r = cli([m, "1", "--trace", "a b"], tmp_path)
    assert r.returncode == 0 and "first appearing at step 1" in r.stdout, r.stdout + r.stderr
    assert "warning" not in r.stderr


def test_word_sep_from_the_model_a_config_and_the_command_line(tmp_path):
    plain = write(tmp_path / "plain.txt", lexeme_model())
    inmodel = write(tmp_path / "inmodel.txt", lexeme_model('[run]\nword_sep = "-"\n'))
    conf = write(tmp_path / "c.toml", '[run]\nword_sep = "-"\n')
    assert "first appearing at step 1" in cli([inmodel, "1", "--trace", "xy-b"], tmp_path).stdout
    assert "first appearing at step 1" in cli([plain, "1", "--trace", "xy-b", "--config", conf], tmp_path).stdout
    assert "not found" in cli([plain, "1", "--trace", "xy-b"], tmp_path).stdout  # no word_sep: a literal '-' symbol
    # the command line overrides the model
    r = cli([inmodel, "1", "--trace", "xy.b", "--word-sep", "."], tmp_path)
    assert "first appearing at step 1" in r.stdout, r.stdout + r.stderr
    r = cli([inmodel, "1", "--trace", "xy.b", "--word-sep", "."], tmp_path)
    assert 'word_sep "."' in r.stdout and 'word_sep "-"' not in r.stdout
    f = write(tmp_path / "d.txt", "xy.a\nxy.b\n")
    assert cli([inmodel, "--replay", f, "--word-sep", "."], tmp_path).returncode == 0
    assert cli([inmodel, "--replay", f], tmp_path).returncode == 4  # the model's "-" does not cut "xy.a"


def test_python_api_replay_with_word_sep(tmp_path):
    m = parse_model(lexeme_model())
    assert replay(m, ["xy-a", "xy-b"], word_sep="-").ok
    assert replay(m, [(1, "xy-a"), (1, "xy-b")], word_sep="-").ok
    f = write(tmp_path / "d.txt", "xy-a\nxy-b\n")
    from gcrsim import replay_file
    assert replay_file(m, f, word_sep="-").ok
    assert not replay(m, ["xy-a", "xy-a"], word_sep="-").ok


def test_class_member_and_guard_word_with_the_separator_are_refused():
    cls = parse_model('[symbols.classes]\nC = "a q-r"\n[axioms]\n1 = ["a"]\n[rules]\na -> a\n')
    with pytest.raises(GcrsimError, match="q-r"):
        replay(cls, ["a"], word_sep="-")
    guard = parse_model('[axioms]\n1 = ["a"]\n[rules]\na -> a, 1; permit: b-c\n')
    with pytest.raises(GcrsimError, match="'-'"):
        replay(guard, ["a"], word_sep="-")
    assert replay(guard, ["a"], word_sep="+").ok


def test_plain_operands_and_contexts_count_as_symbols():
    m = parse_model('[axioms]\n1 = ["a"]\n[rules]\nins(x,b,y),1\na -> a\n')
    with pytest.raises(GcrsimError, match="'x'"):
        replay(m, ["a"], word_sep="x")


def test_print_sep_warning(tmp_path):
    f = write(tmp_path / "d.txt", "xya\n")
    collide = '[symbols]\nlexemes = ["x-y"]\n[run]\nprint_sep = "-"\n[axioms]\n1 = ["a"]\n[rules]\na -> a\n'
    m = write(tmp_path / "collide.txt", collide)
    r = cli([m, "1"], tmp_path)
    assert "warning" in r.stderr and "print_sep" in r.stderr and "'x-y'" in r.stderr, r.stderr
    r = cli([m, "--replay", write(tmp_path / "e.txt", "a\na\n")], tmp_path)
    assert "print_sep" in r.stderr
    nolex = write(tmp_path / "nolex.txt", '[run]\nprint_sep = "-"\n[axioms]\n1 = ["a-b"]\n[rules]\na -> a\n')
    assert "warning" not in cli([nolex, "1"], tmp_path).stderr
    clean = write(tmp_path / "clean.txt", lexeme_model('[run]\nprint_sep = " "\n'))
    assert "warning" not in cli([clean, "1"], tmp_path).stderr
    del f


def test_colon_in_word_sep_is_refused_in_a_replay(tmp_path):
    text = '[symbols]\nalphabet = "1 ab a b"\n[axioms]\n1 = ["ab"]\n[rules]\nab -> ab\n'
    m = write(tmp_path / "m.txt", text)
    f = write(tmp_path / "d.txt", "1:ab\n")
    r = cli([m, "--replay", f, "--word-sep", ":"], tmp_path)
    assert r.returncode == 2 and "':'" in r.stderr and "component" in r.stderr, r.stderr
    with pytest.raises(GcrsimError, match="component"):
        replay(parse_model(text), ["1:ab"], word_sep=":")
    assert cli([m, "1", "--trace", "ab", "--word-sep", ":"], tmp_path).returncode == 0  # --trace is not affected


def test_settings_positional_order_is_kept():
    from gcrsim import Settings
    assert Settings(True, "", None, "", None, False, "", 7).steps == 7


def test_python_replay_uses_the_word_sep_of_the_model():
    m = parse_model(lexeme_model('[run]\nword_sep = "-"\n'))
    assert replay(m, ["xy-a"]).ok
    assert not replay(m, ["xy-a"], word_sep="").ok  # explicitly none: "-" is a symbol


def test_invalid_word_sep_is_refused_before_anything_runs(tmp_path):
    from conftest import ROOT
    model = ROOT / "examples" / "features" / "overlapping_symbols.txt"
    r = cli([model, "0", "--word-sep", "a"], tmp_path)
    assert r.returncode == 2 and "word_sep" in r.stderr
    f = write(tmp_path / "d.txt", "S\n")
    r = cli([model, "--replay", "-", "--word-sep", "a"], tmp_path)  # stdin is not read: refused first
    assert r.returncode == 2 and "word_sep" in r.stderr


def test_one_character_lexeme_counts_as_a_symbol():
    m = parse_model('[symbols]\nlexemes = ["q", "xy"]\n[axioms]\n1 = ["xy"]\n[rules]\nxy -> xy\n')
    with pytest.raises(GcrsimError, match="'q'"):
        replay(m, ["xy"], word_sep="q")


def test_trace_heading_shows_the_query_as_typed(tmp_path):
    m = write(tmp_path / "m.txt", lexeme_model())
    r = cli([m, "1", "--trace", "xy-b", "--word-sep", "-"], tmp_path)
    assert "Trace of 'xy-b'" in r.stdout, r.stdout


def test_word_sep_equal_to_an_internal_character_is_refused():
    m = parse_model(lexeme_model())
    code = next(iter(m.lexicon.names()))
    with pytest.raises(GcrsimError, match="internal"):
        replay(m, ["xya"], word_sep=code)


class _NoRead:
    def read(self, *a):
        raise AssertionError("the standard input was read")


def test_replay_file_checks_word_sep_before_reading(monkeypatch):
    import sys
    from gcrsim import replay_file
    m = parse_model('[symbols]\nalphabet = "a b ab"\n[axioms]\n1 = ["a"]\n[rules]\na -> b\n')
    monkeypatch.setattr(sys, "stdin", _NoRead())
    for sep in ("b", ":", "\n"):
        with pytest.raises(GcrsimError):
            replay_file(m, "-", word_sep=sep)
    bad = parse_model('[symbols]\nalphabet = "a b ab"\n[run]\nword_sep = "b"\n[axioms]\n1 = ["a"]\n[rules]\na -> b\n')
    with pytest.raises(GcrsimError):
        replay_file(bad, "-")


def test_replay_reads_only_the_word_sep_setting():
    m = parse_model('[run]\nsteps = "unused"\nword_sep = "-"\n[axioms]\n1 = ["a"]\n[rules]\na -> b\n')
    assert replay(m, ["a", "b"]).ok
    assert replay(parse_model('[run]\nsteps = "unused"\n[axioms]\n1 = ["a"]\n[rules]\na -> b\n'), ["a", "b"]).ok


def test_line_break_in_word_sep_is_refused_in_a_replay(tmp_path):
    m = parse_model(lexeme_model())
    for sep in ("\n", "\r", "-\n"):
        with pytest.raises(GcrsimError, match="line break"):
            replay(m, ["xya"], word_sep=sep)
    mf = write(tmp_path / "m.txt", lexeme_model())
    f = write(tmp_path / "d.txt", "xya\n")
    r = cli([mf, "--replay", f, "--word-sep", "\r"], tmp_path)
    assert r.returncode == 2 and "line break" in r.stderr
