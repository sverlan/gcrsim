"""Language listing uses completed simulator frontiers and scopes completeness to the configured model."""

import json

import pytest

from gcrsim import GcrsimError, LanguageResult, Settings, Simulator, language, main, parse_model
from gcrsim import _language, operations


SHRINK = """
[symbols]
terminals = "a"
[axioms]
1 = ["S"]
[rules]
S -> AB
AB -> a
"""

BRANCH = """
[symbols]
terminals = "a b"
[axioms]
1 = ["", "S"]
[rules]
S -> a
S -> b
"""

ANBN = """
[symbols]
terminals = "a b"
[axioms]
1 = ["S"]
[rules]
S -> aSb
S ->
"""

MULTI = """
[symbols]
alphabet = "zz aa S"
terminals = "aa zz bb"
[symbols.classes]
Extra = "bb"
[run]
print_sep = "|"
[axioms]
1 = ["bbaa", "aa", "zz", "zzbb", "", "bb", "aazz"]
[rules]
S -> aa
"""


def test_length_is_a_selection_and_native_rejection_is_an_exploration_restriction():
    result = language(parse_model(SHRINK), 1, "a")
    assert isinstance(result, LanguageResult)
    assert (result.words, result.counts, result.steps, result.outcome, result.reason, result.status) == (
        [["a"]], {1: 1}, 3, "complete", "frontier_exhausted", 0,
    )
    result = language(parse_model(SHRINK + "\n[model]\nreject_max_len = 1\n"), 1)
    assert (result.words, result.counts, result.steps, result.status) == ([], {}, 1, 0)
    assert result.restrictions["reject_max_len"] == 1


@pytest.mark.parametrize("cap,words", [(0, []), (1, []), (2, [["a"]])])
def test_nonterminal_cap_only_applies_to_generated_forms(cap, words):
    result = language(parse_model(SHRINK), 1, max_nonterminals=cap)
    assert (result.words, result.status, result.bounds["max_nonterminals"]) == (words, 0, cap)
    assert result.restrictions["max_nonterminals"] == cap
    assert language(parse_model(BRANCH), 1, max_nonterminals=0).words == [[], ["a"], ["b"]]


def test_anbn_is_partial_at_live_depth_bound_and_match_is_whole_word():
    model = parse_model(ANBN)
    result = language(model, 4, max_steps=4)
    assert (result.words, result.counts, result.steps, result.reason, result.status) == (
        [[], list("ab"), list("aabb")], {0: 1, 2: 1, 4: 1}, 4, "depth_bound", 3,
    )
    assert language(model, 4, "", max_steps=3).words == [[]]
    assert language(model, 4, "a+b+", max_steps=3).words == [list("ab"), list("aabb")]
    assert language(model, 4, "b", max_steps=3).words == []
    assert language(model, 0, max_steps=1).words == [[]]


def test_insertion_deletion_with_rejected_growth_and_dedup_across_steps():
    model = parse_model("""
    [symbols]
    terminals = "a"
    [model]
    reject_max_len = 2
    [axioms]
    1 = ["a"]
    [rules]
    ins(,a,)
    del(,a,)
    """)
    result = language(model, 2)
    assert (result.words, result.status) == ([[], ["a"], ["a", "a"]], 0)
    settings = Settings(history=False, reject_max_len=2)
    partial = language(model, 2, max_steps=4, settings=settings)
    assert (partial.words, partial.counts, partial.status) == (result.words, {0: 1, 1: 1, 2: 1}, 3)


def test_other_components_are_explored_even_with_an_empty_selected_frontier():
    model = parse_model("""
    [symbols]
    terminals = "a"
    [axioms]
    1 = ["S"]
    [rules.1]
    S -> a, 2
    [rules.2]
    send(), 3
    [rules.3]
    a ->, 3
    """)
    assert language(model, 1).words == []
    assert language(model, 1, component=2).words == [["a"]]
    assert language(model, 1, component=3).words == [[], ["a"]]


def test_symbol_order_and_whole_word_symbol_regex():
    model = parse_model(MULTI)
    result = language(model, 2)
    assert result.words == [[], ["zz"], ["aa"], ["bb"], ["zz", "bb"], ["aa", "zz"], ["bb", "aa"]]
    assert model.lexicon.alphabet == {"zz", "aa", "S", "bb"}
    assert language(model, 2, "{Extra}aa|zz").words == [["zz"], ["bb", "aa"]]
    no_alphabet = parse_model(MULTI.replace('alphabet = "zz aa S"', 'lexemes = "zz aa S"'))
    assert language(no_alphabet, 1).words == [[], ["aa"], ["bb"], ["zz"]]


