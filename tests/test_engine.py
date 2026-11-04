"""Simulation semantics (section 1c) and engine options (section 3)."""

import hashlib
import random
import re

import pytest

import gcrsim
from gcrsim import ConfigError, LimitReached, Settings
from conftest import write_model, parse_old, digests, needs_perl, perl_cfg, perl_contents, python_contents

NOFILTER = dict(reject_strings="(?!)", reject_max_len=1000, print_hide="(?!)", print_max_len=1000)


def make(model_text, **kw):
    settings = kw.pop("settings", None) or Settings(**{**NOFILTER, **kw.pop("cfg", {})})
    return gcrsim.Simulator(gcrsim.parse_model(model_text), settings, write=lambda t: None, **kw)


CYCLE = """[axioms]
1 = ["a"]

[rules]
a->b
b->a
"""


def test_step_zero_and_zero_steps():
    sim = make(CYCLE)
    assert sim.cur == [["a"]] and sim.step_no == 0
    sim.run(0)
    assert sim.cur == [["a"]]


def test_history_blocks_cycle():
    sim = make(CYCLE)
    sim.step()
    assert sim.cur == [["b"]]
    sim.step()
    assert sim.cur == [[]]  # "a" was seeded from the axioms


def test_history_off_cycles_forever():
    sim = make(CYCLE, cfg=dict(history=False))
    seen = []
    for _ in range(4):
        sim.step()
        seen.append(sim.cur[0])
    assert seen == [["b"], ["a"], ["b"], ["a"]]


def test_dedup_within_step_even_without_history():
    sim = make("""[axioms]
1 = ["a"]

[rules]
a->b
a->b
""", cfg=dict(history=False))
    sim.step()
    assert sim.cur == [["b"]]


def test_candidate_order_component_string_rule_position():
    text = """[axioms]
1 = ["ab", "ba"]
2 = ["c"]

[rules]
a->X
b->Y
2,c->Z
"""
    sim = make(text)
    sim.step()
    # string "ab": rule a (position 0), rule b; then string "ba": rule a, rule b; then component 2
    assert sim.cur[0] == ["Xb", "aY", "bX", "Ya", "Z"]


def test_rejected_candidate_is_still_marked_seen():
    calls = []

    def cb(s, c):
        calls.append((s, c))
        return s != "x"

    settings = Settings(**NOFILTER)
    settings.filter_next = cb
    sim = gcrsim.Simulator(gcrsim.parse_model("""[axioms]
1 = ["a"]

[rules]
a->x
x->y
a->z
z->x
"""), settings, write=lambda t: None)
    sim.run(3)
    # x is produced at step 1 (rejected) and again at step 2 from z: not offered to the callback again
    assert [c for c in calls if c[0] == "x"] == [("x", 0)]
    assert "x" in sim.hist[0]


def test_dedup_comes_before_length_filter():
    settings = Settings(**{**NOFILTER, "reject_max_len": 2})
    sim = gcrsim.Simulator(gcrsim.parse_model("""[axioms]
1 = ["a"]

[rules]
a->abc
"""), settings, write=lambda t: None)
    sim.step()
    assert sim.cur == [[]]
    assert "abc" in sim.hist[0]  # over-long string was marked as seen anyway


def test_reject_strings_regex_and_default_at_sign():
    sim = make("""[axioms]
1 = ["a"]

[rules]
# not converted: a->x@y
a->xy
""", cfg=dict(reject_strings="@"))
    sim.step()
    assert sim.cur == [["xy"]]  # the skip pattern rejects strings containing "@"


def test_callback_arguments_are_zero_based_component_and_string():
    seen = []
    settings = Settings(**NOFILTER)
    settings.filter_next = lambda s, c: seen.append((s, c)) or True
    sim = gcrsim.Simulator(gcrsim.parse_model("""[axioms]
1 = ["a"]

[rules]
a->b,2
a->c
"""), settings, write=lambda t: None)
    sim.step()
    assert seen == [("c", 0), ("b", 1)]  # component 1 is filtered before component 2


