"""The engine against the reference interpreter on every *surface form* of the plain fragment.

``test_reference.py`` renders every rule as ``sub(...)`` in numbered sections.  Here the same random
rules are written in whichever of ``plain``, ``ins``, ``del`` and ``sub`` applies, in numbered or in the
general ``Rules`` section (with and without the optional prefix and target), with the engine's other
execution paths (streaming, a candidate limit) and with overlapping lexemes read by an independent
tokeniser.
"""
import random

import pytest

import gcrsim
from gcrsim import _reference as ref
from gcrsim import Settings, parse_model

from test_reference import (
    CLASSES, SYMBOLS, item_text, random_item, random_rule, seq_text,
)

LITERAL = set(SYMBOLS)


def guards_text(r):
    out = ""
    if r.permit:
        out += ";permit:" + ",".join("".join(w) for w in r.permit)
    if r.forbid:
        out += ";forbid:" + ",".join("".join(w) for w in r.forbid)
    if r.permit_any:
        out += ";permit-any:" + ",".join("".join(w) for w in r.permit_any)
    return out


def surface(r, rng):
    """The rule body (without prefix and target) in a randomly chosen applicable form."""
    if r.kind == "send":
        return "send()"
    options = ["sub(%s,%s,%s,%s)" % (seq_text(r.u), seq_text(r.x), "".join(r.y), seq_text(r.v))]
    if not r.x:
        options.append("ins(%s,%s,%s)" % (seq_text(r.u), "".join(r.y), seq_text(r.v)))
    if not r.y:
        options.append("del(%s,%s,%s)" % (seq_text(r.u), seq_text(r.x), seq_text(r.v)))
    if not r.u and not r.v and all(i in LITERAL for i in r.x):
        options.append("%s->%s" % ("".join(r.x), "".join(r.y)))
    return rng.choice(options)


def render(axioms, rules, rng):
    lines = ["[symbols]", 'lexemes = ["K1"]', "[symbols.classes]"]
    lines += ['%s = "%s"' % (n, " ".join(sorted(m))) for n, m in CLASSES.items()]
    lines += ["", "[axioms]"]
    for c, strings in enumerate(axioms):
        items = [""] * any(not s for s in strings) + ["".join(s) for s in strings if s]
        lines.append("%d = [%s]" % (c + 1, ", ".join('"%s"' % i for i in items)))
    if rng.random() < 0.5:  # numbered sections
        for c in range(len(axioms)):
            lines.append("[rules.%d]" % (c + 1))
            for r in (r for r in rules if r.source == c):
                prefix = "%d," % (c + 1) if rng.random() < 0.3 else ""
                lines.append("%s%s,%d%s" % (prefix, surface(r, rng), r.target + 1, guards_text(r)))
    else:  # the general section: the order of the rules of one component is kept
        lines.append("[rules]")
        for r in rules:
            prefix = "%d," % (r.source + 1) if (r.source != 0 or rng.random() < 0.5) else ""
            guards = guards_text(r)
            target = ",%d" % (r.target + 1) if (r.target != 0 or guards or rng.random() < 0.5) else ""
            lines.append("%s%s%s%s" % (prefix, surface(r, rng), target, guards))
    return "\n".join(lines) + "\n"


def decoded(sim, contents):
    return [[tuple(sim.lexicon.tokens(s)) for s in comp] for comp in contents]


@pytest.mark.parametrize("seed", range(300))
def test_every_surface_form_agrees_with_the_reference(seed):
    rng = random.Random(10_000 + seed)
    ncomp = rng.randint(1, 3)
    axioms = [[tuple(rng.choice(SYMBOLS) for _ in range(rng.randint(0, 3))) for _ in range(rng.randint(0, 2))] for _ in range(ncomp)]
    axioms = [[w for w in dict.fromkeys(a) if not w] + [w for w in dict.fromkeys(a) if w] for a in axioms]
    rules = [random_rule(rng, ncomp) for _ in range(rng.randint(1, 6))]
    history = rng.random() < 0.6
    max_len = rng.choice([None, 4, 6])
    text = render(axioms, rules, rng)
    # the general section keeps the order of the rules of a component, the numbered one too: same reference order
    want = ref.run(axioms, rules, 4, history, max_len)
    settings = dict(history=history, reject_strings="", reject_max_len=max_len if max_len is not None else 10**9, print_hide="", print_max_len=1000)
    for mode in ({}, {"streaming": True}, {"max_step_candidates": 10**7}):
        sim = gcrsim.Simulator(parse_model(text), Settings(**settings), write=lambda t: None, **mode)
        for k in range(1, 5):
            sim.step()
            got = decoded(sim, sim.cur)
            if mode.get("streaming"):  # streaming may order a content differently, never change its content
                assert [sorted(c) for c in got] == [sorted(c) for c in want[k]["contents"]], (seed, k, mode, text)
            else:
                assert got == want[k]["contents"], (seed, k, mode, text)
            assert sim.last_candidates == want[k]["raw"], (seed, k, mode, text)


# -- overlapping lexemes, read by an independent longest-match tokeniser ---------------------------------------------------


def reference_tokens(text, lexemes):
    """Longest match first, otherwise one character: written independently of the engine."""
    out, i = [], 0
    while i < len(text):
        best = max((l for l in lexemes if text.startswith(l, i)), key=len, default=text[i])
        out.append(best)
        i += len(best)
    return out


@pytest.mark.parametrize("seed", range(40))
def test_overlapping_lexemes_are_read_longest_first(seed):
    rng = random.Random(seed)
    lexemes = rng.sample(["ab", "bc", "abc", "ca", "aab", "cc", "bca"], rng.randint(1, 4))
    cfg = "lexemes = [%s]" % ", ".join('"%s"' % l for l in lexemes)
    for _ in range(30):
        text = "".join(rng.choice("abc") for _ in range(rng.randint(0, 9)))
        if not text:
            continue
        model = parse_model('[symbols]\n%s\n[axioms]\n1 = ["%s"]\n[rules]\n1,ins(,x,),1\n' % (cfg, text))
        enc = model.axioms[0][0]
        assert model.lexicon.tokens(enc) == reference_tokens(text, lexemes), (lexemes, text)
        # a single-symbol insertion point is a position between *symbols*, never inside a lexeme
        assert len(model.rules[0][0].edits(enc)) == len(reference_tokens(text, lexemes)) + 1
