r"""The choice of the operation of the command line: ``--mode`` and its aliases."""
import pytest

from gcrsim import GcrsimError, operations
from conftest import run_py

MODEL = '[axioms]\n1 = ["S"]\n[rules]\nS -> a S, 2\n2, S -> S b, 1\n'


def choose(*argv):
    op, rest = operations.select(list(argv))
    return op.name, rest


def cli(args, cwd, stdin=None):
    args = [str(a) for a in args]
    if "--format" not in args and "--help" not in args:
        args += ["--format", "text"]
    return run_py(args, cwd, stdin=stdin, trusted=False)


@pytest.fixture
def files(tmp_path):
    (tmp_path / "m.txt").write_bytes(MODEL.encode())
    (tmp_path / "d.txt").write_bytes(b"S\n2: aS\n")
    return tmp_path


def test_run_is_the_default():
    assert choose("m.txt", "3") == ("run", ["m.txt", "3"])
    assert choose() == ("run", [])
    assert choose("m.txt", "--mode", "run", "3") == ("run", ["m.txt", "3"])
    assert choose("--mode=run", "m.txt", "3") == ("run", ["m.txt", "3"])


def test_canonical_and_alias_forms_select_replay():
    assert choose("m.txt", "--mode", "replay", "d.txt") == ("replay", ["m.txt", "d.txt"])
    assert choose("m.txt", "--mode=replay", "d.txt") == ("replay", ["m.txt", "d.txt"])
    assert choose("m.txt", "--replay", "d.txt") == ("replay", ["m.txt", "--replay", "d.txt"])
    assert choose("m.txt", "--replay=d.txt") == ("replay", ["m.txt", "--replay=d.txt"])


def test_selector_placement():
    assert choose("--mode", "replay", "m.txt", "d.txt", "--explain")[0] == "replay"
    assert choose("m.txt", "d.txt", "--explain", "--mode", "replay")[0] == "replay"
    assert choose("--replay", "d.txt", "m.txt", "--quiet")[0] == "replay"
    assert choose("m.txt", "--quiet", "--mode=replay", "--component", "2", "d.txt") == (
        "replay", ["m.txt", "--quiet", "--component", "2", "d.txt"])


def test_the_terminator_ends_the_scan():
    assert choose("m.txt", "--", "--mode", "replay") == ("run", ["m.txt", "--", "--mode", "replay"])
    assert choose("--mode", "replay", "m.txt", "--", "--mode", "x") == ("replay", ["m.txt", "--", "--mode", "x"])


def test_a_value_that_looks_like_a_selector_is_not_one():
    assert choose("m.txt", "3", "--trace", "--mode") == ("run", ["m.txt", "3", "--trace", "--mode"])
    assert choose("m.txt", "3", "--config", "--replay") == ("run", ["m.txt", "3", "--config", "--replay"])
    assert choose("m.txt", "3", "--trace-mark-label", "--mode") == ("run", ["m.txt", "3", "--trace-mark-label", "--mode"])
    assert choose("m.txt", "3", "--trace=--mode") == ("run", ["m.txt", "3", "--trace=--mode"])
    assert choose("m.txt", "3", "--comp", "--mode") == ("run", ["m.txt", "3", "--comp", "--mode"])  # an abbreviation of --component
    assert choose("m.txt", "--trace", "--mode", "--mode", "replay", "d.txt") == (
        "replay", ["m.txt", "--trace", "--mode", "d.txt"])


@pytest.mark.parametrize("argv", [
    ["m.txt", "--mode", "replay", "--replay", "d.txt"],
    ["m.txt", "--mode", "replay", "--mode", "replay", "d.txt"],
    ["m.txt", "--mode", "run", "--mode", "run", "3"],
    ["m.txt", "--mode", "run", "--mode", "replay"],
    ["m.txt", "--replay", "d.txt", "--replay=e.txt"],
    ["m.txt", "--mode=replay", "--replay=d.txt"],
])
def test_more_than_one_selector_is_an_error(argv):
    with pytest.raises(GcrsimError, match="more than one mode selector"):
        operations.select(argv)


def test_unknown_or_missing_mode_name():
    with pytest.raises(GcrsimError, match=r"unknown mode 'frobnicate': the modes are run, replay, search"):
        operations.select(["m.txt", "--mode", "frobnicate"])
    with pytest.raises(GcrsimError, match="unknown mode"):
        operations.select(["m.txt", "--mode="])
    with pytest.raises(GcrsimError, match="needs a mode name"):
        operations.select(["m.txt", "--mode"])


@pytest.mark.parametrize("argv", [["m.txt", "--rep", "d.txt"], ["m.txt", "--repl=d.txt"], ["m.txt", "--mod", "replay"], ["m.txt", "--mode-replay"]])
def test_abbreviations_are_not_selectors(argv):
    assert operations.select(argv)[0].name == "run"


def test_the_table_has_one_entry_per_operation():
    table = operations.operations()
    assert [(op.name, op.alias) for op in table] == [("run", None), ("replay", "--replay"), ("search", "--search")]