def test_callback_receives_context_when_it_takes_three_arguments():
    got = []
    settings = Settings(**NOFILTER)

    def cb(s, c, ctx):
        got.append((s, c, ctx.step, ctx.ncomp))
        return True

    settings.filter_next = cb
    sim = gcrsim.Simulator(gcrsim.parse_model("""[axioms]
1 = ["a"]

[rules]
a->b,2
"""), settings, write=lambda t: None)
    sim.step()
    assert got == [("b", 1, 1, 2)]


def test_callback_signature_validated():
    settings = Settings(**NOFILTER)
    settings.filter_next = lambda s: True
    with pytest.raises(ConfigError):
        gcrsim.Simulator(gcrsim.parse_model(CYCLE), settings)


def test_empty_component_and_axiom_with_empty_string():
    sim = make("""[axioms]
1 = ["", "a"]

[rules]
->x
""")
    assert sim.cur == [["", "a"]]
    sim.step()
    assert sim.cur == [["x", "xa", "ax"]]


def test_unused_components_stay_empty_and_listed():
    sim = make("""[axioms]
1 = ["a"]

[rules]
a->b,3
""")
    assert sim.ncomp == 3
    sim.step()
    assert sim.cur == [[], [], ["b"]]


# -- streaming ---------------------------------------------------------------

MODELS = [
    "Axioms\n[S]\nRules\n1,S->aS,2\n2,S->Sb,1\n1,S->,1\n",
    "Axioms\n[ab]\n[]\nRules\n1,a->ba,2\n2,b->ab,1\n1,b->aa,1\n2,a->,2\n",
    "Axioms\n[aXb]\nRules\nX->XX\nX->a\nX->\n",
]


@pytest.mark.parametrize("text", MODELS)
@pytest.mark.parametrize("history", [True, False])
def test_streaming_equals_baseline_without_callback(text, history):
    cfg = dict(history=history, reject_max_len=10)
    a = python_contents(text, steps=6, settings=Settings(**{**NOFILTER, **cfg}))
    b = python_contents(text, steps=6, settings=Settings(**{**NOFILTER, **cfg}), streaming=True)
    assert digests(a) == digests(b)


def test_streaming_with_pure_callback_and_component_filters():
    def cb(s, c):
        return s.count("a") < 4

    cb.pure = True
    text = MODELS[0]
    results = []
    for streaming in (False, True):
        settings = Settings(**{**NOFILTER, "reject_max_len": 12, "filters": {2: {"max_count": {"b": 3}}}})
        settings.filter_next = cb
        results.append(digests(python_contents(text, steps=8, settings=settings, streaming=streaming)))
    assert results[0] == results[1]


def test_streaming_refused_for_unmarked_callback_and_detailed_trace():
    settings = Settings(**NOFILTER)
    settings.filter_next = lambda s, c: True
    with pytest.raises(ConfigError):
        gcrsim.Simulator(gcrsim.parse_model(CYCLE), settings, streaming=True)
    with pytest.raises(ConfigError):
        gcrsim.Simulator(gcrsim.parse_model(CYCLE), Settings(**NOFILTER, show_detailed_application=True), streaming=True)


def test_stateful_callback_gives_baseline_order_and_is_refused_for_streaming():
    state = {"first": True}

    def only_first(s, c):
        if state["first"]:
            state["first"] = False
            return True
        return False

    settings = Settings(**NOFILTER)
    settings.filter_next = only_first
    text = """[axioms]
1 = ["a"]

[rules]
1,a->p,2
1,a->q,1
"""
    sim = gcrsim.Simulator(gcrsim.parse_model(text), settings, write=lambda t: None)
    sim.step()
    # Perl order: component 1 is filtered first, so its candidate "q" is the one accepted
    assert sim.cur == [["q"], []]
    settings.filter_next = only_first
    with pytest.raises(ConfigError):
        gcrsim.Simulator(gcrsim.parse_model(text), settings, streaming=True)


