"""Regression tests for the review findings (limits, \\Z, trace boundaries, mark order, counting)."""

import tracemalloc

import pytest

import gcrsim
from gcrsim import LimitReached, Settings, TraceError
from conftest import write_model, parse_old, needs_perl, normalize_header, perl_cfg, py_cfg, run_perl, run_py

NOFILTER = dict(reject_strings="(?!)", reject_max_len=1000, print_hide="(?!)", print_max_len=1000)
TWO = """[axioms]
1 = ["S"]

[rules]
S->A,2
S->B
"""


def sim_of(text, *, settings=None, **kw):
    return gcrsim.Simulator(gcrsim.parse_model(text), settings or Settings(**NOFILTER), write=lambda t: None, **kw)


# -- 1. max_history counts rejected candidates --------------------------------------------------------


@pytest.mark.parametrize("streaming", [False, True])
def test_max_history_stops_on_a_rejected_candidate(streaming):
    # every non-empty string is rejected by reject_strings ".", yet each one enters the history
    settings = Settings(**{**NOFILTER, "reject_strings": "."})
    sim = sim_of("""[axioms]
1 = ["a"]

[rules]
a->b
""", settings=settings, max_history=1, streaming=streaming)
    with pytest.raises(LimitReached) as exc:
        sim.step()
    assert exc.value.limit == "max-history" and exc.value.step == 1
    assert sim.step_no == 0 and sim.cur == [["a"]]


def test_max_history_boundary_is_inclusive():
    settings = Settings(**{**NOFILTER, "reject_strings": "."})
    sim = sim_of("""[axioms]
1 = ["a"]

[rules]
a->b
""", settings=settings, max_history=2)
    sim.step()  # a, b: exactly two entries
    assert sim.hist_count == 2


def test_max_history_validates_the_initial_history():
    with pytest.raises(LimitReached) as exc:
        sim_of("""[axioms]
1 = ["a", "b", "c"]

[rules]
a->b
""", max_history=2)
    assert exc.value.limit == "max-history" and exc.value.step == 0
    assert "initial configuration" in str(exc.value)
    sim_of("""[axioms]
1 = ["a", "b", "c"]

[rules]
a->b
""", max_history=3)  # at the limit is fine
    sim_of("""[axioms]
1 = ["a", "b", "c"]

[rules]
a->b
""", settings=Settings(**NOFILTER, history=False), max_history=1)


def test_max_history_on_rejected_candidate_with_no_mark_rejected_is_not_counted():
    # with --no-mark-rejected the pure filter runs first, so a rejected string never enters the history
    settings = Settings(**{**NOFILTER, "reject_strings": "."})
    sim = sim_of("""[axioms]
1 = ["a"]

[rules]
a->b
""", settings=settings, max_history=1, no_mark_rejected=True)
    sim.step()
    assert sim.hist_count == 1


def test_max_history_cli_exit_status(tmp_path):
    write_model(tmp_path / "m.txt", """[axioms]
1 = ["a"]

[rules]
a->b
""")
    (tmp_path / "c.py").write_text("reject_strings = '.'\n")
    r = run_py(["m.txt", "3", "--python-filter", "c.py", "--max-history", "1"], tmp_path)
    assert r.returncode == 3 and "max-history" in r.stderr


# -- 2. bounded generation under max_step_candidates --------------------------------------------------------------


def peak_bytes(action):
    tracemalloc.start()
    try:
        action()
    except LimitReached:
        pass
    finally:
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
    return peak


BIG = "[axioms]\n1 = [\"" + "a" * 2000 + "\"]\n\n[rules]\n->X\n"  # 2001 candidates of ~2000 characters each


@pytest.mark.parametrize("streaming, detailed", [(False, False), (False, True), (True, False)])   # streaming and detailed tracing do not combine
def test_candidate_limit_stops_before_materialising_the_batch(streaming, detailed):
    settings = Settings(**NOFILTER, show_detailed_application=detailed)
    sim = sim_of(BIG, settings=settings, max_step_candidates=1, streaming=streaming)
    peak = peak_bytes(sim.step)
    assert peak < 400_000, peak  # the edits are small tuples; the full batch of strings would be about 4 MB
    with pytest.raises(LimitReached) as exc:
        sim_of(BIG, settings=settings, max_step_candidates=1, streaming=streaming).step()
    assert exc.value.limit == "max-step-candidates" and exc.value.step == 1
    assert exc.value.counts["count"] == 2  # generation stopped at the first excess candidate


def test_without_a_limit_the_full_batch_is_still_generated():
    sim = sim_of(BIG, settings=Settings(**{**NOFILTER, "reject_max_len": 5000}))
    sim.step()
    assert sim.last_candidates == 2001 and len(sim.cur[0]) == 2001


