"""Regression tests for the fourth Codex review (documentation and code)."""
import tracemalloc

import pytest

import gcrsim
from gcrsim import LimitReached, ModelError, Settings, parse_model

BS = chr(92)


def test_a_mark_can_be_traced_when_lexemes_overlap():
    text = """[symbols]
lexemes = ["ab", "abc"]

[axioms]
1 = ["abXc"]

[rules]
del(,X,)
"""
    model = parse_model(text)
    st = Settings(marks={0: {"t": BS + "A.*" + BS + "Z"}})
    sim = gcrsim.Simulator(model, st, write=lambda t: None, retain=True)
    sim.step()
    mark = sim.marks[0]
    assert mark.string == "abc"                      # the real names, as written
    chains = sim._trace_many([(mark.component, mark.encoded, mark.step)])   # the internal identity still traces
    assert chains[0][0].source.startswith(model.lexicon.encode("ab"))


def test_a_failed_retention_leaves_the_last_complete_step():
    model = parse_model("""[axioms]
1 = ["a"]

[rules]
a->b
""")
    sim = gcrsim.Simulator(model, Settings(), write=lambda t: None, retain=True, max_retained=1)
    with pytest.raises(LimitReached):
        sim.step()
    assert sim.step_no == 0 and sim.strings() == [["a"]]


def test_scoped_flag_groups_are_not_read_as_lexemes():
    model = parse_model("""[symbols]
lexemes = [":a", ">a"]

[axioms]
1 = ["ab"]

[rules]
re((?m:a))->X
re((?>a))->Y
""")
    assert [list(r.expand("ab")) for r in model.rules[0]] == [["Xb"], ["Yb"]]


def test_dollar_produced_by_an_escape_is_a_symbol():
    parse_model('[axioms]\n1 = ["a"]\n\n[rules]\nre(a)->\\x24\nre($)->X\n')
    parse_model("""[axioms]
1 = ["a"]

[rules]
re((?#$)a)->X
""")      # a '$' inside a regex comment is not an anchor


def test_escaped_backslash_before_ue000_is_not_the_reserved_code():
    model = parse_model("""[symbols]
lexemes = ["p1"]

[axioms]
1 = ["p1"]

[rules]
p1->p1
""")
    from gcrsim.pattern import compile_pattern
    compile_pattern(BS + BS + "ue000", model.lexicon)      # a literal backslash followed by "ue000"
    with pytest.raises(ValueError, match="reserved"):
        compile_pattern(BS + "ue000", model.lexicon)


def test_print_sep_does_not_touch_white_space():
    from gcrsim.lexicon import Lexicon
    lex = Lexicon(["p1"])
    code = lex.encode("p1")
    assert lex.decode_spaced("a" + code + "\n" + code + " b" + code + code, " ") == "a p1\np1 b p1 p1"


def test_counting_the_edits_of_a_plain_rule_does_not_build_them():
    model = parse_model("""[axioms]
1 = ["a"]

[rules]
ins(,x,)
""")
    rule = model.rules[0][0]
    s = "a" * 10000
    tracemalloc.start()
    count = rule.edit_count(s)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert count == 10001 and peak < 20000


def test_conditions_see_the_symbol_being_rewritten():
    m = parse_model("""[axioms]
1 = ["AB"]

[rules]
A->x,1;forbid:A
A->y,1;permit:A
""")
    assert list(m.rules[0][0].expand("AB")) == [] and list(m.rules[0][1].expand("AB")) == ["yB"]


def test_sqlite_retention_gives_the_same_trace(tmp_path):
    from gcrsim.retention import SqliteRetention
    model = parse_model("""[axioms]
1 = ["S"]

[rules.1]
S->aS,2
S->,1
[rules.2]
S->Sb,1
""")
    results = []
    for store in (None, SqliteRetention(str(tmp_path / "r.db"))):
        sim = gcrsim.Simulator(model, Settings(), write=lambda t: None, retain=True, retain_store=store)
        sim.run(6)
        results.append([(d.step, d.source, d.result) for d in sim.trace("aabb")])
    assert results[0] == results[1] and results[0]


def test_retain_file_option(tmp_path):
    from conftest import run_py
    (tmp_path / "m.txt").write_text("""[axioms]
1 = ["S"]

[rules.1]
S->aS,2
S->,1
[rules.2]
S->Sb,1
""")
    a = run_py(["m.txt", "6", "--trace", "aabb"], tmp_path).stdout
    b = run_py(["m.txt", "6", "--trace", "aabb", "--retain-file", "r.db"], tmp_path).stdout
    assert a == b and "Trace of" in a and (tmp_path / "r.db").exists()


def test_hashed_history_gives_the_same_contents_and_less_memory():
    import tracemalloc
    text = """[axioms]
1 = ["S"]

[rules]
S->aSbbbbbbbbbbbbbbbbbbbbbbbb
S->bSaaaaaaaaaaaaaaaaaaaaaaaa
S->
"""
    results, peaks = [], []
    for hashed in (False, True):
        model = parse_model(text)
        st = Settings(reject_max_len=400, hash_history=hashed)
        tracemalloc.start()
        sim = gcrsim.Simulator(model, st, write=lambda t: None)
        sim.run(11)
        peaks.append(tracemalloc.get_traced_memory()[1])
        tracemalloc.stop()
        results.append((sim.strings(), sim.hist_count))
    assert results[0] == results[1]
    assert peaks[1] < peaks[0]


