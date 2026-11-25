# Model syntax

This is the complete description of the model language. How a step works is described in [semantics.md](semantics.md); the settings in the `[model]` and `[run]` sections and in configuration files are in [configuration.md](configuration.md); worked examples for each kind of grammar are in [grammars.md](grammars.md).

## Model files

A model is a TOML document in which the rules are lines. Its sections are `[symbols]` (how the text is read, see below), `[model]` and
`[run]` (settings, see [configuration.md](configuration.md)), `[axioms]`, and `[rules]` and `[rules.N]` (the rules). The names are
case-insensitive (`[SYMBOLS.CLASSES]` is `[symbols.classes]`), but the names you choose (classes, ranges, mark labels) keep
their case, and the sections may come in any order. A line `[rules]` or `[rules.N]` opens a block of rule lines that ends at
the next section header; everything else is read as TOML.

```
# A comment is a line whose first non-blank character is #. Elsewhere # is a symbol,
# so a comment cannot follow a rule on the same line.
[axioms]
# component 1 holds the string S
1 = ["S"]
# component 2 holds nothing (a missing number means the same)
2 = []
# component 3 holds three strings: the empty one, a, and bc
3 = ["", "a", "bc"]

# General section: [component,] rule [, target component]. Without a component number a
# rule starts in component 1, and without a target it sends its result to component 1.
[rules]
# plain rule: in component 1, replace S by aS and send the result to component 2 (its name is grow)
1, S -> a S, 2; name: grow
# in component 2, replace S by Sb and send the result to component 1
2, S -> S b, 1
# the right-hand side may be empty (the empty string): erase S, stay in component 1
S ->
# insertion: insert X between a and b, wherever a b occurs
ins(a, X, b)
# deletion: delete X where it stands between a and b
del(a, X, b)
# substitution: replace x by y where it stands between a and b
sub(a, x, y, b)
# send the whole string, unchanged, to component 2
send(), 2
# regular-expression rule: exchange two adjacent symbols, a b becomes b a
# (\1 and \2 are the symbols matched by the first and second parenthesis)
1, re((a)(b)) -> \2\1, 1

# Every rule in this section starts in component 2; the target is required.
[rules.2]
S -> S b, 1
```

**Components.** A model has numbered components, 1, 2, 3, ..., each holding a set of strings. A component is created when it is
mentioned, in `[axioms]` or in a rule; one without axioms starts empty. A rule *belongs to* a component, its **source**: it is
applied to the strings of that component. It sends its result to another component, its **target** (it may be the same one).
* In the general `[rules]` section a rule is written `[N,] rule [, M] [; clauses]`: `N` is the source component and `M` the
  target. Both default to 1, so `S -> aS` works in component 1 and sends to component 1.
* In a section `[rules.N]` every rule belongs to component `N`, so no source is written (`N,` may be written, but it must be `N`),
  and the target `, M` is required.
* The clauses (`; permit: ...`, `; forbid: ...`, `; name: ...`, see below) come after the target, which must then be written even when it is 1.
* Component numbers start at 1. The largest allowed number is 10000.

**Rule forms.** Each form below is a rule `rule` in the lines above, and acts on the string of its source component. Every
character in the operands is a symbol (`.`, `+`, `$`, `#`, a backslash are ordinary symbols), and `{`, `}`, `,`, `(`, `)` and
`->` cannot be used in them (write such rules with `re(...)`).

| Form | What it does | Operands that match | Operands that are written |
| --- | --- | --- | --- |
| `x -> y` | replaces `x` by `y` | `x` | `y` |
| `ins(u,y,v)` | inserts `y` where `u` ends right before the insertion point and `v` starts right after it | `u`, `v` | `y` |
| `del(u,x,v)` | deletes `x` where it stands between `u` and `v` | `u`, `x`, `v` | |
| `sub(u,x,y,v)` | replaces `x` by `y` where it stands between `u` and `v` | `u`, `x`, `v` | `y` |
| `send()` | passes the string unchanged to the target | | |
| `re(pattern) -> rhs` | regular expression: replaces what the pattern matches by `rhs` | `pattern` (a regular expression) | `rhs` (with `\N`, see below) |

