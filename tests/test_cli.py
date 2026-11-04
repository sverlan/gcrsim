"""Command line behaviour: output, configuration lookup, buffering, errors."""

import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

import gcrsim
from conftest import (
    CONVERT,
    old_to_new,
    EXAMPLES,
    CLI_ENV,
    PERL_PRINT_ALL,
    ROOT,
    needs_perl,
    normalize_header,
    perl_cfg,
    py_cfg,
    run_perl,
    run_py,
)

ANBN = "Axioms\n[S]\nRules\n1,S->aS,2\n2,S->Sb,1\n1,S->,1\n"


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_bytes((old_to_new(text) if name.endswith(".txt") else text).encode("utf-8"))
    return p


# -- output format -------------------------------------------------------------------------------


def test_readme_example_output(tmp_path):
    write(tmp_path, "m.txt", ANBN)
    r = run_py(["m.txt", "3"], tmp_path)
    assert r.returncode == 0
    body = r.stdout.split("The initial configuration (at STEP 0):", 1)[1]
    assert body == (
        "\n\n\nComponent 1:\nS\n\nComponent 2:\n"
        "\n\n============\nSTEP 1\n============\n\n\nComponent 1:\n\n\nComponent 2:\naS\n"
        "\n\n============\nSTEP 2\n============\n\n\nComponent 1:\naSb\n\nComponent 2:\n"
        "\n\n============\nSTEP 3\n============\n\n\nComponent 1:\nab\n\nComponent 2:\naaSb\n"
    )


def test_header_lines(tmp_path):
    write(tmp_path, "m.txt", ANBN)
    out = run_py(["m.txt", "0"], tmp_path).stdout
    assert out.startswith("\n\n========================================\ngcrsim simulator v.")
    assert 'Print_hide = ""; Print_max_len=unlimited;' in out
    assert 'Reject_strings = ""; Reject_max_len=unlimited' in out
    assert "Filter function used: no, History: yes" in out
    assert "Configuration: model\n" in out


def test_zero_steps_prints_only_step_zero(tmp_path):
    write(tmp_path, "m.txt", ANBN)
    out = run_py(["m.txt", "0"], tmp_path).stdout
    assert "STEP" not in out.replace("(at STEP 0)", "")


def test_print_filters_do_not_affect_the_simulation(tmp_path):
    write(tmp_path, "m.txt", """[axioms]
1 = ["a"]

[rules]
a->aaaa
b->b
""")
    write(tmp_path, "c.py", "print_max_len = 3\nreject_max_len = 100\n")
    out = run_py(["m.txt", "2", "--python-filter", "c.py"], tmp_path).stdout
    # step 2 contains "aaaaaaa" (hidden by print_max_len) which still exists; step 3 would show it was kept
    out3 = run_py(["m.txt", "1", "--python-filter", "c.py"], tmp_path).stdout
    assert "aaaa" not in out3 and "STEP 1" in out3


def test_print_all_overrides_print_filters(tmp_path):
    write(tmp_path, "m.txt", """[axioms]
1 = ["a"]

[rules]
a->aaaa
""")
    write(tmp_path, "c.py", "print_max_len = 3\n")
    assert "aaaa" in run_py(["m.txt", "1", "--python-filter", "c.py", "--print-all"], tmp_path).stdout


def test_quiet_suppresses_listing_but_not_callback_output(tmp_path):
    write(tmp_path, "m.txt", """[axioms]
1 = ["a"]

[rules]
a->b
""")
    write(tmp_path, "c.py", "def filter_next(s, c):\n    print('seen ' + s)\n    return True\n")
    out = run_py(["m.txt", "1", "--python-filter", "c.py", "--quiet"], tmp_path).stdout
    assert out == "seen b\n"


def test_progress_goes_to_stderr(tmp_path):
    write(tmp_path, "m.txt", ANBN)
    r = run_py(["m.txt", "2", "--progress"], tmp_path)
    assert "step 2: strings per component [1,0]" in r.stderr
    assert "step 1:" not in r.stdout


def test_stops_when_all_components_are_empty_unless_run_empty(tmp_path):
    write(tmp_path, "m.txt", """[axioms]
1 = ["a"]

[rules]
a->b
""")
    r = run_py(["m.txt", "6"], tmp_path)
    assert "STEP 2" in r.stdout and "STEP 3" not in r.stdout
    assert "no strings remain at step 2" in r.stderr
    r = run_py(["m.txt", "4", "--run-empty"], tmp_path)
    assert "STEP 4" in r.stdout


