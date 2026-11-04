"""Lazy trace-back, batch tracing and marks."""

import pytest

import gcrsim
from gcrsim import LimitReached, Settings, TraceError
from conftest import parse_old, write_model, EXAMPLES, needs_perl, perl_cfg, perl_contents, run_py

NOFILTER = dict(reject_strings="(?!)", reject_max_len=1000, print_hide="(?!)", print_max_len=1000)
ANBN = """[axioms]
1 = ["S"]

[rules]
S->aS,2
2,S->Sb
S->
"""


def sim_for(text, steps, cfg=None, callback=None, **kw):
    settings = Settings(**{**NOFILTER, **(cfg or {})})
    settings.filter_next = callback
    sim = gcrsim.Simulator(gcrsim.parse_model(text), settings, write=lambda t: None, retain=kw.pop("retain", True), **kw)
    sim.run(steps)
    return sim


def replay(sim, derivation, component, string):
    """Check a derivation: each rule applied at its position gives the child."""
    assert derivation, "empty derivation"
    cur = sim.model.axioms
    assert derivation[0].source in cur[derivation[0].source_component]
    for i, d in enumerate(derivation):
        assert d.step == i + 1
        s = d.source
        assert d.rule.source == d.source_component and d.rule.target == d.target_component
        spans = d.rule.spans(s)
        assert (d.start, d.end, d.result) in spans
        if i + 1 < len(derivation):
            assert derivation[i + 1].source == d.result
            assert derivation[i + 1].source_component == d.target_component
    assert derivation[-1].result == string and derivation[-1].target_component == component


def test_trace_replays_to_the_axiom():
    sim = sim_for(ANBN, 7)
    target = "aaabbb"
    comp = 0
    step = sim.find_step(comp, target)
    assert step == 7
    d = sim.trace(target, comp)
    assert len(d) == step
    replay(sim, d, comp, target)


def test_trace_of_axiom_is_empty():
    sim = sim_for(ANBN, 2)
    assert sim.trace("S", 0) == []


def test_trace_is_a_shortest_derivation():
    # "ab" is reachable in 3 steps; the derivation must have exactly its first-appearance step
    sim = sim_for(ANBN, 8)
    assert len(sim.trace("ab", 0)) == sim.find_step(0, "ab") == 3


def test_batch_equals_single_traces():
    sim = sim_for(ANBN, 8)
    targets = [(0, "ab", None), (0, "aabb", None), (1, "aS", None), (0, "aaabbb", None)]
    batch = sim.trace_many(targets)
    for (comp, string, _), chain in zip(targets, batch):
        single = sim.trace(string, comp)
        assert [(d.step, d.source, d.start, d.result, d.rule.index) for d in chain] == [
            (d.step, d.source, d.start, d.result, d.rule.index) for d in single
        ]
        replay(sim, chain, comp, string)


def test_parent_is_the_first_discoverer():
    # "c" is produced from "ab" (rule 1) and from "ba" (rule 2); the first in generation order wins
    text = """[axioms]
1 = ["ab", "ba"]

[rules]
ab->c
ba->c
"""
    sim = sim_for(text, 1)
    d = sim.trace("c", 0)
    assert d[0].source == "ab"


def test_trace_requires_retention():
    sim = sim_for(ANBN, 3, retain=False)
    with pytest.raises(TraceError):
        sim.trace("ab", 0)


def test_trace_unknown_string():
    sim = sim_for(ANBN, 3)
    with pytest.raises(TraceError):
        sim.trace("zzz", 0)


def test_empty_steps_are_not_retained():
    sim = sim_for("""[axioms]
1 = ["a"]

[rules]
a->b
""", 5)
    assert sorted(sim.retained) == [0, 1]
    assert sim.retained_count == 2


def test_retention_off_by_default_even_with_history_off():
    sim = sim_for(
        """[axioms]
1 = ["a"]

[rules]
a->b
b->a
""", 50, cfg=dict(history=False), retain=False
    )
    assert sim.retained == {} and sim.retained_count == 0


def test_retention_limit_stops_the_run():
    with pytest.raises(LimitReached) as exc:
        sim_for("""[axioms]
1 = ["a"]

[rules]
a->b
b->a
""", 50, cfg=dict(history=False), max_retained=10)
    assert exc.value.limit == "max-retained"


def test_retention_best_effort_continues_without_tracing():
    sim = sim_for("""[axioms]
1 = ["a"]

[rules]
a->b
b->a
""", 50, cfg=dict(history=False), max_retained=10, trace_best_effort=True)
    assert sim.step_no == 50 and sim.trace_lost_from is not None
    assert sim.retained_count <= 10
    with pytest.raises(TraceError):
        sim.trace("a", 0, step=50)


# -- marks ---------------------------------------------------------------------------------------


