r"""Occurrence identities along a derivation (private helper): consumed, produced and context occurrences, the row order."""
import os

import pytest

import gcrsim
from gcrsim import Settings, parse_model, parse_model_file, replay
from gcrsim._occurrences import OccurrenceError, occurrences
from conftest import ROOT


def derive(rules, forms, axiom=None, extra=""):
    """The replay of ``forms`` (the first one is the axiom) in a model whose component 1 has ``rules``, and its occurrence trace."""
    first = forms[0].split(":")[-1] if axiom is None else axiom
    m = parse_model('%s[axioms]\n1 = ["%s"]\n[rules.1]\n%s\n' % (extra, first, rules))
    rep = replay(m, ["1:" + f if ":" not in f else f for f in forms])
    assert rep.ok, rep.failure
    return rep, occurrences(rep.steps)


def row(t, ids=None):
    return [t.nodes[i].symbol for i in (t.order if ids is None else ids)]


# -- insertion ---------------------------------------------------------------------------------


def test_insertion_with_contexts():
    rep, t = derive("ins(a, c, b), 1", ["ab", "acb"])
    e = t.events[0]
    assert (e.kind, e.consumed, e.produced, e.left_context, e.right_context) == ("ins", [], [2], [0], [1])
    assert e.supported and e.note is None and not e.ambiguous
    assert t.order == [0, 2, 1] and t.survivors == [0, 2, 1]
    assert [f.ids for f in t.forms] == [[0, 1], [0, 2, 1]]
    assert [(n.symbol, n.created, n.deleted) for n in t.nodes] == [("a", 0, None), ("b", 0, None), ("c", 1, None)]


def test_insertion_with_contexts_of_length_two():
    rep, t = derive("ins(ab, c, ba), 1", ["abba", "abcba"])
    e = t.events[0]
    assert (e.left_context, e.right_context, e.produced) == ([0, 1], [2, 3], [4])
    assert t.order == [0, 1, 4, 2, 3]


def test_insertion_with_left_context_only_goes_right_after_it():
    rep, t = derive("ins(a, c, ), 1", ["ab", "acb"])
    e = t.events[0]
    assert (e.left_context, e.right_context, e.produced) == ([0], [], [2])
    assert t.order == [0, 2, 1]


def test_insertion_with_right_context_only_goes_right_before_it():
    rep, t = derive("ins(, c, b), 1", ["ab", "acb"])
    e = t.events[0]
    assert (e.left_context, e.right_context) == ([], [1])
    assert t.order == [0, 2, 1]


def test_insertion_without_left_context_goes_before_the_next_present_letter():
    # ab -> acb -> ab (c erased) -> adb: d is placed before b, after the erased c
    rep, t = derive("ins(a, c, b), 1\ndel(a, c, b), 1\nins(, d, b), 1", ["ab", "acb", "ab", "adb"])
    assert t.order == [0, 2, 3, 1] and row(t) == ["a", "c", "d", "b"]
    assert t.events[2].produced == [3] and t.events[2].right_context == [1]
    # with a left context the new letter follows its context directly, before the erased c
    rep, t = derive("ins(a, c, b), 1\ndel(a, c, b), 1\nins(a, d, b), 1", ["ab", "acb", "ab", "adb"])
    assert t.order == [0, 3, 2, 1]


def test_insertion_at_the_end_without_contexts_goes_to_the_end_of_the_row():
    rep, t = derive("ins(, c, {end}), 1\ndel(, c, {end}), 1\nins(, d, {end}), 1", ["ab", "abc", "ab", "abd"])
    assert t.order == [0, 1, 2, 3] and t.events[0].produced == [2] and t.events[2].produced == [3]
    assert t.events[0].right_context == [] and t.events[0].left_context == []
    assert t.events[1].consumed == [2]


def test_empty_word_and_empty_edits():
    rep, t = derive("ins(, d, ), 1", ["", "d"], axiom="")
    assert t.events[0].produced == [0] and t.order == [0] and t.survivors == [0]
    assert t.forms[0].ids == [] and not t.events[0].ambiguous
    # an insertion of nothing: no occurrence, the form is the same, the contexts are still matched
    m = parse_model('[axioms]\n1 = ["ab"]\n[rules.1]\nins(a,,b), 1\n')
    rep = replay(m, ["ab", "ab"])
    t = occurrences(rep.steps)
    e = t.events[0]
    assert (e.consumed, e.produced, e.left_context, e.right_context) == ([], [], [0], [1])
    # a rule that replaces nothing by nothing (plain, no contexts)
    m = parse_model('[axioms]\n1 = ["ab"]\n[rules.1]\n->, 1\n')
    rep = replay(m, ["ab", "ab"])
    assert rep.ok
    t = occurrences(rep.steps)
    assert (t.events[0].consumed, t.events[0].produced) == ([], []) and t.order == [0, 1]