def test_interactive_mode(tmp_path):
    write(tmp_path, "m.txt", ANBN)
    r = run_py(["m.txt", "-i"], tmp_path, stdin="\n\nq\n")
    assert r.stdout.count("step 0> ") + r.stdout.count("step 1> ") + r.stdout.count("step 2> ") == 3
    assert "STEP 2" in r.stdout and "STEP 3" not in r.stdout
    r = run_py(["m.txt", "-i"], tmp_path, stdin="")  # EOF quits
    assert r.returncode == 0 and "STEP 1" not in r.stdout


def test_without_a_model_the_help_is_shown_and_nothing_is_asked(tmp_path):
    for args in ([], ["-i"], ["--format", "csv"]):
        r = run_py(args, tmp_path, stdin="m.txt\nq\n")
        assert r.returncode == 2
        assert r.stdout.startswith("usage: gcrsim") and "MODEL" in r.stdout and "--max-step-accepted" in r.stdout
        assert "Enter input file name" not in r.stdout


def test_the_other_programs_show_their_help_without_arguments(capsys):
    from gcrsim.convert import main_convert
    from gcrsim.retention import main as retention_main
    for main, name in ((main_convert, "gcrsim-convert"), (retention_main, "gcrsim-retention")):
        assert main([]) == 2
        out = capsys.readouterr().out
        assert out.startswith("usage: " + name) and "show this help message" in out


# -- errors -------------------------------------------------------------------------------------------


def test_bad_input_file_and_bad_steps(tmp_path):
    r = run_py(["nope.txt", "1"], tmp_path)
    assert r.returncode == 2 and "cannot read the model nope.txt: no such file" in r.stderr
    write(tmp_path, "m.txt", ANBN)
    assert "Bad number of steps: -1" in run_py(["m.txt", "-1"], tmp_path).stderr
    assert "Bad number of steps: x" in run_py(["m.txt", "x"], tmp_path).stderr


def test_model_error_names_file_and_line(tmp_path):
    write(tmp_path, "m.txt", """[axioms]
1 = ["a"]

[rules]
not a rule
""")
    r = run_py(["m.txt", "1"], tmp_path)
    assert r.returncode == 2 and "m.txt:5:" in r.stderr and "Traceback" not in r.stderr


def test_limit_exit_status_and_message(tmp_path):
    write(tmp_path, "m.txt", """[axioms]
1 = ["a"]

[rules]
a->aa
aa->a
""")
    r = run_py(["m.txt", "5", "--max-step-candidates", "1"], tmp_path)
    assert r.returncode == 3
    assert "limit max-step-candidates=1 reached during step 2" in r.stderr and "incomplete" in r.stderr
    assert "STEP 1" in r.stdout  # earlier steps were printed


# -- configuration lookup -------------------------------------------------------------------------------


def test_config_path_is_relative_to_the_working_directory(tmp_path):
    sub = tmp_path / "models"
    sub.mkdir()
    write(sub, "m.txt", ANBN)
    write(sub, "c.toml", "[run]\nprint_max_len = 7\n")
    r = run_py([str(Path("models") / "m.txt"), "1", "--config", str(Path("models") / "c.toml")], tmp_path)
    assert "Print_max_len=7" in r.stdout and "Configuration: model + " in r.stdout

def test_python_filter_settings_win_over_config_files(tmp_path):
    write(tmp_path, "m.txt", ANBN)
    write(tmp_path, "c.toml", "[run]\nprint_max_len = 3\n")
    write(tmp_path, "c.py", "print_max_len = 5\n")
    r = run_py(["m.txt", "1", "--config", "c.toml", "--python-filter", "c.py"], tmp_path)
    assert r.returncode == 0 and "Print_max_len=5" in r.stdout and "Configuration: model + c.toml + c.py" in r.stdout

def test_perl_config_is_never_executed(tmp_path):
    write(tmp_path, "m.txt", ANBN)
    write(tmp_path, "old.cfg", "$print_len = 5;\n")
    r = run_py(["m.txt", "1", "--config", "old.cfg"], tmp_path)
    assert r.returncode == 2 and "Perl configuration" in r.stderr


