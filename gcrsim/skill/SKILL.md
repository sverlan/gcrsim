---
name: gcrsim
description: gcrsim is a Python simulator of string rewriting systems - grammars (context-free, monotone, type 0), insertion-deletion systems, Marcus contextual grammars, graph-controlled, matrix, programmed and regulated rewriting, evolutionary processors and networks of processors. Use this skill when asked to write, run, check or explore such a model with gcrsim, to find a derivation of a word, to list the words a system generates up to a length, to check that a derivation is legal, or to measure a derivation (steps, length, size of an insertion-deletion system).
---

# gcrsim

gcrsim runs *components* that hold sets of strings; *rules* rewrite a string of one component and send the result to another
(the control graph). Every system above is written as such a model file (TOML plus rule lines).

## 1. Setup

* Install: `pip install gcrsim` (Python 3.11+). Check: `gcrsim --version`. `python -m gcrsim` is the same program.
* Install this skill: `mkdir -p .claude/skills/gcrsim && gcrsim --print-skill > .claude/skills/gcrsim/SKILL.md` (Codex:
  `.agents/skills/gcrsim/` or `~/.codex/skills/gcrsim/`; other tools: their skills folder; the folder must be named `gcrsim`).
* The example models below are files of the source repository (`examples/`). With only the installed package, save each fenced
  model to a file and use that path in the commands.
* The links describe the latest release. If `gcrsim --version` is older, replace `blob/main` by `blob/vX.Y.Z` (the installed
  version) in a link. When behaviour and docs disagree, trust `gcrsim --mode NAME --help` and the installed version.

## 2. Safe running: hard rules

A model can grow without bound and use many GB in seconds. Always:

1. Give a step count (`gcrsim MODEL 20`); there is no default. Start small, then raise it.
2. Set limits; a limit stops with exit 3. Run: `--max-step-accepted N`, `--max-step-candidates N`, `--max-history N`, `--max-marks N`,
   `--max-time 60s` (`2m`, `1h`). Search and language: the same except `--max-marks`, plus `--max-steps N` (depth). Replay: only
   `--max-time`. Bound the strings too: `reject_max_len = 20` in `[model]` (`--reject-max-len N` in `--language`), see section 3.
3. `--max-retained N` and `--retain-file FILE` matter only when strings are retained for derivations (`--trace`, `--trace-marks`,
   search); the file keeps them on disk. For long runs also set `hash_history = true` in `[run]` (digests instead of strings: saves
   memory only for strings of 60+ symbols, makes exhaustive answers conditional) and use `--progress` (stderr).
4. Stop early: `--trace WORD --stop-on-found`, `--stop-on-mark-label LABEL`, `--stop-on-mark`.
5. Parse output only in `--format jsonl`. `--quiet` shortens text output (not in `--language`; jsonl headers stay).
6. `--python-filter FILE.py` executes code: use only files you wrote or trust.
7. When unsure which option a mode takes, run `gcrsim --mode NAME --help`; do not guess.