def test_configured_filters_and_keep_apply_to_candidates():
    model = parse_model(BRANCH)
    settings = Settings(reject_strings="a", filters={1: {"forbid": ["b"]}})
    result = language(model, 1, settings=settings)
    assert (result.words, result.status) == ([[]], 0)
    assert result.restrictions["reject_strings"] == "a"
    assert result.restrictions["component_filters"] == [1]

    def keep(word, component, ctx):
        assert (component, ctx.step) == (0, 1)
        return word == "b"

    partial = language(model, 1, keep=keep)
    assert (partial.words, partial.status) == ([[], ["b"]], 3)
    assert partial.restrictions["python_filter"] is True
    assert "keep is not declared pure" in partial.detail
    keep.pure = True
    assert language(model, 1, keep=keep).status == 0


def test_digest_history_and_impure_component_or_mark_callbacks_are_partial():
    model = parse_model(BRANCH)
    result = language(model, 1, settings=Settings(hash_history=True))
    assert (result.reason, result.status) == ("frontier_exhausted", 3)
    assert "digests may collide" in result.detail
    assert language(model, 1, settings=Settings(history=False, hash_history=True)).status == 0

    def predicate(word):
        return False

    for settings in (Settings(filters={1: {"forbid": [predicate]}}),
                     Settings(marks={1: {"seen": {"pattern": "a", "expected_re": predicate}}})):
        result = language(model, 1, settings=settings)
        assert (result.words, result.status) == ([[], ["a"], ["b"]], 3)
        assert "predicate" in result.detail


@pytest.mark.parametrize("option,value,limit", [
    ("max_step_candidates", 1, "max-step-candidates"),
    ("max_history", 3, "max-history"),
    ("max_step_accepted", 1, "max-step-accepted"),
    ("max_history", 0, "max-history"),
])
def test_limits_keep_axioms_and_discard_incomplete_steps(option, value, limit):
    result = language(parse_model(BRANCH), 1, **{option: value})
    assert (result.words, result.steps, result.reason, result.limit, result.status) == ([[]], 0, "limit", limit, 3)
    assert result.bounds[option] == value


def test_depth_zero_includes_axioms_and_exhaustion_at_bound_is_complete():
    model = parse_model(BRANCH)
    result = language(model, 1, max_steps=0)
    assert (result.words, result.steps, result.reason, result.status) == ([[]], 0, "depth_bound", 3)
    assert language(model, 1, max_steps=2).status == 0


def test_interrupt_in_simulator_keeps_completed_steps():
    def keep(word, component):
        if word == "b":
            raise KeyboardInterrupt
        return True

    result = language(parse_model(BRANCH), 1, keep=keep)
    assert (result.words, result.steps, result.reason, result.status) == ([[]], 0, "interrupted", 3)


class Clock:
    seconds = 1
    stopped = False

    def expired(self):
        return self.stopped


def test_time_before_simulation(monkeypatch):
    clock = Clock()
    clock.stopped = True
    monkeypatch.setattr(_language, "Deadline", lambda *args: clock)

    def fail(*args, **kwargs):
        pytest.fail("simulator started after the deadline")

    monkeypatch.setattr(_language, "Simulator", fail)
    result = language(parse_model(BRANCH), 1, max_time=1)
    assert (result.words, result.reason, result.status) == ([], "time", 3)


@pytest.mark.parametrize("stop", ["time", "interrupted"])
def test_collection_does_not_publish_a_prefix_of_a_step(monkeypatch, stop):
    clock = Clock()
    monkeypatch.setattr(_language, "Deadline", lambda *args: clock)

    class Pattern:
        def fullmatch(self, word):
            if word == "b":
                if stop == "interrupted":
                    raise KeyboardInterrupt
                clock.stopped = True
            return True

    monkeypatch.setattr(_language, "compile_pattern", lambda *args: Pattern())
    result = language(parse_model(BRANCH), 1, ".*", max_time=1)
    assert (result.words, result.steps, result.reason, result.status) == ([[]], 0, stop, 3)


