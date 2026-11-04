# The step-by-step mode

`gcrsim MODEL -i` runs the model one step at a time. After each step it waits for a command, so you can look at the strings, search for
one, ask for its derivation, mark or remove a string, and decide when to go on. It works with the `text` format (the default) and the `perl` format, not with `csv` and `jsonl`.

```
gcrsim model.txt -i
```

The prompt shows the number of steps done (`step 3> `). An empty line (Enter) does the next step. The end of the input quits, so a
file of commands can be piped in: `gcrsim model.txt -i < commands.txt`.

## The commands

Components count from 1 in the commands, as in the listings. A string that contains spaces (symbols separated by spaces, see
[model-syntax.md](model-syntax.md)) is written in quotes: `mark 1 "p1 a" check`. Strings are written with the real symbol names.

| Command | Effect |
| --- | --- |
| Enter, or `n [K]` | do the next step, or `K` steps; each step is listed as in an ordinary run |
| `show [C]` | list the strings of the current step, of component `C` or of all, in the layout of the run (the print settings `print_hide` and `print_max_len` apply) |
| `find STRING` | for each component, the step in which the string appeared first, and whether it is in the current step |
| `trace STRING [C]` | the derivation of the string in component `C` (default 1), from the axiom |
| `marks` | the marks recorded so far |
| `mark C STRING LABEL` | mark a string of the current step by hand; it is recorded and printed like any other mark |
| `remove C STRING` | take a string out of the current step: it is not rewritten in the next step, but it stays in the history, so it is not produced again |
| `stats` | the counters: strings per component, candidates of the last step, strings in the history and retained, marks |
| `help` | the list of commands |
| `q` | quit |

A mistake in a command (an unknown command, a component out of range, a string that is not in the component) prints a message and
asks for the next command; it does not end the run.

## A session

The lines after a prompt, on the same line, are what was typed.

```
gcrsim 0.1.0.dev0   examples/cookbook/07_graph_controlled.txt
2 components, 2 rules

step 0
component 1
S

component 2

step 0> 
step 1
component 1
aSb

component 2
(empty word)

step 1> n 2
step 2
component 1
aaSbb

component 2
ab

step 3
component 1
aaaSbbb

component 2
aabb

step 3> find aaSbb
component 1: first at step 2; it is not in the current step
step 3> trace aabb 2
Trace of 'aabb' (component 2):
    step 1: S => aSb   (component 1 -> 1, rule at line 10: S->a S b,1, position 0)
    step 2: aSb => aaSbb   (component 1 -> 1, rule at line 10: S->a S b,1, position 1)
    step 3: aaSbb => aabb   (component 1 -> 2, rule at line 12: S->,2, position 2)
step 3> mark 1 aaaSbbb check
Mark (check): aaaSbbb
step 3> marks

Marks (1, 1 distinct):
  [check] component 1: aaaSbbb  (steps 3)
step 3> stats
step 3; strings per component: 1, 1
candidates of the last step: 2; strings in the history: 7; strings retained: 7; marks: 1
step 3> show 2
component 2
aabb

step 3> q

Marks (1, 1 distinct):
  [check] component 1: aaaSbbb  (steps 3)
  (run with --trace-marks to see how each was derived)
```

## What to know

* **The steps are retained.** To answer `find` and `trace`, the mode keeps the content of every step in memory, as `--trace-marks` does.
  For a long exploration with large steps use the ordinary run with `--retain-file` ([cli.md](cli.md)) and look into the file with
  `gcrsim-retention`.
* **Manual changes are part of the run.** A string taken out with `remove` is not rewritten in the next step, so the later steps no
  longer follow from the axioms alone, and a derivation requested afterwards does not know about the removal. A mark made by hand is
  attached to the step just completed.
* **The options still apply.** The limits stop the run as usual, and `--trace` and the stop options work between the steps.
  `--cross-check` compares every step as usual, so after a `remove` it reports a difference (status 5): the reference interpreter does
  not know about the removal.
