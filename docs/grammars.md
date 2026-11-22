# Cookbook: one example for each kind of grammar

A summary of the supported types of grammars is in [grammar-types.md](grammar-types.md). Every entry shows the grammar in the usual notation and its translation into a gcrsim model. The models are the files in
`examples/cookbook/`; `tests/test_cookbook.py` runs each of them and checks the language it generates, and checks the plain ones
with `--cross-check` (see [checking.md](checking.md)). Components are the states or nodes of the control; a rule `x->y,N` sends its
result to component `N` (default 1). Lower case letters are terminals, upper case letters are nonterminals.

In axioms and in rules spaces are ignored, so `S -> a S b` is the rule `S->aSb`; they are used for readability, and they separate
symbols when multi-character symbols are declared ([examples/features/symbols_and_classes.txt](../examples/features/symbols_and_classes.txt)). In a `re(...)` pattern spaces are ignored as well, but they do not
separate symbols. The short axioms below are written without spaces.

Scattered-context grammars are available only in part (entry 18). Not available: parallel rewriting (L systems, ET0L), splicing and communicating grammar systems,
leftmost / rightmost derivations (postponed), Petri-net control, counting conditions (postponed).

## 1. Context-free, context-sensitive (monotone), unrestricted and pure grammars

**How it is expressed:** plain rules `x->y` with arbitrary strings on both sides (so type 0, type 1 and type 2 grammars alike); terminals are ordinary symbols, here lower case letters.

**Classical notation and the language:**

```text
Context-free grammar G = ({S}, {a,b}, S, P) with P = { S -> aSb, S -> lambda }.   L(G) = { a^n b^n : n >= 0 }
```

**Model** ([`examples/cookbook/01_context_free.txt`](../examples/cookbook/01_context_free.txt)):

```

# the words of the language: a string of terminal symbols (lower-case letters) that reaches component 1 is marked
[model.marks]
terminal = '\A[a-z]*\Z'

[axioms]
1 = ["S"]

[rules]
# S -> aSb
S -> a S b
# S -> lambda: erase S (the right-hand side is empty)
S ->
```

Run: `gcrsim examples/cookbook/01_context_free.txt 6`

**Result:** Within 6 steps, mark `terminal`: `(empty word)` (step 1), `ab` (step 2), `aabb` (step 3), `aaabbb` (step 4), `aaaabbbb` (step 5), `aaaaabbbbb` (step 6).

### Another example: monotone anbncn

**Classical notation and the language:**

```text
Monotone (context-sensitive) grammar, a special case of an unrestricted grammar: left and right-hand sides are arbitrary strings.
G = ({S,B,C}, {a,b,c}, S, P) with
  S -> aSBC | aBC     CB -> BC     aB -> ab     bB -> bb     bC -> bc     cC -> cc
L(G) = { a^n b^n c^n : n >= 1 }
A rule x->y may have any strings on both sides (a plain rule is a rewriting rule of a type-0 grammar).
```

**Model** ([`examples/cookbook/01_monotone_anbncn.txt`](../examples/cookbook/01_monotone_anbncn.txt)):

```

# the words of the language: a string of terminal symbols (lower-case letters) that reaches component 1 is marked
[model.marks]
terminal = '\A[a-z]*\Z'

[axioms]
1 = ["S"]

[rules]
# S -> aSBC | aBC
S -> a S B C
S -> a B C
# CB -> BC: sort the nonterminals, B before C
C B -> B C
# aB -> ab, bB -> bb, bC -> bc, cC -> cc: turn them into terminals from left to right
a B -> a b
b B -> b b
b C -> b c
c C -> c c
```

Run: `gcrsim examples/cookbook/01_monotone_anbncn.txt 12`

**Result:** Within 12 steps, mark `terminal`: `abc` (step 3), `aabbcc` (step 7), `aaabbbccc` (step 12).

### Another example: type0 powers of two

**Classical notation and the language:**

```text
Unrestricted (type 0) grammar with erasing rules: G = ({S,A,B,C,D,E}, {a}, S, P) with
  S -> ACaB    Ca -> aaC    CB -> DB    CB -> E    aD -> Da    AD -> AC    aE -> Ea    AE -> lambda
L(G) = { a^(2^n) : n >= 1 }.   C doubles the a's it passes on its way to B; D carries the marker back to A for the next
round, and E (instead of D) ends the derivation.
```

**Model** ([`examples/cookbook/01_type0_powers_of_two.txt`](../examples/cookbook/01_type0_powers_of_two.txt)):

```

[model]
reject_max_len = 40

[run]
# Number of steps and the longest word kept: with these settings the run prints a^2 (step 6), a^4 (14), a^8 (28), a^16 (54).
steps = 54

# the words of the language: a string of terminal symbols (lower-case letters) that reaches component 1 is marked
[model.marks]
terminal = '\A[a-z]*\Z'

[axioms]
1 = ["S"]

[rules]
# start: S -> ACaB (A and B are the left and right end markers, C a doubling marker)
S -> A C a B
# C doubles every a it passes on its way to B
C a -> a a C
# at B, C either turns into D (one more round) or into E (the last round)
C B -> D B
C B -> E
# D carries the marker back to A, and A D -> A C starts the next round
a D -> D a
A D -> A C
# E goes back to A, and A E is erased: the derivation ends
a E -> E a
A E ->
```

Run: `gcrsim examples/cookbook/01_type0_powers_of_two.txt`

**Result:** Within 54 steps, mark `terminal`: `aa` (step 6), `aaaa` (step 14), `aaaaaaaa` (step 28), `aaaaaaaaaaaaaaaa` (step 54).

## 2. Insertion-deletion systems

**How it is expressed:** `ins(u,y,v)` and `del(u,x,v)`; the sizes of the system are the lengths of `u`, `y` or `x`, and `v`.

**Classical notation and the language:**

```text
Insertion-deletion system (V, T, A, I, D) with V = T = {a,b}, A = { ab },
I = { (a, ab, b) } (insert ab between a and b), D = {}.   L = { a^n b^n : n >= 1 }
ins(u,y,v): insert y where u ends right before it and v starts right after it.
```

**Model** ([`examples/cookbook/02_insdel.txt`](../examples/cookbook/02_insdel.txt)):

```

# the words of the language: a string of terminal symbols (lower-case letters) that reaches component 1 is marked
[model.marks]
terminal = '\A[a-z]*\Z'

[axioms]
1 = ["ab"]

[rules]
# insert "ab" between an a and a b
ins(a, ab, b)
```

Run: `gcrsim examples/cookbook/02_insdel.txt 6`

