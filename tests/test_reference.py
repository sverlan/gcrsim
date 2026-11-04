"""The engine against the independent reference interpreter (SPEC.md), on the plain fragment.

``reference.py`` was written from SPEC.md alone.  The tests render data into a model file, run the
engine on it and compare, step by step, with the reference: exhaustive for single rules over a small
alphabet, seeded random for whole multi-component models.
"""
import itertools
import random

import pytest

import gcrsim
from gcrsim import _reference as ref
from gcrsim import Settings, parse_model

SYMBOLS = ("a", "b", "K1")  # K1 is a lexeme
CLASS_AB = frozenset({"a", "b"})
CLASS_BK = frozenset({"b", "K1"})
CLASSES = {"AB": CLASS_AB, "BK": CLASS_BK}


def item_text(item):
    if item is ref.ANY:
        return "{any}"
    if item is ref.START:
        return "{start}"
    if item is ref.END:
        return "{end}"
    if isinstance(item, frozenset):
        return "{%s}" % next(name for name, members in CLASSES.items() if members == item)
    return item


def seq_text(items):
    return "".join(item_text(i) for i in items)


def rule_text(r, section):
    """One rule line in a ``Rules N`` section (the source component is the section)."""
    guards = ""
    if r.permit:
        guards += ";permit:" + ",".join("".join(w) for w in r.permit)
    if r.forbid:
        guards += ";forbid:" + ",".join("".join(w) for w in r.forbid)
    if r.permit_any:
        guards += ";permit-any:" + ",".join("".join(w) for w in r.permit_any)
    if r.kind == "send":
        return "send(),%d%s" % (r.target + 1, guards)
    return "sub(%s,%s,%s,%s),%d%s" % (seq_text(r.u), seq_text(r.x), "".join(r.y), seq_text(r.v), r.target + 1, guards)


def model_text(axioms, rules):
    lines = ["[symbols]", 'lexemes = ["K1"]', "[symbols.classes]"]
    lines += ['%s = "%s"' % (name, " ".join(sorted(members))) for name, members in CLASSES.items()]
    lines += ["", "[axioms]"]
    for c, strings in enumerate(axioms):
        items = [""] * any(not s for s in strings) + ["".join(s) for s in strings if s]
        lines.append("%d = [%s]" % (c + 1, ", ".join('"%s"' % i for i in items)))
    for c in range(len(axioms)):
        lines.append("[rules.%d]" % (c + 1))
        lines += [rule_text(r, c) for r in rules if r.source == c]
    return "\n".join(lines) + "\n"


def tokens(sim, encoded):
    return tuple(sim.lexicon.tokens(encoded))


def engine_run(axioms, rules, steps, use_history, max_len):
    model = parse_model(model_text(axioms, rules))
    settings = Settings(history=use_history, reject_strings="", reject_max_len=max_len if max_len is not None else 10**9,
                        print_hide="", print_max_len=1000)
    sim = gcrsim.Simulator(model, settings, write=lambda t: None)
    out = [{"contents": [[tokens(sim, s) for s in comp] for comp in sim.cur], "raw": 0}]
    for _ in range(steps):
        sim.step()
        out.append({"contents": [[tokens(sim, s) for s in comp] for comp in sim.cur], "raw": sim.last_candidates})
    return out, sim


def strings_up_to(n, alphabet=SYMBOLS):
    for k in range(n + 1):
        yield from itertools.product(alphabet, repeat=k)


ITEMS = list(SYMBOLS) + [ref.ANY, ref.START, ref.END, CLASS_AB, CLASS_BK]


def sequences(max_len):
    for k in range(max_len + 1):
        yield from itertools.product(ITEMS, repeat=k)


# -- exhaustive: every single sub rule with operands of length <= 1 ------------------------------------------------------------


def test_every_small_sub_rule_agrees_on_every_short_string():
    strings = list(strings_up_to(4))
    ys = [(), ("a",), ("K1", "b")]
    checked = 0
    for u in sequences(1):
        for x in sequences(1):
            for v in sequences(1):
                for y in ys:
                    rule = ref.Rule("sub", 0, 0, u, x, y, v)
                    model = parse_model(model_text([[("a",)]], [rule]))
                    eng = model.rules[0][0]
                    lex = model.lexicon
                    for s in strings:
                        enc = lex.encode("".join(s))
                        want = ref.edits(rule, s)
                        got = eng.edits(enc)
                        assert [(p, q, lex.decode(m)) for p, q, m in got] == [(p, q, "".join(m)) for p, q, m in want], (rule, s)
                        assert [tuple(lex.tokens(c)) for c in eng.expand(enc)] == ref.candidates(rule, s), (rule, s)
                        checked += 1
    assert checked > 100_000


