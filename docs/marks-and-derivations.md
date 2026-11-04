# Marks and derivation sequences

Two tools answer the questions that come after a run: *which of the strings I generated are the ones I care about?* (marks) and *how
was this string derived?* (derivation sequences, also called trace-back).

## Marks

A mark flags a string that has passed every filter (it is new in its component, short enough, and accepted by the other settings).
The simulator records it (step, component, string, label), prints a line when it appears, and lists all marks at the end of the run.

A mark is declared in the settings: in the model file, or in a file given with `--config FILE`, the section
`[model.components.N.marks]` (a table, in TOML terms) is named by the component number, `0` meaning every component:

```toml
[model.components.1.marks]                  # component 1
terminal = '\A[ab]*\Z'                      # label = regular expression (the whole string is a, b only)
unexpected = { pattern = '\A[ab]*\Z', expected = ["", "ab", "aabb"] }   # marked unless it is one of the expected strings

[model.components.0.marks]                  # every component
seen_x = ['X1', 'X2']                       # several patterns, one label
found = { pattern = '\Aab\Z', message = "found {string} in component {component} at step {step}" }
```

**Shortcut.** `[model.marks]` is an alias for `[model.components.1.marks]`: the marks of component 1, which holds the terminal strings in
most models. The two spellings mean exactly the same, and using both for component 1 is an error:

```toml
[model.marks]                               # the same as [model.components.1.marks]
terminal = '\A[ab]*\Z'
```

The key of each entry is the **label** of the mark. The value has three forms:

| Value | Meaning |
| --- | --- |
| a string `'regex'` | a string of the component is marked when the regular expression is found in it |
| a list `['regex1', 'regex2']` | marked when any of the regular expressions is found |
| a dictionary `{ pattern = ..., expected = ..., expected_re = ..., message = ... }` (an inline table, in TOML terms) | the same, with the options below |

The regular expressions are Python regular expressions (written in single quotes, which keep the backslashes as they are; see
*Single and double quotes* in [configuration.md](configuration.md)), *searched* in the string: use `\A` and `\Z` for the ends (`$` is a literal
symbol). A multi-character symbol declared in the model is one symbol in a pattern.

The keys of the dictionary form:

| Key | Value | Meaning |
| --- | --- | --- |
| `pattern` | a regular expression, or a list of them | required; the strings to consider |
| `expected` | a list of strings (Python: any collection of strings) | the strings that are *fine*: a string equal to one of them is not marked. They are exact strings, **not** regular expressions |
| `expected_re` | a regular expression, or a list of them (Python: also functions) | the strings that are fine, by rule: a string is not marked when one regular expression is found in it, or a function returns true for it |
| `message` | a template string | replaces the default line; the fields are `{string}`, `{component}`, `{step}` and `{label}` (Python: `None` records the mark and prints no line) |

Marks have a Python interface as well, with a few more possibilities (the Python entries in the table, and `ctx.mark(label)` in a
callback, which marks a string even when the callback then rejects it); it is described in [python.md](python.md).

The default line is `Mark (LABEL): STRING` for every label. `expected` and `expected_re` can be combined, and either one saves the string.
A regular expression for the strings that are fine goes in `expected_re` (`expected` holds exact strings only), which is also the way to
describe an infinite language.

This is how a grammar is checked: mark every terminal string and list the ones you expect, then everything that is marked is a
deviation. The tables are part of the model file (as in the cookbook example below), so a model carries its own marks.

```toml
[model.components.1.marks]
# every terminal string is marked, except these three exact strings and except any power of ab:
deviation = { pattern = '\A[ab]*\Z', expected = ["", "ab", "aabb"], expected_re = '\A(?:ab)*\Z' }
```

### Checking a grammar: an example

[`examples/features/checking_an_bn.txt`](../examples/features/checking_an_bn.txt) is meant to generate `{ a^n b^n : n <= 4 }` but has an extra rule `S -> bSa`. Its
`[model.components.1.marks]` table lists the expected strings; every other terminal string is marked `unexpected`:

```toml
[model.components.1.marks]
unexpected = { pattern = '\A[ab]*\Z', expected = ["", "ab", "aabb", "aaabbb", "aaaabbbb"] }
```

```
gcrsim examples/features/checking_an_bn.txt 5
```

```
STEP 2
Mark (unexpected): ba
...
```

Useful options:

| Option | Effect |
| --- | --- |
| `--fail-on-mark LABEL` | exit with status 4 if a mark with this label was recorded (`*` = any label); for scripts |
| `--stop-on-mark-label LABEL` | stop at the end of the step that produced the first such mark |
| `--no-mark-summary` | do not print the list of marks at the end |
| `--max-marks N` | stop (status 3) after N marks |

## Derivation sequences

A derivation sequence is the list of rule applications that leads from an axiom to a string. gcrsim can print it for one string you
name, or for every marked string.

### For one string

```
gcrsim examples/cookbook/08_matrix.txt 12 --quiet --trace aabbcc --component 8
```

```
Trace of 'aabbcc' (component 8), first appearing at step 9:
    step 1: S => ABC   (component 1 -> 1, rule at line 9: S->ABC,1, position 0)
    step 2: ABC => ABC   (component 1 -> 2, rule at line 10: send(),2, position 0)
    step 3: ABC => aABC   (component 2 -> 3, rule at line 13: A->aA,3, position 0)
    step 4: aABC => aAbBC   (component 3 -> 4, rule at line 15: B->bB,4, position 2)
    step 5: aAbBC => aAbBcC   (component 4 -> 1, rule at line 17: C->cC,1, position 4)
    step 6: aAbBcC => aAbBcC   (component 1 -> 5, rule at line 11: send(),5, position 0)
    step 7: aAbBcC => aabBcC   (component 5 -> 6, rule at line 19: A->a,6, position 1)
    step 8: aabBcC => aabbcC   (component 6 -> 7, rule at line 21: B->b,7, position 3)
    step 9: aabbcC => aabbcc   (component 7 -> 8, rule at line 23: C->c,8, position 5)
```

Each line is one step: the string before and after, the components it moved between, the rule (with its line in the model file), and
the position where the rule applied. `--component N` says in which component to look (default 1). `--stop-on-found` stops the run
at the end of the step where the string appeared. The sequence is the one found first, so it is a shortest derivation.

### For every marked string

```
gcrsim examples/features/checking_an_bn.txt 5 --trace-mark-label unexpected
```

```
Mark [unexpected] at step 2, component 1: ba
    step 1: S => bSa   (component 1 -> 1, rule at line 8: S->bSa, position 0)
    step 2: bSa => ba   (component 1 -> 1, rule at line 9: S->, position 1)
```

`--trace-marks` prints the derivation of every mark; `--trace-mark-label LABEL` (repeatable) only of marks with that label.

### From Python

```python
sim = gcrsim.Simulator(model, settings, retain=True)       # retain the contents of every step
sim.run(12)
steps = sim.trace("aabbcc", component=7)                    # component numbers start at 0 here
for s in steps:
    print(s.step, s.source, "=>", s.result, s.rule)
```

### Cost and limits

The trace is rebuilt the way one would do it by hand from a dump of every step: take the string, look in the previous step for
the string and the rule that produced it, and repeat. gcrsim keeps the contents of all steps for this (in memory, or in an SQLite
file with `--retain-file FILE`) and finds each parent by applying the rules to the previous content.


Tracing keeps every step's content in memory. `--max-retained N` limits the number of retained strings; when the limit is reached
the run stops with status 3, or with `--trace-best-effort` it continues without tracing. The history (the strings seen) is kept with
or without tracing; `--max-history N` limits it.
