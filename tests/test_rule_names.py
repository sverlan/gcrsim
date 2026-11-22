r"""Rule names (the clause ``; name: NAME``) and the renamed output fields (``notation``, ``*_string``)."""
import json

import pytest

import gcrsim
from gcrsim import GcrsimError, ModelError, main, parse_model, replay, search

HEAD = '[symbols]\nterminals = "a b"\n[axioms]\n1 = ["S"]\n'

NAMED = HEAD + """[rules]
S -> a S b, 1; name: grow
S -> a b, 1
"""

# Lines 6-12
ALL_KINDS = HEAD + """[rules.1]
S -> a S b, 1; name: plain-rule
ins(a, c, b), 1; name: ins_rule
send(), 2; name: send.rule
[rules.2]
del(,c,), 2; name: del1
sub(,a,x,), 2; name: sub1
re(c+) -> d, 1; name: re_rule
"""


def run(capsys, *args):
    status = main([str(a) for a in args])
    cap = capsys.readouterr()
    return status, cap.out, cap.err


def objs(out):
    return [json.loads(line) for line in out.splitlines() if line.strip()]


@pytest.fixture
def files(tmp_path):
    def make(name, text):
        path = tmp_path / name
        path.write_bytes(text.encode("utf-8"))
        return str(path)
    return make


def names(model):
    return [(r.kind, r.name) for rules in model.rules for r in rules]


# ---------------------------------------------------------------- parsing


def test_names_of_every_kind_and_section():
    m = parse_model(ALL_KINDS)
    assert names(m) == [("plain", "plain-rule"), ("ins", "ins_rule"), ("send", "send.rule"), ("del", "del1"),
                        ("sub", "sub1"), ("re", "re_rule")]


def test_a_rule_without_a_name_has_none():
    m = parse_model(NAMED)
    assert [r.name for r in m.rules[0]] == ["grow", None]


@pytest.mark.parametrize("tail", [
    "; name: n1; permit: a; forbid: b",
    "; permit: a; name: n1; forbid: b",
    "; permit: a; forbid: b; name: n1",
    ";name:n1;permit:a;forbid:b",
    " ;  name :n1 ; permit : a ; forbid : b",
])
def test_clause_order_and_white_space(tail):
    base = parse_model(HEAD + "[rules]\nS -> aS, 1; permit: a; forbid: b\n").rules[0][0]
    rule = parse_model(HEAD + "[rules]\nS -> aS, 1" + tail.replace(" :", ":") + "\n").rules[0][0]
    assert rule.name == "n1"
    assert (rule.permit, rule.forbid, rule.target, rule.source) == (base.permit, base.forbid, base.target, base.source)
    assert rule.guarded


def test_name_with_permit_any_and_ins():
    r = parse_model(HEAD + "[rules]\nins(a,X,b),1; permit-any: a,b; name: put-X\n").rules[0][0]
    assert r.name == "put-X" and r.any_of


def test_name_with_unicode_letters_and_digits():
    r = parse_model(HEAD + "[rules]\nS -> a, 1; name: règle2.b-c_d\n").rules[0][0]
    assert r.name == "règle2.b-c_d"


def test_a_name_does_not_change_the_rule():
    plain = parse_model(HEAD + "[rules]\nS -> a S b, 1; forbid: a\nS -> a b, 1\n")
    named = parse_model(NAMED.replace("S -> a S b, 1; name: grow", "S -> a S b, 1; forbid: a; name: grow"))
    assert [(r.notation, r.line, r.source, r.target, r.permit, r.forbid) for rs in plain.rules for r in rs] == \
           [(r.notation, r.line, r.source, r.target, r.permit, r.forbid) for rs in named.rules for r in rs]


# ---------------------------------------------------------------- errors


def err(text, line):
    with pytest.raises(ModelError) as ei:
        parse_model(text, "m.txt")
    msg = str(ei.value)
    assert ("m.txt:%d:" % line) in msg
    return msg


def test_empty_name():
    assert "empty rule name" in err(HEAD + "[rules]\nS -> a, 1; name:\n", 6)
    assert "empty rule name" in err(HEAD + "[rules]\nS -> a, 1; name:  ; forbid: b\n", 6)


@pytest.mark.parametrize("bad", ["1abc", "-x", "a b", "a,b", "a/b", "a:b", "_x", ".x"])
def test_bad_name(bad):
    assert "bad rule name" in err(HEAD + "[rules]\nS -> a, 1; name: %s\n" % bad, 6)


def test_second_name_clause():
    assert "more than one name" in err(HEAD + "[rules]\nS -> a, 1; name: x; name: y\n", 6)