def test_hash_history_is_a_boolean_setting():
    from gcrsim.settings import apply_settings
    st = Settings()
    assert st.hash_history is False
    apply_settings(st, {"hash_history": True}, "t")
    assert st.hash_history is True
    with pytest.raises(gcrsim.ConfigError):
        apply_settings(st, {"hash_history": "yes"}, "t")


def test_hashed_history_with_sqlite_retention_gives_the_exact_trace(tmp_path):
    from gcrsim.retention import SqliteRetention
    text = """[axioms]
1 = ["S"]

[rules.1]
S->aS,2
S->,1
[rules.2]
S->Sb,1
"""
    chains = []
    for hashed in (False, True):
        store = SqliteRetention(str(tmp_path / ("h%d.db" % hashed))) if hashed else None
        sim = gcrsim.Simulator(parse_model(text), Settings(hash_history=hashed), write=lambda t: None, retain=True, retain_store=store)
        sim.run(8)
        chains.append([(d.step, d.source, d.result, d.rule.notation) for d in sim.trace("aaabbb")])
    assert chains[0] == chains[1] and chains[0]


def test_retention_dump_shows_real_symbol_names(tmp_path):
    from gcrsim.retention import SqliteRetention, dump
    model = parse_model("""[symbols]
lexemes = ["p1"]

[axioms]
1 = ["p1"]

[rules]
p1->p1p1
""")
    store = SqliteRetention(str(tmp_path / "r.db"))
    sim = gcrsim.Simulator(model, Settings(), write=lambda t: None, retain=True, retain_store=store)
    sim.run(2)
    store._db.commit()
    lines = []
    assert dump(str(tmp_path / "r.db"), write=lines.append) == 0
    assert lines[0].endswith("3 steps retained")
    lines.clear()
    assert dump(str(tmp_path / "r.db"), step=2, write=lines.append) == 0
    assert lines == ["Component 1:", "p1p1p1"]


def test_sqlite_retention_finds_the_first_step_with_an_index(tmp_path):
    from gcrsim.retention import SqliteRetention
    store = SqliteRetention(str(tmp_path / "r.db"))
    store[0] = [["S"], []]
    store[1] = [["aS"], ["x"]]
    store[2] = [["aS", "b"], ["x", ""]]
    assert store.first_step(0, "aS") == 1 and store.first_step(1, "x") == 1 and store.first_step(0, "zz") is None
    assert store[2] == [["aS", "b"], ["x", ""]]


def test_retention_find_and_trace_from_the_file(tmp_path):
    from conftest import run_py
    (tmp_path / "m.txt").write_text("""[axioms]
1 = ["S"]

[rules.1]
S->aS,2
S->,1
[rules.2]
S->Sb,1
""")
    live = run_py(["m.txt", "5", "--trace", "aabb", "--retain-file", "r.db", "--quiet"], tmp_path).stdout
    import subprocess, sys
    from conftest import CLI_ENV, RETENTION
    def cmd(*a):
        return subprocess.run([*RETENTION, *a], cwd=str(tmp_path), env=CLI_ENV, capture_output=True, text=True)
    found = cmd("r.db", "--find", "aaSb")
    assert found.returncode == 0 and "step 3, component 2" in found.stdout
    assert cmd("r.db", "--find", "zzz").returncode == 2
    traced = cmd("r.db", "--trace", "aabb", "--model", "m.txt")
    assert traced.returncode == 0, traced.stderr
    steps = [l for l in traced.stdout.split(chr(10)) if l.strip().startswith("step ")]
    assert steps == [l for l in live.split(chr(10)) if l.strip().startswith("step ")] and len(steps) == 5


def test_entry_points_work_without_arguments_passed_in(tmp_path):
    """Console scripts call the function with no argument: it must read sys.argv itself."""
    import subprocess, sys
    from conftest import CLI_ENV
    for module, func in (("gcrsim.convert", "main_convert"), ("gcrsim.retention", "main"), ("gcrsim.cli", "main")):
        code = "import sys; sys.argv = [%r, %r]; from %s import %s; sys.exit(%s())" % ("prog", "--help", module, func, func)
        r = subprocess.run([sys.executable, "-c", code], cwd=str(tmp_path), env=CLI_ENV, capture_output=True, text=True)
        assert r.returncode == 0 and "usage" in r.stdout.lower(), (module, r.stderr[-300:])