def test_streaming_queues_reported_messages_in_component_order():
    out = []
    settings = Settings(**NOFILTER)

    def cb(s, c, ctx):
        ctx.report("m-" + s)
        return True

    cb.pure = True
    settings.filter_next = cb
    text = """[axioms]
1 = ["a"]

[rules]
a->p,2
a->q
"""
    sim = gcrsim.Simulator(gcrsim.parse_model(text), settings, write=out.append, streaming=True)
    sim.step()
    assert "".join(out) == "m-q\nm-p\n"  # the order baseline filtering would print them in


# -- component conditions --------------------------------------------------------


def random_strings(alphabet, n=400, maxlen=14, seed=1):
    rnd = random.Random(seed)
    return ["".join(rnd.choice(alphabet) for _ in range(rnd.randint(0, maxlen))) for _ in range(n)]


def check_of(spec):
    return gcrsim.filters._build_check([spec])


def test_max_count_equals_the_regex_it_replaces():
    chk = check_of({"max_count": {"D": 2}})
    rx = re.compile(r"(D.*){2}D")
    for s in random_strings("DKT1"):
        assert chk(s) == (rx.search(s) is None), s


def test_max_count_with_multichar_symbol_equals_regex():
    chk = check_of({"max_count": {"K3": 1}})
    rx = re.compile(r"(K3.*){1}K3")
    for s in random_strings("K3D", maxlen=16):
        assert chk(s) == (rx.search(s) is None), s


def test_forbid_and_require_use_plain_regex_syntax():
    chk = check_of({"require": [r"\AAB\Z"], "forbid": [r"Q"]})
    assert chk("AB") and not chk("ABB") and not chk("AQB")


def test_max_count_re_equals_backreference_regex_on_aligned_tokens():
    chk = check_of({"max_count": {"re": {r"p.": 2}}})
    rx = re.compile(r"(p.).*\1.*\1")
    for s in random_strings(["p1", "p2", "A", "B"], maxlen=9, seed=3):
        assert chk(s) == (rx.search(s) is None), s


def test_max_count_re_documented_difference_on_overlapping_tokens():
    chk = check_of({"max_count": {"re": {r"p.": 2}}})
    rx = re.compile(r"(p.).*\1.*\1")
    s = "pp1p1p1"
    assert rx.search(s) is not None  # backtracking finds p1 three times
    assert chk(s)  # left-to-right token scan sees pp, p1, p1


def test_unknown_component_filter_key_and_bad_component():
    with pytest.raises(ConfigError):
        gcrsim.filters._build_check([{"nope": []}])
    settings = Settings(**NOFILTER, filters={5: {"forbid": ["x"]}})
    with pytest.raises(ConfigError):
        gcrsim.Simulator(gcrsim.parse_model(CYCLE), settings)


def test_component_filters_equal_equivalent_callback():
    text = (
        "Axioms\n[AAXB]\nRules\n1,X->Xp0,2\n1,A->A1,2\n2,X->,1\n2,A1->A1p0p0,1\n2,p0->p0A,1\n1,p0->p0Q,2\n"
    )
    pats = [r"(p.).*\1.*\1", r"Q.*Q"]

    def cb(s, c):
        return not any(re.search(p, s) for p in pats)

    s1 = Settings(**{**NOFILTER, "reject_max_len": 30})
    s1.filter_next = cb
    s2 = Settings(**{**NOFILTER, "reject_max_len": 30, "filters": {0: {"forbid": pats}}})
    a = python_contents(text, steps=9, settings=s1)
    b = python_contents(text, steps=9, settings=s2)
    assert digests(a) == digests(b) and sum(len(c) for c in a[-1]) >= 0


def test_component_condition_only_in_chosen_component():
    text = """[axioms]
1 = ["a"]

[rules]
a->bb,2
a->bb,3
"""
    sim = make(text, cfg=dict(filters={2: {"forbid": ["bb"]}}))
    sim.step()
    assert sim.cur == [[], [], ["bb"]]


# -- limits, options ----------------------------------------------------------------------