def test_axiom_only_derivation():
    t = occurrences([], first=["a", "b", "c"], first_component=1)
    assert t.events == [] and t.order == [0, 1, 2] and t.survivors == [0, 1, 2]
    assert len(t.forms) == 1 and t.forms[0].component == 1
    assert [n.symbol for n in t.nodes] == ["a", "b", "c"]
    t = occurrences([], first=[])
    assert t.nodes == [] and t.order == [] and t.survivors == []
    with pytest.raises(OccurrenceError):
        occurrences([])


# -- deletion, substitution, plain rules -------------------------------------------------------------


def test_deletion():
    rep, t = derive("del(a, c, b), 1", ["acb", "ab"])
    e = t.events[0]
    assert (e.kind, e.consumed, e.produced, e.left_context, e.right_context) == ("del", [1], [], [0], [2])
    assert t.order == [0, 1, 2] and t.survivors == [0, 2]
    assert t.nodes[1].deleted == 1 and t.nodes[0].deleted is None


def test_deletion_of_two_letters_with_contexts_of_length_two():
    rep, t = derive("del(ab, cd, ef), 1", ["abcdef", "abef"])
    e = t.events[0]
    assert (e.consumed, e.left_context, e.right_context) == ([2, 3], [0, 1], [4, 5])


def test_substitution_stays_at_the_place_of_what_it_replaced():
    rep, t = derive("sub(a, c, xy, b), 1", ["acb", "axyb"])
    e = t.events[0]
    assert (e.kind, e.consumed, e.produced, e.left_context, e.right_context) == ("sub", [1], [3, 4], [0], [2])
    assert t.order == [0, 1, 3, 4, 2] and t.survivors == [0, 3, 4, 2]


def test_substitution_is_placed_after_the_consumed_letter_not_before_an_erased_one():
    # ab -> acb -> ab (c erased) -> ay (b replaced by y): y follows b in the row
    rep, t = derive("ins(a, c, b), 1\ndel(a, c, b), 1\nsub(a, b, y, ), 1", ["ab", "acb", "ab", "ay"])
    assert t.events[2].consumed == [1] and t.events[2].produced == [3]
    assert row(t) == ["a", "c", "b", "y"] and t.order == [0, 2, 1, 3]


def test_plain_rules_have_no_contexts_and_replace_in_place():
    rep, t = derive("S -> a S b, 1\nS -> a b, 1", ["S", "aSb", "aabb"])
    e0, e1 = t.events
    assert (e0.kind, e0.consumed, e0.produced, e0.left_context, e0.right_context) == ("plain", [0], [1, 2, 3], [], [])
    assert (e1.consumed, e1.produced) == ([2], [4, 5])
    assert t.order == [0, 1, 2, 4, 5, 3]
    assert t.survivors == [1, 4, 5, 3] and row(t, t.survivors) == ["a", "a", "b", "b"]
    assert t.nodes[0].deleted == 1 and t.nodes[2].deleted == 2


def test_plain_rule_that_erases_and_that_creates_from_nothing():
    rep, t = derive("S ->, 1", ["S", "1:"])
    e = t.events[0]
    assert (e.consumed, e.produced) == ([0], []) and t.survivors == [] and t.forms[1].ids == []
    rep, t = derive("->a, 1", ["", "a"], axiom="")
    assert t.events[0].produced == [0] and t.order == [0] and t.events[0].consumed == []


# -- send, components ----------------------------------------------------------------------------


def test_send_changes_the_component_only():
    rep, t = derive("a -> b, 1\nsend(), 2\n[rules.2]\nb -> c, 1", ["a", "b", "2:b", "c"], axiom="a")
    e = t.events[1]
    assert e.kind == "send" and (e.consumed, e.produced) == ([], [])
    assert (e.source_component, e.target_component) == (0, 1)
    assert e.supported and e.left_context == [] and e.right_context == []
    assert [f.component for f in t.forms] == [0, 0, 1, 0]
    assert t.forms[1].ids == t.forms[2].ids == [1]
    assert t.nodes[1].created_component == 0 and t.events[0].target_component == 0
    assert t.to_dict()["forms"][2]["component"] == 2  # to_dict counts from 1


