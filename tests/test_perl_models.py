"""Real models: engine equivalence and printed output against the Perl simulator.

Engine equivalence compares, for every step and component, the full ordered
accepted content (hashed with unambiguous framing), independent of any print
filter: the Perl configuration is extended with settings that print every
string, and the Python side is read through the API.
"""

import contextlib
import io
import shutil

import pytest

import gcrsim
from conftest import (
    parse_old,
    EXAMPLES,
    HAVE_PERL,
    PERL_FIXTURES,
    PERL_PRINT_ALL,
    digests,
    first_difference,
    needs_perl,
    normalize_header,
    parse_listing,
    python_contents,
    without_configfile,
    run_perl,
    run_py,
)

# model, engine-equivalence depth, slow depth, printed-output depth
MODELS = [
    ("ins_a_110200", 16, 24, 10),
    ("ins_b_110200", 16, 22, 9),
    ("ins_c_211110", 14, 20, 9),
    ("ins_222", 7, 10, 5),
]


def perl_listing(model, steps, workdir, print_all):
    shutil.copy(PERL_FIXTURES / (model + ".txt"), workdir / (model + ".txt"))
    cfg = (PERL_FIXTURES / (model + ".cfg")).read_bytes()
    if print_all:
        cfg += PERL_PRINT_ALL.encode()
    (workdir / (model + ".cfg")).write_bytes(cfg)
    return run_perl(model + ".txt", steps, workdir)


def check_engine(model, depth, tmp_path, config="%s_conf.py", **kw):
    text = (PERL_FIXTURES / (model + ".txt")).read_bytes().decode("latin-1")
    perl = parse_listing(perl_listing(model, depth, tmp_path, print_all=True))
    ours = python_contents(text, EXAMPLES / (config % model), depth, **kw)
    assert len(perl) == depth + 1
    assert digests(perl) == digests(ours), first_difference(perl, ours)
    return ours


@needs_perl
@pytest.mark.perl
@pytest.mark.parametrize("model, depth, slow, shown", MODELS, ids=[m[0] for m in MODELS])
def test_engine_equivalence(model, depth, slow, shown, tmp_path):
    ours = check_engine(model, depth, tmp_path)
    assert sum(len(c) for c in ours[-1]) >= 0


@needs_perl
@pytest.mark.perl
@pytest.mark.slow
@pytest.mark.parametrize("model, depth, slow, shown", MODELS, ids=[m[0] for m in MODELS])
def test_engine_equivalence_deep(model, depth, slow, shown, tmp_path):
    check_engine(model, slow, tmp_path)


@needs_perl
@pytest.mark.perl
@pytest.mark.parametrize("model, depth, slow, shown", MODELS, ids=[m[0] for m in MODELS])
def test_printed_output_matches_perl(model, depth, slow, shown, tmp_path):
    perl = perl_listing(model, shown, tmp_path, print_all=False)
    # the translated model refers to its Python configuration through <model>_conf.py, found next to the model
    work = tmp_path / "py"
    work.mkdir()
    for f in EXAMPLES.glob(model + "*"):
        shutil.copy(f, work / f.name)
    r = run_py([model + ".txt", str(shown), "--run-empty"], work)
    assert r.returncode == 0, r.stderr
    assert normalize_header(r.stdout) == normalize_header(perl)


@needs_perl
@pytest.mark.perl
@pytest.mark.parametrize("model, depth, slow, shown", MODELS, ids=[m[0] for m in MODELS])
def test_declarative_config_engine_equivalence(model, depth, slow, shown, tmp_path):
    """Component conditions + declarative marks (no callback) give Perl's contents."""
    check_engine(model, depth, tmp_path, config="%s_declarative.py")