**Result:** Within 6 steps, mark `terminal`: `aabb` (step 1), `aaabbb` (step 2), `aaaabbbb` (step 3), `aaaaabbbbb` (step 4), `aaaaaabbbbbb` (step 5), `aaaaaaabbbbbbb` (step 6).

## 3. Marcus contextual grammars, internal

**How it is expressed:** a plain rule `w->uwv`.

**Classical notation and the language:**

```text
Internal contextual grammar (Marcus) G = ({a,b}, { ab }, { (ab, (a, b)) }):
the selector ab may be surrounded by the context (a, b):  ab -> a ab b.   L = { a^n b^n : n >= 1 }
```

**Model** ([`examples/cookbook/03_marcus_internal.txt`](../examples/cookbook/03_marcus_internal.txt)):

```

# the words of the language: a string of terminal symbols (lower-case letters) that reaches component 1 is marked
[model.marks]
terminal = '\A[a-z]*\Z'

[axioms]
1 = ["ab"]

[rules]
# the selector ab is surrounded by the context (a, b)
ab -> a ab b
```

Run: `gcrsim examples/cookbook/03_marcus_internal.txt 6`

**Result:** Within 6 steps, mark `terminal`: `aabb` (step 1), `aaabbb` (step 2), `aaaabbbb` (step 3), `aaaaabbbbb` (step 4), `aaaaaabbbbbb` (step 5), `aaaaaaabbbbbbb` (step 6).

## 4. Marcus contextual grammars, external

**How it is expressed:** insertions at the two ends, `ins({start},u,)` and `ins(,v,{end})`, in two components.

**Classical notation and the language:**

```text
External contextual grammar (Marcus) G = ({a,b}, { ab }, { (a, b) }): the context (a, b) is added
at the two ends of the whole word, w -> a w b.   L = { a^n b^n : n >= 1 }
Two components: component 1 adds the left part, component 2 the right part. The language is read in component 1 (a word in
component 2 has only its left part added).
```

**Model** ([`examples/cookbook/04_marcus_external.txt`](../examples/cookbook/04_marcus_external.txt)):

```

# the words of the language: a string of terminal symbols (lower-case letters) that reaches component 1 is marked
[model.marks]
terminal = '\A[a-z]*\Z'

[axioms]
1 = ["ab"]

[rules.1]
# add an a at the left end of the word, then go to component 2
ins({start}, a, ), 2
[rules.2]
# add a b at the right end of the word, then go back to component 1
ins( , b, {end}), 1
```

Run: `gcrsim examples/cookbook/04_marcus_external.txt 6`

**Result:** Within 6 steps, mark `terminal`: `aabb` (step 2), `aaabbb` (step 4), `aaaabbbb` (step 6).

## 5. Evolutionary processors

**How it is expressed:** `sub`, `ins`, `del`, with `{start}` and `{end}` for the ends of the word (one kind of operation per processor in the classical definition; shown together here).

**Classical notation and the language:**

```text
The three operations of evolutionary processors, shown together on the word aY. (In the classical definition one processor
does one kind of operation; here the three rules sit in one component only to show their notation.)
  substitution of a symbol anywhere:  a -> b        sub(,a,b,)
  insertion at the left end:          lambda -> X   ins({start},X,)
  deletion at the right end:          Y -> lambda   del(,Y,{end})
In one step the three rules give  bY,  XaY  and  a.
```

**Model** ([`examples/cookbook/05_evolutionary_processors.txt`](../examples/cookbook/05_evolutionary_processors.txt)):

```

[axioms]
1 = ["aY"]

[rules]
# substitution: replace an a by b, anywhere in the word
sub( , a, b, )
# insertion at the left end: put X in front of the word
ins({start}, X, )
# deletion at the right end: remove a Y that is the last symbol
del( , Y, {end})
```

Run: `gcrsim examples/cookbook/05_evolutionary_processors.txt 6`

**Result:** After 1 step: `XaY`, `a`, `bY`.

## 6. Networks of evolutionary processors

**How it is expressed:** one component per node; a filter is a `send()` rule with `permit:` / `forbid:` (communication takes a step).

**Classical notation and the language:**

```text
Network of evolutionary processors with two nodes.
Node 1 substitutes a -> b at any place and keeps the result.  A word leaves node 1 for node 2 only when it
contains no a (the output filter of the node: forbid:a).   Input word aab; node 2 receives bbb.
```

**Model** ([`examples/cookbook/06_network_of_processors.txt`](../examples/cookbook/06_network_of_processors.txt)):

```

# the words of the language: a string of terminal symbols (lower-case letters) that reaches component 2 is marked
[model.components.2.marks]
terminal = '\A[a-z]*\Z'

[axioms]
1 = ["aab"]

[rules.1]
# node 1: replace an a by b anywhere and keep the result in node 1
sub( , a, b, ), 1
# output filter: a word goes to node 2 only if it contains no a
send(), 2; forbid: a
```

Run: `gcrsim examples/cookbook/06_network_of_processors.txt 6`

**Result:** Within 6 steps, mark `terminal`: `bbb` (step 3).

## 7. Graph-controlled grammars, with and without appearance checking

**How it is expressed:** components are the states, the target component of a rule is its success field; the failure field of appearance checking (the rule is not applicable because its symbol does not occur) is a `send()` with `forbid:` that symbol.

**Classical notation and the language:**

```text
Graph-controlled grammar: rules r1: S -> aSb, r2: S -> lambda; control graph  q1 -r1-> q1,  q1 -r2-> q2.
The states of the graph are the components; the target of a rule is its success field.
L = { a^n b^n : n >= 0 }
```

**Model** ([`examples/cookbook/07_graph_controlled.txt`](../examples/cookbook/07_graph_controlled.txt)):

```

# the words of the language: a string of terminal symbols (lower-case letters) that reaches component 2 is marked
[model.components.2.marks]
terminal = '\A[a-z]*\Z'

[axioms]
1 = ["S"]

[rules.1]
# r1: S -> aSb, the next rule is again in component 1
S -> a S b, 1
# r2: S -> lambda, the derivation continues in component 2 (the end)
S -> , 2
```

Run: `gcrsim examples/cookbook/07_graph_controlled.txt 6`

**Result:** Within 6 steps, mark `terminal`: `(empty word)` (step 1), `ab` (step 2), `aabb` (step 3), `aaabbb` (step 4), `aaaabbbb` (step 5), `aaaaabbbbb` (step 6).

### Another example: graph controlled appearance checking

**Classical notation and the language:**

