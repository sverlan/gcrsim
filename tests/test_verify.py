"""``--cross-check``: the reference interpreter next to the engine."""
import pytest

import gcrsim
from gcrsim import Settings, parse_model
from gcrsim.verify import VerificationError, Verifier
from conftest import run_py

PLAIN = """[axioms]
1 = ["S"]

[rules]
S->aSb,2
S->
ins(a,X,b),2;forbid:Z
[rules.2]
send(),1;permit:a
"""
NOFILTER = dict(history=True, reject_strings="", reject_max_len=16, print_hide="", print_max_len=16)


def test_verify_runs_a_plain_model(tmp_path):
    (tmp_path / "m.txt").write_bytes(PLAIN.encode("utf-8"))
    r = run_py(["m.txt", "5", "--cross-check", "--quiet"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "verified 5 step(s)" in r.stderr


def test_verify_refuses_what_it_cannot_check(tmp_path):
    (tmp_path / "re.txt").write_bytes(b'[axioms]\n1 = ["ab"]\n[rules]\nre(a.)->X\n')
    r = run_py(["re.txt", "2", "--cross-check"], tmp_path)
    assert r.returncode == 2 and "plain fragment" in r.stderr and "regular-expression rule" in r.stderr
    (tmp_path / "p.txt").write_bytes(b'[axioms]\n1 = ["ab"]\n[rules]\na->X\n')
    (tmp_path / "p_conf.toml").write_text('[model]\nreject_strings = "X"\n')
    r = run_py(["p.txt", "2", "--cross-check", "--config", "p_conf.toml"], tmp_path)
    assert r.returncode == 2 and "reject_strings" in r.stderr


def test_verify_notices_a_wrong_engine():
    sim = gcrsim.Simulator(parse_model(PLAIN), Settings(**NOFILTER), write=lambda t: None)
    verifier = Verifier(sim)
    rule = sim.rules[0][0]
    good = rule.expand
    rule.expand = lambda s: list(good(s))[:-1] if len(good(s)) > 1 else good(s)  # drop one candidate
    sim.rules[0][2].expand = lambda s: []  # a rule that never fires
    with pytest.raises(VerificationError):
        for _ in range(4):
            sim.step()
            verifier.check_step()


def test_verify_notices_a_wrong_candidate_count():
    sim = gcrsim.Simulator(parse_model(PLAIN), Settings(**NOFILTER), write=lambda t: None)
    verifier = Verifier(sim)
    sim.step()
    sim.last_candidates += 1
    with pytest.raises(VerificationError, match="candidates"):
        verifier.check_step()