* The contexts `u` and `v` have to be present but stay unchanged. The forms are the same rule in different notations:
  `x -> y` is `sub("", x, y, "")`, `ins(u,y,v)` is `sub(u, "", y, v)` and `del(u,x,v)` is `sub(u, x, "", v)`.
* The matching operands (`u`, `x`, `v`) can be any sequence of symbols, and they may also use `{start}` and `{end}` (the
  beginning and end of the string), `{any}` (one symbol) and declared classes `{V}`. They only match, they are never written.
* The written operand `y` and the permit/forbid words are literal text: no classes, no `{any}`.
* In `re(...)` only, backslashes have a meaning; everywhere else a backslash is a symbol.

**Details.**

* White space in rule lines is ignored, so `a b -> c d , 1` means `ab->cd,1`; use it to make rules readable. One
  exception concerns multi-character symbols (see below): a space *between two symbols* stops a symbol from being read across
  it. An axiom is a TOML string, so it may hold any character (a quote or a backslash is written `\"` and `\\`; see *Single and double quotes* in [configuration.md](configuration.md)); a space between
  two symbols separates them as in a rule, and the empty string `""` is the empty word.
* A rule applies at every occurrence of its left-hand side, overlapping ones included.
* In `re(...)`: `$` is a literal symbol in every regular expression of the model and the configuration;
  anchor the string with `\A` and `\Z`. The verbose flag `(?x)` is rejected. In the right-hand side `\N` (one digit
  1-9) and `\g<N>` / `\g<name>` insert a captured group, `\\` is a backslash, `\xHH` and `\uXXXX` are code
  points (use them for a comma or a slash); everything else is literal.
* `re(...)` can also express some scattered-context rules, where several symbols are rewritten at once at arbitrary places of
  the word, in a given order: `re(A(.*?)B(.*?)C) -> aA\1bB\2cC` rewrites an `A`, a later `B` and a later `C`, and `\1` and `\2`
  are the text between them. A regular expression gives one match per start position, so this is exact only when each of these
  symbols occurs once in the word; otherwise some of the possible choices are never produced (see entry 18 of
  [grammars.md](grammars.md)).
* A rule whose left-hand side starts with `#` needs the component prefix (`1, #A -> B`),
  because a line that starts with `#` is a comment. Comments are whole lines starting with `#`; there is no other
  comment form, and `/` is an ordinary symbol.
* Files are read as UTF-8 (a BOM is accepted): one code point is one symbol.
* A line that does not match the grammar is an error with file and line number.

## Permitting and forbidding words

A rule can carry random-context / semi-conditional conditions after the target
component. They are tested on the whole string the rule is applied to, before any
matching, and a rule that fails them produces nothing. The occurrence about to be rewritten counts, as in the
definition of random-context grammars (Dassow and Paun, *Regulated Rewriting in Formal Language Theory*, section 1.1:
the permitting symbols must occur in `uAv`, the forbidding ones must not): `A -> x, 1; forbid: A` never applies, and
`A -> x, 1; permit: A` is always satisfied.

```
# in component 1, replace A by aD, but only if B and C both occur in the string and none of D, E, F does
1, A -> a D, 1; permit: B, C; forbid: D, E, F
```

* The clause follows the target component (`, 1` above; it must be written, even
  when it is the default 1). A comment is a whole line starting with `#`.
* `permit:` every listed word must occur in the string as a contiguous
  substring; `forbid:` none of the listed words may; `permit-any:` at least one of them must.
* Words are literal text (`$ # '` need no escape), separated by commas. A clause
  may be repeated; the words add up.

[`examples/real/rcanbncn/rcanbncn.txt`](../examples/real/rcanbncn/rcanbncn.txt) is a random-context grammar for aⁿbⁿcⁿ written this way.

## Rule names

A rule can have a name, a clause `; name: NAME` after the target component, in any position among the conditions:

```
1, S -> a S b, 1; name: grow
ins(a, X, b), 1; forbid: c; name: put-X
```

* A name is a letter followed by letters, digits (0-9), `_`, `-` or `.`; white space is allowed around the name only. Like the
  conditions, the clause follows the target component, which must be written, and a rule has at most one. After the target,
  `; name:` always starts the clause, as `; forbid:` does.
