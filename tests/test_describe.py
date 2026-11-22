"""The describe operation: the size of an insertion-deletion system, the symbols, the control graph."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

import gcrsim
from gcrsim import describe, parse_model

ROOT = Path(__file__).resolve().parents[1]
COOKBOOK = ROOT / "examples" / "cookbook"


def d(text):
    return describe(parse_model(text)).to_dict()


def sz(text):
    return d(text)["size"]


def test_size_one_one_zero_one_one_zero():
    s = sz('[axioms]\n1=["S"]\n[rules]\nins(a,b,c)\nins(a,b,)\ndel(a,b,)\nins(,a,)\n')
    assert s["insdel"] is True and s["other_kinds"] == []
    assert s["ins"] == {"n": 1, "m": 1, "m_right": 1}
    assert s["del"] == {"p": 1, "q": 1, "q_right": 0}


def test_size_ins_only_two_symbols():
    s = sz('[axioms]\n1=["S"]\n[rules]\nins(,ab,)\nins(,a,)\n')
    assert s["ins"] == {"n": 2, "m": 0, "m_right": 0} and s["del"] is None and s["insdel"]
    assert gcrsim._describe.size_tuple(s) == "(2,0,0;0,0,0)"


def test_size_del_only_two_symbols():
    s = sz('[axioms]\n1=["S"]\n[rules]\ndel(,ab,)\n')
    assert s["del"] == {"p": 2, "q": 0, "q_right": 0} and s["ins"] is None


def test_contexts_of_length_two_and_boundaries_and_classes():
    text = ('[symbols]\nalphabet = "a b c"\n[symbols.classes]\nV = ["a","b"]\n[axioms]\n1=["a"]\n[rules]\n'
            'ins(ab,c,{end})\nins({start}{V}a,c,b)\ndel({start},{any}{V},{end})\n')
    s = sz(text)
    assert s["ins"] == {"n": 1, "m": 2, "m_right": 1}
    assert s["del"] == {"p": 2, "q": 0, "q_right": 0}


def test_guards_are_counted_and_noted():
    r = d('[axioms]\n1=["S"]\n[rules]\nins(a,b,c),1;forbid:S\nins(a,b,c),1;permit:S\nins(a,b,c)\n')
    assert r["rules"]["with_conditions"] == 2
    assert any("with conditions" in n for n in r["notes"])
    assert r["size"]["ins"]["n"] == 1


def test_graph_controlled_sizes_and_transitions():
    text = ('[axioms]\n1=["S","T"]\n[rules.1]\nins(a,b,c),2\nins(a,bb,),1\nsend(),2\n[rules.2]\ndel(a,b,c),1\n')
    r = d(text)
    c1, c2 = r["components"]
    assert c1["size"]["ins"] == {"n": 2, "m": 1, "m_right": 1} and c1["size"]["del"] is None
    assert c2["size"]["del"] == {"p": 1, "q": 1, "q_right": 1} and c2["size"]["ins"] is None
    assert c1["targets"] == [{"target": 1, "rules": 1}, {"target": 2, "rules": 2}]
    assert c1["axioms"] == 2 and c2["axioms"] == 0
    assert r["rules"]["by_kind"]["send"] == 1 and r["size"]["insdel"] is True


def test_sub_plain_re_are_not_insdel():
    text = '[axioms]\n1=["S"]\n[rules]\nsub(a,b,c,d)\nS->aS\nre(a+)->b\nins(,a,)\n'
    r = d(text)
    assert r["size"]["insdel"] is False and r["size"]["other_kinds"] == ["sub", "plain", "re"]
    assert r["size"]["ins"] == {"n": 1, "m": 0, "m_right": 0}
    assert r["symbols"]["roles_exact"] is False
    assert any("not an insertion-deletion" in n for n in r["notes"])


def test_roles_and_any():
    text = ('[symbols]\nalphabet = "S a b c d"\n[axioms]\n1=["S"]\n[rules]\n'
            'ins(,a,)\ndel(,b,)\nins(,c,)\ndel(,c,)\nins(d,a,)\n')
    r = d(text)["symbols"]
    assert r["roles"] == {"inserted_only": ["a"], "deleted_only": ["b"], "inserted_and_deleted": ["c"],
                          "never_edited": ["S", "d"]}
    assert r["roles_exact"] is True
    r = d('[axioms]\n1=["S"]\n[rules]\ndel(,{any},)\n')
    assert r["symbols"]["roles_exact"] is False


def test_declared_and_undeclared():
    declared = d('[symbols]\nalphabet = "a b Z"\nterminals = "a b"\n[axioms]\n1=["a"]\n[rules]\nins(a,b,)\n')["symbols"]
    assert declared["declared"] is True and declared["count"] == 3 and declared["terminals"] == ["a", "b"]
    assert declared["roles"]["never_edited"] == ["Z", "a"] or declared["roles"]["never_edited"] == ["a", "Z"]
    found = d('[axioms]\n1=["ab"]\n[rules]\nins(a,b,)\n')["symbols"]
    assert found["declared"] is False and found["terminals"] is None and found["count"] == 2


def test_cookbook_models_describe():
    paths = sorted(COOKBOOK.glob("*.txt"))
    assert paths
    for path in paths:
        r = describe(path).to_dict()
        assert r["rules"]["count"] == sum(c["rules"] for c in r["components"])
        json.dumps(r)


def run(*args):
    return subprocess.run([sys.executable, "-m", "gcrsim", *map(str, args)], capture_output=True, text=True, cwd=ROOT)


def test_text_and_jsonl_agree():
    model = COOKBOOK / "02_insdel.txt"
    text = run(model, "--describe")
    assert text.returncode == 0
    assert "insertion-deletion size (n,m,m';p,q,q') (2,1,1;0,0,0)" in text.stdout
    lines = [json.loads(x) for x in run(model, "--describe", "--format", "jsonl").stdout.splitlines()]
    assert [x["type"] for x in lines] == ["header", "description", "end"]
    assert lines[0]["mode"] == "describe" and lines[0]["terminals"] is None
    assert lines[2] == {"type": "end", "status": 0, "steps": 0}
    body = {k: v for k, v in lines[1].items() if k != "type"}
    assert body == describe(model).to_dict()
    assert body["size"]["ins"] == {"n": 2, "m": 1, "m_right": 1}
    assert "1 -> 1: 1 rule" in text.stdout


def test_python_api_accepts_path_and_model():
    model = COOKBOOK / "02_insdel.txt"
    a = describe(model)
    b = describe(gcrsim.parse_model_file(str(model)))
    assert a.to_dict() == b.to_dict()
    assert a.rules["count"] == 1 and a.symbols["count"] == 2 and "terminals" in a.symbols


def test_mode_selection_and_help():
    model = COOKBOOK / "02_insdel.txt"
    assert run("--mode", "describe", model).stdout == run(model, "--describe").stdout
    h = run("--mode", "describe", "--help")
    assert h.returncode == 0 and "--describe" in h.stdout
    assert "describe" in run("--help").stdout


def test_model_error_is_status_2(tmp_path):
    f = tmp_path / "bad.txt"
    f.write_text("[rules]\nins(a,b\n", encoding="utf-8")
    assert run(f, "--describe").returncode == 2
    assert run(tmp_path / "none.txt", "--describe").returncode == 2


def test_symbols_written_by_a_regex_replacement_are_counted():
    nl = chr(10)
    r = d(nl.join(['[axioms]', '1=["a"]', '[rules]', 're(a)->z', '']))["symbols"]
    assert r["count"] == 2 and r["roles_exact"] is False


def test_long_symbols_are_not_split_when_wrapping():
    long = "x" * 105
    text = '[symbols]' + chr(10) + 'lexemes = "%s"' % long + chr(10) + '[axioms]' + chr(10) + '1=["a"]' + chr(10) + '[rules]' + chr(10) + 'ins(a,%s,)' % long + chr(10)
    out = describe(parse_model(text)).text()
    assert any(line.endswith(long) for line in out.split(chr(10)))