def test_missing_explicit_config_is_an_error(tmp_path):
    write(tmp_path, "m.txt", ANBN)
    assert run_py(["m.txt", "1", "--python-filter", "nope.py"], tmp_path).returncode == 2


def test_configuration_files_are_not_looked_up_by_name(tmp_path):
    write(tmp_path, "m.txt", ANBN)
    write(tmp_path, "gcrsim_config.toml", "[run]\nprint_max_len = 11\n")
    write(tmp_path, "m_conf.toml", "[run]\nprint_max_len = 12\n")
    out = run_py(["m.txt", "0"], tmp_path).stdout
    assert "Print_max_len=unlimited" in out and "Configuration: model\n" in out

def test_config_syntax_error_is_reported(tmp_path):
    write(tmp_path, "m.txt", ANBN)
    write(tmp_path, "c.py", "print_max_len = (\n")
    r = run_py(["m.txt", "1", "--python-filter", "c.py"], tmp_path)
    assert r.returncode == 2 and "c.py" in r.stderr and "Traceback" not in r.stderr


def test_module_and_script_invocations_agree(tmp_path):
    write(tmp_path, "m.txt", ANBN)
    a = run_py(["m.txt", "3"], tmp_path).stdout
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    proc = subprocess.run([sys.executable, "-m", "gcrsim", "m.txt", "3", "--format", "perl"], cwd=str(tmp_path), capture_output=True, env=env)
    assert proc.returncode == 0
    assert proc.stdout.decode("latin-1") == a


def test_importing_module_has_no_side_effects(tmp_path):
    code = "import sys, gcrsim; sys.stdout.write('imported')"
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=str(tmp_path), capture_output=True, env=dict(os.environ, PYTHONPATH=str(ROOT))
    )
    assert proc.stdout == b"imported" and proc.stderr == b""


def test_version_option():
    proc = subprocess.run([sys.executable, "-m", "gcrsim", "--version"], capture_output=True, env=CLI_ENV)
    assert proc.stdout.decode().strip() == "gcrsim " + gcrsim.__version__


def test_config_does_not_need_to_import_gcrsim_for_context(tmp_path):
    write(tmp_path, "m.txt", ANBN)
    write(tmp_path, "c.py", "def filter_next(s, c, ctx):\n    if s == 'ab': ctx.mark('t')\n    return True\n")
    out = run_py(["m.txt", "4", "--python-filter", "c.py"], tmp_path).stdout
    assert "Mark (t): ab" in out


# -- output ordering and buffering -----------------------------------------------------------------------------------


def test_output_buffer_flushes_on_demand_and_when_full():
    class Stream:
        def __init__(self):
            self.chunks = []
            self.flushes = 0

        def write(self, text):
            self.chunks.append(text)

        def flush(self):
            self.flushes += 1

    s = Stream()
    out = gcrsim.Output(s, max_items=3)
    out.write("a")
    out.write("b")
    assert s.chunks == []
    out.write("c")  # reaches max_items: flushed as one chunk
    assert s.chunks == ["abc"]
    out.write("d")
    out.flush()
    assert s.chunks == ["abc", "d"]


def test_callback_prints_stay_in_order_with_step_output(tmp_path):
    write(tmp_path, "m.txt", """[axioms]
1 = ["a"]

[rules]
a->b
a->c
""")
    write(
        tmp_path,
        "c.py",
        "show_detailed_application = True\n"
        "def filter_next(s, c):\n    print('callback ' + s)\n    return True\n",
    )
    out = run_py(["m.txt", "1", "--python-filter", "c.py"], tmp_path).stdout
    order = [out.index(x) for x in ("a => b", "a => c", "callback b", "callback c", "Component 1:\nb")]
    assert order == sorted(order)


