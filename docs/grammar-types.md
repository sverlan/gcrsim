# Types of grammars and systems that gcrsim supports

gcrsim runs one kind of object: components that hold sets of strings, and rules that rewrite a string of one component and send the
result to another. Many classical grammars and systems are special cases of it, and this page lists them, says how each one is written
in a model, and says what is missing. For each entry [grammars.md](grammars.md), the cookbook, gives the grammar in its classical notation,
the model, and the command that runs it; the entry numbers below refer to it, and the models are the files in [`examples/cookbook/`](../examples/cookbook/). The
model language is described in [model-syntax.md](model-syntax.md).

## How to read the tables

The column *Support* says how the grammar is written in a model:

* **direct**: the rules and conditions of the grammar are written as they are, with the rule forms of the language;
* **encoding**: the grammar is written through a small encoding, typically a control structure built from components and `send()`,
  or a few helper symbols; the model is as large as the grammar, but it is not a one-to-one copy of the definition;
* **extension**: a short form for something the classical definition writes with several rules;
* **in part**: it works only in some cases (the limit is stated);
* **no**: not available.

Three ideas are behind most of the encodings, so it helps to know them first:

* **Components are states.** A grammar with a control structure (a graph, a matrix, a regular language, a cycle of rule sets) becomes a
  set of components. A rule leads to another component through its *target*, and the target is the *success field* of the classical
  definition.
* **`send()` is a free move.** `send(), N` hands the whole string, unchanged, to component `N` (it takes one step). With `;permit:` and
  `;forbid:` it becomes a test: a *failure field* of a programmed or graph-controlled grammar, the choice of the next matrix, the
  filter of a node of a network.
* **Conditions are tested on the whole word.** `;permit:` and `;forbid:` list words that must, or must not, occur in the word that is
  rewritten (including the rewritten part), as in random-context and semi-conditional grammars. Conditions on the *result*, such as a
  bound on the number of nonterminals, are filters of a component ([configuration.md](configuration.md)).

## Rewriting grammars

The basic case: a plain rule `x -> y` rewrites an occurrence of the string `x`. The terminals are ordinary symbols, there is no
distinction between terminals and nonterminals in the model, and an erasing rule has an empty right-hand side (`S ->`). The usual
restrictions are properties of the rules you write, so the same notation covers the whole Chomsky hierarchy. Contextual grammars of
Marcus insert a context around a selector; the internal ones are plain rules, and the external ones add material at the two ends of the
word, which takes two components.

