"""The ten worked examples of SPEC.md, as written by the author of the reference interpreter."""
from gcrsim._reference import START, END, ANY, Rule, edits, candidates, step, run


def word(text):
    return tuple(text)


def words(*texts):
    return [word(text) for text in texts]


def plain(left, right):
    return Rule("sub", 0, 0, x=word(left), y=word(right))


# 1. Overlapping occurrences.
r = plain("aa", "b")
assert edits(r, word("aaa")) == [
    (0, 2, word("b")),
    (1, 3, word("b")),
]
assert candidates(r, word("aaa")) == words("ba", "ab")
assert run([words("aaa")], [r], 1, use_history=False) == [
    {"contents": [words("aaa")], "raw": 0},
    {"contents": [words("ba", "ab")], "raw": 2},
]

# 2. Insertion between contexts.
r = Rule("sub", 0, 0, u=word("a"), y=word("X"), v=word("b"))
assert edits(r, word("abab")) == [
    (1, 1, word("X")),
    (3, 3, word("X")),
]
assert candidates(r, word("abab")) == words("aXbab", "abaXb")

# 3. Insertion with empty contexts.
r = plain("", "X")
assert edits(r, word("ab")) == [
    (0, 0, word("X")),
    (1, 1, word("X")),
    (2, 2, word("X")),
]
assert candidates(r, word("ab")) == words("Xab", "aXb", "abX")

# 4. Deletion, including deletion of the empty string.
r = Rule("sub", 0, 0, u=word("a"), x=word("b"))
assert candidates(r, word("ab")) == words("a")
assert candidates(plain("", ""), word("ab")) == words("ab", "ab", "ab")

# 5. ANY consumes exactly one symbol.
r = Rule("sub", 0, 0, u=word("a"), x=(ANY,), y=word("X"), v=word("b"))
assert edits(r, word("abab")) == []
assert edits(r, word("aab")) == [(1, 2, word("X"))]
assert candidates(r, word("aab")) == words("aXb")

# 6. START consumes nothing.
r = Rule("sub", 0, 0, u=(START,), y=word("X"), v=word("a"))
assert edits(r, word("aa")) == [(0, 0, word("X"))]
assert candidates(r, word("aa")) == words("Xaa")

# 7. END consumes nothing.
r = Rule("sub", 0, 0, u=word("a"), y=word("X"), v=(END,))
assert edits(r, word("aba")) == [(3, 3, word("X"))]
assert candidates(r, word("aba")) == words("abaX")

# 8. Guarded send.
r = Rule("send", 0, 0, permit=(word("a"),))
assert edits(r, word("ab")) == [(0, 0, ())]
assert candidates(r, word("ab")) == words("ab")
assert candidates(r, word("b")) == []

# 9. History suppresses an identity candidate.
r = plain("a", "a")
assert run([words("a")], [r], 1)[1] == {
    "contents": [[]], "raw": 1
}
assert run([words("a")], [r], 1, use_history=False)[1] == {
    "contents": [words("a")], "raw": 1
}

# 10. Length rejection still records the candidate in history.
r = plain("a", "aa")
initial_contents = [words("a")]
initial_history = [{word("a")}]
new_contents, new_history, raw = step(
    initial_contents, initial_history, [r], True, 1
)
assert new_contents == [[]]
assert raw == 1
assert new_history == [{word("a"), word("aa")}]
assert initial_contents == [words("a")]
assert initial_history == [{word("a")}]

# Supply a later content that generates "aa" again. Relaxing the length
# limit makes its rejection demonstrate the retained history entry.
later_contents, later_history, later_raw = step(
    [words("a")], new_history, [r], True, 2
)
assert later_contents == [[]]
assert later_history == new_history
assert later_raw == 1


def test_the_worked_examples_of_the_specification_hold():
    """The asserts above run when this module is imported."""