def test_duplicate_name_names_both_lines():
    msg = err(HEAD + "[rules.1]\nS -> a, 1; name: x\n[rules.2]\nS -> b, 1; name: x\n", 8)
    assert "'x'" in msg and "lines 6 and 8" in msg


# ---------------------------------------------------------------- models without names


def test_models_without_names_are_unchanged(files, capsys):
    path = files("m.txt", HEAD + "[rules]\nS -> a S b, 1; forbid: aa\nS -> a b, 1\n")
    status, out, _ = run(capsys, path, "4", "--trace", "aabb")
    assert status == 0
    assert "rule at line 6: S->a S b,1" in out or "rule at line 6: S->aSb,1" in out.replace(" ", "")
    assert "rule at line 7:" in out
    m = parse_model(HEAD + "[rules]\nS -> a S b, 1; forbid: aa\nS -> a b, 1\n")
    assert [r.name for r in m.rules[0]] == [None, None]
    assert [r.notation for r in m.rules[0]] == ["S->a S b,1;forbid:aa", "S->a b,1"]


# ---------------------------------------------------------------- display


def test_trace_line(files, capsys):
    path = files("m.txt", NAMED)
    status, out, _ = run(capsys, path, "4", "--trace", "aabb")
    assert status == 0
    assert "rule grow at line 6: S->a S b,1" in out
    assert "rule at line 7: S->a b,1" in out
    assert "rule grow at line 7" not in out


def test_python_step_and_provenance():
    sim = gcrsim.Simulator(parse_model(NAMED), retain=True)
    sim.run(4)
    steps = sim.trace("aabb")
    first = steps[0]
    assert first.name == "grow" and first.rule_notation == "S->a S b,1"
    assert first.provenance["name"] == "grow" and first.provenance["notation"] == "S->a S b,1"
    assert first.to_dict()["rule"]["name"] == "grow"
    assert steps[1].name is None
    assert "rule grow at line 6: S->a S b,1" in gcrsim.format_derivation(steps)


def test_replay_explain_and_steps(files, capsys):
    path = files("m.txt", NAMED)
    good = files("good.txt", "S\naSb\naabb\n")
    status, out, _ = run(capsys, path, "--mode", "replay", good, "--explain")
    assert status == 0
    assert "rule grow at line 6: S->a S b,1" in out
    assert "rule at line 7: S->a b,1" in out
    assert "rules: grow (line 6) x1, S->a b,1 (line 7) x1;" in out
    report = replay(parse_model(NAMED), ["S", "aSb", "aabb"])
    assert [s.rule.name for s in report.steps] == ["grow", None]
    assert report.steps[0].provenance["name"] == "grow"
    assert report.steps[0].to_dict()["rule"]["notation"] == "S->a S b,1"


def test_measures_line_and_entries(files, capsys):
    path = files("m.txt", NAMED)
    status, out, _ = run(capsys, path, "5", "--trace", "aabb")
    assert "rules: grow (line 6) x1, S->a b,1 (line 7) x1;" in out
    status, out, _ = run(capsys, path, "5", "--trace", "aabb", "--format", "jsonl")
    rules = [o for o in objs(out) if o["type"] == "derivation"][0]["measures"]["rules"]
    assert [(r["name"], r["notation"], r["line"]) for r in rules] == [("grow", "S->a S b,1", 6), (None, "S->a b,1", 7)]
    assert all("text" not in r for r in rules)


def test_measures_same_notation_is_told_apart_by_line(files, capsys):
    text = '[axioms]\n1 = ["a"]\n[rules]\na -> b\nb -> a\na -> b\n'
    path = files("m.txt", text)
    status, out, _ = run(capsys, path, "3", "--trace", "b")
    assert status == 0 and "a->b (line 4)" in out and "a->b (line 6)" not in out.split("rules:")[1].split("components")[0] or "a->b (line 6)" in out


def test_search_pruning_note_uses_the_name():
    text = HEAD + "[rules]\nS -> a S b, 1\nS -> a b, 1\na -> c, 1; name: spoil\n"
    note = gcrsim._search.pruning_obstacle(parse_model(text), "ab")
    assert note.startswith("rule spoil (line 8)") and "rewrites the terminal a" in note
    plain = text.replace("; name: spoil", "")
    note = gcrsim._search.pruning_obstacle(parse_model(plain), "ab")
    assert note.startswith("rule a->c,1 (line 8)")