Exit codes: 0 done / word found / listing complete; 2 error in model, setting or arguments (stderr; a run without a step count is
refused); 3 a limit or the time stopped it (result partial); 4 `--fail-on-mark LABEL` met a mark, or a replay found an illegal
step; 5 `--cross-check` found a difference; 6 search finished without finding the word; 130 interrupted.
[limits](https://github.com/sverlan/gcrsim/blob/main/docs/cli.md#limits),
[memory](https://github.com/sverlan/gcrsim/blob/main/docs/cli.md#memory-and-speed).

## 3. Which operation for which question

Each mode accepts only its own options; `gcrsim --mode NAME --help` lists them (no model needed).

| Question | Command |
| --- | --- |
| What is in this model? (rules, size `(n,m,m';p,q,q')`, symbols) First step. | `gcrsim MODEL --describe` |
| Run it and look at the strings | `gcrsim MODEL 20 --max-step-accepted 100000 --max-step-candidates 1000000 --max-time 60` |
| Flag the strings that are not the intended ones | marks in the model, `--fail-on-mark LABEL`, `--trace-marks` |
| How is WORD derived? (a shortest derivation) | `gcrsim MODEL --search WORD --terminals "a b" --max-steps 30 --max-history 2000000 --max-time 60` |
| Which words up to length N does it generate? | `gcrsim MODEL --language --max-word-len N --terminals "a b" --max-steps 30 --max-history 2000000 --max-time 60` |
| Is this list of forms a derivation? | `gcrsim MODEL --replay FILE --explain --max-time 60` (line `[N:] WORD`, unprefixed lines use `--component` or 1; `--fragment` if the first is not an axiom) |
| Derivation of one string in a run | `gcrsim MODEL 30 --trace WORD --stop-on-found --max-step-candidates 1000000 --max-history 2000000 --max-retained 2000000 --max-time 60` (exit 0 even if WORD never appears: read the output) |

* **Search** is breadth first; it needs the terminals (`terminals = "a b"` in `[symbols]`, or `--terminals`) and looks in component 1
  unless `--component N` says otherwise (words that arrive in component 4 are not found in 1). Outcomes: `found` (exit 0, a real
  derivation, whatever the settings), `not_found` (6), `inconclusive` (3: limit, time, interrupt). `not_found` is relative to the
  *configured model*: rules plus `reject_max_len`, `reject_strings`, component filters, `--python-filter` and the printed bounds
  (with `reject_strings = 'AB'`, `S -> AB`, `AB -> a` gives `not_found` for `a` though replay accepts the derivation). The search
  merges duplicate forms and prunes branches that cannot reach the target; it does not enumerate every derivation. `depth_bound`:
  the target is not reachable within `--max-steps` steps in the configured search, nothing about more steps, and only under the
  `conditional` entries the result lists (e.g. `hash_history`). `frontier_exhausted`:
  no new string is left; still conditional on any condition the outcome lists. Never report "not in the language" from a bounded
  search. Depth is not capped (100-step derivations were found when the strings stayed few); the limits decide.
* `--quiet` omits the derivation and its measures (marks may still print); use `--format jsonl` for a parseable derivation.
* **Language** lists the distinct terminal words of at most N symbols, with counts per length, `complete` or `partial`.
  `--max-word-len` only selects the printed words; it does not bound the exploration. `--max-steps`, `--max-history` or the time
  stopping it make the listing `partial`; `hash_history` can too (the result says why). A length filter (`reject_max_len`) can
  make it `complete` *relative to the filtered model*, wrongly if a short word needs a longer intermediate form: with `S -> AB`,
  `AB -> a`, terminal `a`, `--max-word-len 1` lists `a`, but with `--reject-max-len 1` it is `complete` and empty. Use a length
  filter only when every rule lengthens the string (as in the `ins` example below, +2 per step) or the longest form is known.
* **Replay** checks the steps only (filters, marks and the history are not checked).
* Details: [search](https://github.com/sverlan/gcrsim/blob/main/docs/cli.md#search), [language](https://github.com/sverlan/gcrsim/blob/main/docs/cli.md#language-listing),
  [replay](https://github.com/sverlan/gcrsim/blob/main/docs/cli.md#replay), [describe](https://github.com/sverlan/gcrsim/blob/main/docs/cli.md#describe).

## 4. Model syntax cheat sheet

A model is a TOML file in which rule lines are plain text. Sections: `[symbols]`, `[model]`, `[run]`, `[axioms]`, `[rules]`,
`[rules.N]` (any order; the fixed words of a header are case-insensitive, `[SYMBOLS.CLASSES]` works, but names you choose, such as
classes `V` and `v`, ranges and mark labels, keep their case). Comments: a whole line starting with `#`. In `[axioms]` a TOML comment may follow the value
(`1 = ["a"] # c` is fine). In a rule line `#` is a symbol: `a -> b # tail` rewrites `a` to `b#tail`, and `a -> b, 1 # tail` is an error.
A left part that starts with `#` needs the source prefix (`1, #a -> b`). Reference:
[model-syntax.md](https://github.com/sverlan/gcrsim/blob/main/docs/model-syntax.md#model-files).

```gcrsim-model
[model.components.1.marks]
word = '\A[ab]*\Z'
[axioms]
1 = ["S"]
[rules]
S -> a S b, 1; name: grow
S -> , 2; forbid: X
ins(a, X, {end}), 1
del({start}, a, {any}), 2
sub(a, b, a, ), 1
send(), 2; permit: X
1, re((a)(b)) -> \2\1, 1
[rules.2]
X -> a, 1
```

* **Components** are numbered from 1 (created when mentioned). `[axioms]`: `N = ["w1", "w2"]`, `""` is the empty word.
* **Rule lines**: `[N,] rule [, TARGET] [; clauses]`. Source and target default to 1. In `[rules.N]` the source is N and the target
  is required. Clauses come after the target (write it): `; permit: w1, w2` (all must occur), `; permit-any: ...`, `; forbid: ...`
  (none may occur), `; name: NAME`. They are tested on the source string *before* rewriting; words are literal substrings
  (no classes, no `{any}`).
* **Rule kinds**: `x -> y` (plain; empty `y` erases), `ins(u,y,v)` insert y between contexts u and v, `del(u,x,v)`, `sub(u,x,y,v)`,
  `send()` (pass the string unchanged; with `permit`/`forbid` it is a test), `re(pattern) -> rhs` (Python regex, `\1`, `\A`, `\Z`;
  `$` is a literal symbol). The contexts stay unchanged but must be present (may be empty). Every rule applies at every match.
* **Control graph**: components are the states, a rule's target is its success field; a failure field is `send(), M; forbid: X`
  (appearance checking). See the table below, [grammar-types.md](https://github.com/sverlan/gcrsim/blob/main/docs/grammar-types.md).
* **Symbols**: without a declaration each character is a symbol; `a1` needs `alphabet`/`lexemes`, see Multi-character symbols below.
  Whitespace never is part of a symbol (`a S b` = `aSb`). `terminals = "a b"` in `[symbols]` (needed by search and language).
* **Marks** flag accepted strings: `[model.components.N.marks]` (or `[model.marks]` for component 1; `0` = every component),
  `label = 'regex'` or `label = { pattern = '...', expected = ["", "ab"], expected_re = '...' }` (flags all but the expected: this
  checks a grammar). Axioms are never marked. [marks](https://github.com/sverlan/gcrsim/blob/main/docs/marks-and-derivations.md#marks).
* **Settings**: `[model]` (`reject_max_len`, `reject_strings`, `history`, ...) and `[run]` (`steps`, `print_sep`, `word_sep`, `hash_history`, ...):
  [configuration.md](https://github.com/sverlan/gcrsim/blob/main/docs/configuration.md#the-settings).
* More: [rule names](https://github.com/sverlan/gcrsim/blob/main/docs/model-syntax.md#rule-names),
  [permit/forbid](https://github.com/sverlan/gcrsim/blob/main/docs/model-syntax.md#permitting-and-forbidding-words).

### `re(pattern) -> rhs`

A Python regex over the string read as symbols: a declared symbol such as `p1` is one symbol (`.` matches all of it), and every match
start gives one candidate (not a global `re.sub`). Whitespace in the pattern is removed (`re(a b)` matches `ab`): write `(?:)` to
separate symbols (`a(?:)b`). Anchors `\A`, `\Z` (`^` works); `$` is a literal symbol: a bare `$` in a pattern is accepted only when the model uses the symbol `$`
(axiom `a$`, `re(a$) -> X` gives `X`), otherwise it is an error; `\$` is always the symbol. In `rhs`: `\1`, `\g<1>`, `\g<name>`, `\\`; the literal text of `rhs` is read into symbols and
checked against the `alphabet` when the model loads, and a group keeps the symbols it captured. An exact alphabet symbol wins over
its decomposition (with `a b ab`, `re(ab)` is the symbol `ab`; use `a(?:)b` for `a` then `b`). `--describe` calls a model with `re`
rules not an insertion-deletion system and its symbol roles approximate. Broad patterns (`.*`) are slow on long strings.

```gcrsim-model
# => after 1 steps: aba Yab p1p1b
[symbols]
alphabet = "a b p1 p2 Y"
[axioms]
1 = ["aab", "p1 p2 b"]
[rules]
re((a)(b)) -> \2\1
re(\Aa) -> Y
re((?P<n>p1)p2) -> \g<n>\g<1>
```

### `send()`

`send(), M` passes the string unchanged to component M (target defaults to 1): one candidate per string, one step. With
`; permit:` / `; forbid:` it is a test of the whole string: `send(), 4; forbid: A` is the failure field of an appearance-checking rule
`A -> ...` (go on when no `A` occurs). With the default history a string that was already seen in the target component is discarded,
so `send(), 1` alone empties component 1 after one step (`history = false` changes this). Use a test, or send to another component.

### Classes

`[symbols.classes]` `V = "a b"` names a set of symbols. `{V}` in a *matching* operand (contexts, left parts, `re` patterns, `re`
classes `[^{V}]`) matches exactly one symbol of the set. Each `{V}` matches independently: `{V}{V} -> X` rewrites `ab`, `aa`, `ba`,
`bb` (checked). Not allowed in written operands (right-hand sides, `ins` insertions, permit/forbid words): `a -> {V}` is an error
(write one rule per member, or a `re` rule). Members longer than one character become multi-character symbols. A class is a set
matched at run time; a range generates rules at load time. [classes](https://github.com/sverlan/gcrsim/blob/main/docs/model-syntax.md#multi-character-symbols-classes-and-the-alphabet).

### Special operands `{start}`, `{end}`, `{any}`

Only in matching operands (contexts, the deleted/replaced part, the left part of a plain rule); never in written
ones or in permit/forbid words (error). `{start}` and `{end}` match the empty beginning and end of the string, no symbol:
`ins({start}, x, )` puts `x` at the left end (`ab` gives `xab`), `del(a, b, {end})` deletes a final `b` after `a`,
`{start}a -> Z` rewrites a leading `a`. `{any}` matches exactly one symbol, independently each time it occurs:
`del(a, {any}, b)` turns `axb` and `ayb` into `ab` and leaves `axxb`; `{any}{any} -> Z` rewrites each pair of neighbours. All three
are tested at every position (`{any} -> Z` on `aba` gives 3 candidates). In the insertion-deletion size `{start}`
and `{end}` count 0 symbols of context, `{any}` and a class count 1; with `{any}` in a deleted part `--describe` marks the symbol
roles as approximate.

### Ranges

`[symbols.ranges]` `K = "1..3"`: the only form is `first..last` (non-negative integers; `"1,2,3"` or a list is an error).
`{:K}` is the value in decimal; expressions use `+ - * %` and parentheses (`{:K+1}`, `{:K%3+1}`, `{:2*K}`): `*` needs a constant
operand (`K*K` is an error) and `%` a positive constant divisor (`{:4%K}` is an error); a negative result is an error.
A line with references stands for one line per value: the same range has the same value everywhere in the line; two different
ranges give all combinations (`A{:I}B{:J}A{:I}` gives `A0B0A0`, `A0B1A0`, `A1B0A1`, `A1B1A1`). They expand in `alphabet`, `lexemes`,
`terminals`, classes, axioms and every part of every rule line (component numbers included); not in `description`, marks,
filters or section headers, and not in `; name:` (an expanded rule is named automatically). `max_expanded_rules` (default 100000)
bounds the generated rules. A result beyond the range is kept (`{:K+1}` is 4 for `K = 3`), so an
`alphabet` that lacks `A4` rejects it with an error: use `{:K%3+1}` or end the chain. Names get the values (`hop[N=1]`). Example, a chain of components 1 to 4 (check with `--describe`, which lists every expanded rule):

```gcrsim-model
[symbols.ranges]
N = "1..3"
[axioms]
1 = ["a"]
[rules]
{:N}, a -> a a, {:N+1}; name: hop
```

`gcrsim MODEL --describe` shows `4 components, 3 rules` and `hop[N=1]  1,a->a a,2` ... `hop[N=3]  3,a->a a,4`.
[ranges](https://github.com/sverlan/gcrsim/blob/main/docs/model-syntax.md#ranges).

### Filters (declarative, no Python)

`[model.components.N.filters]` (`0` or `all` = every component; `[model.filters]` is the same as `0`) test every string that
*arrives* in component N, from any rule, after the history and `reject_max_len` / `reject_strings`: a failing string is rejected.
Keys: `forbid = ['re1', ...]` (rejected if any regex is found), `require = ['re1', ...]` (rejected if one is not found),
`max_count = { a = 5, class.N = 2, re."p." = 2 }` (a symbol at most 5 times; the symbols of a class together; each token of a
pattern separately). Regexes are searched (`\A`, `\Z`). Unlike a rule clause
`; forbid:` (literal words, on the source string before rewriting), a filter looks at the *result* and applies to all rules.
Filters, `reject_max_len` and `reject_strings` change the model: a search `not_found` and a `complete` language listing hold
only for the filtered model. [filters](https://github.com/sverlan/gcrsim/blob/main/docs/configuration.md#the-filters-of-a-component).

### Multi-character symbols

Symbols such as `a1`, `X12`, `p1` need a declaration; without one every character is a symbol and `a1` is the two symbols `a`, `1`
(a common mistake). In `[symbols]` write `alphabet = "a1 a2 b X12 S"`: every symbol of axioms, rules and permit/forbid words is
checked against it, a run of characters that reads in two ways is an error (`alphabet "a b ab"`: `abab` is ambiguous, write
`ab ab`), and a unique reading wins even over a longer symbol (`alphabet "a ab bc"` reads `abc` as `a`, `bc`). Or
`lexemes = "a1 a2"`: only names the long symbols, nothing is checked, read longest-first. Spaces are never part of a symbol but
separate symbols (`a b` is `a`, `b` even when `ab` is a symbol); axioms and replay forms are read this way. Members of a class
longer than one character are symbols too.
* *Typed words* (`--trace`, `--search`) are read as one run unless `--word-sep TEXT` (or `word_sep` in `[run]`) separates the
  symbols: `--search "a1 b" --word-sep " "`; TEXT must not occur in a symbol.
* *Printing*: text output joins the symbols with nothing, so `a1 b` and `a 1 b` look alike; `print_sep = " "` in `[run]` (not in
  `[symbols]`) prints a space where the reading would be ambiguous. jsonl gives each word as an array of symbols (`["a1","b"]`)
  plus a `*_string`. `--describe` lists the symbols it found: a quick check of how the model was read.
* *`re(...)`, marks, filters*: patterns work on symbols (`.` matches a whole `X12`; `'a1.b'` matches `a1Sb`); in `re` write `(?:)`
  between symbols (`a1(?:)b`).

```gcrsim-model
[symbols]
alphabet = "a1 a2 b X12 S"
terminals = "a1 b"
[symbols.classes]
A = "a1 a2"
[axioms]
1 = ["S"]
[rules]
S -> a1 S b
S -> a2 X12
{A}b -> X12
re(a1(?:)b) -> a2
```

More: [overlapping_symbols.txt](https://github.com/sverlan/gcrsim/blob/main/examples/features/overlapping_symbols.txt),
[symbols_and_classes.txt](https://github.com/sverlan/gcrsim/blob/main/examples/features/symbols_and_classes.txt),
[reference](https://github.com/sverlan/gcrsim/blob/main/docs/model-syntax.md#multi-character-symbols-classes-and-the-alphabet).

### Encoding each kind of system

Models in `examples/cookbook/`, explained in [grammars.md](https://github.com/sverlan/gcrsim/blob/main/docs/grammars.md)
(each file name links to the model on GitHub). Components are states; a rule's target is its success field.

| System | Construction | Model files |
| --- | --- | --- |
| Type 0, monotone, context-free, pure | plain rules `x -> y` | [`01_context_free`](https://github.com/sverlan/gcrsim/blob/main/examples/cookbook/01_context_free.txt), [`01_monotone_anbncn`](https://github.com/sverlan/gcrsim/blob/main/examples/cookbook/01_monotone_anbncn.txt), [`01_type0_powers_of_two`](https://github.com/sverlan/gcrsim/blob/main/examples/cookbook/01_type0_powers_of_two.txt) |
| Marcus internal / external | `w -> u w v` / two components, `ins({start},u,)` and `ins(,v,{end})` | [`03_marcus_internal`](https://github.com/sverlan/gcrsim/blob/main/examples/cookbook/03_marcus_internal.txt), [`04_marcus_external`](https://github.com/sverlan/gcrsim/blob/main/examples/cookbook/04_marcus_external.txt) |
| Insertion-deletion (with substitution) | `ins`, `del`, `sub` with contexts | [`02_insdel`](https://github.com/sverlan/gcrsim/blob/main/examples/cookbook/02_insdel.txt) |
| Evolutionary processors / networks | `ins`/`del`/`sub` with `{start}` `{end}`; node = component, filters = `send()` with permit/forbid | [`05_evolutionary_processors`](https://github.com/sverlan/gcrsim/blob/main/examples/cookbook/05_evolutionary_processors.txt), [`06_network_of_processors`](https://github.com/sverlan/gcrsim/blob/main/examples/cookbook/06_network_of_processors.txt) |
| Left-right insdel, Post / tag systems | operations at the ends; `re` rule or `del({start}, a{any}, )` + `ins(, x, {end})` | [`19_post_left_right`](https://github.com/sverlan/gcrsim/blob/main/examples/cookbook/19_post_left_right.txt), [`19_post_tag_system`](https://github.com/sverlan/gcrsim/blob/main/examples/cookbook/19_post_tag_system.txt) |
| Graph-controlled, with appearance checking | component = state; failure = `send()` + `forbid:` | [`07_graph_controlled`](https://github.com/sverlan/gcrsim/blob/main/examples/cookbook/07_graph_controlled.txt), [`07_graph_controlled_appearance_checking`](https://github.com/sverlan/gcrsim/blob/main/examples/cookbook/07_graph_controlled_appearance_checking.txt) |
| Matrix (with appearance checking) | a chain of components per matrix | [`08_matrix`](https://github.com/sverlan/gcrsim/blob/main/examples/cookbook/08_matrix.txt), [`08_matrix_direct`](https://github.com/sverlan/gcrsim/blob/main/examples/cookbook/08_matrix_direct.txt), [`08_matrix_appearance_checking`](https://github.com/sverlan/gcrsim/blob/main/examples/cookbook/08_matrix_appearance_checking.txt) |
| Programmed, time-varying, regular control | success = target, failure = `send()`; cycle of components; automaton states | [`09_programmed`](https://github.com/sverlan/gcrsim/blob/main/examples/cookbook/09_programmed.txt), [`10_time_varying`](https://github.com/sverlan/gcrsim/blob/main/examples/cookbook/10_time_varying.txt), [`11_regular_control`](https://github.com/sverlan/gcrsim/blob/main/examples/cookbook/11_regular_control.txt) |
| Random-context, semi-conditional, `permit-any`, ordered | `permit:` / `forbid:` / `permit-any:`; the lower rule forbids the left side of the higher | [`12_random_context`](https://github.com/sverlan/gcrsim/blob/main/examples/cookbook/12_random_context.txt), [`13_semi_conditional`](https://github.com/sverlan/gcrsim/blob/main/examples/cookbook/13_semi_conditional.txt), [`14_context_conditional`](https://github.com/sverlan/gcrsim/blob/main/examples/cookbook/14_context_conditional.txt), [`15_ordered`](https://github.com/sverlan/gcrsim/blob/main/examples/cookbook/15_ordered.txt) |
| Bounded index | filter `max_count.class.N = k` on the class of nonterminals / `max_count = { S = 2 }` on one symbol | [`16_bounded_index_classes`](https://github.com/sverlan/gcrsim/blob/main/examples/cookbook/16_bounded_index_classes.txt), [`16_finite_index`](https://github.com/sverlan/gcrsim/blob/main/examples/cookbook/16_finite_index.txt) |
| Scattered context (in part) | one `re(...)` with lazy gaps, exact when each symbol occurs once | [`18_scattered_context`](https://github.com/sverlan/gcrsim/blob/main/examples/cookbook/18_scattered_context.txt), [`18_scattered_context_choices`](https://github.com/sverlan/gcrsim/blob/main/examples/cookbook/18_scattered_context_choices.txt) |
| Counter machines | a counter is a run of one symbol; `ins`/`del` count, `send()` with `forbid:` tests zero | [`17_counter_machine`](https://github.com/sverlan/gcrsim/blob/main/examples/cookbook/17_counter_machine.txt) |
| Valence grammars | signed unary counter (`P`/`M`) updated with `ins`/`del`; a mark finds the empty counter | [`20_valence`](https://github.com/sverlan/gcrsim/blob/main/examples/cookbook/20_valence.txt) |

Not supported: parallel rewriting (L systems), binary operations (splicing, PC grammar systems), leftmost/rightmost derivations,
control by pushdown or Petri nets ([not supported](https://github.com/sverlan/gcrsim/blob/main/docs/grammar-types.md#not-supported)).

## 5. Worked examples (the models are in `examples/cookbook/` of the source repository)

Each block is the cookbook model (comments omitted). A line `# => TEXT` in a command block is a line the output contains;
`# exit N` the exit status (default 0).

### A context-free grammar, L = { a^n b^n : n >= 0 } (`01_context_free.txt`)

```gcrsim-model examples/cookbook/01_context_free.txt
[model.marks]
terminal = '\A[a-z]*\Z'
[axioms]
1 = ["S"]
[rules]
S -> a S b
S ->
```

```sh
gcrsim examples/cookbook/01_context_free.txt 3 --quiet --max-step-candidates 100000 --max-time 20
# => Mark (terminal): aabb
gcrsim examples/cookbook/01_context_free.txt --search aabb --terminals "a b" --max-steps 10 --max-history 100000 --quiet --max-time 20
# => search: found 'aabb' in component 1 at step 3
gcrsim examples/cookbook/01_context_free.txt --search aab --terminals "a b" --max-steps 8 --max-history 100000 --quiet --max-time 20   # exit 6
# => search: not found: no strings remain after step 3
```

### An insertion-deletion system, L = { a^n b^n : n >= 1 } (`02_insdel.txt`)

```gcrsim-model examples/cookbook/02_insdel.txt
[model.marks]
terminal = '\A[a-z]*\Z'
[axioms]
1 = ["ab"]
[rules]
ins(a, ab, b)
```

```sh
gcrsim examples/cookbook/02_insdel.txt --describe
# => insertion-deletion size (n,m,m';p,q,q') (2,1,1;0,0,0)
gcrsim examples/cookbook/02_insdel.txt --language --max-word-len 6 --terminals "a b" --max-steps 6 --reject-max-len 6 --max-time 30
# => Counts by symbol length 2=1, 4=1, 6=1
# => Language listing is complete for component 1 of the effective configured model, up to 6 symbols. Last collected step 3.
```

Every step adds 2 symbols, so a length filter loses no short word: the listing is `complete` (without `--reject-max-len` it is
`partial`, with `--max-steps` alone, and without both it never stops).

### A graph-controlled system with appearance checking, L = { a^(2^n) } (`07_graph_controlled_appearance_checking.txt`)

```gcrsim-model examples/cookbook/07_graph_controlled_appearance_checking.txt
[model]
reject_max_len = 20
[run]
steps = 36
[model.components.4.marks]
terminal = '\A[a-z]*\Z'
[axioms]
1 = ["A"]
3 = ["A"]
[rules.1]
A -> B B, 1
send(), 2; forbid: A
[rules.2]
B -> A, 2
send(), 1; forbid: B
send(), 3; forbid: B
[rules.3]
A -> a, 3
send(), 4; forbid: A
```

```sh
gcrsim examples/cookbook/07_graph_controlled_appearance_checking.txt --quiet --max-step-candidates 100000 --max-time 60
# => Mark (terminal): aaaa
gcrsim examples/cookbook/07_graph_controlled_appearance_checking.txt --search aaaa --terminals a --component 4 --max-steps 40 --max-history 100000 --quiet --max-time 60
# => search: found 'aaaa' in component 4 at step 18
```

The words reach component 4, so the search needs `--component 4` (in component 1 it ends `not found`). The steps (36) come from `[run]`.

### Checking a grammar, and Python

List the expected terminal strings in `expected` of a mark: every other generated terminal string is flagged. This grammar has
a mistake (the extra rule `S -> bSa`). Stop at the first deviation (otherwise thousands of lines) and let a script fail on it:

```gcrsim-model examples/features/checking_an_bn.txt
[model.components.1.marks]
unexpected = { pattern = '\A[ab]*\Z', expected = ["", "ab", "aabb", "aaabbb", "aaaabbbb"] }
[axioms]
1 = ["S"]
[rules]
S -> a S b
S -> b S a
S ->
```

```sh
gcrsim examples/features/checking_an_bn.txt 5 --quiet --fail-on-mark unexpected --stop-on-mark-label unexpected --max-step-candidates 100000 --max-time 20   # exit 4
# => Mark (unexpected): ba
```

Marks see only generated strings (not axioms) and say nothing about words that are missing. With the `02_insdel.txt` model saved
as `insdel.txt`:

```python
import gcrsim
res = gcrsim.search("insdel.txt", "aabb", terminals="a b", max_steps=20, max_history=100000, max_time=60)
if res.found:
    print(res.step, res.measures.steps, res.measures.max_len)   # steps, longest form
    print(gcrsim.format_derivation(res.derivation))
else:
    print(res.outcome, res.reason, res.conditional)             # not_found / inconclusive
lang = gcrsim.language("insdel.txt", 6, terminals="a b", max_steps=3, max_history=100000, max_time=60)
print(lang.outcome, lang.reason, lang.counts)                   # partial depth_bound {2: 1, 4: 1, 6: 1}
```

Also `gcrsim.describe(model)` and `gcrsim.replay_file(model, file)`;
[python.md](https://github.com/sverlan/gcrsim/blob/main/docs/python.md#search).

## 6. Output, derivations and settings

### Development workflow

1. `gcrsim MODEL --describe`: rule kinds, size, symbol roles, control graph; fix surprises before running.
2. A short bounded run with marks (`gcrsim MODEL 10 --max-time 20 ...`): are the first strings plausible?
3. Mark the intended words: `expected = [...]` or `expected_re` plus `--fail-on-mark LABEL --stop-on-mark-label LABEL`; list the
   language up to a length (`--language`) and compare it with the words you expect (extra, missing).
4. `--search WORD` for specific words (both ones that must and ones that must not be generated), with bounds.
5. `--replay FILE` on a derivation from the paper (`--fragment` for a part); fix the rules until each step is legal.

### Derivations and measures

`--trace WORD` prints `Trace of 'w' (component c), first appearing at step n:`; `--trace-marks` / `--trace-mark-label L` print
`Mark [LABEL] at step n, component c: STRING` for every mark (they retain the strings of every step: bound them, section 2); a
search prints `Derivation of 'w' ...`. Then one line per step, `step i: before => after   (component s -> t, rule at line L:
NOTATION, position P)` (position counts symbols from 0; a named rule shows its name), the `measures:` line and the `rules:` line
(uses of each rule). Measures (text, `measure(...)` in Python, the `measures` object in jsonl): `steps`; `max_len`, `max_len_step`
(longest form, first step where; 0 is the first form); `rules` (`line`, `component`, `notation`, `name`, `kind`, `bindings`,
`count`); `created`, `deleted` (symbols inserted and removed over all steps); `max_nonterminals`, `max_nonterminals_step` (needs
declared terminals, else `null`); `components` (the forms the derivation has in each component).
[derivation sequences](https://github.com/sverlan/gcrsim/blob/main/docs/marks-and-derivations.md#derivation-sequences),
[measures](https://github.com/sverlan/gcrsim/blob/main/docs/python.md#measures-of-a-derivation).

### Output conventions

Text output is for people; scripts use `--format jsonl` (one object per line, field `type`, components from 1, a word is an array of
symbols with `[]` the empty word, plus a `*_string` sibling; `--quiet` does not remove the jsonl header). Records by mode (the
mode is in `header.mode`; compare with a tiny run, [jsonl](https://github.com/sverlan/gcrsim/blob/main/docs/cli.md#jsonl)):

| Mode | Records (`header` first, `end` last on a normal end; the others interleave as the run goes, e.g. step 0, marks, step 1, derivations) |
| --- | --- |
| run | `header`, `step` (`step`, `components`, `components_string`) per step, `message` (marks, notes), `derivation` + `derivation_step` for `--trace` / `--trace-marks`, `end` (`status`, `steps`) |
| search | `header` (adds `word`, `word_string`, `component`), `message`, on success `derivation` (`word`, `found_at`, `steps`, `measures`) + `derivation_step`, `end` (`outcome`, `reason`, `limit`, `explored`, `bounds`, `pruning`, `conditional`) |
| language | `header` (adds `component`), `message`, `word` (`word`, `word_string`), `end` (`outcome`, `reason`, `detail`, `counts`, `bounds`, `restrictions`) |
| replay | `header` (adds `file`, `fragment`), `message` (settings output), `derivation_step` (with `lines`, `ways`; no `derivation` record), `end` (`ok`, `failure`, `measures`) |

`derivation_step`: `step`, `component`, `target`, `before`, `after` (with `_string`), `rule` (`line`, `kind`, `notation`, `name`,
`bindings`, `u`, `x`, `y`, `v`), `start`, `end`, `removed`, `inserted`. `end.status` is the exit code. After an error that
follows the header (for example `--terminals z`) there is no `end` record: use the exit status and stderr; a missing `end` also
means an interrupted run.

Streams: with no model, `gcrsim` and `gcrsim --describe` print the help (stdout) and exit 2; argument errors have no source line and
some model errors name only the file (`<string>: unknown setting 'PI' in [model]`).

### The empty word

Axiom `1 = [""]`; a rule with an empty right-hand side erases (`S ->`). Text output prints `(empty word)`; jsonl has `[]` and `""`.
Replay file: `1:`. Search: `--search "" --terminals "a b"` finds it in the context-free example (step 1).

### Settings layers, quoting

Later layers win key by key: defaults, the `[model]` / `[run]` of the model file, each `--config FILE.toml` (repeatable, later
files win), `--python-filter FILE.py`, then command-line switches (`--print-all`, the step count, the limits).
[layers](https://github.com/sverlan/gcrsim/blob/main/docs/configuration.md#the-order-of-the-layers). Write regular expressions in
single quotes: `'\A[ab]*\Z'` is literal; in double quotes every backslash is doubled (`"\\A[ab]*\\Z"`). A single-quoted string
cannot contain `'`: use double quotes for such a value. Model files take no multi-line strings (`'''`, `"""`); a `--config`
TOML file is read as plain TOML. Rule lines have no quotes; axioms are TOML strings.
[quotes](https://github.com/sverlan/gcrsim/blob/main/docs/configuration.md#single-and-double-quotes).

### `--python-filter` (last resort)

`--python-filter FILE.py` runs the file (it executes code) and takes its settings and `keep(s, component[, ctx])`, called for every
candidate that passed the declarative filters (axioms bypass filters); `s` has the real symbol names, `component` counts from 0, a
false result rejects, `ctx.mark(label)` can mark a candidate that `keep` then rejects. Prefer declarative filters. `--streaming`
refuses a `keep` not declared `keep.pure = True`; a search turns pruning off for it, and its answers hold only under the filter.
[python.md](https://github.com/sverlan/gcrsim/blob/main/docs/python.md#the-filter-function-keep).

## 7. Pitfalls

* **A step** (semantics): every match of every rule of a component, in every string of that component, gives one candidate made from
  the *original* string. On `aa` the rules `a -> b` and `b -> c` give `ba` and `ab` at step 1 and no `c`. Candidates go to the
  target components; those that are already in the history, too long, matched by `reject_strings` or failing a filter are dropped;
  the accepted ones are the contents used at the next step and the old contents are discarded. So a string stays in a component
  only if a rule produces it there again: with the default history `send(), 1` on a string already seen yields a duplicate and
  the string vanishes (`history = false` allows repeats). Overlapping matches all count (`aa -> b` on `aaa`: `ba`, `ab`). There are
  no leftmost or rightmost modes. [semantics.md](https://github.com/sverlan/gcrsim/blob/main/docs/semantics.md#one-step).
* A run that stops by its step count says nothing about the language; marks see only generated strings (not axioms) and cannot show missing words.
* Memory: a run keeps the history; language keeps the frontier, the history and the words; search also keeps the past frontiers for the derivation. Use the limits of section 2. A rule that matches at every position (`{any}`, empty contexts) gives about one candidate per position and string.
* `{:` always starts a range reference in axioms and rule lines; `\{:` (an odd number of backslashes) is a literal `{:` in a
  `re` pattern.

## 8. More documentation

[cli.md](https://github.com/sverlan/gcrsim/blob/main/docs/cli.md) (all options), [model-syntax.md](https://github.com/sverlan/gcrsim/blob/main/docs/model-syntax.md), [semantics.md](https://github.com/sverlan/gcrsim/blob/main/docs/semantics.md), [configuration.md](https://github.com/sverlan/gcrsim/blob/main/docs/configuration.md), [marks-and-derivations.md](https://github.com/sverlan/gcrsim/blob/main/docs/marks-and-derivations.md), [grammar-types.md](https://github.com/sverlan/gcrsim/blob/main/docs/grammar-types.md), [grammars.md](https://github.com/sverlan/gcrsim/blob/main/docs/grammars.md) (cookbook), [python.md](https://github.com/sverlan/gcrsim/blob/main/docs/python.md), [checking.md](https://github.com/sverlan/gcrsim/blob/main/docs/checking.md) (how results are verified), [interactive.md](https://github.com/sverlan/gcrsim/blob/main/docs/interactive.md) (`-i`, not for scripts).
