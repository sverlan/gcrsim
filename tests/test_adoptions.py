"""Behaviour adopted from the comparison with the other implementation."""

import sys

import pytest

import gcrsim
from gcrsim import CallbackError, ConfigError, LimitReached, ModelError, Settings
from conftest import write_model, parse_old, run_py

NOFILTER = dict(reject_strings="(?!)", reject_max_len=1000, print_hide="(?!)", print_max_len=1000)


def sim_with(callback, text="""[axioms]
1 = ["a"]

[rules]
a->b
a->c
""", **kw):
    settings = Settings(**NOFILTER)
    settings.config_name = "cfg.py"
    settings.filter_next = callback
    return gcrsim.Simulator(gcrsim.parse_model(text), settings, write=lambda t: None, **kw)


# -- callback exceptions are reported with their location ----------------------------------------------------


def test_callback_exception_names_step_component_and_string():
    def boom(s, c):
        raise ValueError("bad string")

    sim = sim_with(boom)
    with pytest.raises(CallbackError) as exc:
        sim.step()
    msg = str(exc.value)
    assert "cfg.py" in msg and "step 1" in msg and "component 1" in msg and "'b'" in msg
    assert "ValueError: bad string" in msg
    assert isinstance(exc.value.__cause__, ValueError)  # the original traceback stays chained


def test_library_errors_raised_inside_a_callback_pass_through_unwrapped():
    def marks(s, c, ctx):
        ctx.mark("t")
        return True

    sim = sim_with(marks, max_marks=1)
    with pytest.raises(LimitReached):
        sim.step()


def test_cli_callback_exception_is_a_clean_error(tmp_path):
    write_model(tmp_path / "m.txt", """[axioms]
1 = ["a"]

[rules]
a->b
""")
    (tmp_path / "c.py").write_text("def filter_next(s, c):\n    raise KeyError('x')\n")
    r = run_py(["m.txt", "1", "--python-filter", "c.py"], tmp_path)
    assert r.returncode == 2 and "Traceback" not in r.stderr
    assert "filter_next failed at step 1, component 1, string 'b'" in r.stderr and "KeyError" in r.stderr


def test_keyboard_interrupt_in_a_callback_is_not_swallowed():
    def interrupt(s, c):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        sim_with(interrupt).step()


# -- time-based flushing ------------------------------------------------------------------------------------------


class FakeStream:
    def __init__(self):
        self.chunks = []

    def write(self, text):
        self.chunks.append(text)

    def flush(self):
        pass


def test_output_flushes_after_the_interval_even_with_few_writes():
    now = [0.0]
    stream = FakeStream()
    out = gcrsim.Output(stream, max_items=10**6, flush_interval=1.0, clock=lambda: now[0])
    out.write("a")
    now[0] = 0.5
    out.write("b")
    assert stream.chunks == []
    now[0] = 1.2
    out.write("c")  # more than a second since the last flush
    assert stream.chunks == ["abc"]
    now[0] = 1.5
    out.write("d")
    assert stream.chunks == ["abc"]  # the interval restarts at each flush
    now[0] = 2.3
    out.write("e")
    assert stream.chunks == ["abc", "de"]


def test_zero_interval_disables_time_flushing():
    now = [0.0]
    stream = FakeStream()
    out = gcrsim.Output(stream, max_items=10**6, flush_interval=0, clock=lambda: now[0])
    out.write("a")
    now[0] = 100.0
    out.write("b")
    assert stream.chunks == []


# -- max_count re needs a nonempty token ---------------------------------------------------------------------------


@pytest.mark.parametrize("pattern", [r"p*", r"x?", r"(p)?"])
def test_max_count_re_rejects_patterns_that_match_the_empty_string(pattern):
    with pytest.raises(ConfigError, match="empty string"):
        gcrsim.filters._build_check([{"max_count": {"re": {pattern: 2}}}])


def test_max_count_re_ignores_zero_width_matches():
    # a lookahead cannot match "" itself, but it matches zero-width inside strings: never a token
    chk = gcrsim.filters._build_check([{"max_count": {"re": {r"(?=p)": 0}}}])
    assert chk("ppp") and chk("")