| Grammar | Support | How, in one sentence | Entry |
| --- | --- | --- | --- |
| Unrestricted (type 0), monotone / context-sensitive (type 1), context-free (type 2), pure grammars | direct | every production is a plain rule `x -> y`, and the terminals are ordinary symbols. | [1](grammars.md#1-context-free-context-sensitive-monotone-unrestricted-and-pure-grammars) |
| Marcus contextual grammars, internal | direct | a context `(u, v)` around a selector `w` is the plain rule `w -> u w v`. | [3](grammars.md#3-marcus-contextual-grammars-internal) |
| Marcus contextual grammars, external | encoding | two components, one adds the left context with `ins({start}, u, )` and the other the right context with `ins( , v, {end})`, each sending to the other. | [4](grammars.md#4-marcus-contextual-grammars-external) |

## Insertion-deletion systems and processors

An insertion rule `ins(u, y, v)` inserts `y` between the contexts `u` and `v`; a deletion rule `del(u, x, v)` deletes `x` between them;
`sub(u, x, y, v)` replaces `x` by `y` between them, so systems with substitutions (insertion-deletion-substitution systems) need nothing special: the three kinds of rules are written side by side. The contexts are written as they appear in the definition, so the size of a system (the lengths of
`u`, `y` or `x`, and `v`) can be read off its rules. `{start}` and `{end}` stand for the two ends of the word, which is what
evolutionary processors need. These systems are the main use of gcrsim: the research models in [examples/real](../examples/README.md)
are insertion-deletion systems of these kinds.

*Left-right* insertion-deletion systems apply their operations only at the ends of the word (or next to end markers, as the models in
[`examples/real/LR`](../examples/real/LR) do): an insertion at the left end is `ins({start}, u, )`, at the right end `ins( , u, {end})`, and the deletions
are `del({start}, x, )` and `del( , x, {end})`. With a deletion at the left end and an insertion at the right end such a system
rewrites a word the way a *Post system* does. A Post normal system has productions `u X -> X v`, where the variable `X` stands for the
rest of the word, and a tag system is the special case in which every production deletes the same number of symbols. A production is
written as one rule with a regular expression, `re(\Au(.*)\Z) -> \1v`, whose group is the variable, or with left-right rules, one
component for each symbol that has been read. Entry 19 shows a tag system in both ways.

| System | Support | How, in one sentence | Entry |
| --- | --- | --- | --- |
| Insertion-deletion systems (contextual, with sizes) | direct | an insertion rule is `ins(u,y,v)` and a deletion rule is `del(u,x,v)`, with the contexts as written. | [2](grammars.md#2-insertion-deletion-systems) |
| Insertion-deletion systems with substitutions | direct | a substitution is written directly as `sub(u,x,y,v)`, next to the `ins` and `del` rules, with the same contexts. | [5](grammars.md#5-evolutionary-processors) |
| Left-right insertion-deletion systems (operations at the ends of the word) | direct | the operations at the ends are `ins({start}, u, )`, `ins( , u, {end})`, `del({start}, x, )` and `del( , x, {end})`; or the contexts are end markers, as in [`examples/real/LR`](../examples/real/LR). | [19](grammars.md#19-post-systems-and-left-right-insertion-deletion-systems) |
| Post systems (Post normal systems, tag systems) | direct | a production `u X -> X v` is the rule `re(\Au(.*)\Z) -> \1v`, where the group is the variable `X`; or a deletion at the left end and an insertion at the right end, in components that remember the symbol read. | [19](grammars.md#19-post-systems-and-left-right-insertion-deletion-systems) |
| Evolutionary processors (substitution, insertion, deletion; anywhere, at the left end, at the right end) | direct | the operations are `sub`, `ins` and `del`, and `{start}` and `{end}` mark the ends of the word. | [5](grammars.md#5-evolutionary-processors) |
| Networks of evolutionary processors | encoding | each node is a component, and its input and output filters are `send()` rules with `permit:` and `forbid:`, so communication takes one extra step. | [6](grammars.md#6-networks-of-evolutionary-processors) |
| Graph-controlled insertion-deletion systems | direct | the graph is the set of components, and the target component of a rule is its success field. | [2](grammars.md#2-insertion-deletion-systems), [7](grammars.md#7-graph-controlled-grammars-with-and-without-appearance-checking) |
| Matrix insertion-deletion systems | encoding | a matrix is a chain of components, one per rule, and the first rules of all the matrices are in the start component (or a component chooses the next matrix with `send()`). | [8](grammars.md#8-matrix-grammars-with-and-without-appearance-checking) |

## Regulated rewriting

A regulated grammar rewrites like a Chomsky grammar, but a control decides which rule may be applied next. The control is a graph
(graph-controlled and programmed grammars), a set of sequences (matrix grammars), a language over the rules (regular control), a cycle of
rule sets (time-varying grammars), a partial order (ordered grammars), or conditions on the word (random-context and semi-conditional
grammars). In gcrsim, a control with states becomes components, and a control by conditions becomes `;permit:` and `;forbid:`.

*Appearance checking* lets a rule be skipped when its left-hand side does not occur in the word; it appears in graph-controlled, matrix
and programmed grammars. It is the same device each time: next to the rule, a `send()` with `forbid:` the symbol of the rule hands the
word to the failure component when the symbol is absent.

| Grammar | Support | How, in one sentence | Entry |
| --- | --- | --- | --- |
| Graph-controlled grammars | direct | the states are components and the success field of a rule is its target component. | [7](grammars.md#7-graph-controlled-grammars-with-and-without-appearance-checking) |
| Graph-controlled grammars with appearance checking (failure fields) | encoding | a failure arrow is a `send()` to the failure component with `forbid:` the symbol of the rule, next to the rule itself. | [7](grammars.md#7-graph-controlled-grammars-with-and-without-appearance-checking) |
| Programmed grammars (success and failure fields) | encoding | the success field is the target, and the failure field is a `send()` with `forbid:` the left-hand side. | [9](grammars.md#9-programmed-grammars-success-and-failure-fields) |
| Matrix grammars | encoding | a matrix is a chain of components, one per rule, and the first rules of all the matrices are in the start component (or a component chooses the next matrix with `send()`). | [8](grammars.md#8-matrix-grammars-with-and-without-appearance-checking) |
| Matrix grammars with appearance checking | encoding | a rule checked for appearance is the rule itself plus a `send()` with `forbid:` its symbol, which covers the case where the rule is skipped. | [8](grammars.md#8-matrix-grammars-with-and-without-appearance-checking) |
| Time-varying grammars | encoding | each rule set is a component and every rule leads to the component of the next rule set, so the components form a cycle. | [10](grammars.md#10-time-varying-grammars) |
| Grammars with regular control | encoding | the states of an automaton for the control language are components, and the label of an edge is the rule that leads along it. | [11](grammars.md#11-regular-control) |
| Random-context grammars | direct | the permitting and forbidding sets are `;permit:` and `;forbid:` with single symbols, tested on the whole word, including the rewritten symbol. | [12](grammars.md#12-random-context-grammars) |
| Semi-conditional grammars | direct | the permitting and forbidding words are `;permit:` and `;forbid:`. | [13](grammars.md#13-semi-conditional-grammars) |
| Context conditions with alternatives | extension | `;permit-any:` means "some word of the set occurs", which the classical definitions write as one rule per word. | [14](grammars.md#14-conditions-with-alternatives-permit-any) |
| Ordered grammars | encoding | the lower rule gets `;forbid:` the left-hand side of every rule above it. | [15](grammars.md#15-ordered-grammars) |
| Grammars with derivations of bounded index (the index-k restriction of finite-index grammars) | direct | a setting, not part of the rules: the `filters` of a component reject every word with more than k nonterminals, with `max_count.class.N` on the class `N` of the nonterminals (or a `forbid` regular expression that counts them). | [16](grammars.md#16-derivations-of-bounded-index-finite-index-grammars) |
| Scattered-context grammars | in part | one `re(...)` rule with lazy gaps rewrites the symbols in order, which is exact only when each symbol occurs once in the word. | [18](grammars.md#18-scattered-context-grammars-in-part-with-re) |

## Machines and other systems

The same machinery simulates devices that are not grammars, when their states and their data can be written as components and strings.

| Subject | Support | How, in one sentence | Entry |
| --- | --- | --- | --- |
| Counter and register machines | encoding | a counter is a run of one symbol, `ins` and `del` count, a `send()` with `forbid:` that symbol tests for zero, and the states are components. | [17](grammars.md#17-counter-and-register-machines) |
| Valence grammars (integer weights) | encoding | the sum of the valences is a unary counter after a separator in the word (`P` for +1, `M` for -1); the rule leads to a component that updates the counter with `del( , M, {end})` or `ins( , P, {end})`, and a word with an empty counter is marked. (With a Python file the weights can also be symbols of the word, compared by a function that gates the word; entry 22.) | [20](grammars.md#20-valence-grammars-integer-weights) |

## Not supported

* **Parallel rewriting** (L systems, ET0L systems): a step rewrites one place of a string, not all of them.
* **Binary operations:** splicing systems, parallel communicating grammar systems and other grammar systems in which strings are
  combined.
* **Leftmost and rightmost derivation modes:** a rule applies at every place where it matches (the setting `derivation` accepts only
  `any`).
* **Other kinds of control:** control by a pushdown automaton or a Petri net; only finite-state control (components) is available.
* **A comparison of counts in the declarative settings:** a filter can limit the number of occurrences of a symbol (`max_count`), but it
  cannot compare the numbers of two symbols; use a function in a filter of a component, or a filter function ([python.md](python.md)).

## Checking a grammar

Whatever the type, a model can be checked against the language you meant: list the expected terminal strings in a mark and every other
terminal string is flagged, with its full derivation on request. See [marks-and-derivations.md](marks-and-derivations.md); the cookbook
[examples/features/checking_an_bn.txt](../examples/features/checking_an_bn.txt) is a grammar with a deliberate mistake.