```text
Graph-controlled grammar with appearance checking. Every rule has a success field (where to go after it was applied) and a
failure field (where to go when it is NOT applicable because its symbol does not occur: appearance checking):
  r1: A -> BB   success {r1}          failure {r2}        while an A occurs, replace it by BB; with no A left go to r2
  r2: B -> A    success {r2}          failure {r1, r4}    turn the B back into A; with no B left start a new round or finish
  r4: A -> a    success {r4}          failure {end}       turn the A into a; with no A left the word is finished
Start: the word A, at r1 or at r4.   L = { a^(2^n) : n >= 0 }
Translation: a node is a component, a success field is the target of the rule, a failure arrow is a send() that is allowed
only if the symbol of the rule does not occur (forbid:). Component 4 is the end, and it holds the generated words.
The number of steps and the longest word are set in the [run] and [model] sections below.
```

**Model** ([`examples/cookbook/07_graph_controlled_appearance_checking.txt`](../examples/cookbook/07_graph_controlled_appearance_checking.txt)):

```

[model]
reject_max_len = 20

[run]
# a^1, a^2, a^4 and a^8 appear at steps 2, 8, 18 and 36
steps = 36

# the words of the language: a string of terminal symbols (lower-case letters) that reaches component 4 is marked
[model.components.4.marks]
terminal = '\A[a-z]*\Z'

[axioms]
# the start nodes are r1 (component 1) and r4 (component 3)
1 = ["A"]
3 = ["A"]

[rules.1]
# r1: A -> BB, success: stay at r1
A -> B B, 1
# r1 failure: no A occurs, go to r2 (component 2)
send(), 2; forbid: A
[rules.2]
# r2: B -> A, success: stay at r2
B -> A, 2
# r2 failure: no B occurs, go to r1 (a new round) ...
send(), 1; forbid: B
# ... or to r4 (component 3, finish)
send(), 3; forbid: B
[rules.3]
# r4: A -> a, success: stay at r4
A -> a, 3
# r4 failure: no A occurs, the word is finished (component 4)
send(), 4; forbid: A
```

Run: `gcrsim examples/cookbook/07_graph_controlled_appearance_checking.txt`

**Result:** Within 36 steps, mark `terminal`: `a` (step 2), `aa` (step 8), `aaaa` (step 18), `aaaaaaaa` (step 36).

## 8. Matrix grammars, with and without appearance checking

**How it is expressed:** a matrix is a chain of components, and `send()` chooses the matrix; a rule checked for appearance is skipped when its symbol does not occur, which is a `send()` with `forbid:` that symbol next to the rule itself.

**Classical notation and the language:**

```text
Matrix grammar G = ({S,A,B,C}, {a,b,c}, S, M) with the matrices
  m1 = (S -> ABC)   m2 = (A -> aA, B -> bB, C -> cC)   m3 = (A -> a, B -> b, C -> c)
L(G) = { a^n b^n c^n : n >= 1 }.
A matrix is a chain of components: each rule hands the word to the next component and the last rule of the
matrix returns to component 1, where the next matrix is chosen by send().
```

**Model** ([`examples/cookbook/08_matrix.txt`](../examples/cookbook/08_matrix.txt)):

```

# the words of the language: a string of terminal symbols (lower-case letters) that reaches component 8 is marked
[model.components.8.marks]
terminal = '\A[a-z]*\Z'

[axioms]
1 = ["S"]

[rules.1]
# matrix m1 (one rule): S -> ABC
S -> A B C, 1
# choose the next matrix: m2 starts in component 2, m3 in component 5
send(), 2
send(), 5
# matrix m2 = (A -> aA, B -> bB, C -> cC): one component per rule, the last one returns to component 1
[rules.2]
A -> a A, 3
[rules.3]
B -> b B, 4
[rules.4]
C -> c C, 1
# matrix m3 = (A -> a, B -> b, C -> c): the last rule ends in component 8
[rules.5]
A -> a, 6
[rules.6]
B -> b, 7
[rules.7]
C -> c, 8
```

Run: `gcrsim examples/cookbook/08_matrix.txt 12`

**Result:** Within 12 steps, mark `terminal`: `abc` (step 5), `aabbcc` (step 9).

### Another example: matrix appearance checking

**Classical notation and the language:**

```text
Matrix grammar with appearance checking, G = ({X, Y, Z, A, B, #}, {a}, XA, M, F). A rule of F, written (A -> #)_ac below, is
applied if its symbol occurs and skipped if it does not (appearance checking); # is a trap symbol that is never removed, so
applying such a rule kills the derivation. Skipping it therefore means "continue only if A does not occur". Matrices:
  m1 = (X -> X, A -> BB)         double one A (the first rule only tests that X occurs)
  m2 = (X -> Y, A -> #)_ac       X -> Y, only if no A is left
  m3 = (Y -> Y, B -> A)          turn one B back into an A
  m4 = (Y -> X, B -> #)_ac       Y -> X, only if no B is left: a new round can start
  m5 = (X -> Z)                  start to finish
  m6 = (Z -> Z, A -> a)          turn one A into a
  m7 = (Z -> lambda, A -> #)_ac  end, only if no A is left
L(G) = { a^(2^n) : n >= 0 }.
Translation: a matrix is a chain of components (as in the matrix grammar of entry 8) and component 1 chooses the matrix. An
appearance-checked rule is a pair of rules in one component: the rule itself (A -> #, applied when A occurs) and a send()
with forbid: A (the rule is skipped when A does not occur). The words with # can never become terminal. The configuration
The [model] section below drops them (reject_strings = "#") and the [run] section sets the number of steps.
```

**Model** ([`examples/cookbook/08_matrix_appearance_checking.txt`](../examples/cookbook/08_matrix_appearance_checking.txt)):

```

[model]
reject_strings = "#"
reject_max_len = 40

[run]
# the trap symbol # marks dead words: drop them. a^1, a^2, a^4 and a^8 appear at steps 8, 26, 56 and 110 in component 15
steps = 110

# the words of the language: a string of terminal symbols (lower-case letters) that reaches component 15 is marked
[model.components.15.marks]
terminal = '\A[a-z]*\Z'

[axioms]
1 = ["XA"]

[rules.1]
# choose a matrix: its first component is 2, 4, 6, 8, 10, 11 or 13
send(), 2
send(), 4
send(), 6
send(), 8
send(), 10
send(), 11
send(), 13
# m1
[rules.2]
X -> X, 3
[rules.3]
A -> B B, 1
# m2: the second rule is checked for appearance of A
[rules.4]
X -> Y, 5
[rules.5]
A -> #, 1
send(), 1; forbid: A
# m3
[rules.6]
Y -> Y, 7
[rules.7]
B -> A, 1
# m4: the second rule is checked for appearance of B
[rules.8]
Y -> X, 9
[rules.9]
B -> #, 1
send(), 1; forbid: B
# m5
[rules.10]
X -> Z, 1
# m6
[rules.11]
Z -> Z, 12
[rules.12]
A -> a, 1
# m7: the second rule is checked for appearance of A, the words that leave it are in component 15
[rules.13]
Z -> , 14
[rules.14]
A -> #, 15
send(), 15; forbid: A
```

