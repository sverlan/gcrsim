# The command line

```
gcrsim MODEL [STEPS] [options]
```

runs the model in the file `MODEL` for `STEPS` steps and lists the strings of every step. From a checkout, `python -m gcrsim` does the
same. `gcrsim --help` lists all the options, and this page explains them, grouped by purpose. `gcrsim` does one operation at a time, chosen with `--mode`: `run` (the default, described on this page), `replay`
([Replay](#replay)) and `search` ([Search](#search)). Two other programs are installed with
the package: `gcrsim-convert`, which translates a model of the Perl simulator ([migration.md](migration.md)), and `gcrsim-retention`,
which reads a file written with `--retain-file` ([Retained steps](#retained-steps)).

Exit statuses:

| Status | Meaning |
| --- | --- |
| 0 | the run completed; a search found the word |
| 2 | an error in the model, a setting or the arguments (the message names the file and the line) |
| 3 | a limit stopped the run ([Limits](#limits)), the time limit included; a search that a limit, the time limit or an interruption stopped before it could answer |
| 4 | `--fail-on-mark` found a mark with a failing label, or a replay found a step that is not legal |
| 5 | `--cross-check` found a difference between the engine and the reference interpreter |
| 6 | a search covered everything within its bounds and did not find the word ([Search](#search)) |
| 130 | interrupted |

## Choosing the operation

`--mode NAME` selects what the command does:

| Mode | Command | What it does |
| --- | --- | --- |
| `run` | `gcrsim MODEL STEPS` | runs the model and lists the strings of every step (the default) |
| `replay` | `gcrsim --mode replay MODEL FILE` or `gcrsim MODEL --replay FILE` | checks that the forms in `FILE` are a derivation of the model |
| `search` | `gcrsim --mode search MODEL WORD` or `gcrsim MODEL --search WORD` | searches for `WORD` breadth first and prints a derivation of it |

`--mode run` is the same as no selector. The selector may stand before or after the model and the other options, as `--mode NAME`
or `--mode=NAME`; it must be written in full (`--mode`, `--replay` and `--search`, not `--mod`, `--rep` or `--sea`). `--replay FILE` and
`--search WORD` are shorter ways to write `--mode replay` and `--mode search` with their operand. Only one selector may be given, even if two of them agree. A selector after the terminator `--`,
or an option value that looks like one (`--trace --mode`), is not a selector.

Each mode accepts only its own options: `gcrsim MODEL FILE --mode replay --trace S` is an error, because `--trace` belongs to `run`.
`gcrsim --mode replay --help` shows the options of the mode and needs no model; `gcrsim --help` shows those of `run`.

## Running

* **The number of steps.** `STEPS` is a number, or the setting `steps` of the model or of a `--config` file. There is no default: with
  neither, the run is refused with a message. A number on the command line wins over the setting.
* **Step by step.** `-i` (`--interactive`) lists the initial strings and then waits for a command after each step: Enter for the next
  step, and commands to look at the strings, find one, trace it, mark or remove a string, or quit; see
  [interactive.md](interactive.md). It cannot be combined with `STEPS` or with the formats `csv` and `jsonl`.
* **The model file.** Without `MODEL` the program shows its help and exits with status 2; `gcrsim-convert` and `gcrsim-retention` do the same
  without their file argument.
* **When everything is empty.** A run stops early, with a message on the standard error, once all components are empty, because nothing
  can happen any more. `--run-empty` keeps running anyway.

### Settings

The settings come from the model file; `--config FILE` (repeatable, later files win) changes them for one run, and
`--python-filter FILE.py` adds a Python file, which **executes code**. The layers and their order are in
[configuration.md](configuration.md) and the Python file is in [python.md](python.md).

## What a run prints

`--format` chooses the layout: `text` (the default), `perl`, `csv` or `jsonl`. All of them apply the print settings `print_hide` (a regular expression: matching strings are not listed)
and `print_max_len` (longer strings are not listed); these settings hide strings from the listing only, and the run goes on with them.
`--print-all` ignores both.

### text (the default)

A short header, then for every step a heading and the strings of each component, one per line:

```
gcrsim 0.1.0.dev0   examples/cookbook/07_graph_controlled.txt
2 components, 2 rules

step 0
component 1
S

component 2

step 1
component 1
aSb

component 2
(empty word)
```

* The header names the program and the model, the description of the model (if it has one), the numbers of components and rules, the
  layers of the settings when a `--config` file or a Python file was used (`settings: model + exp1.toml`), and then **only the settings
  that differ from the defaults** (`print_max_len 60, reject_max_len 100, history off, filters for 2 components, ...`). A default
  run has no line of settings.
* An empty component is a heading followed by a blank line. The empty word is written `(empty word)`, so that it is not mistaken for an
  empty component.
* The strings are printed as they are, flush left, so that a string can be copied or searched for exactly.
* A mark prints its line when it appears (`Mark (label): string`), and the marks are listed again at the end of the run. A derivation
  requested with `--trace` or `--trace-marks` is printed under the step that produced it.

| Option | Effect |
| --- | --- |
| `--quiet` | no header and no listings; only the lines printed by marks, derivations and callbacks remain |
| `--no-mark-summary` | do not list the marks at the end of the run |
| `--progress` | write one summary line per step to the standard error: strings per component, candidates, history size, retained strings, elapsed time |

### perl

The layout of the Perl simulator, kept for comparing results with it (the tests that compare with the Perl simulator use it): a
header that lists all the settings, then for every step a banner and the strings of each component. The options of the table above
work in the same way.

```
========================================
gcrsim simulator v.0.1.0.dev0
Program configuration:
Input file: examples/cookbook/07_graph_controlled.txt
Configuration: model
Print_hide = ""; Print_max_len=unlimited;
Reject_strings = ""; Reject_max_len=unlimited
Filter function used: no, History: yes
========================================
The initial configuration (at STEP 0):

Component 1:
S

Component 2:


============
STEP 1
============

Component 1:
aSb

Component 2:
```

### csv

Only the strings, as plain CSV that any spreadsheet or data library reads: a header row `step,component,string` and one row per string.
Step 0 is the axioms, and components count from 1.

```
step	component	string
0	1	S
1	1	aSb
1	2	
2	1	aaSbb
2	2	ab
```

The separator is a tab by default; `--csv-sep` takes one character (`--csv-sep ,` or `--csv-sep ';'`) or the word `tab`. Marks, derivations
and messages go to the standard error, so the data stay clean. Every step but the last is complete, and the exit status says whether the
run ended normally.

### jsonl

One JSON object per line (JSON Lines), with a field `type`. Components are counted from 1. A word is an array of symbol names (the empty
word is `[]`), so a multi-character symbol is never cut and `print_sep` is not applied; every such field has a sibling with the suffix
`_string` that holds the word as the text output prints it (the names joined with `print_sep`; plain concatenation without it; the empty
word is `""`).

```
{"type": "header", "version": "0.1.1", "mode": "run", "model": "examples/cookbook/07_graph_controlled.txt", "configuration": "model", "description": ""}
{"type": "step", "step": 0, "components": [[["S"]], []], "components_string": [["S"], []]}
{"type": "step", "step": 1, "components": [[["a", "S", "b"]], [[]]], "components_string": [["aSb"], [""]]}
{"type": "end", "status": 0, "steps": 1}
```

| Object | Fields |
| --- | --- |
| `header` | `version`, `mode` (`run`, `replay` or `search`), `model`, `configuration`, `description`; a replay adds `file` and `fragment`; a search adds `word`, `word_string` and `component` |
| `step` | `step`; `components`: for each component, its words as symbol arrays; `components_string`: the same with strings |
| `derivation` | a derivation asked for with `--trace` or `--trace-marks`, or the derivation that a search found: `word`, `word_string`, `component`, `found_at` (the step), `steps` (their number), `measures` and, for a mark, `mark` (the label); it is followed by its `derivation_step` objects |
| `derivation_step` | `step`, `component`, `target`, `before`, `before_string`, `after`, `after_string`, `rule`, `start`, `end`, `removed`, `inserted`; a replay adds `lines` and `ways` |
| `measures` (inside `derivation` and `end`) | `steps`; `max_len` and `max_len_step` (the longest form, and the first step where it occurs; 0 is the first form); `rules` (a list of `line`, `component`, `notation`, `name`, `kind`, `count`, in the order of the lines); `created` and `deleted` (symbols inserted and removed over all steps); `max_nonterminals` and `max_nonterminals_step` (`null` when no terminals are declared); `components` (a list of `component` and `forms`: the forms the derivation has in each component, the first form included) |
| `message` | `text`: the text of a mark, a callback or a note; what a configuration file prints while it loads is a `message` object right after the header |
| `end` | `status` and `steps`; a replay adds `ok` and `failure` (`null`, or `line`, `step`, `component`, `target`, `before`, `before_string`, `after`, `after_string`, `reason`; `after` and `after_string` are `null` when the first form is not an axiom), and `reason` `time` when the time limit stopped it (`ok` is then false and `failure` `null`); a search adds `outcome` (`found`, `not_found`, `inconclusive`), `reason`, `limit` (the name of the limit that stopped it, or `null`), `explored`, `bounds` (`max_steps`, `max_nonterminals`, `max_len`, `max_time` in seconds; `null` when not set), `pruning` (`on` and `reason`, `null` when it was on) and `conditional` (a list of `python_filter`, `hash_history`, `max_nonterminals`, `max_len`); there `steps` is the last complete step, or the step at which the word appeared. A replay also has `measures` (those of the steps checked; `null` when the first form is not an axiom) and `measures_partial` (true when the replay stopped before its last form: the measures then are those of the legal steps before the failure) |

In a `derivation_step`, `start` and `end` delimit the replaced part of `before` in symbols; `removed` are the symbols that were replaced and
`inserted` the ones that took their place. The `rule` object has `line`, `kind` (`plain`, `ins`, `del`, `sub`, `send` or `re`), `notation`
(the rule in the notation of the model, without the white space it does not need), `name` (the name of the rule, or `null`) and the
operands `u`, `x`, `y`, `v` as arrays of symbols, named as in
[model-syntax.md](model-syntax.md): `sub(u,x,y,v)` replaces `x` by `y`; a plain rule `x -> y` has `x` and `y`; `ins(u,y,v)` has `u`, `y`
and `v`; `del(u,x,v)` has `u`, `x` and `v`; `send` and `re` have none. An operand that the kind of rule does not have is `null`; a class is
written `{NAME}`, and `{start}`, `{end}` and `{any}` stand for themselves.

```
{"type": "derivation", "word": ["a", "S", "b"], "word_string": "aSb", "component": 1, "found_at": 1, "steps": 1}
{"type": "derivation_step", "step": 1, "component": 1, "target": 1, "before": ["S"], "before_string": "S", "after": ["a", "S", "b"], "after_string": "aSb",
 "rule": {"line": 12, "kind": "plain", "notation": "S->aSb", "name": null, "u": null, "x": ["S"], "y": ["a", "S", "b"], "v": null},
 "start": 0, "end": 1, "removed": ["S"], "inserted": ["a", "S", "b"]}
```

The derivation of an axiom has `steps` 0 and no `derivation_step`. A reader keeps the complete lines and drops a last line that does not
parse; a missing `end` means that the run was interrupted.

## Marks and derivations

A mark flags a string ([marks-and-derivations.md](marks-and-derivations.md)); a derivation is the list of rule applications that leads
from an axiom to a string. These options ask for them:

| Option | Effect |
| --- | --- |
| `--trace STRING` | print the derivation of `STRING` when it first appears; `--component N` says in which component (default 1). `STRING` is the literal string, a space included; with `--word-sep TEXT` (or the setting `word_sep`) it is cut at `TEXT` instead, and the pieces are read as symbols. |
| `--word-sep TEXT` | the separator of the symbols of `STRING` (overrides the setting `word_sep`; see [configuration.md](configuration.md)) |
| `--stop-on-found` | stop after the step in which the string of `--trace` appeared |
| `--trace-marks` | print a derivation for every mark |
| `--trace-mark-label LABEL` | derivations only for the marks with this label (repeatable; implies `--trace-marks`) |
| `--stop-on-mark` | stop after the step in which a mark was recorded |
| `--stop-on-mark-label LABEL` | the same, for marks with this label (repeatable) |
| `--fail-on-mark LABEL` | exit with status 4 if a mark with this label was recorded; `*` means any label (repeatable). For scripts |

A stop option always finishes the current step first.

```
$ gcrsim examples/cookbook/07_graph_controlled.txt 4 --trace aabb --component 2 --quiet
Trace of 'aabb' (component 2), first appearing at step 3:
    step 1: S => aSb   (component 1 -> 1, rule at line 14: S->a S b,1, position 0)
    step 2: aSb => aaSbb   (component 1 -> 1, rule at line 14: S->a S b,1, position 1)
    step 3: aaSbb => aabb   (component 1 -> 2, rule at line 16: S->,2, position 2)
    measures: 3 steps, longest form 5 symbols (step 2), 6 symbols created, 3 deleted
    rules: S->a S b,1 (line 14) x2, S->,2 (line 16) x1; components: 1 (3 forms), 2 (1 form)
```

Each line gives the step, the string before and after, the components, the rule (its line in the model file and its text; a rule with a name is shown as `rule NAME at line N: ...`) and the
position of the rewritten part. Nothing is recorded for this during an ordinary run. When a derivation is requested, the simulator
keeps the accepted content of each step (references to the strings that the history holds anyway, about 8 bytes per string) and
rebuilds the derivation backwards by applying the rules again to the previous content, in the original generation order. The result is
the chain of the first discovery, which is a shortest derivation. Several marked strings are traced together, in one pass per level.
With `--format jsonl` the derivation is written as a `derivation` object followed by `derivation_step` objects ([jsonl](#jsonl)) instead of text.

After the steps, two lines give the measures of the derivation, computed from the steps themselves: the number of steps; the longest
form, in symbols, and the first step at which it occurs (0 is the first form); the largest number of symbols that are not terminals,
and its first step (only when the terminals are declared: the setting `terminals` in `[symbols]`, or `--terminals` in a search); the
number of symbols created (inserted) and deleted over all steps; how many times each rule is used (shown as its name, or its notation if it has none, and its line: `grow (line 14) x2`); and how many forms
the derivation has in each component, the first form included. The peak of non-terminals counts the first form, while a search does
not apply `--max-nonterminals` to the axioms. They are printed after every derivation: `--trace`, `--trace-marks`, a derivation found
by a search, the steps shown by `replay --explain`, the interactive `trace` command and `gcrsim-retention --trace`. With `--format jsonl`
they are the `measures` object of the `derivation` object ([jsonl](#jsonl)).

### Retained steps

By default the kept steps are in memory. `--retain-file FILE` keeps them in an SQLite file instead (one step is read back only when
a derivation is rebuilt); the history of the strings seen, which is the larger part of the memory, stays in memory.
`--max-retained N` caps the number of retained strings: the run then stops with status 3, or with `--trace-best-effort` it continues
without tracing.

The file can be examined later, without running the simulation again, with `gcrsim-retention`:

| Command | Shows |
| --- | --- |
| `gcrsim-retention FILE` | a summary: the number of strings of each component in each step |
| `gcrsim-retention FILE --step N [--component C]` | the strings of one step, with the real symbol names |
| `gcrsim-retention FILE --find STRING [--component C]` | the steps and components that hold a string |
| `gcrsim-retention FILE --trace STRING --model MODEL [--component C]` | its derivation; `MODEL` is the model of the run that wrote the file |

It is an ordinary SQLite database, so `sqlite3 FILE` or any SQLite browser also works. The table `strings(step, comp, idx, s)` has one row
per string (`comp` and `idx` count from 0), and the table `lexeme(code, name)` maps the internal characters of the multi-character
symbols back to their names.

## Checking the engine

`--cross-check` runs an independent reference interpreter next to the engine and compares every step; a difference stops the run with
status 5. It works for the plain fragment only (no `re(...)` rules, `reject_strings`, filters or filter function), and is described in
[checking.md](checking.md).

## Replay

```
gcrsim --mode replay MODEL FILE [options]
```

checks that the forms in `FILE` (`-` is the standard input) are a derivation of the model: every form follows from the one before it
by one step of the model. It is the way to check a derivation that comes from elsewhere, a proof in a paper, the output of another
program, or a trace that you edited. `gcrsim MODEL --replay FILE` means the same.

**The file.** Read as UTF-8 text (an optional byte order mark is dropped; the same for the standard input). One form per line. A form is a word in a component, written `N: WORD`, where `N` is the component (counted from 1). A
line without `N:` is in the component given by `--component` (default 1). Blank lines are ignored, and so is a line whose first
non-blank character is `#`. A word is written with the symbols together (`rd0a0`) or separated by spaces (`rd0 a0`), so that a word printed by a run can be pasted into the file. The empty word is an empty text after the
prefix: `2:` is the empty word of component 2, and `1:` is the empty word of component 1 (an empty line is not a form). A word that
starts with digits and a colon needs its prefix, `1: 12:a`, because `12:a` alone would be read as the word `a` in component 12.

```
# a derivation of examples/cookbook/07_graph_controlled.txt
1: S
1: aSb
1: aaSbb
2: aabb
```

Symbols are written together or separated by white space, and by the setting `word_sep` (`--word-sep TEXT`) when it is set: `xy a`,
`xy-a` with `word_sep = "-"` and `xya` are the same two symbols when `xy` is a symbol. `print_sep` plays no part in reading a word, but
with equal `print_sep` and `word_sep` the words that a run prints can be pasted back. No character of `word_sep` may occur in a symbol
of the model: the replay is refused otherwise, and a model with `re(...)` rules gets a warning. In a replay file `:` marks the
component, so a `word_sep` that contains `:` (or a line break) is refused for a replay. A word cannot hold a space as a symbol (a
regular-expression rule can produce one), so such a derivation cannot be replayed. The internal characters of the program (the null
character and the private-use characters that stand for multi-character symbols) are refused in a word.

**What is checked.** The first form must be an axiom of its component; `--fragment` removes this condition, to check a part of a
derivation. For every pair of consecutive forms, `s` in component `c` and `t` in component `d`, some rule of component `c` that sends
its result to component `d` must give `t` from `s`: its permit and forbid conditions hold for `s`, and `t` is one of its results.
The history, the length bounds, `reject_strings`, the component filters, the filter function and the marks are not checked, so a
derivation that the simulator would have dropped can still be legal. A step that two rules, or two positions, give is legal once; the
number of ways is shown with `--explain`.

**Output.** The text format prints the usual header, then, with `--explain`, a line for every legal step:

```
step 2 (lines 2-3): aSb => aaSbb   (component 1 -> 1, rule at line 14: S->a S b,1, position 1)
```

(`, 2 ways` follows the position when several rules or positions give the step), and a last line:

```
replay of derivation.txt: 3 steps, all legal (filters and the history are not checked)
replay of derivation.txt: step 3 (line 4) is not legal: no rule of component 1 gives this string in component 2: 'aaSbb' => 'aab'
replay of derivation.txt: line 1: the first form is not an axiom of component 1: 'aS' (use --fragment to check a derivation that does not start from an axiom)
```

`--quiet` prints only the last line. With `--explain` the steps are followed by the two lines of measures of the derivation ([Marks and derivations](#marks-and-derivations)). `--format jsonl` writes a `header` object (with `mode` `replay`), one `derivation_step` object for every legal step
(the object of a traced derivation, with `lines` and `ways` added) and an `end` object with `status`, `steps`, `ok`, `failure` and `measures`; see [jsonl](#jsonl).

The exit status is 0 if every step is legal, 4 if one is not (the report names the first), and 2 if the model or the file cannot be
read, a symbol is not in the alphabet, a component does not exist or the file holds no form (the message names the file and the line).

With `--max-time`, a replay that runs out of time reports the steps it had checked and
ends with status 3: the text format says that the rest was not checked, and the jsonl format writes an `end` object. A replay that
ends after the limit has passed is not reported as successful.

| Option | Meaning |
| --- | --- |
| `--component N` | the component of the forms that have no `N:` (default 1) |
| `--fragment` | the first form need not be an axiom |
| `--word-sep TEXT` | `TEXT` also separates the symbols of a word, as white space does (overrides the setting `word_sep`) |
| `--explain` | text format: show the rule, the position and the number of ways of every step |
| `--format {text,jsonl}` | the layout of the report (the other formats of a run do not apply) |
| `--quiet` | text format: print only the last line |
| `--config FILE`, `--python-filter FILE.py` | settings, of which only `print_sep` (how `--explain` writes the words) and `word_sep` (how the words are read) matter here; the filters of a Python file are not applied |
| `--max-time T` | stop with status 3 when the elapsed time of the program passes `T` ([Limits](#limits)) |

## Search

```
gcrsim --mode search MODEL WORD [options]
```

looks for `WORD` in a component of the model, breadth first, and prints a derivation of it: the run goes on step by step until the word
appears, and the derivation is then rebuilt, so it is a shortest one in steps. `gcrsim MODEL --search WORD` means the same. The word is
read like the word of `--trace`: its symbols are written together or separated by `--word-sep` (or the setting `word_sep`); it may be
empty and may hold non-terminals; `--component N` (default 1) says in which component it must appear.

**Terminals.** The search must know which symbols are terminals: declare them with the setting `terminals = "a b"` in `[symbols]`
([configuration.md](configuration.md)), or give them with `--terminals "a b"`, which wins over the setting. Without either the search is
refused (status 2). An empty declaration (`terminals = ""`, `--terminals ""`) is an error too, and so is a name that is not one symbol
of the model. A run and a replay accept the setting and ignore it.

**Pruning.** The terminals are used to cut the search. If no rule deletes or rewrites a terminal, the terminals of a string never
disappear or change their order, so a string whose terminals, in order, are not a subsequence of the terminals of `WORD` can never lead
to `WORD`; it is dropped before it enters the history. This is sound: the answer does not change, only the work. The condition is
checked on every rule of every component: the part that a rule replaces or deletes must hold no terminal (contexts, guards,
insertions and `send()` do not matter). When it fails, or cannot be checked, pruning is switched off, the search still runs, and the
outcome says why; a note is written at the start too. Pruning is also switched off, with a note, when a function of yours that can
reject strings (the filter function `keep`, or a function in the filters of a component) is not declared pure (`keep.pure = True`):
pruning changes which strings the function sees, so a function with state could accept a different set. A function declared pure keeps
pruning on. `--no-pruning` switches it off.

**Bounds.** `--max-steps N` is the depth bound; without it the search runs until the word appears, no string remains, or a limit stops
it. `--max-nonterminals K` drops every derived string with more than `K` symbols that are not terminals; the axioms are not tested. This
is a restriction, not sound pruning: a negative answer then holds only within it. The length bound `reject_max_len` of the model is a
bound of the search too. `--max-time T` is the time limit ([Limits](#limits)); the other limits work as in a run and make the search
inconclusive.

**The outcome.** A search ends with exactly one outcome, in the last lines of the output and in the exit status:

| Outcome | Status | Reasons |
| --- | --- | --- |
| `found` | 0 | the word appeared at step *n*; the derivation is printed |
| `not_found` | 6 | `frontier_exhausted`: no string remains, so every string within the bounds was explored; `depth_bound`: all the steps up to `--max-steps` were completed without the word |
| `inconclusive` | 3 | `limit`: `--max-history`, `--max-step-candidates`, `--max-step-accepted` or `--max-retained` stopped it (a limit that the axioms already reach is reported at step 0); `time`: `--max-time`; `interrupted`: Ctrl-C, at any point of the search, also while the settings are loaded |

A partial exploration is never reported as "not found", and a search whose time limit has passed never answers "found" or "not found".
The outcome also gives the last complete step, the number of strings that entered the history (`explored`; without a history, the number
of candidates generated), the bounds that were set, whether pruning was on (and, if not, why), and the conditions under which a negative
answer holds: a filter of yours ran (`--python-filter`), `hash_history` is on (digests may collide), `--max-nonterminals` or a length
bound of the model is set. A found derivation is a real derivation whatever the conditions. A found derivation is followed by its measures ([Marks and derivations](#marks-and-derivations)).

```
$ gcrsim examples/python/target_pruning.txt --search abba
gcrsim 0.1.1   examples/python/target_pruning.txt
1 component, 3 rules
reject_max_len 19

Derivation of 'abba' (component 1), first appearing at step 5:
    step 1: S => aS   (component 1 -> 1, rule at line 22: ins(,a,), position 0)
    step 2: aS => aaS   (component 1 -> 1, rule at line 22: ins(,a,), position 0)
    step 3: aaS => abaS   (component 1 -> 1, rule at line 23: ins(,b,), position 1)
    step 4: abaS => abbaS   (component 1 -> 1, rule at line 23: ins(,b,), position 1)
    step 5: abbaS => abba   (component 1 -> 1, rule at line 24: del(,S,), position 4)
    measures: 5 steps, longest form 5 symbols (step 4), at most 1 non-terminal (step 0), 4 symbols created, 1 deleted
    rules: ins(,a,) (line 22) x2, ins(,b,) (line 23) x2, del(,S,) (line 24) x1; components: 1 (6 forms)

search: found 'abba' in component 1 at step 5
        explored 45 strings; pruning on
        bounds: strings of at most 19 symbols
        conditions: the length bound
$ gcrsim examples/python/target_pruning.txt --search abba --max-steps 3 --quiet
search: not found: no derivation of at most 3 steps
        explored 36 strings; pruning on
        bounds: at most 3 steps; strings of at most 19 symbols
        the answer holds only under: the length bound
$ gcrsim examples/python/target_pruning.txt --search abbaabbaab --no-pruning --max-history 20000 --quiet
search: inconclusive: the limit max-history (20000) stopped step 10; last complete step 9
        explored 20001 strings; pruning off (switched off by the user)
        bounds: strings of at most 19 symbols
        conditions: the length bound
```

The three runs end with status 0, 6 and 3. The text format does not list the strings of the steps; `--progress` writes a line per step to
the standard error. `--quiet` prints only the outcome. `--format jsonl` writes a `header` object (with `mode` `search`, `word`,
`word_string` and `component`), on success a `derivation` object and its `derivation_step` objects, messages, and an `end` object; for
the second example above, with `--format jsonl`, the `end` object is:

```
{"type": "end", "status": 6, "steps": 3, "outcome": "not_found", "reason": "depth_bound", "limit": null, "explored": 36, "bounds": {"max_steps": 3, "max_nonterminals": null, "max_len": 19, "max_time": null}, "pruning": {"on": true, "reason": null}, "conditional": ["max_len"]}
```

The other formats of a run do not apply; see [jsonl](#jsonl). The filter of the file `--python-filter` is applied after the built-in
pruning; a negative answer is then conditional on it, and the outcome says so.

| Option | Meaning |
| --- | --- |
| `--component N` | the component in which `WORD` must appear (default 1) |
| `--word-sep TEXT` | `TEXT` also separates the symbols of `WORD` (overrides the setting `word_sep`) |
| `--terminals "a b"` | the terminals, separated by white space (overrides the setting `terminals`) |
| `--max-steps N` | the depth bound |
| `--max-nonterminals K` | drop the derived strings with more than `K` non-terminals (a restriction) |
| `--no-pruning` | do not prune by the terminals |
| `--max-time T`, `--max-step-candidates N`, `--max-history N`, `--max-step-accepted N` | limits, as in a run ([Limits](#limits)); the search is then inconclusive |
| `--max-retained N`, `--retain-file FILE` | cap the strings retained for the derivation, or keep them in a file ([Retained steps](#retained-steps)); the file is emptied when opened, so the model, a `--config` file and the `--python-filter` file are refused as its name |
| `--format {text,jsonl}` | the layout of the report |
| `--quiet`, `--progress` | text format: print only the outcome; one summary line per step to the standard error |
| `--config FILE`, `--python-filter FILE.py` | settings, and the filter function `keep`, which runs after the built-in pruning |

**Limitations.**

* *Some models get no pruning.* A rule that deletes or rewrites a terminal breaks the argument above, so pruning is off for the model.
  A class, `{any}` or a regular expression in the part that a rule replaces can match a terminal in a way that the rule does not show,
  so the condition cannot be checked and pruning is off too. The search still runs; the outcome names the first rule (in the order of
  the file) that caused it, by its name or notation and its line.
* *The pruning is sound but gains little on its own.* It removes only the strings whose terminals cannot fit the word. On an
  insertion-deletion model with 46 rules and a length bound of 8, a search for a word of 5 symbols (12 steps) put 19.6 million strings
  in the history instead of 24.4 million; on a model with 530 rules the saving was under 1 %. It helps much more when the terminals are
  the only thing that grows (see [`target_pruning.txt`](../examples/python/target_pruning.txt): 93 thousand strings instead of
  millions).
* *The cap `--max-nonterminals K` is a restriction.* A "not found" holds only within it, and `K` must be at least the largest number of
  non-terminals that a derivation of the word needs, or the derivation is cut. With a cap, a witness of 12 steps was found in 0.4 s
  with `K = 3` and in 237 s with `K = 6`: a larger cap costs a great deal of time.
* *Long derivations are out of reach.* Breadth first search stores every string of every step. In a search for an 88-step
  derivation the number of strings grew about 34 times per step and passed 38 million at step 5. Derivations of tens of steps are
  generally not found this way; the limits (`--max-history`, `--max-time`) make such a search stop with an honest "inconclusive".
* *Refine with a filter.* Knowledge of the model can prune further: non-terminals that no rule can delete, the first symbol under a
  left-context deletion, the gaps between terminals that are neighbours in the word. Write the test as a `keep` function declared pure
  and give it with `--python-filter`; [`target_pruning.py`](../examples/python/target_pruning.py) is a worked example, with the
  subsequence test and a cap written as a filter. A filter receives the strings as the real names of the symbols written together, so
  it can tokenize them only when that spelling reads in one way (a model with the symbols `a`, `b` and `ab` is ambiguous for it); the
  built-in search has no such limit. The filter is not checked by the program, so the answer is conditional on it, and the outcome
  says so.

## Limits

A limit stops the run with status 3 and a message that names the limit and the step. The step in progress is incomplete, so the result
must not be compared with an unlimited run; the state after the stop is the last completed step.

The names tell the scope: `step` in a name means that the count is per step (it starts again at every step); the others count over the
whole run.

| Option | What is counted |
| --- | --- |
| `--max-step-candidates N` | the candidates generated in one step. Generation is incremental while the limit is in force: a rule application stops at the first excess candidate instead of building the whole batch (a 2,000-character string with a rule whose left-hand side is empty allocates a few KB, not 4 MB) |
| `--max-history N` | every unique string inserted into the history, **including candidates rejected afterwards** (they occupy memory too), checked at the insertion; the initial history is checked as well |
| `--max-step-accepted N` | the strings accepted in one step, summed over **all** components |
| `--max-marks N` | the marks recorded (the marks of a streaming step are counted while pending) |
| `--max-retained N` | the strings kept for derivations ([Retained steps](#retained-steps)) |
| `--max-time T` | the elapsed time of the whole run, measured from the start of the program (reading the model is counted). `T` is a number of seconds, or a number with the suffix `s`, `m` or `h` (`90`, `90s`, `1.5m`, `2h`); anything else is an error. It is checked while the candidates of a step are generated and filtered, and between steps, so a long step does not overrun it much. A replay checks it between the steps, and a replay or a search whose time has passed never reports success: a search is `inconclusive`, a replay stops with status 3 after reporting the steps it had checked. A run that completed all its steps keeps status 0 |

There is one time limit for the whole run, not one per step.

Candidates are counted, and shown by `--progress`, with or without a limit.

## Memory and speed

Three things take memory in a run, and each has its own remedy:

| What takes memory | When it matters | What to do |
| --- | --- | --- |
| **The history**, the set of all the strings ever seen (it is how a string is never produced twice) | almost always; it grows with the run | `hash_history` for long strings; `--max-history` to stop before memory runs out |
| **The retained steps**, the content of every step, kept so that a derivation can be rebuilt | only when derivations are requested | `--retain-file` to keep them on disk; `--max-retained` to cap them |
| **The candidates of one step**, built before the filters run | steps with very many candidates | `--streaming`; `--max-step-candidates` to stop |

The limits are in [Limits](#limits) and the retained steps in [Retained steps](#retained-steps). As a guide to the size of the history:
on the largest benchmark (180,491 history entries, strings up to about 40 characters) the peak Python allocation was 28 MB, about 150
bytes per history entry. The rest of this section is about the three settings that change how the history and the candidates are
kept.

### Digests in the history: `hash_history`

`hash_history = true` (a setting in `[run]`, off by default) keeps a 128-bit digest of each string in the history instead of the string.

* **It saves memory only for long strings**, about 60 characters and more. On the `ins_b` model, with strings of about 25 characters, it
  saved nothing and was about 45 % slower.
* **It makes the test for duplicates probabilistic.** A collision has a probability far below 2^-60, but not zero, so such a run is
  outside the exactness guarantee of [checking.md](checking.md).
* **With `--retain-file`** the memory holds only the digests, and every link of a reported derivation is still checked exactly: the
  parent is found by applying the rules to the stored previous step and comparing whole strings. What a collision could still do is
  hide a new string as already seen, so that it is never generated; it cannot produce a wrong derivation.

### Strings rejected by the filters: `--no-mark-rejected`

By default a string rejected by a declarative filter (`filters`, `reject_strings`, the length limit) is still entered in the history, so
that it is not generated and tested again. `--no-mark-rejected` keeps such strings out of the history: the contents are the same and
the history is smaller, which helps heavily pruned runs, but a rejected string may be generated and tested again. Because it changes
the history, `--cross-check` refuses it.

### Filtering while generating: `--streaming`

Normally all the candidates of a step are built first and then filtered. `--streaming` filters each candidate as it is generated, so a
step with very many candidates never holds them all. It gives the same contents and works for every model; the declarative settings
(`filters`, `marks`, `reject_strings`, the length limits) need nothing special, because they depend only on the string they look at.

Streaming has one restriction that holds for every run, and one that concerns only runs with a Python filter function:

* **For every run:** the setting `show_detailed_application` (the detailed trace of every rule application) cannot be combined with
  streaming, because the trace would depend on the order of generation. The run is refused.
* **Only with a Python filter function:** it has to be declared *pure* (it depends on nothing but the string and the component), and it
  must not call `print`; see *With `--streaming`* in [python.md](python.md#with---streaming).

## Translating a Perl model

`gcrsim-convert OLD_MODEL [-o NEW_MODEL] [--source-encoding ENC]` translates a model of the Perl simulator, and the `.cfg` file that it
names, into the current notation. The new model goes to `NEW_MODEL` (the standard output by default) and the warnings to the standard error.
The files are read as `latin-1` unless `--source-encoding` says otherwise. [migration.md](migration.md) lists what changes.