@needs_perl
@pytest.mark.perl
@pytest.mark.parametrize("model, depth, slow, shown", MODELS, ids=[m[0] for m in MODELS])
def test_declarative_config_printed_output_matches_perl(model, depth, slow, shown, tmp_path):
    """The mark lines ('Terminal?: ...') appear in the same places as the Perl callback's prints."""
    perl = perl_listing(model, shown, tmp_path, print_all=False)
    work = tmp_path / "py"
    work.mkdir()
    shutil.copy(EXAMPLES / (model + ".txt"), work / (model + ".txt"))
    shutil.copy(EXAMPLES / (model + "_declarative.py"), work / (model + "_declarative.py"))
    r = run_py([model + ".txt", str(shown), "--python-filter", model + "_declarative.py", "--run-empty", "--no-mark-summary"], work)
    assert r.returncode == 0, r.stderr
    assert normalize_header(r.stdout) == normalize_header(perl)


@needs_perl
@pytest.mark.perl
@pytest.mark.slow
@pytest.mark.parametrize("model, depth, slow, shown", MODELS, ids=[m[0] for m in MODELS])
def test_declarative_config_engine_equivalence_deep(model, depth, slow, shown, tmp_path):
    check_engine(model, slow, tmp_path, config="%s_declarative.py")


def test_declarative_configs_have_no_callback():
    for model, _, _, _ in MODELS:
        st = gcrsim.load_config(str(EXAMPLES / (model + "_declarative.py")))
        assert st.filter_next is None and st.marks, model


@pytest.mark.parametrize("model, depth, slow, shown", MODELS, ids=[m[0] for m in MODELS])
def test_declarative_config_streaming_equals_baseline(model, depth, slow, shown):
    """Without a callback the config is eligible for streaming as it is (no 'pure' declaration)."""
    text = (PERL_FIXTURES / (model + ".txt")).read_bytes().decode("latin-1")
    cfg = EXAMPLES / (model + "_declarative.py")
    base_settings = gcrsim.load_config(str(cfg))
    base_settings.show_detailed_application = False
    fast_settings = gcrsim.load_config(str(cfg))
    fast_settings.show_detailed_application = False
    n = min(depth, 12)
    base_sim = gcrsim.Simulator(parse_old(without_configfile(text)), base_settings, write=lambda t: None)
    fast_sim = gcrsim.Simulator(parse_old(without_configfile(text)), fast_settings, write=lambda t: None, streaming=True)
    for _ in range(n):
        base_sim.step()
        fast_sim.step()
        assert digests([base_sim.cur]) == digests([fast_sim.cur])
    as_tuples = lambda sim: [(m.step, m.component, m.string, m.label) for m in sim.marks]
    assert as_tuples(base_sim) == as_tuples(fast_sim)


@pytest.mark.parametrize("model, depth, slow, shown", MODELS, ids=[m[0] for m in MODELS])
def test_streaming_and_no_mark_rejected_equal_baseline_on_real_models(model, depth, slow, shown):
    text = (PERL_FIXTURES / (model + ".txt")).read_bytes().decode("latin-1")
    cfg = EXAMPLES / (model + "_conf.py")
    base = python_contents(text, cfg, min(depth, 10))
    settings = gcrsim.load_config(str(cfg))
    settings.show_detailed_application = False
    if settings.filter_next is not None:
        original = settings.filter_next

        def silent_pure(s, c):
            # the real callbacks print "Terminal?" lines; streaming forbids print, and the order
            # of those prints is not what this test compares, so run them with output discarded
            with contextlib.redirect_stdout(io.StringIO()):
                return original(s, c)

        silent_pure.pure = True
        settings.filter_next = silent_pure
    fast = python_contents(text, steps=min(depth, 10), settings=settings, streaming=True)
    assert digests(base) == digests(fast)


def test_example_models_run_from_other_directories(tmp_path):
    for model, _, _, shown in MODELS:
        r = run_py([str(EXAMPLES / (model + ".txt")), "3"], tmp_path)
        assert r.returncode == 0, (model, r.stderr)
        line = [ln for ln in r.stdout.splitlines() if ln.startswith("Configuration:")][0]
        assert line.endswith(model + "_conf.py"), line
