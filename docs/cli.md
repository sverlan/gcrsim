# The command line

```
gcrsim MODEL [STEPS] [options]
```

runs the model in the file `MODEL` for `STEPS` steps and lists the strings of every step. From a checkout, `python -m gcrsim` does the
same. `gcrsim --help` lists all the options, and this page explains them, grouped by purpose. Two other programs are installed with
the package: `gcrsim-convert`, which translates a model of the Perl simulator ([migration.md](migration.md)), and `gcrsim-retention`,
which reads a file written with `--retain-file` ([Retained steps](#retained-steps)).

Exit statuses:

| Status | Meaning |
| --- | --- |
| 0 | the run completed |
| 2 | an error in the model, a setting or the arguments (the message names the file and the line) |
| 3 | a limit stopped the run ([Limits](#limits)) |
| 4 | `--fail-on-mark` found a mark with a failing label |
| 5 | `--cross-check` found a difference between the engine and the reference interpreter |
| 130 | interrupted |

## Running

* **The number of steps.** `STEPS` is a number, or the setting `steps` of the model or of a `--config` file. There is no default: with
  neither, the run is refused with a message. A number on the command line wins over the setting.
* **Step by step.** `-i` (`--interactive`) lists the initial strings and then waits for a command after each step: Enter for the next
  step, and commands to look at the strings, find one, trace it, mark or remove a string, or quit; see
  [interactive.md](interactive.md). It cannot be combined with `STEPS` or with the formats `csv` and `jsonl`.
* **The model file.** If `MODEL` is omitted, the program asks for the name.
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

One JSON object per line (JSON Lines), with a field `type`:

```
{"type": "header", "version": "0.1.0.dev0", "model": "examples/cookbook/07_graph_controlled.txt", "configuration": "model", "description": ""}
{"type": "step", "step": 0, "components": [["S"], []]}
{"type": "step", "step": 1, "components": [["aSb"], [""]]}
{"type": "end", "steps": 1, "status": 0}
```

The `header` object describes the run (the `description` is the one of the model, if it has any), each `step` object holds the strings of
all the components of one step, `message` objects carry the text of marks, derivations and callbacks, and the final `end` object gives the
number of steps and the exit status. A reader keeps the complete lines and drops a last line that does not parse; a missing `end` means
that the run was interrupted.

## Marks and derivations

A mark flags a string ([marks-and-derivations.md](marks-and-derivations.md)); a derivation is the list of rule applications that leads
from an axiom to a string. These options ask for them:

| Option | Effect |
| --- | --- |
| `--trace STRING` | print the derivation of `STRING` when it first appears; `--component N` says in which component (default 1) |
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
    step 1: S => aSb   (component 1 -> 1, rule at line 10: S->a S b,1, position 0)
    step 2: aSb => aaSbb   (component 1 -> 1, rule at line 10: S->a S b,1, position 1)
    step 3: aaSbb => aabb   (component 1 -> 2, rule at line 12: S->,2, position 2)
```

Each line gives the step, the string before and after, the components, the rule (its line in the model file and its text) and the
position of the rewritten part. Nothing is recorded for this during an ordinary run. When a derivation is requested, the simulator
keeps the accepted content of each step (references to the strings that the history holds anyway, about 8 bytes per string) and
rebuilds the derivation backwards by applying the rules again to the previous content, in the original generation order. The result is
the chain of the first discovery, which is a shortest derivation. Several marked strings are traced together, in one pass per level.

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