Run: `gcrsim examples/cookbook/08_matrix_appearance_checking.txt`

**Result:** Within 110 steps, mark `terminal`: `a` (step 8), `aa` (step 26), `aaaa` (step 56), `aaaaaaaa` (step 110).

### Another example: matrix direct

**Classical notation and the language:**

```text
Matrix grammar G = ({S,A,B,C}, {a,b,c}, S, M), the same as above, with the first rule of each matrix in component 1.
  m1 = (S -> ABC)   m2 = (A -> aA, B -> bB, C -> cC)   m3 = (A -> a, B -> b, C -> c)
L(G) = { a^n b^n c^n : n >= 1 }.
A matrix is a chain of components, one per rule. The first rules of all the matrices are in component 1, so the matrix does not
have to be chosen with send(): the first rule that is applied chooses it. The last rules of m2 and m3 return to component 1,
where the words of the language are.
```

**Model** ([`examples/cookbook/08_matrix_direct.txt`](../examples/cookbook/08_matrix_direct.txt)):

```

# the words of the language: a string of terminal symbols (lower-case letters) in component 1 is marked
[model.components.1.marks]
terminal = '\A[a-z]*\Z'

[axioms]
1 = ["S"]

[rules.1]
# m1 (one rule), and the first rules of m2 and m3
S -> A B C, 1
A -> a A, 2
A -> a, 4
# m2 = (A -> aA, B -> bB, C -> cC)
[rules.2]
B -> b B, 3
[rules.3]
C -> c C, 1
# m3 = (A -> a, B -> b, C -> c)
[rules.4]
B -> b, 5
[rules.5]
C -> c, 1
```

Run: `gcrsim examples/cookbook/08_matrix_direct.txt 12`

**Result:** Within 12 steps, mark `terminal`: `abc` (step 4), `aabbcc` (step 7), `aaabbbccc` (step 10).

## 9. Programmed grammars (success and failure fields)

**How it is expressed:** success = target component; failure = a `send()` with `forbid:<left-hand side>`.

**Classical notation and the language:**

```text
Programmed grammar with failure fields (appearance checking), rules
  r1: B -> b   success field { r1 }   failure field { r2 }     (r2 is entered only when r1 is not applicable)
  r2: A -> x   success field { }
Start word ABB.  Derivation: ABB => AbB => Abb => xbb.   L = { xbb }
The failure field is a send() allowed only when the left-hand side does not occur (forbid:B).
```

**Model** ([`examples/cookbook/09_programmed.txt`](../examples/cookbook/09_programmed.txt)):

```

# the words of the language: a string of terminal symbols (lower-case letters) that reaches component 3 is marked
[model.components.3.marks]
terminal = '\A[a-z]*\Z'

[axioms]
1 = ["ABB"]

[rules.1]
# r1: B -> b, success field {r1}: stay here
B -> b, 1
# failure field {r2}: if no B is left (forbid: B), go on to r2 in component 2
send(), 2; forbid: B
[rules.2]
# r2: A -> x, then stop in component 3
A -> x, 3
```

Run: `gcrsim examples/cookbook/09_programmed.txt 6`

**Result:** Within 6 steps, mark `terminal`: `xbb` (step 4).

## 10. Time-varying grammars

**How it is expressed:** a cycle of components, one rule set per component.

**Classical notation and the language:**

```text
Time-varying grammar with period 2:  V1 = { S -> aT },  V2 = { T -> bS, T -> b }.   L = { (ab)^n : n >= 1 }
At steps 1, 3, 5 ... the rules of V1 apply, at steps 2, 4 ... those of V2: one component per rule set,
each pointing to the next.
```

**Model** ([`examples/cookbook/10_time_varying.txt`](../examples/cookbook/10_time_varying.txt)):

```

# the words of the language: a string of terminal symbols (lower-case letters) that reaches component 3 is marked
[model.components.3.marks]
terminal = '\A[a-z]*\Z'

[axioms]
1 = ["S"]

[rules.1]
# rule set V1 (steps 1, 3, 5 ...): S -> aT, then V2 applies
S -> a T, 2
[rules.2]
# rule set V2 (steps 2, 4 ...): T -> bS goes back to V1 ...
T -> b S, 1
# ... or T -> b finishes the word in component 3
T -> b, 3
```

Run: `gcrsim examples/cookbook/10_time_varying.txt 6`

**Result:** Within 6 steps, mark `terminal`: `ab` (step 2), `abab` (step 4), `ababab` (step 6).

## 11. Regular control

**How it is expressed:** the states of the automaton of the control language are the components.

**Classical notation and the language:**

```text
Grammar with regular control: rules r1: S -> aS, r2: S -> Sb, r3: S -> lambda,
control language (r1 r2)* r3.   L = { a^n b^n : n >= 0 }.
The states of a finite automaton for the control language are the components: r1 leads from q0 to q1,
r2 from q1 back to q0, r3 leaves q0 for the final state.
```

**Model** ([`examples/cookbook/11_regular_control.txt`](../examples/cookbook/11_regular_control.txt)):

```

# the words of the language: a string of terminal symbols (lower-case letters) that reaches component 3 is marked
[model.components.3.marks]
terminal = '\A[a-z]*\Z'

[axioms]
1 = ["S"]

[rules.1]
# r1 in state q0: S -> aS, the control moves to q1 (component 2)
S -> a S, 2
# r3 in state q0: S -> lambda, the control moves to the final state (component 3)
S -> , 3
[rules.2]
# r2 in state q1: S -> Sb, the control moves back to q0
S -> S b, 1
```

Run: `gcrsim examples/cookbook/11_regular_control.txt 6`

**Result:** Within 6 steps, mark `terminal`: `(empty word)` (step 1), `ab` (step 3), `aabb` (step 5).

## 12. Random-context grammars

**How it is expressed:** `;permit:` and `;forbid:` with single symbols.

**Classical notation and the language:**

```text
Random-context grammar for { a^n b^n c^n : n >= 1 }. A rule (A -> x, P, Q) applies when every symbol of the
permitting set P occurs and no symbol of the forbidding set Q occurs.  D, E, F are the marked forms of A, B, C.
  (A -> aD, {B,C}, {D,E,F})   (B -> bE, {D,C}, {E,F})   (C -> cF, {D,E}, {F})   ...
They are written with ;permit: and ;forbid: after the target component.
```