* A name is used by one rule only (in all components). An empty name, a bad character, a second `name:` clause or a name used
  twice is an error that names the file and the line.
* A name changes nothing in the rule. It is shown in the traces (`rule grow at line 14: ...`) and, instead of the rule's notation,
  in short references (the `rules:` line of the measures, the notes of a search), and it is the `name` of the rule in
  `--format jsonl` and in Python.

## Ranges

A range is a finite interval of integers with a name. A line that uses a range stands for one line per value, so a family of similar
symbols or rules is written once. Declare the ranges in `[symbols.ranges]`, as `first..last` (both included, non-negative integers of
at most 15 digits). The declarations may come in any order, also after their use:

```toml
[symbols]
alphabet = "S a b C{:K} D{:I}{:J}"

[symbols.ranges]
I = "0..1"
J = "0..1"
K = "1..3"
```

`{:X}` stands for the value of the range `X`, written in decimal without leading zeros: with `X = "1..3"`, `A{:X}` is `A1`, `A2` and
`A3`. Between `{:` and `}` there can be an expression with integers, range names, `+`, `-`, `*`, `%` and parentheses, with spaces or
tabs around its parts: `{:X+1}`, `{:1-X}`, `{:2*X}`, `{:(X+1)%4}`. `*` needs a constant operand (`2*X`, not `X*Y`), and `%` a positive
constant divisor (`X%0` and `X%Y` are errors, found when the model is loaded). A reference has at most 300 characters and 40 levels of
parentheses. A negative result is an error that names the line, the rule and the values. A result above the range is kept: `{:X+1}` is 4
for `X = 3`, and an alphabet that does not contain `A4` rejects it; write `{:X%3+1}` to wrap around.

`{:` always starts a reference, in every part of a model that is read as symbols or rules, so a text that uses `{:` as ordinary symbols
must change. A `{:` after an odd number of backslashes is never a reference: `\{:` is left as written, which in the pattern of a
`re(...)` rule is the literal text `{:`. An even number of backslashes (`\\{:X}`) leaves the reference.

**Where ranges can be used.**

* In `alphabet`, `lexemes`, `terminals` and in the definition of a class: each word that has references is replaced by its expansions,
  so `alphabet = "A{:X}"` is `A1 A2 A3`, and the class `P = "A{:X}"` is the class `{P}` of those three symbols (a class is still matched
  when the rule is applied: `{P}->b` is one rule).
* In an axiom: one axiom for each combination, `1 = ["S C{:K}"]` is `1 = ["S C1", "S C2", "S C3"]`.
* In every rule line, of every kind (`ins`, `del`, `sub`, plain, `send()` and `re(...)`), in any part of it: the operands, the contexts,
  the `permit`, `forbid` and `permit-any` words, and the component numbers of the general `[rules]` section
  (`{:X}, A{:X} -> B, {:X+1}`; a component number is checked after the values are put in). A section header cannot have a range
  (`[rules.{:X}]` is an error): write the rules in `[rules]`.
* A range cannot be used in a rule name (the values are added to the name, see below). The text of `description` and of the other
  settings is never expanded.

**Rules.** A rule line that uses ranges is replaced, when the model is loaded, by one ordinary rule for each combination of the values
of the ranges it uses; the same range has the same value everywhere in the line. Several ranges give all the combinations, in the order
in which the ranges first appear in the line (the first one changes slowest). The generated rules take the place of the line in the
order of the file, so the order in which the rules are tried does not change. The line is read as any rule line is, with the references
as place holders, so the components, the pattern of a `re(...)` rule, the conditions and the name are found as in a line without ranges.

```
A{:X}A{:X} -> b            # A1A1->b, A2A2->b, A3A3->b: only equal indices
{A}{A} -> b                # one rule: any two members of the class A, A1A2 too
D{:I}{:J} -> D{:J}{:1-I}   # I outer, J inner: D00->D01, D01->D11, D10->D00, D11->D10
```

With `re(...)` the expansion is made first, and the generated lines are read as usual, so `{2}`, `\1`, `(?:)` and `{CLASS}` keep their
meaning: for `X = "1..2"`, `re(({C})A{:X}{2})->\1B{:X}` is `re(({C})A1{2})->\1B1` and `re(({C})A2{2})->\1B2`.