def test_max_count_with_a_class_counts_its_symbols_together():
    text = """[symbols.classes]
N = "S A B"

[axioms]
1 = ["S"]

[rules]
S -> A B C
A -> a
B -> b
C -> c
"""
    model = parse_model(text)

    def reach(limit):
        st = Settings(filters={0: {"max_count": {"class": {"N": limit}}}})
        sim = gcrsim.Simulator(model, st, write=lambda t: None)
        seen = set()
        for _ in range(5):
            sim.step()
            seen |= set(sim.strings()[0])
        return seen

    assert "abc" not in reach(1) and "ABC" not in reach(1)       # S -> ABC has 2 of the class N (A, B) at once
    assert "ABC" in reach(2) and "abc" in reach(2)
    # a single symbol is counted alone, as before: S -> AAB has two A and one B
    twice = parse_model("""[axioms]
1 = ["S"]

[rules]
S -> A A B
""")
    for symbol, limit, expected in (("A", 1, []), ("A", 2, ["AAB"]), ("B", 1, ["AAB"])):
        st = Settings(filters={0: {"max_count": {symbol: limit}}})
        sim = gcrsim.Simulator(twice, st, write=lambda t: None)
        sim.step()
        assert sim.strings()[0] == expected, (symbol, limit)


def test_max_count_class_errors_are_config_errors():
    model = parse_model("""[axioms]
1 = ["S"]

[rules]
S -> S
""")
    with pytest.raises(gcrsim.ConfigError, match="unknown symbol class"):
        gcrsim.Simulator(model, Settings(filters={0: {"max_count": {"class": {"N": 1}}}}), write=lambda t: None)


def test_max_count_class_with_multi_character_symbols():
    text = """[symbols]
lexemes = "N1 N2"

[symbols.classes]
N = "N1 N2"

[axioms]
1 = ["N1"]

[rules]
N1 -> N1 N2
N2 -> a
"""
    model = parse_model(text)
    st = Settings(filters={0: {"max_count": {"class": {"N": 2}}}})
    sim = gcrsim.Simulator(model, st, write=lambda t: None)
    seen = set()
    for _ in range(5):
        sim.step()
        seen |= set(sim.strings()[0])
    assert max(w.count("N1") + w.count("N2") for w in seen) == 2


def test_max_count_rejects_braces_and_other_tables():
    model = parse_model("""[axioms]
1 = ["S"]

[rules]
S -> S
""")
    for bad, message in (({"{N}": 1}, "write a class as"), ({"other": {"N": 1}}, "only the keys 'class' and 're'")):
        with pytest.raises(gcrsim.ConfigError, match=message):
            gcrsim.Simulator(model, Settings(filters={0: {"max_count": bad}}), write=lambda t: None)


def test_a_symbol_named_class_is_still_a_symbol():
    model = parse_model("""[symbols]
lexemes = "class"

[axioms]
1 = ["class class"]

[rules]
S -> S
""")
    st = Settings(filters={0: {"max_count": {"class": 1}}})
    sim = gcrsim.Simulator(model, st, write=lambda t: None)
    sim.step()
    assert sim.strings()[0] == []          # the axiom has two of them, the limit is 1: a number is a symbol, a table is a class group


def test_the_toml_spellings_of_the_class_key_are_equal():
    import tomllib
    from gcrsim.errors import ConfigError
    from gcrsim.sections import flatten
    from gcrsim.settings import apply_settings

    def reject(message):
        raise ConfigError(message)

    forms = (
        "[model.components.0.filters]\nmax_count = { A = 2, class.N = 2 }\n",
        "[model.components.0.filters]\nmax_count.A = 2\nmax_count.class.N = 2\n",
        "[model.components.0.filters.max_count]\nA = 2\n[model.components.0.filters.max_count.class]\nN = 2\n",
        "[model]\ncomponents.0.filters.max_count.A = 2\ncomponents.0.filters.max_count.class.N = 2\n",
        "[model.filters]\nmax_count.A = 2\nmax_count.class.N = 2\n",
    )
    results = []
    for text in forms:
        st = Settings()
        apply_settings(st, flatten(tomllib.loads(text), "t", True, reject), "t", from_model=True)
        results.append(st.filters)
    assert all(r == results[0] for r in results) and results[0] == {0: {"max_count": {"A": 2, "class": {"N": 2}}}}

def test_add_mark_and_remove_work_between_steps():
    out = []
    model = parse_model("""[axioms]
1 = ["S"]

[rules]
S -> a S
S -> b S
""")
    sim = gcrsim.Simulator(model, Settings(), write=out.append, retain=True)
    sim.step()
    assert sorted(sim.strings()[0]) == ["aS", "bS"]
    sim.add_mark(0, "aS", "look")
    assert [(m.step, m.component, m.string, m.label) for m in sim.marks] == [(1, 0, "aS", "look")]
    assert "".join(out).strip() == "Mark (look): aS"
    sim.remove(0, "bS")
    assert sim.strings()[0] == ["aS"]
    assert sim.retained[1] == [["aS", "bS"]]                    # the step already done keeps its content
    sim.step()
    assert sorted(sim.strings()[0]) == ["aaS", "abS"]            # nothing came from bS
    assert [d.result for d in sim.trace("abS")] == ["aS", "abS"]
    for call in (lambda: sim.add_mark(0, "zzz", "t"), lambda: sim.remove(0, "zzz")):
        with pytest.raises(gcrsim.GcrsimError, match="is not in component 1"):
            call()