**Model** ([`examples/cookbook/12_random_context.txt`](../examples/cookbook/12_random_context.txt)):

```

# the words of the language: a string of terminal symbols (lower-case letters) that reaches component 1 is marked
[model.marks]
terminal = '\A[a-z]*\Z'

[axioms]
1 = ["S"]

[rules]
# start: S -> ABC
S -> A B C
# first phase: rewrite A, B, C in this order, marking them as D, E, F; (A -> aD, {B,C}, {D,E,F}) means:
# A -> aD only if B and C occur and none of D, E, F does
A -> a D, 1; permit: B, C; forbid: D, E, F
B -> b E, 1; permit: D, C; forbid: E, F
C -> c F, 1; permit: D, E; forbid: F
# unmark in the order D, E, F, giving A, B, C back
D -> A, 1; permit: E, F
E -> B, 1; permit: F; forbid: D
F -> C, 1; forbid: D, E
# last phase: turn A, B, C into terminals, in this order
A -> a, 1; permit: B, C; forbid: D, E, F
B -> b, 1; permit: C; forbid: A
C -> c, 1; forbid: A, B
```

Run: `gcrsim examples/cookbook/12_random_context.txt 14`

**Result:** Within 14 steps, mark `terminal`: `abc` (step 4), `aabbcc` (step 10).

## 13. Semi-conditional grammars

**How it is expressed:** `;permit:` and `;forbid:` with words.

**Classical notation and the language:**

```text
Semi-conditional grammar: rules (A -> x, permitting word, forbidding word).
  (S -> aSb, lambda, bbb)   (S -> lambda, lambda, lambda)       L = { a^n b^n : 0 <= n <= 3 }
After three rounds the word contains bbb, so the first rule is blocked.
```

**Model** ([`examples/cookbook/13_semi_conditional.txt`](../examples/cookbook/13_semi_conditional.txt)):

```

# the words of the language: a string of terminal symbols (lower-case letters) that reaches component 1 is marked
[model.marks]
terminal = '\A[a-z]*\Z'

[axioms]
1 = ["S"]

[rules]
# (S -> aSb, no permitting word, forbidding word bbb): applies only while bbb does not occur
S -> a S b, 1; forbid: bbb
# (S -> lambda, no conditions)
S ->
```

Run: `gcrsim examples/cookbook/13_semi_conditional.txt 6`

**Result:** Within 6 steps, mark `terminal`: `(empty word)` (step 1), `ab` (step 2), `aabb` (step 3), `aaabbb` (step 4).

## 14. Conditions with alternatives (`permit-any`)

**How it is expressed:** `;permit-any:` (some word of the set), an extension of the classical permitting sets, which require all words.

**Classical notation and the language:**

```text
Conditions with alternatives. In the classical formalisms a permitting set requires ALL of its words (that is `;permit:`), and
"some word of a set" is written with several rules, one for each word. gcrsim has a short form for it, `;permit-any:` (an
extension, not a classical definition): the rule (X -> Y, some of {ab, ba}, none of {c}) applies when the word contains ab or ba
and does not contain c.
On Xab and Xba the rule gives Yab and Yba; Xabc (forbidden c) and Xbb (no permitting word) are blocked.
```

**Model** ([`examples/cookbook/14_context_conditional.txt`](../examples/cookbook/14_context_conditional.txt)):

```

[axioms]
1 = ["Xab", "Xba", "Xabc", "Xbb"]

[rules]
# X -> Y if the word contains ab or ba (permit-any) and does not contain c (forbid)
X -> Y, 1; permit-any: ab, ba; forbid: c
```

Run: `gcrsim examples/cookbook/14_context_conditional.txt 6`

**Result:** After 1 step: `Yab`, `Yba`.

## 15. Ordered grammars

**How it is expressed:** the lower rule forbids the left-hand side of the higher one.

**Classical notation and the language:**

```text
Ordered grammar: rules r1: A -> a and r2: B -> b with r1 > r2 (r2 applies only when r1 is not applicable).
On the word AB only r1 applies; once no A is left, r2 applies.   L = { ab }
Translation: the lower rule forbids the left-hand side of the higher one.
```

**Model** ([`examples/cookbook/15_ordered.txt`](../examples/cookbook/15_ordered.txt)):

```

# the words of the language: a string of terminal symbols (lower-case letters) that reaches component 1 is marked
[model.marks]
terminal = '\A[a-z]*\Z'

[axioms]
1 = ["AB"]

[rules]
# r1 (the higher rule): A -> a
A -> a
# r2 (the lower rule): B -> b, allowed only when r1 is not applicable, that is when no A occurs
B -> b, 1; forbid: A
```

Run: `gcrsim examples/cookbook/15_ordered.txt 6`

**Result:** Within 6 steps, mark `terminal`: `ab` (step 2).

## 16. Derivations of bounded index (finite-index grammars)

**How it is expressed:** a setting, not a rule: the `filters` of a component (`[model.components.N.filters]`) drop the words with more than k nonterminals, with `max_count` for one symbol or a `forbid` regular expression that counts several.

**Classical notation and the language:**

```text
Derivations of bounded index with several nonterminals. G: S -> AB, A -> aA | a, B -> bB | b generates { a^n b^m : n, m >= 1 }.
Every derivation has at most 2 nonterminals at a time (AB, aAB or AbB, ...), so G has index 2 and the restriction "at most 2
nonterminals" changes nothing; with "at most 1" nothing is generated, because the first step already gives 2.
The nonterminals are a class N, and the setting counts the symbols of the class together
([model.components.0.filters] below: max_count.class.N = 2).
```

**Model** ([`examples/cookbook/16_bounded_index_classes.txt`](../examples/cookbook/16_bounded_index_classes.txt)):

```

[symbols.classes]
N = "S A B"

[model]
reject_max_len = 12

[model.components.0.filters]          # 0 = every component
max_count.class.N = 2          # the symbols of the class N together at most 2 times: derivations of index at most 2

# the words of the language: a string of terminal symbols (lower-case letters) that reaches component 1 is marked
[model.marks]
terminal = '\A[a-z]*\Z'

[axioms]
1 = ["S"]

[rules]
# S -> AB
S -> A B
# A -> aA | a
A -> a A
A -> a
# B -> bB | b
B -> b B
B -> b
```

Run: `gcrsim examples/cookbook/16_bounded_index_classes.txt 5`

