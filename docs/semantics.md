# What a step does

This is the meaning of a model in plain words. The exact version, for the part of the language without regular expressions, is
[SPEC.md](../SPEC.md); the syntax is in [model-syntax.md](model-syntax.md).

## In short

A run starts with the axioms as the content of the components. Each step does the same thing to every string:

1. **Rewrite.** Every rule of the string's component that applies is applied at every position where it matches. Each result is a
   *candidate* for the component that the rule names.
2. **Filter.** A candidate is dropped if it was seen before (the history), is too long (`reject_max_len`), matches `reject_strings`,
   or is rejected by the filters of its component or by the Python filter function. The others are *accepted*.
3. **Mark.** An accepted string that matches a mark of its component is recorded with its label and the step; with a trace, its
   derivation is kept too ([marks-and-derivations.md](marks-and-derivations.md)).
4. **Replace.** The accepted strings are the new content of the components, and the old content is discarded.

The run stops after the given number of steps, when no string remains, or at a limit. The rest of this page gives the detail of
these four points.

## Components and strings

A model has numbered **components** (the states of a graph control, the nodes of a network, the matrices of a matrix grammar...).
Each component holds a list of strings, its **content**. At the start the content of component *i* is the list of its axioms.
A string is a sequence of **symbols**; a symbol is one character, or a declared multi-character symbol (a lexeme).

## One step

All components advance together. In one step:

1. **Generation.** Take every string of every component, in order of component and then in the order of the content. For each
   rule of that component, in the order they are written, produce the rule's **candidates** for that string and append them to the
   list of the rule's **target** component.
2. **Filtering.** For every target component, go through its candidates in order and keep a candidate unless
   * it was seen before in that component: with `history = true` (the default) in any earlier step, the history starting with the
     axioms; with `history = false` only earlier in this same step (a duplicate candidate is kept once in either case), or
   * it is longer than `reject_max_len`, or it matches `reject_strings`, or the component conditions or the filter function reject it.
   A candidate is marked as seen as soon as it is looked at, even when a later filter rejects it (except for strings rejected by
   the declarative conditions when `--no-mark-rejected` is used).
3. The kept candidates are the new content of the target component. The old contents are discarded.

So a string lives in a component for exactly one step, unless a rule sends it again. Rules that produce nothing for a string make it
disappear.

## Candidates of a rule

Every rule form is a substitution `sub(u,x,y,v)`: the pattern `u x v` is searched in the string; where it matches, `x` is replaced
by `y` and the contexts `u` and `v` stay. A plain rule `x->y` is `sub("",x,y,"")`, `ins(u,y,v)` is `sub(u,"",y,v)`, `del(u,x,v)` is
`sub(u,x,"",v)`.

* The pattern is tried at **every** start position, so a rule gives at most `length + 1` candidates for a string, and occurrences
  that overlap all count: `aa->b` on `aaa` gives `ba` and `ab`.
* The candidates come in order of increasing position.
* Duplicates are not removed at this stage, but they are by the history in the filtering.
* `send()` gives exactly one candidate, the string itself.
* `{start}` and `{end}` match the empty beginning and end of the string, `{any}` matches one symbol, `{V}` one symbol of a declared class.
* `;permit:` / `;forbid:` / `;permit-any:` are tested on the string first: a rule whose condition fails gives no candidates.
* `re(pattern)->rhs` finds matches of a regular expression at every start position (one match per position) and replaces the match
  by the right-hand side.

## What is not specified by the model

The order in which candidates of **different** rules interleave inside a target component is the order of generation above, so it
is fixed; but nothing in the language depends on it except which duplicate is kept first and the order of the printed list (a stateful
filter function would also see strings in this order).
Derivations are `any`: every applicable rule is applied everywhere, in parallel over the strings; leftmost or rightmost derivation
is not available.

## Stopping

The run stops after the requested number of steps, or earlier when all components are empty (`--run-empty` keeps going), or when a
resource limit is reached (exit status 3, see [cli.md](cli.md)).