@pytest.mark.parametrize("limit", [0, 1, 2, 5, 2001])
def test_candidate_limit_is_exact(limit):
    sim = sim_of(BIG, max_step_candidates=limit)
    if limit >= 2001:
        sim.step()
        assert sim.last_candidates == 2001
    else:
        with pytest.raises(LimitReached):
            sim.step()


def test_candidate_limit_accumulates_over_strings_and_rules():
    sim = sim_of("""[axioms]
1 = ["a", "b"]

[rules]
a->x
b->y
a->z
""", max_step_candidates=3)
    sim.step()  # exactly three candidates
    assert sim.last_candidates == 3
    with pytest.raises(LimitReached):
        sim_of("""[axioms]
1 = ["a", "b"]

[rules]
a->x
b->y
a->z
""", max_step_candidates=2).step()


def test_expand_spans_and_build_agree():
    from test_rules import CASES, model_text

    for name, axiom, rule, _ in CASES:
        r = parse_old(model_text(axiom, rule)).rules[0][0] if parse_old(model_text(axiom, rule)).rules[0] else None
        if r is None:
            continue
        for s in (axiom, "", "ab", "abab"):
            full = list(r.expand(s))
            assert r.build(s, r.edits(s)) == full, (name, s)
            assert [res for _, _, res in r.spans(s)] == full, (name, s)


# -- 3. max_step_accepted bounds the whole step ----------------------------------------------------------------------


@pytest.mark.parametrize("streaming", [False, True])
def test_max_step_accepted_counts_all_components(streaming):
    sim = sim_of(TWO, max_step_accepted=1, streaming=streaming)
    with pytest.raises(LimitReached) as exc:
        sim.step()
    assert exc.value.limit == "max-step-accepted" and exc.value.counts["count"] == 2
    sim = sim_of(TWO, max_step_accepted=2, streaming=streaming)
    sim.step()
    assert sorted(len(c) for c in sim.cur) == [1, 1]
    assert sim.peak_strings == 2


def test_max_step_accepted_resets_every_step():
    sim = sim_of("""[axioms]
1 = ["a"]

[rules]
a->b
b->a
""", settings=Settings(**NOFILTER, history=False), max_step_accepted=1)
    sim.run(6)  # one accepted string per step, never more than one in a step


# -- 4. Perl-only regex syntax is not translated -------------------------------------------------------------------


def test_perl_named_group_syntax_is_a_load_error():
    with pytest.raises(gcrsim.ModelError):
        gcrsim.parse_model("""[axioms]
1 = ["ab"]

[rules]
(?<n>a)->x
""")
    _, warnings = gcrsim.convert_model("Axioms\n[ab]\nRules\n(?<n>a)->x\n")
    assert len(warnings) == 1 and "named group" in warnings[0]


def test_python_named_group_syntax_works():
    sim = sim_of("""[axioms]
1 = ["ab"]

[rules]
re((?P<n>a)(?P=n)?)->x
""", settings=Settings(**NOFILTER, history=False))
    sim.step()
    assert sim.cur == [["xb"]]


def test_backslash_Z_is_the_strict_end_of_the_string():
    sim = sim_of('[axioms]\n1 = ["ab"]\n\n[rules]\nre(\\Z)->X\n', settings=Settings(**NOFILTER, history=False))
    sim.step()
    assert sim.cur == [["abX"]]


# -- 5. trace validation and CLI boundaries ------------------------------------------------------------------------


def traced_sim(text="""[axioms]
1 = ["a"]

[rules]
a->b
b->c
""", steps=2):
    sim = sim_of(text, retain=True)
    sim.run(steps)
    return sim


def test_trace_at_step_zero_requires_an_axiom():
    sim = traced_sim()
    assert sim.trace("a", 0, step=0) == []
    with pytest.raises(TraceError, match="not an axiom"):
        sim.trace("NEVER", 0, step=0)


def test_trace_validates_component_and_step():
    sim = traced_sim()
    with pytest.raises(TraceError, match="component"):
        sim.trace("a", 5)
    with pytest.raises(TraceError, match="component"):
        sim.trace("a", -1)
    with pytest.raises(TraceError, match="step"):
        sim.trace("c", 0, step=9)
    with pytest.raises(TraceError, match="step"):
        sim.trace("c", 0, step=-1)
    assert [d.result for d in sim.trace("c", 0, step=2)] == ["b", "c"]