def test_a_node_remembers_the_component_in_which_it_was_created():
    rep, t = derive("a -> b, 2\n[rules.2]\nb -> c, 1", ["a", "2:b", "c"], axiom="a")
    assert t.nodes[1].created_component == 1 and t.nodes[2].created_component == 0
    assert (t.events[0].source_component, t.events[0].target_component) == (0, 1)


# -- regular expressions ----------------------------------------------------------------------------


def test_regex_rule_with_a_capture_gives_no_identity_link():
    rule = "re(a(b)) -> %s1%s1, 1" % (chr(92), chr(92))
    rep, t = derive(rule, ["xaby", "xbby"], axiom="xaby")
    e = t.events[0]
    assert e.kind == "re" and not e.supported and "regular" in e.note
    assert e.consumed == [1, 2] and e.produced == [4, 5]  # the copied b is a new occurrence
    assert e.left_context == [] and e.right_context == []
    assert t.survivors == [0, 4, 5, 3] and row(t, t.survivors) == ["x", "b", "b", "y"]
    assert t.order == [0, 1, 2, 4, 5, 3]


# -- multi-character symbols, classes, {start} and {end} --------------------------------------------------


def test_multi_character_symbols_count_as_one_occurrence():
    m = parse_model('[symbols]\nalphabet = "p1 p2 S"\n[run]\nprint_sep = " "\nword_sep = " "\n[axioms]\n1 = ["S"]\n'
                    '[rules.1]\nS -> p1 S, 1\nins(p1, p2, S), 1\ndel(p2, S, ), 1\n')
    rep = replay(m, ["S", "p1 S", "p1 p2 S", "p1 p2"])
    assert rep.ok, rep.failure
    t = occurrences(rep.steps)
    assert t.events[1].left_context == [1] and t.events[1].right_context == [2]
    assert t.events[2].kind == "del" and t.events[2].consumed == [2]
    assert [n.symbol for n in t.nodes] == ["S", "p1", "S", "p2"]
    assert t.order == [0, 1, 3, 2] and row(t, t.survivors) == ["p1", "p2"]


def test_classes_and_any_in_contexts_match_one_occurrence_each():
    extra = '[symbols.classes]\nV = "a b"\n'
    rep, t = derive("ins({V}, c, {any}), 1", ["abd", "abcd"], extra=extra)
    e = t.events[0]
    assert (e.left_context, e.right_context, e.produced) == ([1], [2], [3])
    assert t.order == [0, 1, 3, 2]
    rep, t = derive("ins({any}{V}, c, {any}{any}), 1", ["abde", "abcde"], extra=extra)
    assert (t.events[0].left_context, t.events[0].right_context) == ([0, 1], [2, 3])


def test_start_and_end_are_zero_width():
    rep, t = derive("ins({start}, z, {any}), 1", ["ab", "zab"])
    e = t.events[0]
    assert (e.left_context, e.right_context, e.produced) == ([], [0], [2]) and t.order == [2, 0, 1]
    rep, t = derive("ins({any}, y, {end}), 1", ["ab", "aby"])
    e = t.events[0]
    assert (e.left_context, e.right_context, e.produced) == ([1], [], [2]) and t.order == [0, 1, 2]
    rep, t = derive("del({start}a, b, {end}), 1", ["ab", "a"])
    e = t.events[0]
    assert (e.left_context, e.consumed, e.right_context) == ([0], [1], [])


# -- ambiguous steps -------------------------------------------------------------------------------


def test_replay_step_with_several_ways_is_marked_and_follows_the_recorded_application():
    rep, t = derive("ins(, c, ), 1", ["ab", "cab"])
    assert rep.steps[0].ways == 1 and not t.events[0].ambiguous
    # inserting an a gives aab at the position 0 or 1: the record holds the first
    rep, t = derive("ins(, a, ), 1", ["ab", "aab"])
    assert rep.steps[0].ways == 2 and rep.steps[0].start == 0
    e = t.events[0]
    assert e.ambiguous and e.produced == [2] and t.order == [2, 0, 1]
    assert t.to_dict()["events"][0]["ambiguous"] is True


