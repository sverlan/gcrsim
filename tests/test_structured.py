"""Structured derivations (symbol-level steps, trace objects in JSONL), and the output with print_sep and multi-character symbols."""

import json

import gcrsim
from conftest import ROOT, run_py

FEATURES = ROOT / "examples" / "features"

LEXEMES = """
[symbols]
alphabet = "a b F1 a10 S"

[run]
print_sep = " "

[axioms]
1 = ["S"]

[rules]
S -> F1 S, 2
2, S -> S a10, 1
S ->
"""

LEXEMES_MARKED = LEXEMES + """
[model.components.1.marks]
done = '\\AF1a10\\Z'
"""

KINDS = """
[symbols]
alphabet = "a b c X p1 p2 F1"

[symbols.classes]
P = "p1 p2"

[run]
print_sep = " "

[axioms]
1 = ["ab"]

[rules]
ins({start}, X, ), 2
2, ins({any}, F1, {end}), 3
3, sub(X, a, p1 p2, {any}), 4
4, del(X, p1, {P}), 5
5, send(), 6
6, re(p2) -> a, 1
1, F1 -> c, 1
"""

TWO = """
[axioms]
1 = ["S"]

[rules]
S -> a S, 2
2, S -> S b, 1
S ->
"""

EMPTY_AXIOM = """
[axioms]
1 = [""]

[rules]
ins({start}, a, ), 2
2, a -> a, 1
"""

LONG = "F1 " * 10 + "a10 " * 10  # derived in 21 steps


def cli(args, cwd, fmt="text", stdin=None):
    return run_py([str(a) for a in args] + ["--format", fmt], cwd, stdin=stdin, trusted=False)


def model_file(tmp_path, text, name="m.txt"):
    p = tmp_path / name
    p.write_bytes(text.encode("utf-8"))
    return str(p)


def make_sim(text, callback=None):
    model = gcrsim.parse_model(text)
    st = gcrsim.settings.settings_for_model(model)
    st.filter_next = callback
    return gcrsim.Simulator(model, st, write=lambda t: None, retain=True)


def all_targets(text, steps):
    """The simulator after ``steps`` single steps and every (component, string, step) that was ever there."""
    sim = make_sim(text)
    found = []
    for _ in range(steps):
        sim.run(1)
        found += [(c, s, sim.step_no) for c, comp in enumerate(sim.cur) for s in comp]
    return sim, found


def kinds_chain():
    sim, found = all_targets(KINDS, 8)
    return sim, found, sim.trace_many([found[-1]])[0]


# -- the output with print_sep and multi-character symbols ---------------------------------------------