# ---------------------------------------------------------------------------
# through the command
# ---------------------------------------------------------------------------


def test_canonical_and_alias_replay_give_the_same_output(files):
    outputs = [
        cli(["m.txt", "--mode", "replay", "d.txt", "--explain"], files),
        cli(["--mode=replay", "m.txt", "d.txt", "--explain"], files),
        cli(["m.txt", "--replay", "d.txt", "--explain"], files),
        cli(["--replay=d.txt", "--explain", "m.txt"], files),
        cli(["m.txt", "--explain", "d.txt", "--mode", "replay"], files),
    ]
    assert all(o.returncode == 0 for o in outputs), [o.stderr for o in outputs]
    assert len({o.stdout for o in outputs}) == 1
    assert "all legal" in outputs[0].stdout


def test_the_file_given_twice_or_not_at_all_is_an_error(files):
    r = cli(["m.txt", "--mode", "replay", "d.txt", "--replay", "d.txt"], files)
    assert r.returncode == 2  # two selectors
    r = cli(["m.txt", "--replay", "d.txt", "d.txt"], files)
    assert r.returncode == 2 and "twice" in r.stderr
    r = cli(["m.txt", "--mode", "replay"], files)
    assert r.returncode == 2 and "no file of forms" in r.stderr


def test_run_only_arguments_are_refused_in_replay_mode(files):
    for extra in (["--trace", "S"], ["--progress"], ["-i"], ["--max-history", "3"], ["--csv-sep", ","], ["--stop-on-found"]):
        r = cli(["m.txt", "--replay", "d.txt", *extra], files)
        assert r.returncode == 2, extra
        assert "unrecognized arguments" in r.stderr or "error" in r.stderr
    r = cli(["m.txt", "--mode", "replay", "d.txt", "3"], files)  # a step count would be a third positional
    assert r.returncode == 2 and "unrecognized arguments" in r.stderr


def test_unknown_mode_and_double_selector_through_the_command(files):
    r = cli(["m.txt", "--mode", "nosuch", "3"], files)
    assert r.returncode == 2 and "unknown mode 'nosuch': the modes are run, replay" in r.stderr
    r = cli(["m.txt", "--mode", "replay", "--replay", "d.txt"], files)
    assert r.returncode == 2 and "more than one mode selector" in r.stderr


def test_abbreviated_selectors_are_not_accepted_through_the_command(files):
    assert cli(["m.txt", "--rep", "d.txt"], files).returncode == 2
    assert cli(["m.txt", "--mo", "replay", "d.txt"], files).returncode == 2
    r = cli(["m.txt", "--mode", "replay", "--repl", "d.txt"], files)
    assert r.returncode == 2


def test_mode_help_needs_no_model(files):
    r = cli(["--mode", "replay", "--help"], files)
    assert r.returncode == 0
    assert "usage: gcrsim --mode replay" in r.stdout and "--fragment" in r.stdout and "--explain" in r.stdout
    assert "--trace" not in r.stdout
    r = cli(["--mode=replay", "-h"], files)
    assert r.returncode == 0 and "--fragment" in r.stdout
    assert cli(["--mode", "run", "--help"], files).returncode == 0
    r = cli(["--mode", "replay"], files)  # no model: the help of the mode and status 2
    assert r.returncode == 2 and "--fragment" in r.stdout


def test_general_help_lists_the_modes():
    r = run_py(["--help"], ".")
    assert r.returncode == 0
    assert "--mode replay" in r.stdout and "--replay FILE" in r.stdout and "default" in r.stdout


def test_default_run_is_unchanged(files):
    r = cli(["m.txt", "2"], files)
    assert r.returncode == 0 and "step 2" in r.stdout and "component 1" in r.stdout
    assert cli(["m.txt", "--mode", "run", "2"], files).stdout == r.stdout
    assert cli(["--mode=run", "m.txt", "2"], files).stdout == r.stdout
    r = run_py([], files)  # no arguments: the help, status 2
    assert r.returncode == 2 and "usage: gcrsim" in r.stdout
    r = cli(["m.txt", "--trace", "--mode"], files)  # a trace of the text '--mode' needs a step count first
    assert r.returncode == 2 and "unknown mode" not in r.stderr


def test_a_terminator_in_the_place_of_a_value_ends_the_scan():
    assert choose("--help", "--config", "--", "--mode=bogus") == ("run", ["--help", "--config", "--", "--mode=bogus"])
    assert choose("--trace", "--", "--mode=bogus")[0] == "run"


def test_help_with_a_terminator_after_an_option(files):
    r = cli(["--help", "--config", "--", "--mode=bogus"], files)
    assert r.returncode == 0 and "usage: gcrsim" in r.stdout


def test_option_values_that_look_like_selectors_through_the_command(files):
    r = cli(["m.txt", "1", "--trace=--mode"], files)
    assert r.returncode == 0, r.stderr
    assert "not found" in r.stdout
    r = cli(["m.txt", "1", "--trace", "--replay"], files)
    assert r.returncode == 2 and "unknown mode" not in r.stderr and "replay" not in r.stdout.split("\n")[0]