def test_two_item_operands_agree():
    strings = list(strings_up_to(3))
    short = [(), ("a",), ("b", "K1"), (ref.START, "a"), ("b", ref.END), (CLASS_AB, ref.ANY), (ref.ANY, ref.ANY)]
    for u in short:
        for y in short:
            for v in short:
                rule = ref.Rule("sub", 0, 0, u, y, ("b",), v)
                eng = parse_model(model_text([[("a",)]], [rule])).rules[0][0]
                lex = parse_model(model_text([[("a",)]], [rule])).lexicon
                for s in strings:
                    enc = lex.encode("".join(s))
                    assert [tuple(lex.tokens(c)) for c in eng.expand(enc)] == ref.candidates(rule, s), (rule, s)


def test_guards_and_send_agree():
    strings = list(strings_up_to(4))
    for permit, forbid in itertools.product([(), (("a",),), (("a", "b"),), (("K1",), ("b",))], [(), (("b",),), (("K1", "a"),)]):
        for rule in (ref.Rule("sub", 0, 0, (), ("a",), ("b",), (), permit, forbid), ref.Rule("send", 0, 0, permit=permit, forbid=forbid)):
            model = parse_model(model_text([[("a",)]], [rule]))
            eng, lex = model.rules[0][0], model.lexicon
            for s in strings:
                enc = lex.encode("".join(s))
                assert [tuple(lex.tokens(c)) for c in eng.expand(enc)] == ref.candidates(rule, s), (rule, s)
                assert [(p, q, lex.decode(m)) for p, q, m in eng.edits(enc)] == [(p, q, "".join(m)) for p, q, m in ref.edits(rule, s)]


# -- random whole models, step by step -------------------------------------------------------------------------------------


def random_item(rng):
    return rng.choice(ITEMS)


def random_rule(rng, ncomp):
    source, target = rng.randrange(ncomp), rng.randrange(ncomp)
    permit = tuple(tuple(rng.choice(SYMBOLS) for _ in range(rng.randint(1, 2))) for _ in range(rng.choice([0, 0, 1])))
    forbid = tuple(tuple(rng.choice(SYMBOLS) for _ in range(rng.randint(1, 2))) for _ in range(rng.choice([0, 0, 1])))
    any_of = tuple(tuple(rng.choice(SYMBOLS) for _ in range(rng.randint(1, 2))) for _ in range(rng.choice([0, 0, 1, 2])))
    if rng.random() < 0.1:
        return ref.Rule("send", source, target, permit=permit, forbid=forbid, permit_any=any_of)
    u, x, v = (tuple(random_item(rng) for _ in range(rng.randint(0, 2))) for _ in range(3))
    y = tuple(rng.choice(SYMBOLS) for _ in range(rng.randint(0, 3)))
    return ref.Rule("sub", source, target, u, x, y, v, permit, forbid, any_of)


@pytest.mark.parametrize("seed", range(400))
def test_random_models_agree_step_by_step(seed):
    rng = random.Random(seed)
    ncomp = rng.randint(1, 3)
    axioms = [[tuple(rng.choice(SYMBOLS) for _ in range(rng.randint(0, 3))) for _ in range(rng.randint(0, 2))] for _ in range(ncomp)]
    # the axiom syntax writes the empty string first (a leading comma), so the reference gets the same order
    axioms = [[w for w in dict.fromkeys(a) if not w] + [w for w in dict.fromkeys(a) if w] for a in axioms]
    rules = [random_rule(rng, ncomp) for _ in range(rng.randint(1, 6))]
    use_history = rng.random() < 0.6
    max_len = rng.choice([None, 4, 6])
    steps = 4
    want = ref.run(axioms, rules, steps, use_history, max_len)
    got, _ = engine_run(axioms, rules, steps, use_history, max_len)
    for k in range(steps + 1):
        assert got[k]["contents"] == want[k]["contents"], (seed, k, model_text(axioms, rules))
        assert got[k]["raw"] == want[k]["raw"], (seed, k)


# -- the engine's own paths agree with each other ---------------------------------------------------------------------


def test_expand_build_and_spans_agree_for_every_rule_form():
    strings = list(strings_up_to(4))
    rules = [
        ref.Rule("sub", 0, 0, (), ("a", "b"), ("K1",), ()),                      # pure literal: the str.find path
        ref.Rule("sub", 0, 0, ("a",), (), ("b",), ("K1",)),                       # literal insertion
        ref.Rule("sub", 0, 0, (), (), ("b",), ()),                                # empty word
        ref.Rule("sub", 0, 0, (ref.START,), ("a",), (), ()),                      # generic path
        ref.Rule("sub", 0, 0, (CLASS_AB,), (ref.ANY,), ("K1",), (ref.END,)),
        ref.Rule("send", 0, 0),
        ref.Rule("sub", 0, 0, (), ("a",), ("b",), (), (("K1",),), ()),           # guarded
    ]
    for rule in rules:
        model = parse_model(model_text([[("a",)]], [rule]))
        eng, lex = model.rules[0][0], model.lexicon
        for s in strings:
            enc = lex.encode("".join(s))
            built = eng.build(enc, eng.edits(enc))
            assert list(eng.expand(enc)) == built
            assert [res for _, _, res in eng.spans(enc)] == built
            assert len(built) <= len(s) + 1 or rule.kind == "send"