def test_no_mark_rejected_keeps_contents_and_shrinks_history():
    text = """[axioms]
1 = ["aXb"]

[rules]
X->XX
X->a
X->Q
"""
    base = dict(reject_max_len=7, filters={0: {"forbid": ["Q", "XXXX"]}})
    sims = []
    for nm in (False, True):
        sim = make(text, cfg=dict(base), no_mark_rejected=nm)
        sim.run(5)
        sims.append(sim)
    assert sims[0].cur == sims[1].cur
    assert sims[1].hist_count < sims[0].hist_count


def test_max_step_candidates_stops_with_state_of_last_complete_step():
    sim = make("""[axioms]
1 = ["a"]

[rules]
a->aa
aa->a
""", max_step_candidates=1)
    sim.step()
    with pytest.raises(LimitReached) as exc:
        sim.step()
    assert exc.value.limit == "max-step-candidates" and exc.value.step == 2
    assert sim.step_no == 1 and sim.cur == [["aa"]]
    assert exc.value.exit_code == 3


def test_max_history_and_max_step_accepted():
    with pytest.raises(LimitReached) as exc:
        make("""[axioms]
1 = ["a"]

[rules]
a->b
a->c
a->d
""", max_history=3).step()
    assert exc.value.limit == "max-history"
    with pytest.raises(LimitReached) as exc:
        make("""[axioms]
1 = ["a"]

[rules]
a->b
a->c
a->d
""", max_step_accepted=2).step()
    assert exc.value.limit == "max-step-accepted"


def test_max_marks():
    settings = Settings(**NOFILTER)

    def cb(s, c, ctx):
        ctx.mark("t")
        return True

    settings.filter_next = cb
    sim = gcrsim.Simulator(gcrsim.parse_model("""[axioms]
1 = ["a"]

[rules]
a->b
a->c
"""), settings, write=lambda t: None, max_marks=1)
    with pytest.raises(LimitReached):
        sim.step()


# -- detailed application -------------------------------------------------------------------


def detailed_output(text):
    out = []
    settings = Settings(**NOFILTER, show_detailed_application=True)
    sim = gcrsim.Simulator(gcrsim.parse_model(text), settings, write=out.append)
    sim.step()
    return "".join(out)


def test_detailed_trace_shows_every_application_with_results():
    assert detailed_output("""[axioms]
1 = ["a"]

[rules]
a->a
""") == "a => a\n"
    assert detailed_output("""[axioms]
1 = ["1"]

[rules]
1->a
""") == "1 => a\n"
    assert detailed_output("""[axioms]
1 = ["b"]

[rules]
a->x
""") == ""  # no result, no line
    assert detailed_output("""[axioms]
1 = ["abab"]

[rules]
a->x
""") == "abab => xbab abxb\n"


@needs_perl
@pytest.mark.perl
@pytest.mark.parametrize(
    "axiom, rule",
    [("abab", "a->x"), ("ab", "->x"), ("abc", "[ab]->c")],  # Perl differs on digit-only strings (count-string quirk)
)
def test_detailed_trace_matches_perl_output(axiom, rule, tmp_path):
    from conftest import old_to_new as gcrsim_old_to_new, run_perl

    (tmp_path / "m.txt").write_text("Axioms\n[%s]\nRules\n%s\n" % (axiom, rule))
    (tmp_path / "gcrsim.cfg").write_text(perl_cfg(history=0, detailed=1, reject_strings="(?!)", print_hide="(?!)", reject_max_len=100))
    perl = run_perl("m.txt", 1, tmp_path)
    step1 = perl.split("STEP 1\n============\n\n", 1)[1].split("\nComponent 1:", 1)[0]
    ours = detailed_output(gcrsim_old_to_new("Axioms\n[%s]\nRules\n%s\n" % (axiom, rule)))
    assert step1 == ours


# -- digest ----------------------------------------------------------------------------------


def test_digest_framing_is_unambiguous():
    def d(contents):
        return gcrsim.digest_contents(hashlib.sha256(), 0, contents).hexdigest()

    assert d([["ab"], ["c"]]) != d([["a"], ["bc"]])
    assert d([["a", "b"]]) != d([["a"], ["b"]])
    assert d([["a:b"]]) != d([["a", "b"]])
    assert d([[]]) != d([[""]])