def test_search_derivation_shows_the_name(files, capsys):
    path = files("m.txt", NAMED)
    status, out, _ = run(capsys, path, "--mode", "search", "aabb")
    assert status == 0 and "rule grow at line 6" in out
    status, out, _ = run(capsys, path, "--mode", "search", "aabb", "--format", "jsonl")
    steps = [o for o in objs(out) if o["type"] == "derivation_step"]
    assert [s["rule"]["name"] for s in steps] == ["grow", None]


def test_interactive_trace_shows_the_name(files, tmp_path):
    import subprocess
    import sys
    path = files("m.txt", NAMED)
    r = subprocess.run([sys.executable, "-m", "gcrsim", path, "-i", "--quiet"], input="n 3\ntrace aabb\nq\n", text=True,
                       capture_output=True)
    assert "rule grow at line 6: S->a S b,1" in r.stdout


# ---------------------------------------------------------------- jsonl and Python fields


def test_jsonl_rule_object(files, capsys):
    path = files("m.txt", NAMED)
    status, out, _ = run(capsys, path, "4", "--trace", "aabb", "--format", "jsonl")
    steps = [o for o in objs(out) if o["type"] == "derivation_step"]
    assert set(steps[0]["rule"]) == {"line", "kind", "notation", "name", "bindings", "u", "x", "y", "v"}
    assert steps[0]["rule"]["name"] == "grow" and steps[0]["rule"]["notation"] == "S->a S b,1"
    assert steps[1]["rule"]["name"] is None


def test_renamed_string_fields_in_jsonl(files, capsys):
    path = files("m.txt", NAMED)
    status, out, _ = run(capsys, path, "2", "--trace", "aabb", "--format", "jsonl")
    rows = objs(out)
    assert "components_string" in [o for o in rows if o["type"] == "step"][0]
    der = [o for o in rows if o["type"] == "derivation"][0]
    assert "word_string" in der
    st = [o for o in rows if o["type"] == "derivation_step"][0]
    assert "before_string" in st and "after_string" in st
    flat = out
    for old in ("components_text", "word_text", "before_text", "after_text", '"rule_text"'):
        assert old not in flat
    assert '"text": "' not in flat.split('"rule"')[1].split("}")[0]


def test_renamed_fields_in_replay_failure(files, capsys):
    path = files("m.txt", NAMED)
    bad = files("bad.txt", "S\naSb\nxx\n")
    status, out, _ = run(capsys, path, "--mode", "replay", bad, "--format", "jsonl")
    fail = objs(out)[-1]["failure"]
    assert "before_string" in fail and "after_string" in fail
    assert "before_text" not in fail and "after_text" not in fail


def test_renamed_fields_in_search_header(files, capsys):
    path = files("m.txt", NAMED)
    status, out, _ = run(capsys, path, "--mode", "search", "aabb", "--format", "jsonl")
    head = objs(out)[0]
    assert head["word_string"] == "aabb" and "word_text" not in head


def test_old_python_names_are_gone():
    sim = gcrsim.Simulator(parse_model(NAMED), retain=True)
    sim.run(4)
    step = sim.trace("aabb")[0]
    assert not hasattr(step, "rule_text") and step.rule_notation
    assert "text" not in step.provenance and "text" not in step.to_dict()["rule"]


# ---------------------------------------------------------------- review fixes


def rules_text(body):
    m = parse_model(HEAD + "[rules]\n" + body + "\n")
    return [(r.notation, r.name, r.permit, r.forbid) for rs in m.rules for r in rs]


@pytest.mark.parametrize("line", ["a->;name:Z", "re(a)->;name:Z"])
def test_name_before_the_target_is_part_of_the_operand(line):
    (notation, name, _, _), = rules_text(line)
    assert name is None and ";name:Z" in notation


def test_name_after_the_target_is_a_clause_like_forbid():
    (_, name, permit, _), = rules_text("a->Z,1;permit:a;name:A")
    assert name == "A" and len(permit) == 1


def test_empty_forbid_list_before_an_empty_name():
    assert "empty word" in err(HEAD + "[rules]\na->Z,1;forbid:;name:\n", 6)


@pytest.mark.parametrize("line", [
    "re(a)->b,1;name:a b", "a->b,1;name:a b", "ins(a,b,c),1;name:a b", "a->b,1;name:a½", "re(a)->b,1;name:a½",
    "a->b,1;name: a b ;forbid:c",
])
def test_name_is_checked_as_written(line):
    assert "bad rule name" in err(HEAD + "[rules]\n" + line + "\n", 6)


def test_white_space_around_the_name_is_allowed():
    assert rules_text("re(a)->b,1;  name :  ok-1.x  ")[0][1] == "ok-1.x"
