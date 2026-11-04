# Configuration

Besides the model itself (symbols, axioms, rules), a run has *settings*: which strings to remember, which to reject, how many steps to
do, what to print. This page says where the settings are written, in what order they are combined, what each of them means, and how
the filters of a component are written.

## Where the settings are written

Settings are written in TOML, in two sections:

* **`[model]`** is what is simulated: the settings that change which strings exist (`history`, `reject_strings`, `reject_max_len`, the
  filters and the marks of the components).
* **`[run]`** is how the run is executed and shown: the settings that never change which strings are produced (`steps`, the print
  settings, `hash_history`).

```toml
[model]
reject_max_len = 100

[run]
steps = 20
print_max_len = 60
```

They can be written in the model file itself, so a model can carry its settings. A separate file given with `--config FILE` can change them
for one experiment (`gcrsim model.txt --config exp1.toml`). Such a file may hold `[model]` and `[run]` only; an unknown section or
setting is an error that names it. The section `[symbols]` (`alphabet` or `lexemes`, and `[symbols.classes]`) changes how the model
text is read, so it belongs to the model and a configuration file cannot hold it.

### The order of the layers

The settings come from these layers, a later one overriding an earlier one key by key:

1. the built-in defaults;
2. the model file's own `[model]` and `[run]`;
3. each file given with `--config` (repeatable: `--config base.toml --config exp1.toml`, later files win);
4. the Python file given with `--python-filter`, if any ([python.md](python.md));
5. command-line switches (`--print-all`, the number of steps after the model, and so on; see [cli.md](cli.md)).

The header of a run lists the layers that were used (`settings: model + exp1.toml`). The filters and the marks of the components are merged by
component number: a layer that sets component 1 replaces the earlier entry for component 1 and leaves the other components alone. A model
can never bring a function (that is the job of the Python file), and an unknown setting is an error, not ignored.

## The settings

### In `[model]`