**Result:** Within 5 steps, mark `terminal`: `ab` (step 3), `aab` (step 4), `abb` (step 4), `aaab` (step 5), `aabb` (step 5), `abbb` (step 5).

### Another example: finite index

**Classical notation and the language:**

```text
Derivations of bounded index. The index of a derivation is the largest number of nonterminals in a sentential form of it; a grammar
has finite index if some k gives every word of its language a derivation of index at most k. Here the index is at most 2: a word
with more than 2 S is dropped, so the run generates the words that have a derivation of index at most 2.
G: S -> SS | a.  The restriction is a setting ([model.components.0.filters] below), not part of the rules.
Run:  gcrsim examples/cookbook/16_finite_index.txt 8
```

**Model** ([`examples/cookbook/16_finite_index.txt`](../examples/cookbook/16_finite_index.txt)):

```

[model.components.0.filters]          # 0 = every component
max_count = { S = 2 }          # reject a word with more than 2 S (one nonterminal here)
# With several nonterminals declare them as a class in the model (see 16_bounded_index_classes.txt) and count the class.
# A regular expression does the same: this one rejects a word with more than 2 upper-case symbols (each repetition skips the
# other symbols and takes one nonterminal, anchored at the start):  forbid = ['\A(?:[^A-Z]*[A-Z]){3}']

# the words of the language: a string of terminal symbols (lower-case letters) that reaches component 1 is marked
[model.marks]
terminal = '\A[a-z]*\Z'

[axioms]
1 = ["S"]

[rules]
# S -> SS
S -> S S
# S -> a
S -> a
```

Run: `gcrsim examples/cookbook/16_finite_index.txt 5`

**Result:** Within 5 steps, mark `terminal`: `a` (step 1), `aa` (step 3), `aaa` (step 5).

## 17. Counter and register machines

**How it is expressed:** a counter is a run of one symbol; `ins` / `del` count, `send()` with `forbid:` tests for zero; the states are the components.

**Classical notation and the language:**

```text
Counter machine with two counters that moves counter 1 into counter 2:
  q0: if c1 > 0 then c1 := c1 - 1, go to q1, else halt        q1: c2 := c2 + 1, go to q0
The word is a^c1 | b^c2.  A counter is a run of one symbol, the states are the components:
  decrement: del({start},a,)     increment: ins(,b,{end})     zero test: send() with forbid:a
Input aaa|bb halts in component 3 with |bbbbb.
```

**Model** ([`examples/cookbook/17_counter_machine.txt`](../examples/cookbook/17_counter_machine.txt)):

```

# the machine halts in component 3 with the word |b...b: that word is marked
[model.components.3.marks]
halt = '\A\|b*\Z'

[axioms]
# counter 1 holds three a, counter 2 holds two b, | separates the counters
1 = ["aaa|bb"]

[rules.1]
# state q0, counter 1 > 0: decrement it (delete the a at the left end) and go to q1
del({start}, a, ), 2
# state q0, counter 1 = 0 (no a in the word): halt in component 3
send(), 3; forbid: a
[rules.2]
# state q1: increment counter 2 (insert a b at the right end) and go back to q0
ins( , b, {end}), 1
```

Run: `gcrsim examples/cookbook/17_counter_machine.txt 8`

**Result:** Within 8 steps, mark `halt`: `|bbbbb` (step 7).

## 18. Scattered-context grammars (in part, with `re`)

**How it is expressed:** a scattered rule is one regular expression with lazy gaps, `re(A(.*?)B(.*?)C) -> aA\1bB\2cC`; exact when each symbol occurs once, otherwise only some of the choices are produced.

**Classical notation and the language:**

```text
Scattered-context grammar G = ({S, A, B, C}, {a, b, c}, S, P) with the rules (each rewrites several symbols at once, which
stand at arbitrary places of the word, in this order):
  (S) -> (ABC)    (A, B, C) -> (aA, bB, cC)    (A, B, C) -> (a, b, c)
L(G) = { a^n b^n c^n : n >= 1 }.
With re(...) one scattered rule is a regular expression with a lazy gap between the symbols: A(.*?)B(.*?)C finds A, B, C in this
order and \1, \2 are what stands between them. This is exact when every symbol occurs once in the word, as here.
It is NOT exact in general: a regular expression gives one decomposition per start position, so a scattered rule whose symbols
occur several times is applied to some of the choices only (see 18_scattered_context_choices.txt).
```

**Model** ([`examples/cookbook/18_scattered_context.txt`](../examples/cookbook/18_scattered_context.txt)):

```

# the words of the language: a string of terminal symbols (lower-case letters) that reaches component 1 is marked
[model.marks]
terminal = '\A[a-z]*\Z'

[axioms]
1 = ["S"]

[rules]
# (S) -> (ABC)
S -> A B C
# (A, B, C) -> (aA, bB, cC): the symbols between A and B and between B and C stay where they are
re(A(.*?)B(.*?)C) -> aA\1bB\2cC
# (A, B, C) -> (a, b, c)
re(A(.*?)B(.*?)C) -> a\1b\2c
```

Run: `gcrsim examples/cookbook/18_scattered_context.txt 6`

**Result:** Within 6 steps, mark `terminal`: `abc` (step 2), `aabbcc` (step 3), `aaabbbccc` (step 4), `aaaabbbbcccc` (step 5), `aaaaabbbbbccccc` (step 6).

### Another example: scattered context choices

**Classical notation and the language:**

```text
What the regular-expression form of a scattered rule does when its symbols occur more than once. The scattered rule (A, B) -> (x, y)
applied to ABB has two results, xyB (the first B is rewritten) and xBy (the second B is). One regular expression gives one of them:
the lazy gap A(.*?)B finds the first B, the greedy gap A(.*)B the last one. Writing both rules gives both results. With three B's
the middle one would still be missed: a regular expression cannot enumerate all the choices.
On ABB: xyB and xBy.
```

**Model** ([`examples/cookbook/18_scattered_context_choices.txt`](../examples/cookbook/18_scattered_context_choices.txt)):

```

[axioms]
1 = ["ABB"]

[rules]
# (A, B) -> (x, y), the first B
re(A(.*?)B) -> x\1y
# the same, the last B
re(A(.*)B) -> x\1y
```

Run: `gcrsim examples/cookbook/18_scattered_context_choices.txt 6`

**Result:** After 1 step: `xBy`, `xyB`.

## 19. Post systems and left-right insertion-deletion systems

**How it is expressed:** a Post normal system or tag system: `re(...)` rules whose group is the variable of the production; or only `del({start}, x, )` and `ins( , y, {end})`, deletions at the left end and insertions at the right end.

**Classical notation and the language:**

