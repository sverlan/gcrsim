"""examples/real: the research models, written as insertions / deletions / substitutions.

Each translated rule is preceded by a ``# old:`` comment with the original rule. The tests rebuild the original
model from those comments and check that both give the same contents, and that the plain ones pass --cross-check.
"""
import re
from pathlib import Path

import pytest

import gcrsim
from conftest import ROOT
from gcrsim.verify import Verifier

REAL = Path(ROOT) / "examples" / "real"
MODELS = sorted(REAL.glob("*/*.txt"))
TRANSLATED = [p for p in MODELS if "# old: " in p.read_text(encoding="utf-8")]   # the models with the old rules in comments
TRANSLATED_LINE = re.compile(r"^(\d*,)?(ins|del|sub)\(")


def old_variant(text):
    """The model with every '# old:' rule restored and the rules translated from it removed."""
    out, skipping = [], False
    for line in text.split("\n"):
        if line.startswith("# old: "):
            out.append(line[len("# old: "):])
            skipping = True
            continue
        if skipping and TRANSLATED_LINE.match(line):
            continue
        skipping = False
        out.append(line)
    return "\n".join(out)


def run(text, steps, settings=None):
    model = gcrsim.parse_model(text)
    st = settings or gcrsim.settings.settings_for_model(model)
    st.reject_strings, st.print_hide, st.reject_max_len, st.print_max_len = "", "", 1000, 1000
    sim = gcrsim.Simulator(model, st, write=lambda t: None, max_step_candidates=2_000_000)
    out = []
    for _ in range(steps):
        sim.step()
        out.append(sim.strings())
    return out


def names(paths):
    return [str(p.relative_to(REAL)) for p in paths]


@pytest.mark.parametrize("path", MODELS, ids=names(MODELS))
def test_the_model_loads_with_its_configuration(path):
    model = gcrsim.parse_model_file(str(path))
    conf = path.with_name(path.stem + "_conf.toml")
    if conf.exists():
        gcrsim.load_config(str(conf), model=model)
    assert any(model.axioms)


@pytest.mark.parametrize("path", TRANSLATED, ids=names(TRANSLATED))
def test_old_rules_and_translated_rules_give_the_same_contents(path):
    text = path.read_text(encoding="utf-8")
    assert run(text, 4) == run(old_variant(text), 4)


def has_regex_rules(path):
    return "re(" in "\n".join(l for l in path.read_text(encoding="utf-8").split("\n") if not l.startswith("#"))


PLAIN_MODELS = [p for p in MODELS if not has_regex_rules(p)]   # --cross-check checks the plain fragment only


@pytest.mark.parametrize("path", PLAIN_MODELS, ids=names(PLAIN_MODELS))
def test_models_without_regex_rules_pass_verify(path):
    text = path.read_text(encoding="utf-8")
    model = gcrsim.parse_model(text)
    st = gcrsim.settings.settings_for_model(model)
    st.reject_strings, st.print_hide, st.reject_max_len, st.print_max_len = "", "", 1000, 1000
    st.filters = {}  # --cross-check checks the rules, not the conditions of the settings
    sim = gcrsim.Simulator(model, st, write=lambda t: None, max_step_candidates=2_000_000)
    verifier = Verifier(sim)
    for _ in range(3):
        sim.step()
        verifier.check_step()


def test_noncf110110_accepts_its_input_in_twelve_steps():
    model = gcrsim.parse_model_file(str(REAL / "noncf110110" / "noncf110110.txt"))
    sim = gcrsim.Simulator(model, gcrsim.settings.settings_for_model(model), write=lambda t: None, max_step_candidates=2_000_000)
    sim.run(12)
    assert [(m.label, m.string, m.step) for m in sim.marks] == [("accepted", "x", 12)]
