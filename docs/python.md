# The Python interface

The settings in the model file and in `--config` files are TOML, which is data only. Python is for what TOML cannot express: a
function that decides whether a string is fine, a set of expected strings that is read from a file or computed, a callback with
state. This page describes those two uses: the Python file given to `--python-filter`, and the `gcrsim` package used from Python
code. The declarative settings (`filters`, `marks`, `reject_strings`, ...) are in [configuration.md](configuration.md), and
marks in [marks-and-derivations.md](marks-and-derivations.md).

## The Python file (`--python-filter FILE.py`)

`gcrsim model.txt 20 --python-filter FILE.py` runs `FILE.py` and takes from it the settings and the filter function it defines.
**It executes code**, so use it only for files you trust. It is the fourth layer of the settings (after the defaults, the model
file and the `--config` files, before the command-line switches); a `.py` file is never a `--config` file, and a model can never
bring a function.

In the file the settings are plain Python names, without the TOML sections:

```python
# The settings with their default values. A setting that has no default, or whose default is "none", is commented out.
history = True                  # remember the strings seen, so that none is produced twice
print_hide = ""                 # regex: do not print matching strings (default: none)
# print_max_len = 100          # do not print longer strings (default: no limit)
reject_strings = ""             # regex: reject matching strings (default: none)
# reject_max_len = 100          # reject longer strings (default: no limit)
show_detailed_application = False
print_sep = ""                  # text put between a multi-character symbol and its neighbours, and between symbols that would read as another one, when printing (e.g. " ")
hash_history = False            # keep 128-bit digests instead of the strings in the history (see docs/cli.md, memory)
# steps = 20                    # the number of steps to run. There is no default: without it, and without a number on the
#                               # command line, the run needs -i (interactive); a number on the command line wins

def keep(s, component):         # the filter function; component is zero-based
    return "XX" not in s        # False rejects the string
```

The name `lit(text)` (`re.escape`) is available in the file without importing anything.

The filters and marks of the components are one dictionary named `components`, with the nesting of the TOML tables
`[model.components.N.filters]` and `[model.components.N.marks]` (`0` is every component):

```python
components = {
    0: {"filters": {"forbid": [r"(p.).*\1.*\1"], "max_count": {"D": 2, "K3": 1}}},   # every component
    1: {"marks": {"terminal": r"\A[$ABY]+\Z"}},                                       # component 1
    2: {"filters": {"max_count": {"b": 3}}},
}
```

