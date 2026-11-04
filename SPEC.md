# Semantics of the plain fragment

This is the precise specification of what gcrsim computes for the *plain fragment*: rules without
regular expressions (`plain`, `ins`, `del`, `sub`, `send`), `permit`/`forbid` words, components, the
history/duplicate filter and the length filter. It is written so that it can be implemented without
looking at the simulator. Anything not stated here is not part of the fragment.

## 1. Objects

* A **symbol** is a non-empty Python `str` of any length (a class, being a `frozenset`, is therefore never a symbol). A **string** is a
  finite sequence of symbols (a Python `tuple` of symbols). The empty string is `()`.
* A **component** is a number `1 .. n`, as in the models. A **content** is an ordered list of strings (duplicates possible
  only in the axioms).
* An **item** is one of: a symbol `a` (matches exactly that symbol); a **class** (a `frozenset` of symbols,
  matches one symbol that is a member); `ANY` (matches one arbitrary symbol); `START` and `END` (match the
  empty sequence at position 0, respectively at position `len(s)`).
* A **rule** has a `source` component, a `target` component, `permit`, `permit_any` and `forbid` (each a tuple of
  non-empty strings), and a **kind**:
  * `sub` with four fields `u`, `x`, `v` (sequences of items) and `y` (a string of symbols): the items `x` are replaced by `y`;
  * `send` (no further fields).
  The model forms map to `sub`: a plain rule `x -> y` is the `sub` with `u=()`, `v=()` and the same `x` and `y`; `ins(u,y,v)` is
  `x=()`; `del(u,x,v)` is `y=()`; `sub(u,x,y,v)` is itself.

## 2. Edits of a rule on a string `s`

Let `n = len(s)`. A *match attempt at position i* (`0 <= i <= n`) matches the item sequence
`W = u ++ x ++ v` against `s` starting at `i`, item by item, left to right, with a cursor `pos` that starts at `i`:

* a symbol item matches if `pos < n` and `s[pos]` equals it; then `pos += 1`;
* a class item matches if `pos < n` and `s[pos]` is a member; then `pos += 1`;
* `ANY` matches if `pos < n`; then `pos += 1`;
* `START` matches if `pos == 0` (the cursor does not move); `END` matches if `pos == n`.

If every item matches, the attempt succeeds. Let `p` be the cursor after the items of `u`, and `q` the cursor
after the items of `x`. The attempt yields the **edit** `(p, q)` with replacement `y`; the **candidate** is
`s[:p] + y + s[q:]`. (Boundary items consume nothing, so `p` and `q` may be smaller than `i + len(u)`.)

`edits(rule, s)` is the list of the edits of all successful attempts, in increasing order of `i`. Properties:
overlapping occurrences all count; the same edit cannot come from two different `i`; there are at most `n + 1`
edits. The contexts `u` and `v` are not changed. A candidate is never searched again by the same rule.

For kind `send` there is exactly one edit, `(0, 0)` with the empty replacement; its candidate is `s` itself.

**Guards.** A rule is *enabled* on `s` if every word of `permit` occurs in `s` as a contiguous subsequence, at least one
word of `permit_any` occurs in `s` (when `permit_any` is not empty), and no word of `forbid` occurs in `s`. If it is not enabled, `edits` is empty. Words are plain symbol sequences
(no classes, no boundaries); an empty word is invalid input.

## 3. One step

State: for every component `c` the **content** `F[c]` (list of strings), and, when **history** is on, a set
`H[c]` of the strings that have ever been *seen as a candidate* in `c`, including candidates later discarded by the length filter (initially the set of the axioms of `c`). Parameter: `max_len`
(an integer, or none for no limit).

1. **Generation.** Create empty lists `C[1..n]` of *raw candidates*. For every component `c` in increasing order,
   for every string `s` in `F[c]` in order, for every rule `r` with `r.source == c` in declaration order, append
   the candidates of `edits(r, s)`, in order, to `C[r.target]`. (Nothing is removed during generation.)
2. **Filtering.** For every target `t` in increasing order, with `seen = H[t]` if history is on and a fresh
   empty set (per target, per step) otherwise: for every candidate `w` of `C[t]` in order:
   * if `w` is in `seen`, discard it;
   * otherwise add `w` to `seen`; then, if `max_len` is not none and `len(w) > max_len`, discard it (it stays in
     `seen`); otherwise append `w` to the new content `N[t]`.
3. The new contents `N[1..n]` replace `F`. The number of raw candidates of the step is `sum(len(C[t]))`.

`len` counts symbols. The first content `F` is the list of axioms of each component, in the given order, with
duplicates kept. A run of `k` steps repeats the step `k` times; the result of step `j` is the list of contents.

## 4. Worked examples (acceptance tests)

Notation: strings are written as words of single-letter symbols; contents as lists.

1. One component, rules `aa -> b`. `F = ["aaa"]`, history off: raw candidates `["ba", "ab"]`; new content `["ba", "ab"]`.
2. `ins(a, X, b)` on `"abab"` gives edits at `p = 1` and `p = 3`: candidates `"aXbab"`, `"abaXb"`.
3. `ins(, X, )` on `"ab"`: edits `p = 0, 1, 2`: `"Xab"`, `"aXb"`, `"abX"`.
4. `del(a, b, )` on `"ab"` gives `"a"`; `del(, , )` (deleting the empty string) on `"ab"` gives `"ab"` three times.
5. `sub(a, {any}, X, b)` on `"abab"`: attempts at `i = 0..`: `W = a, ANY, b`; success at `i = 0`? `s[0]='a'`,
   `s[1]='b'` is ANY, `s[2]='a'` is not `b`: fails; no match at `i = 2` either. With `"aab"`: success at `i = 0` gives edit `(1, 2)` and candidate `"aXb"`.
6. `ins({start}, X, a)` on `"aa"`: only `i = 0` succeeds (START needs `pos == 0`): candidate `"Xaa"`.
7. `ins(a, X, {end})` on `"aba"`: `W = a, END`: success at `i = 2` (`a` at position 2, then pos 3 == n): candidate `"abaX"`.
8. `send()` with `permit: ((a,),)` on `"ab"` gives `"ab"`; on `"b"` gives nothing.
9. History: one component, rule `a -> a`, axiom `"a"`, history on, step 1: raw candidate `"a"`, already in `H`, so the new content is `[]`. With history off: new content `["a"]`.
10. Length filter: `max_len = 1`, rule `a -> aa`, axiom `"a"`: raw `"aa"` is marked seen but discarded; new content `[]`; if a later step produces `"aa"` again (history on) it is discarded as a duplicate.

## 5. What the tests compare

For a model given as data (axioms, rules, classes, `history`, `max_len`) and `k` steps, an implementation must
produce, for each step, the list of contents (lists of tuples of symbols, in order) and the raw candidate
count. Order matters.

## 6. Out of scope of this specification

How model *text* becomes symbol sequences (lexemes, the alphabet, longest-match tokenisation, the internal
private-use characters) is part of the model language, not of this fragment: the specification starts from
sequences of symbols. The engine's tokenisation is tested separately (`tests/test_lexicon.py`).