def test_broken_pipe_exits_quietly(tmp_path):
    write(tmp_path, "m.txt", """[axioms]
1 = ["a"]

[rules]
a->aa
a->b
b->bb
""")
    write(tmp_path, "c.py", "print_max_len = 100\nreject_max_len = 100\n")
    proc = subprocess.Popen(
        [sys.executable, "-m", "gcrsim", "m.txt", "12", "--python-filter", "c.py", "--format", "perl"],
        cwd=str(tmp_path),
        env=CLI_ENV,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    proc.stdout.read(10)
    proc.stdout.close()
    err = proc.stderr.read().decode()
    proc.wait(timeout=60)
    assert "Traceback" not in err


# -- Perl comparison of the printed output -----------------------------------------------------------------------------


def perl_and_python(tmp_path, model, perl_cfg_text, py_cfg_text, steps):
    (tmp_path / "m.txt").write_bytes(model.encode("utf-8"))  # Perl reads the old syntax
    write(tmp_path, "mp.txt", model)  # the simulator reads the converted model
    write(tmp_path, "gcrsim.cfg", perl_cfg_text)
    perl = run_perl("m.txt", steps, tmp_path)
    write(tmp_path, "c.py", py_cfg_text)
    py = run_py(["mp.txt", str(steps), "--python-filter", "c.py", "--run-empty"], tmp_path)
    assert py.returncode == 0, py.stderr
    return perl, py.stdout


SMALL_MODELS = {
    "anbn": ANBN,
    "branching": "Axioms\n[ab,]\n[c]\nRules\n1,a->ba,2\n2,b->ab,1\n1,b->aa,1\n2,c->,2\n2,->c,1\n3,a->,1\n",
    "captures": "Axioms\n[abc]\nRules\n(b)->$$1$$1\n(a)(b)->$$2$$1\n",
    "empty-axiom": "Axioms\n[,a]\nRules\n->x\n",
}


@needs_perl
@pytest.mark.perl
@pytest.mark.parametrize("name", sorted(SMALL_MODELS))
@pytest.mark.parametrize("history", [1, 0])
def test_printed_output_matches_perl(tmp_path, name, history):
    perl, py = perl_and_python(
        tmp_path,
        SMALL_MODELS[name],
        perl_cfg(history=history, print_max_len=6, reject_max_len=8),
        py_cfg(history=bool(history), print_max_len=6, reject_max_len=8),
        5,
    )
    assert normalize_header(py) == normalize_header(perl)


@needs_perl
@pytest.mark.perl
def test_callback_message_order_matches_perl(tmp_path):
    model = "Axioms\n[a]\nRules\n1,a->b,2\n1,a->c,1\n1,a->d,2\n2,b->a,1\n"
    perl_extra = 'sub filter_next($$){ my ($s,$c)=@_; print "cb $s $c\\n" if $s =~ /[bcd]/; return $s ne "d"; }'
    py_extra = "def filter_next(s, c):\n    if s in 'bcd':\n        print('cb %s %d' % (s, c))\n    return s != 'd'\n"
    perl, py = perl_and_python(
        tmp_path, model, perl_cfg(extra=perl_extra), py_cfg(extra=py_extra), 3
    )
    assert normalize_header(py) == normalize_header(perl)
    assert "cb c 0" in py


@needs_perl
@pytest.mark.perl
def test_detailed_application_output_matches_perl(tmp_path):
    model = "Axioms\n[abab,c]\n[]\nRules\na->x,1\n1->a,2\nb->b\n->z,2\n"
    perl, py = perl_and_python(
        tmp_path,
        model,
        perl_cfg(detailed=1, print_max_len=40, reject_max_len=40),
        py_cfg(detailed=True, print_max_len=40, reject_max_len=40),
        3,
    )
    assert normalize_header(py) == normalize_header(perl)
    assert "abab => xbab abxb" in py


@needs_perl
@pytest.mark.perl
def test_missing_config_header_matches_perl_notice(tmp_path):
    (tmp_path / "m.txt").write_bytes(ANBN.encode("utf-8"))  # Perl reads the old syntax
    write(tmp_path, "mp.txt", ANBN)
    perl = run_perl("m.txt", 1, tmp_path)
    py = run_py(["mp.txt", "1", "--run-empty"], tmp_path).stdout
    assert "Configuration file: Bad config file (gcrsim.cfg). Using default." in perl
    assert normalize_header(py) == normalize_header(perl)


# -- engine options from the command line ----------------------------------------------------------------------------


def test_streaming_option_equals_default_and_is_refused_for_stateful_callbacks(tmp_path):
    write(tmp_path, "m.txt", ANBN)
    write(tmp_path, "pure.py", "reject_max_len = 8\ndef filter_next(s, c):\n    return s.count('a') < 4\nfilter_next.pure = True\n")
    write(tmp_path, "state.py", "def filter_next(s, c):\n    return True\n")
    a = run_py(["m.txt", "9", "--python-filter", "pure.py"], tmp_path).stdout
    b = run_py(["m.txt", "9", "--python-filter", "pure.py", "--streaming"], tmp_path).stdout
    assert a == b
    r = run_py(["m.txt", "3", "--python-filter", "state.py", "--streaming"], tmp_path)
    assert r.returncode == 2 and "pure" in r.stderr


def test_no_mark_rejected_option_keeps_the_listing(tmp_path):
    write(tmp_path, "m.txt", """[axioms]
1 = ["aXb"]

[rules]
X->XX
X->a
X->Q
""")
    write(tmp_path, "c.py", "reject_max_len = 7\ncomponents = {0: {'filters': {'forbid': ['Q', 'XXXX']}}}\n")
    a = run_py(["m.txt", "5", "--python-filter", "c.py"], tmp_path).stdout
    b = run_py(["m.txt", "5", "--python-filter", "c.py", "--no-mark-rejected"], tmp_path).stdout
    assert a == b


def test_detailed_trace_shows_applications_with_results(tmp_path):
    write(tmp_path, "m.txt", """[axioms]
1 = ["1"]

[rules]
1->a
""")
    write(tmp_path, "c.py", "show_detailed_application = True\n")
    assert "1 => a" in run_py(["m.txt", "1", "--python-filter", "c.py"], tmp_path).stdout


def test_max_retained_stops_with_status_3(tmp_path):
    write(tmp_path, "m.txt", """[axioms]
1 = ["a"]

[rules]
a->b
b->a
""")
    write(tmp_path, "c.py", "history = False\n")
    r = run_py(["m.txt", "50", "--python-filter", "c.py", "--trace", "zzz", "--max-retained", "6"], tmp_path)
    assert r.returncode == 3 and "max-retained" in r.stderr
    r = run_py(["m.txt", "50", "--python-filter", "c.py", "--trace", "zzz", "--max-retained", "6", "--trace-best-effort"], tmp_path)
    assert r.returncode == 0 and "STEP 50" in r.stdout


def test_readme_rule_example(tmp_path):
    write(tmp_path, "m.txt", '[axioms]\n1 = ["ab"]\n\n[rules]\nre((a)(b))->\\2\\1\n')
    assert "\nba\n" in run_py(["m.txt", "1"], tmp_path).stdout


def test_no_steps_without_interactive_switch_is_an_error(tmp_path):
    write(tmp_path, "m.txt", ANBN)
    r = run_py(["m.txt"], tmp_path)
    assert r.returncode == 2 and "no number of steps" in r.stderr and "-i" in r.stderr
    assert run_py(["m.txt", "2", "-i"], tmp_path).returncode == 2


def test_csv_format_is_plain_data_only(tmp_path):
    import csv, io
    write(tmp_path, "m.txt", ANBN)
    r = run_py(["m.txt", "3", "--format", "csv"], tmp_path)
    assert r.returncode == 0
    rows = list(csv.reader(io.StringIO(r.stdout), delimiter="\t"))
    assert rows[0] == ["step", "component", "string"]
    assert all(len(row) == 3 for row in rows) and "#" not in r.stdout and "STEP" not in r.stdout
    assert {row[0] for row in rows[1:]} == {"0", "1", "2", "3"}
    comma = run_py(["m.txt", "1", "--format", "csv", "--csv-sep", ","], tmp_path).stdout
    assert comma.splitlines()[0] == "step,component,string"
    assert run_py(["m.txt", "1", "--format", "csv", "--csv-sep", "xx"], tmp_path).returncode == 2
    assert run_py(["m.txt", "-i", "--format", "csv"], tmp_path).returncode == 2


def test_jsonl_format_has_header_steps_and_end(tmp_path):
    import json
    write(tmp_path, "m.txt", ANBN)
    r = run_py(["m.txt", "2", "--format", "jsonl"], tmp_path)
    objs = [json.loads(line) for line in r.stdout.splitlines()]
    assert [o["type"] for o in objs] == ["header", "step", "step", "step", "end"]
    assert [o["step"] for o in objs[1:4]] == [0, 1, 2]
    assert objs[-1] == {"type": "end", "steps": 2, "status": 0}


# -- the commands of the step-by-step mode (docs/interactive.md) ---------------------------------------


def session(tmp_path, commands, *extra):
    write(tmp_path, "m.txt", ANBN)
    r = run_py(["m.txt", "-i", *extra], tmp_path, stdin=commands)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_stepper_n_runs_several_steps_and_show_lists_a_component(tmp_path):
    out = session(tmp_path, "n 2\nshow 1\nq\n", "--quiet")
    assert "step 2> " in out and "Component 1:\naSb\n" in out

def test_stepper_find_and_trace_use_the_retained_steps(tmp_path):
    out = session(tmp_path, "n 3\nfind aSb\ntrace ab\nq\n", "--quiet")
    assert "component 1: first at step 2; it is not in the current step" in out
    assert "Trace of 'ab' (component 1):" in out and "step 3: aSb => ab" in out

def test_stepper_mark_remove_marks_and_stats(tmp_path):
    out = session(tmp_path, "n\nmark 2 aS t\nmarks\nremove 2 aS\nstats\nn\nq\n", "--quiet")
    assert "Mark (t): aS" in out and "[t] component 2: aS" in out
    assert "removed 'aS' from component 2" in out
    assert "strings per component: 1, 0" in out  # after the removal; the string of component 1 is the empty one
    assert "step 2> " in out and "Component" not in out

def test_stepper_reports_mistakes_and_goes_on(tmp_path):
    out = session(tmp_path, "bogus\nmark 9 a x\nmark 1 zz t\nn 0\ntrace nothing\nhelp\nq\n")
    assert "unknown command 'bogus'" in out
    assert "a component is a number from 1 to 2, not '9'" in out
    assert "'zz' is not in component 1" in out
    assert "usage: n [K]" in out
    assert "is not in component 1 of any retained step" in out
    assert "commands (components count from 1" in out


def test_stepper_ends_at_the_end_of_the_input(tmp_path):
    out = session(tmp_path, "n\n")
    assert out.rstrip().endswith("step 1>")


# -- the text format (the default) ------------------------------------------------------------------------


def test_text_format_is_the_default_and_has_a_short_header(tmp_path):
    write(tmp_path, "m.txt", ANBN)
    r = subprocess.run([sys.executable, "-m", "gcrsim", "m.txt", "2"], cwd=str(tmp_path), capture_output=True, env=CLI_ENV)
    out = r.stdout.decode("utf-8").replace("\r\n", "\n")
    lines = out.split("\n")
    assert lines[0].startswith("gcrsim ") and lines[0].endswith("m.txt")
    assert lines[1] == "2 components, 3 rules"
    assert "Program configuration" not in out and "====" not in out
    assert "step 0\ncomponent 1\nS\n\ncomponent 2\n\nstep 1\n" in out


def test_text_format_shows_the_empty_word_and_leaves_an_empty_component_blank(tmp_path):
    write(tmp_path, "m.txt", ANBN)
    out = run_py(["m.txt", "1", "--format", "text"], tmp_path).stdout.replace("\r\n", "\n")
    assert "step 1\ncomponent 1\n(empty word)\n\ncomponent 2\naS\n\n" in out
    assert "step 0\ncomponent 1\nS\n\ncomponent 2\n\n" in out


def test_text_header_names_only_the_settings_that_differ_from_the_defaults(tmp_path):
    (tmp_path / "m.txt").write_text(
        '[model]\ndescription = "G: S -> aSb | ab"\nhistory = false\nreject_max_len = 9\n[run]\nprint_max_len = 5\n'
        '[axioms]\n1 = ["S"]\n[rules]\nS->aSb\nS->ab\n', encoding="utf-8")
    (tmp_path / "e.toml").write_text("[run]\nprint_sep = ' '\n")
    out = run_py(["m.txt", "1", "--format", "text", "--config", "e.toml"], tmp_path).stdout.replace("\r\n", "\n")
    lines = out.split("\n")
    assert lines[1] == "G: S -> aSb | ab"
    assert lines[2] == "1 component, 2 rules; settings: model + e.toml"
    assert lines[3] == 'print_max_len 5, reject_max_len 9, history off, print_sep " "'


def test_text_format_works_with_the_stepper_and_quiet(tmp_path):
    out = session(tmp_path, "n\nshow\nq\n", "--format", "text")
    assert "component 2\naS\n" in out and "(empty word)" in out and "step 1> " in out
    write(tmp_path, "m.txt", ANBN)
    assert run_py(["m.txt", "2", "--format", "text", "--quiet"], tmp_path).stdout == ""