The entries of the dictionary may hold functions: see [Functions in `components`](#functions-in-components).

## The filter function `keep`

`keep(s, component)` is called for every candidate string that passed the other filters, with the real symbol names; it returns
false to reject the string. The order of the filters is: duplicate (the string is marked as seen even if rejected later), length,
`reject_strings`, the filters of the component, then `keep`.

* `keep.pure = True` declares a function without state, which `--streaming` needs ([below](#with---streaming)).
* An exception raised by `keep` is reported as one message naming the file, the step, the component and the string (exit status 2),
  with the original traceback chained for debugging. The older name `filter_next` for the function is still accepted.

### With a context

A third parameter gives the function access to the run:

```python
def keep(s, component, ctx):
    if component == 0 and TERMINAL.match(s):
        ctx.mark("terminal")         # flag this string (even if the function then rejects it)
    return not BAD.search(s)

keep.pure = True                     # optional: allows --streaming
```

`ctx.mark(label)` is the only way to mark a string that is then rejected; the label is required. `ctx.report(text)` prints a
message line (in the baseline order, also with `--streaming`). `ctx.step` and `ctx.ncomp` are also available.

### With `--streaming`

`--streaming` ([cli.md](cli.md#filtering-while-generating---streaming)) filters each candidate as it is generated, so the function sees
the candidates in a different order, and the strings of different components are mixed. That is harmless only if its answer depends on
nothing but the string and the component: it keeps no state (no counter, no set of strings seen) and has no effects. Such a function
is called *pure*, and you declare it with `keep.pure = True`; for a function in `components` write `pure(lambda s: ...)`
(the name `pure` is available in a Python file without an import, like `lit`).

* A function that is not declared pure is refused with `--streaming`, whether it is `keep` or a function in the filters or marks of
  `components`; run it without the option.
* A pure function must not call `print`, because the order of its output would depend on the order of generation (it is an error).
  Use `ctx.report` for messages and `ctx.mark` for marks: both are committed in the usual order, so the mark records, the summaries and
  the derivations are identical to those of a run without streaming.

## Functions in `components`

`components` is the second place where code enters a run, next to the filter function `keep`. The two differ in what they see: `keep`
is called for every candidate of every component and has the context `ctx`, while an entry of `components` belongs to one component
and is tested only on the strings that arrive there. A function in `components` is cheaper and easier to read, and it needs no
test on the component number. In the Python file the entries can hold functions (lambdas) where the TOML tables can only hold data.

### Filters

An entry of `forbid` or `require` may be a function instead of a regular expression. It gets the string, with the real symbol names:

* a `forbid` function rejects the string when it returns true;
* a `require` function rejects the string when it returns false.

```python
components = {
    2: {"filters": {"require": [pure(lambda s: s.count("P") == s.count("M"))]}},     # a gate: only balanced words reach component 2
}
```

A function should depend only on the string, as the declarative filters do; with `--streaming` the order in which it sees the strings
changes, and a function with state would give other results. `pure(...)` declares that it has none (it is required for `--streaming`,
see [above](#with---streaming)). It can compare two counts, which no regular expression and no `max_count`
can. The valence grammar of [grammars.md](grammars.md#22-a-valence-grammar-with-a-gate-with-python) uses it as a gate in front of a clean-up loop.

### Marks

The entries of a mark are the same as in TOML (see [marks-and-derivations.md](marks-and-derivations.md)), with these additions:

* `expected` can be any collection of strings, for example one read from a file
  ([entry 23](grammars.md#23-expected-strings-read-from-a-file-with-python) reads twenty-one words):
  `EXPECTED = set(open("expected.txt").read().split("\n"))` and
  `components = {1: {"marks": {"unexpected": {"pattern": r"\A[ab]*\Z", "expected": EXPECTED}}}}`;
* `expected_re` can also hold functions, which return true for the strings that are fine, alone or in a list with regular expressions.
  This is how a grammar is checked against a language that is not regular
  ([entry 21](grammars.md#21-checking-against-an-infinite-language-with-python)):
  `pure(lambda s: s == "a" * (len(s) // 2) + "b" * (len(s) // 2))` accepts every `aⁿbⁿ`;
* `message` can be `None`, which records the mark and prints no line.

### Examples

Small examples, each a model and its Python file, are in [`examples/python/`](../examples/python/) and are described in
[grammars.md](grammars.md#examples-with-python). The models are grammars for `aⁿbⁿ` (with a deliberate mistake) and a valence grammar;
run each with `gcrsim MODEL STEPS --python-filter FILE.py`.

| Python file | What it shows |
| --- | --- |
| [`check_infinite.py`](../examples/python/check_infinite.py) | `expected_re` with a function: every terminal word must be some `aⁿbⁿ`, a language no regular expression describes; the wrong words are marked `unexpected` |
| [`check_from_file.py`](../examples/python/check_from_file.py) | `expected` read from a file: the same check against a list of words kept in [`expected_anbn.txt`](../examples/python/expected_anbn.txt) |
| [`valence.py`](../examples/python/valence.py) | a `require` function in the filters of a component: a word gets in only when its `P` and `M` weights are equal |
| [`valence_keep.py`](../examples/python/valence_keep.py) | the same gate as the filter function `keep`, which tests the component number itself (pure, so `--streaming` works) |
| [`mark_what_is_cut.py`](../examples/python/mark_what_is_cut.py) | `keep` with `ctx.mark`: words longer than 7 symbols are marked `too_long` and then rejected, so the run shows what the limit removed |
| [`beam.py`](../examples/python/beam.py) | `keep` with state: only the first 3 strings of each component are kept in each step; `--streaming` refuses it |

## The package

`import gcrsim` has no side effects: it reads no file and prints nothing. In the objects of the package **components count from 0**
(the listings of the command line add 1), and strings are given and returned with the real symbol names.

```python
import gcrsim

model = gcrsim.parse_model_file("model.txt")                    # or gcrsim.parse_model(text)
settings = gcrsim.settings.settings_for_model(model)            # the defaults and the model's own sections
sim = gcrsim.Simulator(model, settings, write=lambda text: None)
sim.run(5)                                                      # five steps
print(sim.strings())                                            # the strings of each component
for mark in sim.marks:
    print(mark.step, mark.component, mark.string, mark.label)
```

### The model

`parse_model(text, path="<string>")` and `parse_model_file(path)` return a `Model`; a mistake raises `ModelError`, whose message
starts with the file and the line. A `Model` has:

| Attribute | Content |
| --- | --- |
| `ncomp` | the number of components |
| `axioms` | the axioms of each component, as internal strings (a multi-character symbol is one character); `model.lexicon.decode(s)` gives the real names |
| `rules` | `rules[c]` is the list of the rules whose source is component `c` |
| `lexicon` | the symbols, classes and alphabet: `encode(text)`, `decode(text)`, `tokens(encoded)` (the list of symbols) |
| `config` | the settings that the model file carries |

A rule has `line`, `text` (the rule as written), `source` and `target` (components, from 0), and `expand(s)`, the list of the strings
it produces from `s` (as internal strings). `gcrsim.convert_model(perl_text)` returns `(new_text, warnings)` for a model of the
Perl simulator.

### The settings

`gcrsim.Settings()` holds the defaults; its attributes are the names of the Python file above (`history`, `reject_max_len`,
`print_sep`, `steps`, ...) and two dictionaries keyed by component, `filters` and `marks` (`0` is every component, other keys are
component numbers counted from 1). To build the settings the way the command line does:

* `gcrsim.settings.settings_for_model(model)` gives the defaults and the model's own sections;
* `gcrsim.resolve_config(model, ["exp1.toml", "exp2.toml"])` adds the `--config` files, in order (the argument may be one name, a
  list, or empty);
* `gcrsim.load_config(path, allow_python=True, model=None)` reads one file, a `.toml` or, if `allow_python` is true, a `.py` (which
  runs code);
* `gcrsim.apply_settings(settings, data, where)` applies a dictionary in the form of the Python file (`{"steps": 3, "components":
  {...}}`) over existing settings.

You can also set the attributes directly (`settings.reject_max_len = 40`, `settings.filters = {}`) before creating the simulator.

### The simulator

`gcrsim.Simulator(model, settings=None, *, write=None, streaming=False, retain=False, max_step_candidates=None, max_history=None,
max_step_accepted=None, max_retained=None, max_marks=None, trace_best_effort=False, no_mark_rejected=False)` builds the engine; the keyword
arguments are the options of the command line with the same names, and `write` receives the text that a run produces besides the
data (mark lines, `ctx.report` messages, the detailed applications). Without it the text goes to the standard output.

| Call or attribute | Meaning |
| --- | --- |
| `sim.step()` | one step; `sim.run(n)` does `n` steps |
| `sim.step_no` | the number of steps done |
| `sim.strings()` | the current strings of every component, as a list of lists |
| `sim.cur` | the same with the internal strings (faster, no decoding) |
| `sim.marks` | the marks recorded so far: `Mark` objects with `step`, `component`, `string`, `label` |
| `sim.add_mark(component, string, label)` | marks a string of the current content by hand, between two steps |
| `sim.remove(component, string)` | takes a string out of the current content; it is not rewritten in the next step, and it stays in the history |
| `sim.trace(string, component=0, step=None)` | the derivation of a string: a list of `DerivationStep` objects (`step`, `source`, `result`, `rule`, `start`, `end`, `source_component`, `target_component`); the simulator must be created with `retain=True` |
| `sim.find_step(component, string)` | the first step in which a string appeared (retention needed) |

`gcrsim.format_derivation(steps)` formats a derivation as the command line prints it. The counters `sim.last_candidates`,
`sim.hist_count` and `sim.retained_count` give the size of the last step, of the history and of the retained contents.

### Errors

All errors derive from `gcrsim.GcrsimError`, which has an `exit_code` (2; 3 for a limit). `ModelError` (the model, with `path` and
`line`), `ConfigError` (a setting or a configuration file), `TraceError` (a derivation that cannot be given), `CallbackError` (the
filter function raised) and `LimitReached` (a limit stopped the run, with `limit`, `value`, `step` and `counts`; the last step is
incomplete).

```python
try:
    sim.run(100)
except gcrsim.LimitReached as stop:
    print("stopped:", stop.limit, "at step", stop.step)
```

### The output of the command line

The header and the listing of the command line are not part of the simulator: `gcrsim.format_conf(contents, skip, max_len)` (`skip` is a function that
returns true for the strings to hide, or `None`) yields the text that lists the strings of the components as the `perl` format does, `gcrsim.digest_contents(hasher, step, contents)` feeds a step into a
hash with unambiguous framing (the tests of the comparison with the Perl simulator use it), and `gcrsim.main(argv)` runs the command
line from Python and returns its exit status.

Derivation sequences from the command line are in [marks-and-derivations.md](marks-and-derivations.md#from-python).