def marking_callback(s, c, ctx):
    if c == 0 and set(s) <= set("ab"):
        ctx.mark("terminal")
    return True


def test_marks_record_step_component_string_label():
    sim = sim_for(ANBN, 5, callback=marking_callback)
    got = [(m.step, m.component, m.string, m.label) for m in sim.marks]
    assert got == [(1, 0, "", "terminal"), (3, 0, "ab", "terminal"), (5, 0, "aabb", "terminal")]


def test_marked_but_rejected_string_still_traces():
    def cb(s, c, ctx):
        if s == "ab":
            ctx.mark("target")
            return False
        return True

    sim = sim_for(ANBN, 4, callback=cb)
    assert len(sim.marks) == 1 and sim.marks[0].step == 3
    assert "ab" not in sim.cur[0]
    m = sim.marks[0]
    d = sim.trace(m.string, m.component, m.step)
    assert d[-1].result == "ab" and len(d) == 3


def test_marks_with_history_on_are_unique_per_component_and_off_repeat_in_cycles():
    text = """[axioms]
1 = ["a"]

[rules]
a->a
"""

    def cb(s, c, ctx):
        ctx.mark("seen")
        return True

    on = sim_for(text, 4, callback=cb)  # history on
    assert len(on.marks) == 0  # "a" was seeded: never a new candidate
    off = sim_for(text, 4, callback=cb, cfg=dict(history=False))
    assert [m.step for m in off.marks] == [1, 2, 3, 4]


def test_same_string_marked_in_two_components():
    text = """[axioms]
1 = ["a"]

[rules]
a->x
a->x,2
"""

    def cb(s, c, ctx):
        ctx.mark("t")
        return True

    sim = sim_for(text, 1, callback=cb)
    assert sorted((m.component, m.string) for m in sim.marks) == [(0, "x"), (1, "x")]


def test_batch_trace_of_marks_levels():
    sim = sim_for(ANBN, 7, callback=marking_callback)
    chains = sim.trace_many([(m.component, m.string, m.step) for m in sim.marks])
    for m, chain in zip(sim.marks, chains):
        assert len(chain) == m.step
        replay(sim, chain, m.component, m.string)


# -- command line ----------------------------------------------------------------------------------


def test_cli_trace_option_prints_derivation(tmp_path):
    p = tmp_path / "m.txt"
    write_model(p, ANBN)
    r = run_py([str(p), "6", "--trace", "aabb"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "Trace of 'aabb' (component 1), first appearing at step 5:" in r.stdout
    assert "step 5: aaSbb => aabb" in r.stdout


def test_cli_stop_on_found_completes_the_step(tmp_path):
    p = tmp_path / "m.txt"
    write_model(p, ANBN)
    r = run_py([str(p), "20", "--trace", "ab", "--stop-on-found"], tmp_path)
    assert r.returncode == 0
    assert "STEP 3" in r.stdout and "STEP 4" not in r.stdout
    # the step's listing is complete: it ends with component 2 of step 3
    body = r.stdout.split("STEP 3", 1)[1]
    assert "Component 1:" in body and "Component 2:" in body and "aaSb" in body


def test_cli_trace_not_found(tmp_path):
    p = tmp_path / "m.txt"
    write_model(p, ANBN)
    r = run_py([str(p), "3", "--trace", "zzz"], tmp_path)
    assert "not found in the steps run" in r.stdout


def test_cli_marks_with_and_without_retention():
    cwd = EXAMPLES
    r = run_py(["an_bn_marks.txt", "5", "--trace-marks"], cwd)
    assert r.returncode == 0, r.stderr
    assert "Mark [terminal] at step 5, component 1: aabb" in r.stdout
    assert "step 5: aaSbb => aabb" in r.stdout
    assert "Marks (3, 3 distinct):" in r.stdout
    r = run_py(["an_bn_marks.txt", "5"], cwd)
    assert "Mark [terminal]" not in r.stdout  # no per-mark blocks without retention
    assert "Mark (terminal): aabb" in r.stdout  # the inline mark line stays
    assert "Marks (3, 3 distinct):" in r.stdout and "run with --trace-marks to see how each was derived" in r.stdout
    r = run_py(["an_bn_marks.txt", "5", "--no-mark-summary"], cwd)
    assert "Marks (" not in r.stdout and "Mark (terminal): aabb" in r.stdout


def test_cli_stop_on_mark(tmp_path):
    r = run_py(["an_bn_marks.txt", "20", "--stop-on-mark"], EXAMPLES)
    assert "STEP 1" in r.stdout and "STEP 2" not in r.stdout  # the empty word is marked at step 1


def test_cli_stop_on_found_needs_trace(tmp_path):
    p = tmp_path / "m.txt"
    write_model(p, ANBN)
    r = run_py([str(p), "3", "--stop-on-found"], tmp_path)
    assert r.returncode == 2 and "--trace" in r.stderr