def test_time_after_exploration_preserves_collected_words(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(_language, "Deadline", lambda *args: clock)
    model = parse_model(BRANCH)
    tokens = model.lexicon.tokens

    def decode(word):
        clock.stopped = True
        return tokens(word)

    monkeypatch.setattr(model.lexicon, "tokens", decode)
    result = language(model, 1, max_time=1)
    assert (result.words, result.steps, result.reason, result.status) == ([[], ["a"], ["b"]], 2, "time", 3)


def test_pruner_polls_the_deadline(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(_language, "Deadline", lambda *args: clock)
    prune = _language.Pruner.__call__
    polled = []

    def delayed_prune(self, candidates):
        clock.stopped = True
        try:
            return prune(self, candidates)
        finally:
            polled.append(self.check is not None)

    monkeypatch.setattr(_language.Pruner, "__call__", delayed_prune)
    result = language(parse_model(BRANCH), 1, max_time=1, max_nonterminals=0)
    assert (result.words, result.steps, result.reason, polled) == ([[]], 0, "time", [True])


@pytest.mark.parametrize("option", ["max_len", "component", "max_steps", "max_nonterminals",
                                    "max_step_candidates", "max_history", "max_step_accepted"])
@pytest.mark.parametrize("value", [True, 1.5, -1])
def test_api_rejects_invalid_integer_counts(option, value):
    with pytest.raises(GcrsimError):
        language(parse_model(BRANCH), **{"max_len": 1, option: value})


def test_bad_pattern_and_terminal_override():
    with pytest.raises(GcrsimError, match="bad --match regular expression"):
        language(parse_model(BRANCH), 1, "[")
    model = parse_model(BRANCH.replace('terminals = "a b"', ""))
    with pytest.raises(GcrsimError, match="terminals are not declared"):
        language(model, 1)
    assert language(model, 1, terminals=["a"]).words == [[], ["a"]]


def test_cli_aliases_and_conflicting_selectors(tmp_path, capsys):
    path = tmp_path / "model.txt"
    path.write_text(MULTI, encoding="utf-8")
    outputs = []
    for selector in (["--language"], ["--mode", "language"], ["--mode=language"]):
        assert main([str(path), *selector, "--max-word-len", "2"]) == 0
        outputs.append(capsys.readouterr().out)
    assert len(set(outputs)) == 1
    assert "(empty word)\nzz\naa\nbb\nzz|bb" in outputs[0]
    assert "Counts by symbol length 0=1, 1=3, 2=3" in outputs[0]
    assert "complete for component 1 of the effective configured model" in outputs[0]
    assert operations.select(["--language", str(path)])[0].name == "language"
    for selectors in (["--language", "--mode", "language"], ["--language", "--search", "aa"],
                      ["--language", "--language"]):
        assert main([str(path), *selectors, "--max-word-len", "2"]) == 2
        assert "more than one mode selector" in capsys.readouterr().err


def test_cli_jsonl_options_and_messages(tmp_path, capsys):
    path = tmp_path / "model.txt"
    path.write_text(MULTI + "\nS -> bb\n", encoding="utf-8")
    config = tmp_path / "config.toml"
    config.write_text('[model]\nreject_max_len = 1\nreject_strings = "S"\n', encoding="utf-8")
    script = tmp_path / "filter.py"
    script.write_text('print("loaded")\ndef keep(s, c):\n    print(s)\n    return True\n', encoding="utf-8")
    assert main([str(path), "--language", "--max-word-len", "2", "--format", "jsonl", "--config", str(config),
                 "--python-filter", str(script), "--progress", "--max-steps", "0", "--max-nonterminals", "0"]) == 3
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert lines[0]["type"] == "header" and lines[0]["mode"] == "language"
    assert lines[1] == {"type": "message", "text": "loaded"}
    assert lines[2] == {"type": "word", "word": [], "word_string": ""}
    assert lines[-2] == {"type": "word", "word": ["bb", "aa"], "word_string": "bb|aa"}
    end = lines[-1]
    assert (end["type"], end["steps"], end["status"], end["outcome"], end["reason"]) == ("end", 0, 3, "partial", "depth_bound")
    assert end["counts"] == {"0": 1, "1": 3, "2": 3}
    assert end["bounds"]["max_word_len"] == 2 and end["bounds"]["max_steps"] == 0
    assert {key: end["restrictions"][key] for key in ("reject_max_len", "reject_strings", "python_filter", "max_nonterminals")} == {
        "reject_max_len": 1, "reject_strings": "S", "python_filter": True, "max_nonterminals": 0,
    }


@pytest.mark.parametrize("overrides,length,pattern,words", [
    ([], 1, "AB", []),
    (["--reject-max-len", "2"], 2, "AB", []),
    (["--reject-strings="], 1, "", []),
    (["--reject-max-len", "2", "--reject-strings="], 2, "", [["a"]]),
    (["--reject-max-len", "2", "--reject-strings", "a"], 2, "a", []),
])
def test_cli_rejection_overrides_config_layers(tmp_path, capsys, overrides, length, pattern, words):
    path = tmp_path / "model.txt"
    path.write_text(SHRINK + '\n[model]\nreject_max_len = 9\nreject_strings = "S"\n', encoding="utf-8")
    config = tmp_path / "config.toml"
    config.write_text('[model]\nreject_max_len = 1\nreject_strings = "AB"\n', encoding="utf-8")
    args = [str(path), "--mode", "language", "--max-word-len", "1", "--config", str(config), "--format", "jsonl"]

    assert main(args + overrides) == 0
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [record["word"] for record in records if record["type"] == "word"] == words
    restrictions = records[-1]["restrictions"]
    assert (restrictions["reject_max_len"], restrictions["reject_strings"]) == (length, pattern)


def test_cli_progress_and_callback_output(tmp_path, capsys, monkeypatch):
    path = tmp_path / "model.txt"
    path.write_text(BRANCH, encoding="utf-8")
    script = tmp_path / "filter.py"
    script.write_text('def keep(s, c):\n    print("saw " + s)\n    return True\nkeep.pure = True\n', encoding="utf-8")
    args = [str(path), "--language", "--max-word-len", "1", "--format", "jsonl", "--python-filter", str(script), "--progress"]
    assert main(args) == 0
    cap = capsys.readouterr()
    records = [json.loads(line) for line in cap.out.splitlines()]
    assert [r["text"] for r in records if r["type"] == "message"] == ["saw a", "saw b"]
    assert "step 1" in cap.err and "step 2" in cap.err

    def interrupt(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr(Simulator, "step", interrupt)
    assert main(args) == 3
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [r["word"] for r in records if r["type"] == "word"] == [[]]
    assert records[-1]["reason"] == "interrupted"


def test_jsonl_interrupted_before_header_still_has_header_and_end(tmp_path, capsys, monkeypatch):
    path = tmp_path / "model.txt"
    path.write_text(BRANCH, encoding="utf-8")
    header = operations.Jsonl.header

    def interrupt_once(self, *args, **kwargs):
        monkeypatch.setattr(operations.Jsonl, "header", header)
        raise KeyboardInterrupt

    monkeypatch.setattr(operations.Jsonl, "header", interrupt_once)
    assert main([str(path), "--language", "--max-word-len", "1", "--format", "jsonl"]) == 3
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [record["type"] for record in records] == ["header", "end"]
    assert records[0]["mode"] == "language" and records[1]["reason"] == "interrupted"


def test_cli_requires_a_length_and_reports_bad_arguments(tmp_path, capsys):
    path = tmp_path / "model.txt"
    path.write_text(SHRINK, encoding="utf-8")
    cmd = [str(path), "--language"]
    with pytest.raises(SystemExit) as exc:
        main(cmd)
    assert exc.value.code == 2
    assert "--max-word-len" in capsys.readouterr().err
    for args, diagnostic in [
        (["--max-word-len", "-1"], "nonnegative integer"),
        (["--max-word-len", "1", "--reject-max-len", "-1"], "--reject-max-len must be a nonnegative integer"),
        (["--max-word-len", "1", "--match", "["], "bad --match regular expression"),
        (["--max-word-len", "1", "--component", "0"], "component must be between"),
    ]:
        assert main(cmd + args) == 2
        assert diagnostic in capsys.readouterr().err

    assert main(cmd + ["--max-word-len", "1", "--match", "a"]) == 0
    assert "\na\n" in capsys.readouterr().out
    path.write_text(SHRINK + "\n[model]\nreject_max_len = 1\n", encoding="utf-8")
    assert main(cmd + ["--max-word-len", "1", "--match", "a"]) == 0
    out = capsys.readouterr().out
    assert "no words" in out and "reject_max_len = 1" in out