def test_cli_trace_of_an_axiom_stops_before_step_one(tmp_path):
    write_model(tmp_path / "m.txt", """[axioms]
1 = ["a"]

[rules]
a->b
""")
    r = run_py(["m.txt", "5", "--trace", "a", "--stop-on-found"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "Trace of 'a' (component 1), first appearing at step 0:" in r.stdout
    assert "(axiom: no derivation steps)" in r.stdout
    assert "STEP 1" not in r.stdout
    r = run_py(["m.txt", "2", "--trace", "a"], tmp_path)  # without the stop flag the run continues
    assert "first appearing at step 0" in r.stdout and "STEP 2" in r.stdout


def test_cli_trace_with_zero_steps(tmp_path):
    write_model(tmp_path / "m.txt", """[axioms]
1 = ["a"]

[rules]
a->b
""")
    out = run_py(["m.txt", "0", "--trace", "a"], tmp_path).stdout
    assert "first appearing at step 0" in out
    out = run_py(["m.txt", "0", "--trace", "zzz"], tmp_path).stdout
    assert "not found in the steps run" in out


CHAIN = """[axioms]
1 = ["a"]

[rules]
a->b
b->c
c->d
d->e
e->f
"""


def test_cli_best_effort_reports_an_unavailable_derivation_and_stops(tmp_path):
    write_model(tmp_path / "m.txt", CHAIN)
    args = ["m.txt", "5", "--trace", "d", "--max-retained", "2", "--trace-best-effort"]
    r = run_py(args + ["--stop-on-found"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "first appearing at step 3" in r.stdout and "derivation unavailable" in r.stdout
    assert "STEP 3" in r.stdout and "STEP 4" not in r.stdout
    r = run_py(args, tmp_path)  # without the stop flag the run continues to the end
    assert r.returncode == 0 and "derivation unavailable" in r.stdout and "STEP 5" in r.stdout


def test_cli_retention_limit_without_best_effort_is_still_a_limit_stop(tmp_path):
    write_model(tmp_path / "m.txt", CHAIN)
    r = run_py(["m.txt", "5", "--trace", "d", "--max-retained", "2"], tmp_path)
    assert r.returncode == 3 and "max-retained" in r.stderr


# -- 6. streaming keeps mark records in baseline order ---------------------------------------------------------------


def marking(s, c, ctx):
    ctx.mark("t")
    return True


marking.pure = True


def run_marks(streaming):
    settings = Settings(**NOFILTER)
    settings.filter_next = marking
    sim = gcrsim.Simulator(gcrsim.parse_model(TWO), settings, write=lambda t: None, retain=True, streaming=streaming)
    sim.step()
    return sim


def test_streaming_mark_records_are_in_baseline_order():
    base, fast = run_marks(False), run_marks(True)
    as_tuples = lambda sim: [(m.step, m.component, m.string, m.label) for m in sim.marks]
    assert as_tuples(base) == as_tuples(fast) == [(1, 0, "B", "t"), (1, 1, "A", "t")]
    d1 = base.trace_many([(m.component, m.string, m.step) for m in base.marks])
    d2 = fast.trace_many([(m.component, m.string, m.step) for m in fast.marks])
    assert [[(x.step, x.result) for x in c] for c in d1] == [[(x.step, x.result) for x in c] for c in d2]


def test_streaming_max_marks_counts_pending_marks():
    settings = Settings(**NOFILTER)
    settings.filter_next = marking
    sim = gcrsim.Simulator(gcrsim.parse_model(TWO), settings, write=lambda t: None, streaming=True, max_marks=1)
    with pytest.raises(LimitReached) as exc:
        sim.step()
    assert exc.value.limit == "max-marks"


def test_streaming_and_baseline_cli_output_are_identical_with_marks(tmp_path):
    write_model(tmp_path / "m.txt", TWO)
    (tmp_path / "c.py").write_text(
        "def filter_next(s, c, ctx):\n    ctx.mark('t')\n    ctx.report('seen ' + s)\n    return True\n"
        "filter_next.pure = True\n"
    )
    a = run_py(["m.txt", "2", "--python-filter", "c.py", "--trace-marks"], tmp_path)
    b = run_py(["m.txt", "2", "--python-filter", "c.py", "--trace-marks", "--streaming"], tmp_path)
    assert a.returncode == b.returncode == 0, b.stderr
    assert a.stdout == b.stdout
    assert "Marks (2, 2 distinct):" in a.stdout


def test_streaming_marks_after_an_aborted_step_do_not_leak():
    settings = Settings(**NOFILTER)
    settings.filter_next = marking
    sim = gcrsim.Simulator(gcrsim.parse_model(TWO), settings, write=lambda t: None, streaming=True, max_step_accepted=1)
    with pytest.raises(LimitReached):
        sim.step()
    assert sim.marks == []  # pending marks of the incomplete step were not committed


# -- 7. candidates are counted without a limit ----------------------------------------------------------------------------


@pytest.mark.parametrize("limit", [None, 100])
@pytest.mark.parametrize("streaming", [False, True])
def test_candidates_are_counted(limit, streaming):
    sim = sim_of("""[axioms]
1 = ["a"]

[rules]
a->b
""", max_step_candidates=limit, streaming=streaming)
    sim.step()
    assert sim.last_candidates == 1


def test_progress_reports_generated_candidates(tmp_path):
    write_model(tmp_path / "m.txt", """[axioms]
1 = ["a"]

[rules]
a->b
""")
    r = run_py(["m.txt", "1", "--progress"], tmp_path)
    assert "candidates 1," in r.stderr