```text
A Post tag system T = ({a, b, c}, 2, P) with the productions P: a -> bc, b -> a, c -> aaa. One step reads the first symbol x, deletes
the first two symbols and appends P(x) at the right end. As a Post normal system the three productions are  a z -> z bc,  b z -> z a
and  c z -> z aaa  (z is a variable, the rest of the word).
The system halts when the word has fewer than two symbols. From aaa it goes through 25 words (a Collatz-like sequence) and halts
on a.
Two ways to write it, both below: with regular-expression rules, where the variable z is a group, and with left-right
insertion-deletion rules only, a deletion at the left end and an insertion at the right end.
```

### Variant 1: regular-expression rules

**Model** ([`examples/cookbook/19_post_tag_system.txt`](../examples/cookbook/19_post_tag_system.txt)):

```

# the system halts on a word with fewer than two symbols: that word is marked
[model.marks]
halt = '\A[abc]?\Z'

[axioms]
1 = ["aaa"]

[rules]
# a z -> z bc : delete the first two symbols (a and any symbol), keep the rest z, append bc
re(\Aa.(.*)\Z) -> \1bc
# b z -> z a
re(\Ab.(.*)\Z) -> \1a
# c z -> z aaa
re(\Ac.(.*)\Z) -> \1aaa
```

Run: `gcrsim examples/cookbook/19_post_tag_system.txt 24`

**Result:** The word of the system, one every step: `aaa`, `abc`, `cbc`, `caaa`, `aaaaa`, `aaabc`, `abcbc`, `cbcbc`, ..., `bc`, `a` (25 words in all, then the system halts). Mark `halt`: `a` (step 24).

### Variant 2: left-right insertion-deletion rules

**Model** ([`examples/cookbook/19_post_left_right.txt`](../examples/cookbook/19_post_left_right.txt)):

```

# the system halts on a word with fewer than two symbols: that word is marked
[model.marks]
halt = '\A[abc]?\Z'

[axioms]
1 = ["aaa"]

[rules.1]
# read the first symbol and delete it with the next one: components 2, 3, 4 stand for a, b, c
del({start}, a{any}, ), 2
del({start}, b{any}, ), 3
del({start}, c{any}, ), 4
# insert the production of the symbol read at the right end and return to component 1
[rules.2]
ins( , bc, {end}), 1
[rules.3]
ins( , a, {end}), 1
[rules.4]
ins( , aaa, {end}), 1
```

Run: `gcrsim examples/cookbook/19_post_left_right.txt 48`

**Result:** The word of the system, one every 2 steps: `aaa`, `abc`, `cbc`, `caaa`, `aaaaa`, `aaabc`, `abcbc`, `cbcbc`, ..., `bc`, `a` (25 words in all, then the system halts). Mark `halt`: `a` (step 48).

## 20. Valence grammars (integer weights)

**How it is expressed:** the sum of the valences is a unary counter in the word (`P` for +1, `M` for -1) that a second component updates with `del` and `ins` at the right end; a word with an empty counter is marked.

**Classical notation and the language:**

```text
A valence grammar G = ({S}, {a, b}, S, P) over the integers: every rule has a valence, and a derivation is successful when the
sum of the valences of the rules it used is 0. The rules and their valences:
  S -> aS   valence +1        S -> bS   valence -1        S -> lambda   valence 0
L(G) = { w in {a, b}* : the number of a equals the number of b }.
The sum is kept in the word, after a separator |, as a counter in unary: P stands for +1 and M for -1, and only one of the two
kinds is present at a time. A rule with a valence leads to a component that updates the counter at the right end: for +1 it deletes
an M if there is one, and otherwise inserts a P (and the other way round for -1). A word is in the language when no counter symbol is
left: that word is marked.
```

**Model** ([`examples/cookbook/20_valence.txt`](../examples/cookbook/20_valence.txt)):

```

[model.marks]
terminal = '\A[ab]*\|\Z'

[axioms]
1 = ["S|"]

[rules.1]
# S -> aS, valence +1: the counter is updated in component 2
S -> a S, 2
# S -> bS, valence -1: the counter is updated in component 3
S -> b S, 3
# S -> lambda, valence 0
S -> , 1
# add +1: cancel an M, or else add a P
[rules.2]
del( , M, {end}), 1
ins( , P, {end}), 1; forbid: M
# add -1: cancel a P, or else add an M
[rules.3]
del( , P, {end}), 1
ins( , M, {end}), 1; forbid: P
```

Run: `gcrsim examples/cookbook/20_valence.txt 9`

**Result:** Within 9 steps, mark `terminal`: `|` (step 1), `ab|` (step 5), `ba|` (step 5), `aabb|` (step 9), `abab|` (step 9), `abba|` (step 9), ... (9 in all).

## Examples with Python

The entries below need a Python file, given with `--python-filter`, next to the model (see [python.md](python.md)). A Python file executes code: run only files you trust. The files are in [`examples/python/`](../examples/python/).

### 21. Checking against an infinite language (with Python)

**How it is expressed:** a function in the `expected_re` of a mark (Python file, `--python-filter`): the expected language is not regular.

**Classical notation and the language:**

```text
A grammar for { a^n b^n : n >= 0 } with a deliberate mistake, the extra rule S -> bSa. The Python files next to it say what is
expected and flag every other word. Run:
```

**Model** ([`examples/python/anbn_with_mistake.txt`](../examples/python/anbn_with_mistake.txt)):

```
[axioms]
1 = ["S"]

[rules]
S -> a S b
# the mistake
S -> b S a
S ->
```

**Python file** ([`examples/python/check_infinite.py`](../examples/python/check_infinite.py)):

```python
# Checking against an infinite language. The expected language, { a^n b^n }, is not regular, so no regular expression says "equal
# numbers"; a function does (pure(...) says that it has no state, so --streaming can be used). Every terminal word of the grammar is marked "unexpected" unless the function says that it is fine.
components = {
    1: {
        "marks": {
            "unexpected": {
                "pattern": r"\A[ab]*\Z",
                "expected_re": pure(lambda s: s == "a" * (len(s) // 2) + "b" * (len(s) // 2)),
            }
        }
    },
}
```

Run: `gcrsim examples/python/anbn_with_mistake.txt 5 --python-filter examples/python/check_infinite.py`

**Result:** Within 5 steps, mark `unexpected`: `ba` (step 2), `abab` (step 3), `baba` (step 3), `bbaa` (step 3), `aababb` (step 4), `ababab` (step 4), ... (26 in all).

### 22. A valence grammar with a gate (with Python)

**How it is expressed:** the weights are symbols in the word, a function in the `require` filter of a component lets a word through only when the weights add up to zero.