| Setting | Default | Meaning |
| --- | --- | --- |
| `description` | none | free text, shown in the header of a run |
| `history` | `true` | remember the strings seen, so that none is produced twice. Without it a string can be produced again in a later step |
| `derivation` | `"any"` | the kind of derivation; only `"any"` is supported |
| `reject_strings` | none | a regular expression; a string in which it is found is rejected |
| `reject_max_len` | no limit | a longer string is rejected |
| `[model.components.N.filters]` | none | conditions on the strings of component `N` ([below](#the-filters-of-a-component)) |
| `[model.components.N.marks]` | none | marks for component `N` ([marks-and-derivations.md](marks-and-derivations.md)) |

### In `[run]`

| Setting | Default | Meaning |
| --- | --- | --- |
| `steps` | none | the number of steps to run. There is no default: without it, and without a number on the command line, the run needs `-i`. A number on the command line wins |
| `print_hide` | none | a regular expression; matching strings are not listed (they stay in the run) |
| `print_max_len` | no limit | longer strings are not listed |
| `print_sep` | none | text put between a multi-character symbol and its neighbours, and between symbols that would read as another one, when printing (for example `" "`) |
| `show_detailed_application` | `false` | print a line for every rule application that produced results |
| `hash_history` | `false` | keep 128-bit digests instead of the strings in the history ([cli.md](cli.md)) |

### The order of the filters

A candidate string passes these filters in this order, and the first one that rejects it decides: the history (a string already seen is
dropped; a string is marked as seen even if a later filter rejects it), `reject_max_len`, `reject_strings`, the filters of the
component, and finally the Python filter function, if there is one. A string that passes all of them is *accepted*, and only accepted
strings are marked.

## The filters of a component

The filters of a component are conditions on the *results*: every string that arrives in component `N`, whichever rule produced it, is
tested, and rejected if it fails. They are written in `[model.components.N.filters]` (`N` is the component number, counted from 1; `0`
or `all` means every component). They are not the conditions of a rule: `;permit:` and `;forbid:` in a rule say when that rule may be
applied, to the string before the rewriting, with literal words ([model-syntax.md](model-syntax.md)). The filters use regular
expressions and counts, and apply to all the rules at once.

| Key | Value | A string is rejected when |
| --- | --- | --- |
| `forbid` | a list of regular expressions | any of them is found in it |
| `require` | a list of regular expressions | one of them is not found in it |
| `max_count` | a dictionary, see below | a symbol, a class or a token occurs more than its limit |

```toml
[model.components.0.filters]               # every component
forbid = ['(p.).*\1.*\1']                  # no pointer symbol three times

[model.components.3.filters]               # component 3
require = ['XQ|PQ']

[model.components.5.filters]
max_count = { D = 2, K3 = 1 }              # at most 2 D and at most 1 K3

[model.components.7.filters]
max_count.class.N = 2                      # the symbols of the class N together at most twice

[model.components.8.filters]
max_count = { a = 5, class.N = 2 }         # at most 5 a, and the symbols of the class N together at most twice

[model.components.6.filters]
max_count.re."p." = 2                      # every token matched by p. at most twice, each token separately
```

All the filters of a component together:

```toml
[model.components.1.filters]
forbid = ['XX', 'ab+c']                                  # none of these is found
require = ['\A[ab]']                                     # the string starts with a or b
max_count = { a = 5, class.N = 2, re."p." = 2 }          # at most 5 a; the class N together at most 2; each p-token at most 2
```

* **Regular expressions** are Python regular expressions, searched in the string. A multi-character symbol is one symbol in them.
* **`max_count`** limits occurrences. It is a dictionary whose keys are of three kinds, and one dictionary can mix them:
  `max_count = { a = 5, class.N = 2, re."p." = 2 }`.
  * `a = 5`: the symbol (or any given text) `a` occurs at most 5 times.
  * `class.N = 2`: the symbols of the class `N` (declared in `[symbols.classes]`) occur at most twice *together*. With it
    `max_count` bounds the index of a derivation: the index is the total number of nonterminals of a sentential form, so
    `max_count.class.N = 2` keeps only the words that have a derivation of index at most 2.
  * `re."p." = 2`: every token matched by the pattern occurs at most twice, *each token separately*. It is `max_count` for a family
    of tokens that need not be listed: `max_count = { p1 = 2, p2 = 2 }` limits the two given tokens, `re."p." = 2` each token of the form
    `p` followed by one symbol (`p1`, `p2`, `pa`, ...). The key is quoted because it holds a pattern (a pattern with a backslash is
    written in single quotes: `re.'p\d' = 2`), and a pattern that can match the empty string is refused.

  `re` and `class` look alike but do different things:

  * `re."pattern" = n` is a *shorthand for listing symbols*: every symbol matched by the pattern gets its own limit `n`. With the
    class `XY = "X00 Y10"`, the key `re."{XY}" = 1` is the same as `{ X00 = 1, Y10 = 1 }`: `X00` at most once and `Y10` at most
    once, so `X00Y10` is accepted and `X00X00` is refused. (A class name in braces stands for any member of the class, as in the
    rules.)
  * `class.XY = 1` is a *group*: the members are counted together, with one limit for the sum. `X00Y10` is refused, because it has
    two symbols of the class, and `X00` alone is accepted.

  For the limit 1 the first form is "no symbol of the family occurs twice" (the regular expression `'(X00|Y10).*\1'` in a `forbid`);
  the second is "at most one symbol of the family occurs".

  A number is a symbol and a table is `class` or `re`, so a symbol that is itself called `class` or `re` can still be counted
  (`re = 2`). `max_count` for a symbol is the fast replacement for a regular expression such as `(D.*){2}D` (about 8 times faster per
  string, because `str.count` replaces a backtracking search). The form `re` is the same as the regular expression `'(p.).*\1.*\1'`
  in a `forbid`, which is faster on short strings; the two can differ on overlapping tokens (`pp1p1p1`).
* The filters are validated when the run starts. With only declarative settings a run can use `--streaming` as it is ([cli.md](cli.md)).

### Shortcuts

Two of the tables have a shorter name, because they are what real models almost always need:

* `[model.filters]` is an alias for `[model.components.0.filters]`, the filters of every component;
* `[model.marks]` is an alias for `[model.components.1.marks]`, the marks of component 1 (the component that holds the terminal strings
  in most models).

```toml
[model.filters]                            # the same as [model.components.0.filters]
forbid = ['(p.).*\1.*\1']

[model.marks]                              # the same as [model.components.1.marks]
terminal = '\A[ab]*\Z'
```

Writing an alias and the numbered table for the same component, for example `[model.filters]` and `[model.components.0.filters]`, is an
error. The other components always use the full form.

## Writing TOML

TOML is a small format, and a few points matter here.

### Tables and dictionaries

A dictionary is called a *table* in TOML, and the documentation uses both words. `[model.components.1.marks]` is a table (a section of
the file), and `{ pattern = '\Aab\Z', message = "found" }` is an inline table (a dictionary written on one line).

### Several ways to write the same thing

TOML offers several spellings of the same value, and gcrsim accepts all of them. These four set the same limit, "at most 2 `A`" in
every component (the first is the one used in this documentation):

```toml
[model.components.0.filters]
max_count = { A = 2 }                      # a table and an inline table
```

```toml
[model.components.0.filters]
max_count.A = 2                            # a table and a dotted key
```

```toml
[model.components.0.filters.max_count]     # a sub-table
A = 2
```

```toml
[model]
components.0.filters.max_count.A = 2       # dotted keys only, written directly under [model]
```

One rule of TOML to remember: a dotted key belongs to the table of the last header above it, which is why the last form is written under
`[model]`. A table cannot be declared twice, nor a key set twice; the parser reports both with the line.

### Single and double quotes

TOML has two kinds of strings, and the documentation uses both on purpose:

* `'single quotes'` make a *literal* string: the characters are taken exactly as written, with no escapes, so a backslash stays a
  backslash. This is the one to use for regular expressions: `'\A[ab]*\Z'`. A literal string cannot contain a single quote.
* `"double quotes"` make a *basic* string, in which a backslash starts an escape (`\n`, `\"`, `\\`, `\uXXXX`). Use it for ordinary text,
  such as a `description`, a `message` or a list of symbols, and when the text itself contains a single quote. A regular expression in
  double quotes has to double each backslash: `"\\A[ab]*\\Z"` is the same string as `'\A[ab]*\Z'`.

Both give the same kind of value, so choose the one that needs fewer escapes. (The rule lines of a model are not TOML strings: they have
no quotes. The axioms are TOML strings, written in double quotes in this documentation.)