def test_derivation_steps_are_never_marked():
    sim = gcrsim.Simulator(parse_model('[axioms]\n1 = ["ab"]\n[rules.1]\nins(, a, ), 1\n'), Settings(reject_max_len=1000),
                           write=lambda s: None, retain=True)
    sim.run(2)
    t = occurrences(sim.trace("aab", 0))
    assert [e.ambiguous for e in t.events] == [False]


# -- the same data as the arcs of the text-trace picture ----------------------------------------------------------
# The picture tool reads the text trace of an insertion-deletion system: it puts all letters in one row, a new letter right
# after its left context if the rule has one, otherwise right before the next present letter (the end of the row if there is
# none); the context letters are the nearest ones around the edit; the letters of one step stay together.


def test_arc_picture_case_one_an_bn():
    # a^n b^n from ab with ins(a, ab, b): ab -> aabb -> aaabbb
    rep, t = derive("ins(a, ab, b), 1", ["ab", "aabb", "aaabbb"])
    # the second step is the first position that fits: between the inserted a and b
    assert [e.left_context for e in t.events] == [[0], [2]] and [e.right_context for e in t.events] == [[1], [3]]
    assert [e.produced for e in t.events] == [[2, 3], [4, 5]]
    assert t.order == [0, 2, 4, 5, 3, 1] and row(t) == ["a", "a", "a", "b", "b", "b"]
    assert [f.ids for f in t.forms] == [[0, 1], [0, 2, 3, 1], [0, 2, 4, 5, 3, 1]]
    assert t.survivors == t.order


def test_arc_picture_case_two_deletion_and_reinsertion_among_erased_letters():
    # ins(a,c,b): ab -> acb; del(a,c,b): -> ab; ins(,d,b) without left context: before the b, after the erased c
    rep, t = derive("ins(a, c, b), 1\ndel(a, c, b), 1\nins(, d, b), 1\ndel(, d, b), 1", ["ab", "acb", "ab", "adb", "ab"])
    assert t.order == [0, 2, 3, 1]
    assert [(e.consumed, e.produced, e.left_context, e.right_context) for e in t.events] == [
        ([], [2], [0], [1]), ([2], [], [0], [1]), ([], [3], [], [1]), ([3], [], [], [1])]


def test_arc_picture_case_three_no_contexts_before_the_next_letter_or_at_the_end():
    rep, t = derive("ins(, a, ), 1\ndel(, a, ), 1", ["", "a", "1:"], axiom="")
    assert t.order == [0] and t.events[0].produced == [0] and t.events[1].consumed == [0]
    assert t.events[0].left_context == [] and t.events[1].right_context == []
    # on the word a: b goes to the end of the row, then c before the first present letter
    rep, t = derive("ins(,b,{end}), 1\nins(,c,{start}), 1", ["a", "ab", "cab"], axiom="a")
    assert t.order == [2, 0, 1] and row(t) == ["c", "a", "b"] and t.events[1].produced == [2]


# -- the invariant over real derivations ----------------------------------------------------------------------


@pytest.mark.parametrize("name", ["02_insdel", "03_marcus_internal", "04_marcus_external", "05_evolutionary_processors"])
def test_cookbook_derivations_keep_the_invariant(name):
    path = os.path.join(ROOT, "examples", "cookbook", name + ".txt")
    sim = gcrsim.Simulator(parse_model_file(path), Settings(reject_max_len=60), write=lambda s: None, retain=True)
    sim.run(8)
    checked = 0
    for comp, forms in enumerate(sim.cur):
        for s in sorted(forms)[:40]:
            chain = sim.trace(s, comp)
            if not chain:
                continue
            t = occurrences(chain)
            assert len(t.events) == len(chain)
            assert [t.nodes[i].symbol for i in t.survivors] == chain[-1].after
            assert sorted(t.order) == list(range(len(t.nodes)))
            for ev, st in zip(t.events, chain):
                assert len(ev.consumed) == len(st.removed) and len(ev.produced) == len(st.inserted)
            checked += 1
    assert checked > 0


def test_a_broken_chain_is_an_internal_error():
    m = parse_model('[axioms]\n1 = ["ab"]\n[rules.1]\nins(a, c, b), 1\ndel(a, c, b), 1\n')
    rep = replay(m, ["ab", "acb", "ab"])
    with pytest.raises(OccurrenceError):
        occurrences([rep.steps[0], rep.steps[0]])