A reference that uses no range name (`q{:2*3}->r`) is evaluated and gives one ordinary rule, without bindings.

The rules that the ranges of a model generate cannot be more than `max_expanded_rules` (100000 by default, a setting of `[model]`, see
[configuration.md](configuration.md)); the words of the declarations and the axioms are not counted. The error names the line that goes
over the limit.

**Names and bindings.** A generated rule keeps the line, the name and the notation of its source line, and has its own *bindings*, the
values of its ranges. A named rule is shown as `grow[X=1]`, a rule without a name as its line as written followed by the bindings,
`ins(S,D{:I}{:J},)[I=0,J=1]`. A name is used by one line only; the rules generated from that line do not clash. A trace shows them like
this (a model with `A{:X} -> B{:X}, 1; name: grow` and an unnamed `B{:X} -> A{:X}`):

```
    step 1: A1A2 => B1A2   (component 1 -> 1, rule grow[X=1] at line 9: A1->B1,1, position 0)
    step 2: B1A2 => B1B2   (component 1 -> 1, rule grow[X=2] at line 9: A2->B2,1, position 1)
    rules: grow[X=1] (line 9) x1, grow[X=2] (line 9) x1; components: 1 (3 forms)
```

In `--format jsonl` and in Python the name, the line and the bindings are separate fields ([cli.md](cli.md#jsonl),
[python.md](python.md)). `gcrsim --describe` lists the rules of each line with ranges, with their bindings.

The example [`examples/features/ranges.txt`](../examples/features/ranges.txt) uses two-bit indices `D{:I}{:J}`, the expressions `1-I`
and `M+1`, a class made from a range and an axiom with a range, and compares a range with a class; the comments of the file explain each
line. In [`examples/features/ranges_components.txt`](../examples/features/ranges_components.txt) the component numbers come from a
range: a chain that goes round four components, `{:X}, S -> c{:X} S, {:X%4+1}`. The description of the first one:

```
$ gcrsim examples/features/ranges.txt --describe
model examples/features/ranges.txt: 1 component, 16 rules (4 ins, 12 plain)
not an insertion-deletion system (it has plain rules)
size of its insertion and deletion rules (n,m,m';p,q,q') (1,1,0;0,0,0)
  ins: inserted 1 symbol; left context 1, right context 0
  no deletion rules
symbols: 10 (declared alphabet); terminals: a b (declared)
  only inserted: a b C3
  only deleted: S C1
  inserted and deleted: C2 D00 D01 D10 D11
  never edited: (none)
ranges: I=0..1, J=0..1, K=1..3, M=1..2
4 rule lines with ranges, giving 14 rules:
  line 30: ins(S,D{:I}{:J},) (I=0..1, J=0..1): 4 rules
    [I=0,J=0]  ins(S,D00,)
    [I=0,J=1]  ins(S,D01,)
    [I=1,J=0]  ins(S,D10,)
    [I=1,J=1]  ins(S,D11,)
  line 32: D{:I}{:J}->D{:J}{:1-I},1;name:step (I=0..1, J=0..1): 4 rules
    step[I=0,J=0]  D00->D01,1
    step[I=0,J=1]  D01->D11,1
    step[I=1,J=0]  D10->D00,1
    step[I=1,J=1]  D11->D10,1
  line 34: C{:M}->C{:M+1},1;name:count (M=1..2): 2 rules
    count[M=1]  C1->C2,1
    count[M=2]  C2->C3,1
  line 36: D{:I}{:J}D{:I}{:J}->,1;name:cancel (I=0..1, J=0..1): 4 rules
    cancel[I=0,J=0]  D00D00->,1
    cancel[I=0,J=1]  D01D01->,1
    cancel[I=1,J=0]  D10D10->,1
    cancel[I=1,J=1]  D11D11->,1
component 1: 1 -> 1: 16 rules; axioms: 3
```

## Multi-character symbols, classes and the alphabet

A symbol such as `p1` is written with several characters, so a rule could match part
of it and an insertion could land inside it (`p1` inserted into `p1` gives `pp11`).
Declare such symbols (lexemes) in the `[symbols]` section of the model, in one of two ways. Both are a string of
symbols separated by spaces (a list of strings is accepted as well), and they exclude each other:

* `alphabet` declares the alphabet of the system. Any symbol that is not in it, in an axiom or in a rule (including its
  `permit:` and `forbid:` words), is rejected with an error. The words of the alphabet that have several characters are
  the multi-character symbols.
* `lexemes` is for a model that has no declared alphabet. Nothing is checked, but multi-character symbols can still be
  useful, so they are listed here and read with the longest-match rule. It does not verify that other symbols are not used
  or generated.

The same section can declare the terminal symbols with `terminals = "a b"`; the search uses it ([configuration.md](configuration.md)).

```
[symbols]
# the alphabet of the system: every symbol of the model must be one of these (p1 p2 K1 have several characters)
alphabet = "a b c S A B X Y p1 p2 K1"
# instead of the alphabet, only the symbols of several characters, without any check:
# lexemes = "p1 p2 K1"
# the terminal symbols (the search needs them)
terminals = "a b c"

# named sets of symbols
[symbols.classes]
P = "p1 p2"
V = "a b K1"

[axioms]
1 = ["S p1"]

[rules]
# replace two symbols of the class P in a row (any of p1, p2) by X
{P}{P} -> X
# a regular expression: replace a symbol that is not in the class V by Y
re([^{V}]) -> Y
```

Two more examples are in [`examples/features/`](../examples/features/): [symbols_and_classes.txt](../examples/features/symbols_and_classes.txt) (a class
in a rule) and [overlapping_symbols.txt](../examples/features/overlapping_symbols.txt) (the symbol `ab` next to the symbols `a` and `b`, and
how a run, a space and `(?:)` say which one is meant).

* Every lexeme is replaced by one private-use character when the model is loaded, so
  `.`, `[^X]`, `{2}`, look-behind, back-references, `print_max_len` and the length limits all
  work on symbols; output, derivations and callbacks show the real names. Matching is
  longest-first: with `ab` and `abc` declared, `abcab` is read as `abc`, `ab`.
* A space between two symbols separates them: `ab c ab` is read as `ab`, `c`, `ab` and `a bc` as `a`, `b`, `c`, even
  though `abc` and `bc` could be read from the same letters without the spaces. Without lexemes spaces change nothing.
* Members of a class that are longer than one character are lexemes too.
* A lexeme cannot contain regex characters, a comma, whitespace or `->`.
* In `re(...)` a lexeme is one symbol: with `ab` declared, `re(ab*)` repeats the symbol `ab`, not the
  letter `b`. The text of a pattern may not contain the private-use characters that stand for lexemes
  (raw or as unicode escapes).
* Declaring a class makes its members longer than one character lexemes for the whole model, not only
  inside `{V}`.
* Symbols are read longest-first with no alphabet check unless `alphabet` is declared. With an `alphabet`, a run of
  symbols without a space that is not itself a symbol and can be read in more than one way is an error, and the message shows the readings: with the
  alphabet `a b ab`, `ab` is the symbol `ab` and `a b` the two symbols, while `abab` is rejected (write `ab ab`). A run
  with one reading is read that way even if a longer symbol matches (with `a ab bc`, `abc` is `a`, `bc`). In a
  `re(...)` pattern a space is not a separator; write `(?:)` between the symbols (`a(?:)b*`).
* With an `alphabet`, an axiom, a right-hand side or a permit/forbid word that holds any
  other symbol is an error, and the message shows how the text was read. This guarantees that every string of the run stays
  over the alphabet, for `re(...)` rules too: the literal text of a right-hand side (escapes such as `z` included) is
  checked, and a group reference only copies symbols of the string. In the left-hand side of a `re(...)` rule the literal
  symbols outside `[...]` are checked as well.
* `{name}` must name a class (an unknown name is an error); quantifiers like `{2,3}` are
  not affected, and `\{name\}` is a literal.

A rule applies at every occurrence of its left-hand side, overlapping ones included
(`aa -> b` on `aaa` gives `ba` and `ab`): one match per start position, so at most
`len(s)+1` candidates per rule and string.

Measured on `ins_b_110200` (depth 20): declaring `p0`..`p5` as lexemes instead of
the `p\d\d` / `f\d\d` filters gives the identical accepted strings and history (66,907
entries) and is faster (0.114 s against 0.141 s of engine time).