def test_max_count_re_accepts_nonempty_tokens():
    assert gcrsim.filters._build_check([{"max_count": {"re": {r"p.": 2}}}]) is not None


# -- streaming callbacks must not print -------------------------------------------------------------------------------


def pure(fn):
    fn.pure = True
    return fn


def test_streaming_callback_that_prints_is_an_error_and_stdout_is_restored(capsys):
    @pure
    def noisy(s, c):
        print("hello")
        return True

    sim = sim_with(noisy, streaming=True)
    original = sys.stdout
    with pytest.raises(ConfigError, match="streaming"):
        sim.step()
    assert sys.stdout is original
    assert "hello" not in capsys.readouterr().out


def test_streaming_callback_without_print_runs_and_messages_still_arrive():
    seen = []

    @pure
    def quiet(s, c, ctx):
        ctx.report("saw " + s)
        return True

    settings = Settings(**NOFILTER)
    settings.filter_next = quiet
    sim = gcrsim.Simulator(gcrsim.parse_model("""[axioms]
1 = ["a"]

[rules]
a->b
"""), settings, write=seen.append, streaming=True)
    original = sys.stdout
    sim.step()
    assert sys.stdout is original and "".join(seen) == "saw b\n"


def test_baseline_callbacks_may_still_print(capsys):
    def noisy(s, c):
        print("hello", s)
        return True

    sim_with(noisy).step()
    assert "hello b" in capsys.readouterr().out


def test_streaming_without_a_callback_does_not_touch_stdout():
    sim = gcrsim.Simulator(gcrsim.parse_model("""[axioms]
1 = ["a"]

[rules]
a->b
"""), Settings(**NOFILTER), write=lambda t: None, streaming=True)
    original = sys.stdout
    sim.step()
    assert sys.stdout is original


# -- \x and octal escapes in right-hand sides ----------------------------------------------------------------------------


def one_step(rule, axiom="ab"):
    settings = Settings(**NOFILTER, history=False)
    sim = gcrsim.Simulator(parse_old("Axioms\n[%s]\nRules\n%s\n" % (axiom, rule)), settings, write=lambda t: None)
    sim.step()
    return sim.cur[0]


def test_hex_and_octal_escapes():
    assert one_step("a->\\x41") == ["Ab"]
    assert one_step("a->x\\x{42}y") == ["xByb"]
    assert one_step("a->\\x24") == ["$b"]  # an escaped dollar sign is literal text
    assert one_step("a->\\101") == ["Ab"]
    assert one_step("a->\\x4Bz") == ["Kzb"]  # at most two hex digits


@pytest.mark.parametrize("rule", ["a->\\x{100}", "a->\\400", "a->x\\xy", "a->\\x{}"])
def test_bad_hex_and_octal_escapes_are_reported(rule):
    new, warnings = gcrsim.convert_model("Axioms\n[ab]\nRules\n%s\n" % rule)
    assert len(warnings) == 1 and "not converted" in warnings[0]
    assert "# not converted" in new


# -- package metadata ------------------------------------------------------------------------------------------------------


def test_project_metadata_has_author_and_links():
    import tomllib
    from conftest import ROOT

    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    assert project["name"] == "gcrsim"
    assert project["authors"] and project["authors"][0]["name"] == "Sergey Verlan"
    assert any("github.com/sverlan/gcrsim" in url for url in project["urls"].values())
    assert "email" not in project["authors"][0]  # no personal address in public metadata


def test_the_changelog_has_a_section_for_the_version_of_the_package():
    import re
    from pathlib import Path
    from gcrsim._meta import __version__
    text = (Path(__file__).resolve().parents[1] / "CHANGELOG.md").read_text(encoding="utf-8")
    sections = re.findall(r"^## \[([0-9][^\]]*)\]", text, re.M)
    assert sections and sections[0] == re.sub(r"\.dev\d+$", "", __version__)