**Classical notation and the language:**

```text
A valence grammar over the integers: S -> aS has valence +1, S -> bS has valence -1, S -> lambda has valence 0, and a derivation
is successful when the valences add up to 0, that is, when the word has as many a as b.
The weights are written into the word: P stands for +1 and M for -1. Component 2 is a gate, and valence.py lets a word into it only
when its weights add up to zero (a comparison of two counts, which a regular expression or a count limit cannot make). Component 3
removes the weight symbols one by one, so the words of the language come out clean.
```

**Model** ([`examples/python/valence.txt`](../examples/python/valence.txt)):

```
[axioms]
1 = ["S"]

[rules.1]
# the three rules with their valences; the last one hands the word to the gate
S -> a S P, 1
S -> b S M, 1
S -> , 2
[rules.2]
send(), 3
# clean-up loop: delete the weight symbols
[rules.3]
del( , P, ), 3
del( , M, ), 3
```

**Python file** ([`examples/python/valence.py`](../examples/python/valence.py)):

```python
# The gate and the mark of the valence grammar. A function in the filters of component 2 lets a word in only when its weights add up
# to zero; the mark flags the clean words that come out of component 3. pure(...) says that the function has no state, so that
# --streaming can be used (the name pure is available in a Python file, like lit).
components = {
    2: {"filters": {"require": [pure(lambda s: s.count("P") == s.count("M"))]}},
    3: {"marks": {"terminal": r"\A[ab]*\Z"}},
}
```

Run: `gcrsim examples/python/valence.txt 12 --python-filter examples/python/valence.py`

**Result:** Within 12 steps, mark `terminal`: `(empty word)` (step 2), `ab` (step 6), `ba` (step 6), `aabb` (step 10), `abab` (step 10), `abba` (step 10), ... (9 in all).

### 23. Expected strings read from a file (with Python)

**How it is expressed:** the `expected` set of a mark is read by the Python file from a text file.

The model of entry 21, checked against a list of expected words that is kept in a file: [`examples/python/expected_anbn.txt`](../examples/python/expected_anbn.txt), one word per line (`a^n b^n` for n up to 20).

**Python file** ([`examples/python/check_from_file.py`](../examples/python/check_from_file.py)):

```python
# Checking against a long list of expected words kept in a file (a^n b^n for n up to 20), read from the folder of this file.
import os

HERE = os.path.dirname(os.path.abspath(__file__))
EXPECTED = set(open(os.path.join(HERE, "expected_anbn.txt")).read().split("\n"))

components = {1: {"marks": {"unexpected": {"pattern": r"\A[ab]*\Z", "expected": EXPECTED}}}}
```

Run: `gcrsim examples/python/anbn_with_mistake.txt 5 --python-filter examples/python/check_from_file.py`

**Result:** Within 5 steps, mark `unexpected`: `ba` (step 2), `abab` (step 3), `baba` (step 3), `bbaa` (step 3), `aababb` (step 4), `ababab` (step 4), ... (26 in all).

### 24. The valence gate as a filter function (with Python)

**How it is expressed:** the filter function `keep`, which sees the candidates of every component and tests the component number itself.

The model of entry 22 with the same gate written as the filter function `keep(s, component)` instead of a function in the filters of component 2. `keep.pure = True` says that it has no state.

**Python file** ([`examples/python/valence_keep.py`](../examples/python/valence_keep.py)):

```python
# The gate of the valence grammar written as the filter function keep, instead of a function in the filters of component 2
# (valence.py). keep is called for the candidates of every component, so it tests the component itself: the components count from 0
# here, and 1 is component 2, the gate. A word enters it only when its weights add up to zero.
def keep(s, component):
    return component != 1 or s.count("P") == s.count("M")

keep.pure = True      # no state: --streaming can be used

components = {3: {"marks": {"terminal": r"\A[ab]*\Z"}}}
```

Run: `gcrsim examples/python/valence.txt 12 --python-filter examples/python/valence_keep.py`

**Result:** Within 12 steps, mark `terminal`: `(empty word)` (step 2), `ab` (step 6), `ba` (step 6), `aabb` (step 10), `abab` (step 10), `abba` (step 10), ... (9 in all).

### 25. Marking what a filter function cuts (with Python)

**How it is expressed:** the filter function `keep` with the context `ctx`: `ctx.mark` flags a string that `keep` then rejects.

The model of entry 21 with a limit of 7 symbols on the length of a word, written as a filter function. The words that are cut are marked `too_long`, so the run shows what the limit removed (the setting `reject_max_len` drops them without a trace).

**Python file** ([`examples/python/mark_what_is_cut.py`](../examples/python/mark_what_is_cut.py)):

```python
# A filter function that cuts the words longer than 7 symbols and marks every word that it cuts. With the context ctx, ctx.mark flags
# a string even though keep then rejects it, so the run shows what the limit removed (the setting reject_max_len would drop the
# words without a trace).
def keep(s, component, ctx):
    if len(s) > 7:
        ctx.mark("too_long")
        return False
    return True

keep.pure = True
```

Run: `gcrsim examples/python/anbn_with_mistake.txt 6 --python-filter examples/python/mark_what_is_cut.py`

**Result:** Within 6 steps, mark `too_long`: `aaaaSbbbb` (step 4), `aaabSabbb` (step 4), `aabaSbabb` (step 4), `aabbSaabb` (step 4), `abaaSbbab` (step 4), `ababSabab` (step 4), ... (16 in all).

### 26. A beam: a filter function with state (with Python)

**How it is expressed:** the filter function `keep` with a counter per step and component; it is not pure, so `--streaming` refuses it.

The model of entry 21 with a beam: at most 3 strings are kept in each component in each step (the first 3 that arrive). The function counts, so it has state.

**Python file** ([`examples/python/beam.py`](../examples/python/beam.py)):

```python
# A beam: at most 3 strings are kept in each component in each step, the first 3 that arrive. keep has state (a counter per step and
# component), so it is not pure: it is not declared with keep.pure, and --streaming refuses it. ctx.step is the number of the step.
kept = {}

def keep(s, component, ctx):
    key = (ctx.step, component)
    kept[key] = kept.get(key, 0) + 1
    return kept[key] <= 3

components = {1: {"marks": {"terminal": r"\A[ab]*\Z"}}}
```

Run: `gcrsim examples/python/anbn_with_mistake.txt 5 --python-filter examples/python/beam.py`

**Result:** Within 5 steps, mark `terminal`: `(empty word)` (step 1), `ab` (step 2), `aabb` (step 3), `aaabbb` (step 4), `aaaabbbb` (step 5).