def test_heading_is_not_split_by_print_sep(tmp_path):
    r = cli([FEATURES / "overlapping_symbols.txt", 1, "--trace", "ab-a-b", "--word-sep=-"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "Trace of 'ab-a-b' (component 1), first appearing at step 1:" in r.stdout
    assert "step 1: S => ab a b   (component 1 -> 1, rule at line 22: S->ab a b, position 0)" in r.stdout


def test_step_numbers_and_rule_texts_are_plain(tmp_path):
    m = model_file(tmp_path, LEXEMES)
    r = cli([m, 24, "--trace", LONG.strip(), "--word-sep= "], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "    step 10: " in r.stdout and "step 1 0" not in r.stdout
    assert "rule at line 12: S->F1 S,2" in r.stdout and "rule at line 13: 2,S->S a10,1" in r.stdout
    assert "step 21: " + "F1 " * 10 + "S " + "a10 " * 9 + "a10 => " + "F1 " * 9 + "F1 a10" in r.stdout


def test_mark_lines_and_derivations_use_print_sep(tmp_path):
    m = model_file(tmp_path, LEXEMES_MARKED)
    r = cli([m, 6, "--trace-marks"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "Mark (done): F1 a10" in r.stdout
    assert "Mark [done] at step 3, component 1: F1 a10" in r.stdout
    assert "step 3: F1 S a10 => F1 a10" in r.stdout
    assert "  [done] component 1: F1 a10  (steps 3)" in r.stdout


def test_listing_uses_print_sep_only_for_strings(tmp_path):
    m = model_file(tmp_path, LEXEMES)
    lines = cli([m, 3], tmp_path).stdout.splitlines()
    assert "F1 S a10" in lines and "F1 a10" in lines and "F1 F1 S a10" in lines
    assert "step 3" in lines and "component 1" in lines


def test_print_sep_in_perl_csv_and_jsonl_formats(tmp_path):
    m = model_file(tmp_path, LEXEMES)
    assert "F1 F1 S a10 a10" in cli([m, 4], tmp_path, fmt="perl").stdout.splitlines()
    assert "F1 F1 S a10 a10" in cli([m, 4], tmp_path, fmt="csv").stdout
    rows = [json.loads(x) for x in cli([m, 4], tmp_path, fmt="jsonl").stdout.splitlines()]
    last = [x for x in rows if x["type"] == "step"][-1]
    assert last["components"] == [[["F1", "F1", "S", "a10", "a10"]], []]  # symbols, no print_sep
    assert last["components_string"] == [["F1 F1 S a10 a10"], []]


def test_callback_print_is_not_touched(tmp_path):
    conf = tmp_path / "c.py"
    conf.write_text("def keep(s, component):\n    print('KEEP F1 a10 step 10')\n    return True\n", encoding="utf-8")
    m = model_file(tmp_path, LEXEMES)
    r = run_py([m, "2", "--python-filter", str(conf), "--format", "text"], tmp_path, trusted=False)
    assert r.returncode == 0, r.stderr
    assert "KEEP F1 a10 step 10" in r.stdout


def test_keep_receives_real_names_without_separators():
    seen = []

    def keep(s, component):
        seen.append(s)
        return True

    sim = make_sim(LEXEMES, callback=keep)
    sim.run(4)
    assert {"F1Sa10", "F1a10", "F1F1Sa10"} <= set(seen)
    assert seen and all(" " not in s and "" not in s and not any(0xE000 <= ord(ch) <= 0xF8FF for ch in s) for s in seen)


def test_interactive_mode_prints_strings_with_print_sep(tmp_path):
    m = model_file(tmp_path, LEXEMES)
    r = run_py([m, "-i", "--format", "text"], tmp_path, stdin="n 3\nshow 1\nq\n", trusted=False)
    assert "F1 a10" in r.stdout or "F1 S a10" in r.stdout, r.stdout + r.stderr
    assert "F1S" not in r.stdout and "a10a10" not in r.stdout


def test_overlapping_symbols_print_all_keeps_separators(tmp_path):
    r = cli([FEATURES / "overlapping_symbols.txt", 2, "--print-all"], tmp_path)
    assert "ab a b" in r.stdout.splitlines()


# -- structured steps ----------------------------------------------------------------------------------


def test_steps_for_every_rule_kind():
    sim, found, chain = kinds_chain()
    assert [d.rule_kind for d in chain] == ["ins", "ins", "sub", "del", "send", "re", "ins", "ins"]
    plain = [t for t in found if t[1].endswith("c")][0]
    assert sim.trace_many([plain])[0][-1].rule_kind == "plain"
    ins, ins2, sub, dele, send, re_ = chain[:6]
    assert (ins.u, ins.x, ins.y, ins.v) == (["{start}"], None, ["X"], [])
    assert (ins2.u, ins2.x, ins2.y, ins2.v) == (["{any}"], None, ["F1"], ["{end}"])
    assert (sub.u, sub.x, sub.y, sub.v) == (["X"], ["a"], ["p1", "p2"], ["{any}"])
    assert (dele.u, dele.x, dele.y, dele.v) == (["X"], ["p1"], None, ["{P}"])
    assert (send.u, send.x, send.y, send.v) == (None, None, None, None)
    assert (re_.u, re_.x, re_.y, re_.v) == (None, None, None, None)
    assert [d.rule_line for d in chain[:6]] == [15, 16, 17, 18, 19, 20]
    assert all(d.name is None for d in chain)
    assert sim.trace_many([plain])[0][-1].y == ["c"] and sim.trace_many([plain])[0][-1].x == ["F1"]


def test_steps_have_symbol_positions_and_edits():
    _, _, chain = kinds_chain()
    ins2, sub, dele, send, re_ = chain[1:6]
    assert (ins2.before, ins2.after) == (["X", "a", "b"], ["X", "a", "b", "F1"])
    assert (ins2.start, ins2.end, ins2.removed, ins2.inserted) == (3, 3, [], ["F1"])
    assert (sub.start, sub.end, sub.removed, sub.inserted) == (1, 2, ["a"], ["p1", "p2"])
    assert (dele.start, dele.end, dele.removed, dele.inserted) == (1, 2, ["p1"], [])
    assert (send.start, send.end, send.removed, send.inserted) == (0, 0, [], [])
    assert send.before == send.after
    assert (re_.removed, re_.inserted) == (["p2"], ["a"])
    for d in chain:  # the edit explains the step; positions are in symbols
        assert d.before[: d.start] + d.inserted + d.before[d.end :] == d.after
        assert d.before[d.start : d.end] == d.removed
        assert "".join(d.before) == d.source and "".join(d.after) == d.result


def test_multi_character_symbols_are_whole_in_the_step():
    sim = make_sim(LEXEMES)
    sim.run(4)
    chain = sim.trace("F1F1Sa10a10")
    last = chain[-1]
    assert last.before == ["F1", "F1", "S", "a10"] and last.after == ["F1", "F1", "S", "a10", "a10"]
    assert last.source == "F1F1Sa10" and last.result == "F1F1Sa10a10"
    assert (last.start, last.end, last.removed, last.inserted) == (2, 3, ["S"], ["S", "a10"])  # symbols, not letters
    assert last.rule_kind == "plain" and (last.x, last.y) == (["S"], ["S", "a10"])


def test_to_dict_is_json_ready_and_counts_components_from_one():
    sim, found = all_targets(KINDS, 4)
    chain = sim.trace_many([found[-1]])[0]
    data = [d.to_dict() for d in chain]
    assert json.loads(json.dumps(data)) == data
    assert [d["step"] for d in data] == [1, 2, 3, 4]
    assert [(d["component"], d["target"]) for d in data] == [(1, 2), (2, 3), (3, 4), (4, 5)]
    assert set(data[0]) == {"step", "component", "target", "before", "after", "rule", "start", "end", "removed", "inserted"}
    assert set(data[0]["rule"]) == {"line", "kind", "notation", "name", "bindings", "u", "x", "y", "v"}


def test_old_attributes_still_work():
    sim = make_sim(TWO)
    sim.run(3)
    d = sim.trace("aSb")[-1]
    assert (d.step, d.source_component, d.target_component) == (2, 1, 0)
    assert (d.source, d.result, d.start, d.end) == ("aS", "aSb", 1, 2)
    assert d.rule.line == 7 and d.rule.target == 0


def test_axiom_only_and_empty_word():
    sim = make_sim(TWO)
    sim.run(1)
    assert sim.trace("S") == []
    sim = make_sim(EMPTY_AXIOM)
    sim.run(2)
    assert sim.trace("", 0, 0) == []
    chain = sim.trace("a", 1, 1)
    assert chain[0].before == [] and chain[0].after == ["a"]
    assert (chain[0].start, chain[0].end, chain[0].removed, chain[0].inserted) == (0, 0, [], ["a"])
    assert chain[0].to_dict()["before"] == []


def test_classes_and_any_in_operands():
    _, _, chain = kinds_chain()
    assert chain[3].v == ["{P}"] and chain[2].v == ["{any}"] and chain[1].u == ["{any}"]


# -- JSONL ---------------------------------------------------------------------------------------------


def trace_rows(tmp_path, text, args):
    m = model_file(tmp_path, text)
    r = cli([m, *args], tmp_path, fmt="jsonl")
    assert r.returncode == 0, r.stderr
    return [json.loads(x) for x in r.stdout.splitlines()]


def test_jsonl_trace_objects(tmp_path):
    rows = trace_rows(tmp_path, LEXEMES, [6, "--trace", "F1 a10", "--word-sep= "])
    kinds = [x["type"] for x in rows]
    assert kinds.count("derivation") == 1 and "message" not in kinds
    head = dict(rows[kinds.index("derivation")])
    assert head.pop("measures")["steps"] == 3
    assert head == {"type": "derivation", "word": ["F1", "a10"], "word_string": "F1 a10", "component": 1, "found_at": 3, "steps": 3}
    steps = [x for x in rows if x["type"] == "derivation_step"]
    assert [s["step"] for s in steps] == [1, 2, 3]
    assert steps[0]["before"] == ["S"] and steps[0]["after"] == ["F1", "S"]
    assert steps[-1]["after"] == ["F1", "a10"] and steps[-1]["rule"]["kind"] == "plain"
    assert steps[1]["rule"] == {"line": 13, "kind": "plain", "notation": "2,S->S a10,1", "u": None, "x": ["S"], "y": ["S", "a10"],
                                "v": None, "name": None, "bindings": None}
    assert (steps[0]["component"], steps[0]["target"]) == (1, 2)


def test_jsonl_trace_matches_the_text_trace(tmp_path):
    m = model_file(tmp_path, LEXEMES)
    text = cli([m, 6, "--trace", "F1 a10", "--word-sep= "], tmp_path).stdout
    rows = [json.loads(x) for x in cli([m, 6, "--trace", "F1 a10", "--word-sep= "], tmp_path, fmt="jsonl").stdout.splitlines()]
    steps = [x for x in rows if x["type"] == "derivation_step"]
    assert steps
    for s in steps:
        assert "step %d: %s => %s " % (s["step"], " ".join(s["before"]), " ".join(s["after"])) in text


def test_jsonl_trace_marks(tmp_path):
    rows = trace_rows(tmp_path, LEXEMES_MARKED, [6, "--trace-marks"])
    heads = [x for x in rows if x["type"] == "derivation"]
    assert heads and heads[0]["word"] == ["F1", "a10"] and heads[0]["found_at"] == 3 and heads[0]["mark"] == "done"
    assert len([x for x in rows if x["type"] == "derivation_step"]) == sum(h["steps"] for h in heads)


def test_jsonl_trace_of_an_axiom_has_no_steps(tmp_path):
    rows = trace_rows(tmp_path, TWO, [2, "--trace", "S"])
    heads = [dict(x) for x in rows if x["type"] == "derivation"]
    assert heads[0].pop("measures")["steps"] == 0
    assert heads == [{"type": "derivation", "word": ["S"], "word_string": "S", "component": 1, "found_at": 0, "steps": 0}]
    assert not [x for x in rows if x["type"] == "derivation_step"]


# -- replay jsonl matches the trace jsonl -----------------------------------------------------------------


def test_replay_steps_equal_the_trace_steps_of_the_cli(tmp_path):
    m = model_file(tmp_path, KINDS)
    _, _, chain = kinds_chain()
    word = " ".join(chain[-1].after)
    rows = [json.loads(x) for x in cli([m, 8, "--trace", word, "--word-sep= ", "--component", chain[-1].target_component + 1], tmp_path, fmt="jsonl").stdout.splitlines()]
    traced = [x for x in rows if x["type"] == "derivation_step"]
    assert len(traced) == len(chain)
    lines = [" ".join(chain[0].before)] + ["%d: %s" % (d.target_component + 1, " ".join(d.after)) for d in chain]
    f = tmp_path / "d.txt"
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    r = cli([m, "--replay", str(f)], tmp_path, fmt="jsonl")
    assert r.returncode == 0, r.stderr
    replayed = [json.loads(x) for x in r.stdout.splitlines() if '"derivation_step"' in x]
    assert len(replayed) == len(traced)
    for got, want in zip(replayed, traced):
        assert got["ways"] >= 1 and len(got["lines"]) == 2
        got = {k: v for k, v in got.items() if k not in ("type", "lines", "ways")}
        assert got == {k: v for k, v in want.items() if k != "type"}


# -- review fixes ---------------------------------------------------------------------------------------


def detailed_overlapping():
    return (FEATURES / "overlapping_symbols.txt").read_text(encoding="utf-8").replace("[run]", "[run]\nshow_detailed_application = true")


def test_detailed_application_uses_print_sep(tmp_path):
    text = detailed_overlapping()
    m = model_file(tmp_path, text)
    for fmt in ("text", "perl"):
        assert "S => ab a b" in cli([m, 1], tmp_path, fmt=fmt).stdout
    written = []
    model = gcrsim.parse_model(text)
    gcrsim.Simulator(model, gcrsim.settings.settings_for_model(model), write=written.append).run(1)
    assert "S => ab a b" in "".join(written)


def test_detailed_application_with_a_candidate_limit(tmp_path):
    m = model_file(tmp_path, detailed_overlapping())
    assert "S => ab a b" in cli([m, 1, "--max-step-candidates", "100"], tmp_path).stdout


CLASSES = """
[symbols]
alphabet = "a b X"

[symbols.classes]
P = "a b"
Q = "b a"

[axioms]
1 = ["a"]

[rules]
{Q} -> X
"""


def test_provenance_keeps_the_class_that_the_rule_names(tmp_path):
    sim = make_sim(CLASSES)
    sim.run(1)
    d = sim.trace("X")[0]
    assert d.rule_notation == "{Q}->X" and d.x == ["{Q}"]
    m = model_file(tmp_path, CLASSES)
    f = tmp_path / "d.txt"
    f.write_text("a\nX\n", encoding="utf-8")
    r = cli([m, "--replay", str(f)], tmp_path, fmt="jsonl")
    step = [json.loads(x) for x in r.stdout.splitlines() if '"derivation_step"' in x][0]
    assert step["rule"]["x"] == ["{Q}"]


def test_changing_a_step_does_not_change_later_records(tmp_path):
    text = '[axioms]\n1 = ["a"]\n\n[rules]\na -> X\n'
    sim = make_sim(text)
    sim.run(1)
    first = sim.trace("X")[0]
    first.x.clear()
    first.before.append("junk")
    first.provenance["y"].append("junk")
    again = sim.trace("X")[0]
    assert again.x == ["a"] and again.y == ["X"] and again.before == ["a"]
    m = model_file(tmp_path, text)
    f = tmp_path / "d.txt"
    f.write_text("a\nX\n", encoding="utf-8")
    r = cli([m, "--replay", str(f)], tmp_path, fmt="jsonl")
    assert [json.loads(x) for x in r.stdout.splitlines() if '"derivation_step"' in x][0]["rule"]["x"] == ["a"]


def test_callback_error_names_the_string_with_print_sep(tmp_path):
    conf = tmp_path / "c.py"
    conf.write_text("def keep(s, component):\n    raise ValueError('boom ' + s)\n", encoding="utf-8")
    m = model_file(tmp_path, (FEATURES / "overlapping_symbols.txt").read_text(encoding="utf-8"))
    r = run_py([m, "1", "--python-filter", str(conf), "--format", "text"], tmp_path, trusted=False)
    assert r.returncode != 0
    assert "'ab a b'" in r.stderr and "boom abab" in r.stderr


def test_format_derivation_uses_the_print_sep_of_the_simulator():
    text = '[symbols]\nalphabet = "p1 a X"\n[run]\nprint_sep = " "\n[axioms]\n1 = ["X"]\n[rules]\nX -> p1 a\n'
    sim = make_sim(text)
    sim.run(1)
    steps = sim.trace("p1a")
    assert steps[0].result == "p1a"  # the attributes have no separators
    assert "X => p1 a " in gcrsim.format_derivation(steps)


def test_csv_separator_stays_the_fourth_argument():
    from gcrsim.listing import Csv

    out = []
    Csv(out.append, str, out.append, ",").step(0, [["ab"]], None, None)
    assert "0,1,ab" in "".join(out)


def test_perl_listing_renders_chunk_by_chunk():
    from gcrsim.output import format_conf

    seen = []

    def show(s):
        seen.append(s)
        return s

    gen = format_conf([[str(i) for i in range(120000)]], None, None, show)
    next(gen)
    next(gen)
    assert len(seen) == 50000


# -- the jsonl schema: words as arrays, one schema for every operation -----------------------------------


def jsonl_rows(tmp_path, text, args, name="m.txt"):
    m = model_file(tmp_path, text, name)
    r = cli([m, *args], tmp_path, fmt="jsonl")
    return [json.loads(x) for x in r.stdout.splitlines()], r


def test_listing_words_are_arrays_with_a_text_form(tmp_path):
    rows, _ = jsonl_rows(tmp_path, LEXEMES, [3])
    steps = [x for x in rows if x["type"] == "step"]
    assert steps[0]["components"] == [[["S"]], []] and steps[0]["components_string"] == [["S"], []]
    assert steps[1]["components"] == [[[]], [["F1", "S"]]]  # the empty word is []
    assert steps[1]["components_string"] == [[""], ["F1 S"]]
    assert steps[3]["components"][1] == [["F1", "F1", "S", "a10"]] and steps[3]["components_string"][1] == ["F1 F1 S a10"]


def test_text_form_without_print_sep_is_plain_concatenation(tmp_path):
    text = LEXEMES.replace('print_sep = " "', "")
    rows, _ = jsonl_rows(tmp_path, text, [2])
    last = [x for x in rows if x["type"] == "step"][-1]
    assert last["components"] == [[["F1", "S", "a10"]], []] and last["components_string"] == [["F1Sa10"], []]


def test_header_has_the_mode_in_both_operations(tmp_path):
    rows, _ = jsonl_rows(tmp_path, TWO, [1])
    head = rows[0]
    assert head["type"] == "header" and head["mode"] == "run"
    assert {"version", "model", "configuration", "description"} <= set(head) and "file" not in head
    f = tmp_path / "d.txt"
    f.write_text("S" + chr(10), encoding="utf-8")
    rows, _ = jsonl_rows(tmp_path, TWO, ["--replay", str(f)])
    head = rows[0]
    assert head["mode"] == "replay" and head["fragment"] is False and head["file"] == str(f)
    assert {"version", "model", "configuration", "description"} <= set(head)


def test_end_fields(tmp_path):
    rows, _ = jsonl_rows(tmp_path, TWO, [2])
    assert rows[-1] == {"type": "end", "status": 0, "steps": 2}
    f = tmp_path / "d.txt"
    f.write_text("S" + chr(10) + "2: aS" + chr(10) + "1: x" + chr(10), encoding="utf-8")
    rows, _ = jsonl_rows(tmp_path, TWO, ["--replay", str(f)])
    end = rows[-1]
    assert (end["type"], end["status"], end["steps"], end["ok"]) == ("end", 4, 1, False)
    assert set(end["failure"]) == {"line", "step", "component", "target", "before", "before_string", "after", "after_string", "reason"}
    assert end["failure"]["before"] == ["a", "S"] and end["failure"]["after"] == ["x"] and end["failure"]["after_string"] == "x"


def test_replay_failure_of_the_first_form_has_no_after(tmp_path):
    f = tmp_path / "d.txt"
    f.write_text("aS" + chr(10), encoding="utf-8")
    rows, _ = jsonl_rows(tmp_path, TWO, ["--replay", str(f)])
    failure = rows[-1]["failure"]
    assert failure["step"] == 0 and failure["before"] == ["a", "S"] and failure["after"] is None and failure["after_string"] is None


def test_replay_failure_with_lexemes_has_text_forms(tmp_path):
    f = tmp_path / "d.txt"
    f.write_text("S" + chr(10) + "1: F1 a10" + chr(10), encoding="utf-8")
    rows, _ = jsonl_rows(tmp_path, LEXEMES, ["--replay", str(f)])
    failure = rows[-1]["failure"]
    assert failure["before"] == ["S"] and failure["after"] == ["F1", "a10"] and failure["after_string"] == "F1 a10"


def test_derivation_step_texts_with_print_sep(tmp_path):
    rows, _ = jsonl_rows(tmp_path, LEXEMES, [6, "--trace", "F1 a10", "--word-sep= "])
    steps = [x for x in rows if x["type"] == "derivation_step"]
    assert steps[1]["before"] == ["F1", "S"] and steps[1]["before_string"] == "F1 S"
    assert steps[1]["after"] == ["F1", "S", "a10"] and steps[1]["after_string"] == "F1 S a10"
    assert "removed_text" not in steps[1] and "inserted_text" not in steps[1]
    assert [k for k in steps[1]] == ["type", "step", "component", "target", "before", "before_string", "after", "after_string", "rule",
                                      "start", "end", "removed", "inserted"]


def test_trace_and_replay_use_one_serializer(tmp_path):
    m = model_file(tmp_path, KINDS)
    _, _, chain = kinds_chain()
    word = " ".join(chain[-1].after)
    rows = [json.loads(x) for x in cli([m, 8, "--trace", word, "--word-sep= ", "--component", chain[-1].target_component + 1],
                                       tmp_path, fmt="jsonl").stdout.splitlines()]
    traced = [x for x in rows if x["type"] == "derivation_step"]
    f = tmp_path / "d.txt"
    f.write_text(chr(10).join([" ".join(chain[0].before)] + ["%d: %s" % (d.target_component + 1, " ".join(d.after)) for d in chain]) + chr(10),
                 encoding="utf-8")
    replayed = [json.loads(x) for x in cli([m, "--replay", str(f)], tmp_path, fmt="jsonl").stdout.splitlines()
                if '"derivation_step"' in x]
    assert len(traced) == len(replayed) == len(chain)
    for t, r in zip(traced, replayed):
        assert [k for k in r if k not in ("lines", "ways")] == list(t) and {k: v for k, v in r.items() if k not in ("lines", "ways")} == t


def test_rule_operands_have_the_names_of_the_model_syntax(tmp_path):
    text = '[axioms]\n1 = ["ab"]\n\n[rules]\na -> c, 2\n'.replace(chr(92) + "n", chr(10))
    # plain: x is replaced by y
    sim = make_sim(text)
    sim.run(1)
    r = sim.trace("cb", 1)[0].to_dict()["rule"]
    assert (r["kind"], r["u"], r["x"], r["y"], r["v"]) == ("plain", None, ["a"], ["c"], None)
    _, _, chain = kinds_chain()
    ins, _, sub, dele, send, re_ = chain[:6]
    for step, kind, ops in ((ins, "ins", (["{start}"], None, ["X"], [])), (sub, "sub", (["X"], ["a"], ["p1", "p2"], ["{any}"])),
                            (dele, "del", (["X"], ["p1"], None, ["{P}"])), (send, "send", (None,) * 4), (re_, "re", (None,) * 4)):
        rule = step.to_dict()["rule"]
        assert rule["kind"] == kind and (rule["u"], rule["x"], rule["y"], rule["v"]) == ops, kind
        assert set(rule) == {"line", "kind", "notation", "name", "bindings", "u", "x", "y", "v"} and rule["name"] is None


# -- second review ---------------------------------------------------------------------------------------


def test_a_step_built_by_hand_does_not_poison_later_records():
    text = (FEATURES / "overlapping_symbols.txt").read_text(encoding="utf-8")
    model = gcrsim.parse_model(text)
    rule = model.rules[0][0]
    hand = gcrsim.DerivationStep(1, 0, "S", rule, 0, 1, 0, "abab")  # built without a lexicon, before any trace
    hand.provenance  # read first: a cache in the rule would keep this lexicon-less answer
    sim = gcrsim.Simulator(model, gcrsim.settings.settings_for_model(model), write=lambda t: None, retain=True)
    sim.run(1)
    d = sim.trace("ab" + chr(0) + "a" + chr(0) + "b")[0]
    assert d.y == ["ab", "a", "b"] and d.to_dict()["rule"]["y"] == ["ab", "a", "b"]
    steps = gcrsim.replay(model, ["S", "ab a b"]).steps
    assert steps[0].to_dict()["rule"]["y"] == ["ab", "a", "b"]


def test_chains_of_trace_many_do_not_share_steps():
    sim = make_sim((FEATURES / "overlapping_symbols.txt").read_text(encoding="utf-8"))
    sim.run(2)
    left, right = sim.trace_many([(0, "T" + chr(0) + "a" + chr(0) + "b", 2), (0, "ab" + chr(0) + "S", 2)])
    assert left[0] is not right[0]
    left[0].before.clear()
    left[0].x.clear()
    assert right[0].before == ["S"] and right[0].x == ["S"]
    assert right[0].to_dict()["before"] == ["S"]


def test_trace_many_takes_the_real_names_of_the_symbols():
    sim = make_sim(LEXEMES)
    sim.run(3)
    a, b = sim.trace_many([(0, "F1a10", 3), (1, "F1F1Sa10", 3)])
    assert [d.step for d in a] == [1, 2, 3] and [d.step for d in b] == [1, 2, 3]
    assert a[-1].after == ["F1", "a10"]


CONFIG_PRINTS = "print('filter startup')" + chr(10) + "def keep(s, component):" + chr(10) + "    return True" + chr(10)


def test_output_of_a_configuration_while_it_loads_is_a_message_in_jsonl(tmp_path):
    conf = tmp_path / "c.py"
    conf.write_text(CONFIG_PRINTS, encoding="utf-8")
    m = model_file(tmp_path, TWO)
    r = run_py([m, "1", "--python-filter", str(conf), "--format", "jsonl"], tmp_path, trusted=False)
    assert r.returncode == 0, r.stderr
    rows = [json.loads(x) for x in r.stdout.splitlines()]  # every line is an object
    assert rows[0]["type"] == "header" and rows[2] == {"type": "message", "text": "filter startup"}
    f = tmp_path / "d.txt"
    f.write_text("S" + chr(10), encoding="utf-8")
    r = run_py([m, "--replay", str(f), "--python-filter", str(conf), "--format", "jsonl"], tmp_path, trusted=False)
    rows = [json.loads(x) for x in r.stdout.splitlines()]
    assert rows[0]["type"] == "header" and rows[1] == {"type": "message", "text": "filter startup"}
    r = run_py([m, "1", "--python-filter", str(conf), "--format", "text"], tmp_path, trusted=False)
    assert "filter startup" in r.stdout  # the text formats are unchanged


def test_replay_steps_do_not_hold_symbol_lists():
    import tracemalloc

    text = "[axioms]" + chr(10) + '1 = ["' + "a" * 5000 + '"]' + chr(10) + "[rules]" + chr(10) + "send(), 1" + chr(10)
    model = gcrsim.parse_model(text)
    forms = ["a" * 5000] * 1001
    tracemalloc.start()
    report = gcrsim.replay(model, forms)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert report.ok and len(report.steps) == 1000
    assert peak < 10 * 1024 * 1024
    step = report.steps[0]
    assert step.before == ["a"] * 5000 and step.to_dict()["before"] == step.before


def test_model_with_named_classes_can_be_copied_and_pickled():
    import copy
    import pickle

    model = gcrsim.parse_model(CLASSES)
    clone = copy.deepcopy(model)
    sim = gcrsim.Simulator(clone, gcrsim.settings.settings_for_model(clone), write=lambda t: None, retain=True)
    sim.run(1)
    assert sim.trace("X")[0].x == ["{Q}"]
    from gcrsim.rules import ClassItem

    c = ClassItem("ab", "Q")
    for copy_of in (copy.deepcopy(c), pickle.loads(pickle.dumps(c))):
        assert copy_of == c and copy_of.name == "Q" and type(copy_of) is ClassItem


def test_configuration_can_look_at_the_encoding_of_stdout_while_it_loads(tmp_path):
    conf = tmp_path / "c.py"
    conf.write_text("import sys" + chr(10) + "print(sys.stdout.encoding.lower(), sys.stdout.isatty())" + chr(10), encoding="utf-8")
    m = model_file(tmp_path, TWO)
    f = tmp_path / "d.txt"
    f.write_text("S" + chr(10), encoding="utf-8")
    for args in ([m, "1", "--format", "jsonl"], [m, "1", "--format", "csv"], [m, "--replay", str(f), "--format", "jsonl"]):
        r = run_py([*args, "--python-filter", str(conf)], tmp_path, trusted=False)
        assert r.returncode == 0, (args, r.stderr)
    r = run_py([m, "1", "--format", "jsonl", "--python-filter", str(conf)], tmp_path, trusted=False)
    assert json.loads(r.stdout.splitlines()[2])["type"] == "message"


def test_output_of_a_failing_configuration_is_not_lost(tmp_path):
    conf = tmp_path / "c.py"
    conf.write_text("print('before the failure')" + chr(10) + "raise RuntimeError('broken')" + chr(10), encoding="utf-8")
    m = model_file(tmp_path, TWO)
    f = tmp_path / "d.txt"
    f.write_text("S" + chr(10), encoding="utf-8")
    for args in ([m, "1", "--format", "jsonl"], [m, "--replay", str(f), "--format", "jsonl"]):
        r = run_py([*args, "--python-filter", str(conf)], tmp_path, trusted=False)
        assert r.returncode != 0 and "before the failure" in r.stderr and r.stdout == "", args
