# Changelog

All notable changes of each released version are listed here, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0]

### Added

* `--mode` selects the operation; `run` stays the default.
* `word_sep` (a setting; `--word-sep` for `--trace` and replay) separates the symbols of a typed word, as `print_sep` does when printing.
* Replay (`gcrsim MODEL --replay FILE`, or `gcrsim.replay` in Python): checks that a sequence of forms is a derivation of the model.
* Search (`gcrsim MODEL --search WORD`, or `gcrsim.search` in Python): a breadth-first search for a word that prints a shortest derivation, prunes by the terminals when that is sound, and ends with an explicit outcome (found, not found within its bounds, inconclusive; exit status 0, 6, 3).
* `--max-time T` (a limit of the elapsed time, in seconds or with the suffix `s`, `m`, `h`) in run, replay and search.
* The setting `terminals` in `[symbols]` declares the terminal symbols (used by the search; run and replay ignore it).
* Structured derivations: a step of `Simulator.trace` has the symbols of the string, the rule (kind, operands) and the edited part; `--format jsonl` writes a traced derivation as data, one object per step.
* Rule names: a clause `; name: NAME` on a rule line; the name is shown in traces, replay, search notes and the measures, and is the `name` of the rule in `--format jsonl` and in Python. The rule's text is its `notation` (`rule_notation` of a step). (`; name:` after the target is now a clause.)
* Measures of a derivation (steps, longest form, rule use, symbols created and deleted, non-terminals, forms per component): printed after every derivation, `measures` in `--format jsonl`, and `gcrsim.measure`, `Measures` in Python.

### Changed

* The message about a Perl configuration points to `docs/migration.md`.
* **Breaking:** in Python, `Rule.text` is `Rule.notation`.
* **Breaking:** the `--format jsonl` output changed: words are arrays of symbols (with a `_string` form as printed), one schema for every operation (`derivation` and `derivation_step` objects, `mode` in the header, `status` and `steps` in every `end`).

### Fixed

* With `print_sep` and multi-character symbols, headings, step numbers, rule texts and messages are no longer split by the separator.
* `--retain-file` refuses the model, a configuration file or the filter file as its destination (it could overwrite them).

## [0.1.1]

### Changed

* `gcrsim`, `gcrsim-convert` and `gcrsim-retention` started without their file argument show their help (exit status 2); `gcrsim` no
  longer asks for the name of the model.
* A missing model file is reported as `cannot read the model FILE: no such file`, in place of `Bad input filename: FILE !`.
* The message about a Perl configuration names the program `gcrsim`.
* The first model of the README is saved and run from its own file; the examples folder is not part of the installed package.
* The release workflow no longer sets up a cache in the upload job, which has no checkout (this removes a warning).

## [0.1.0]

First release of the Python version of gcrsim. It continues the [Perl simulator](https://github.com/sverlan/gcrsim-perl) with a
new, declarative model notation; models of the Perl version can be converted with `gcrsim-convert`
([docs/migration.md](docs/migration.md)).

### Added

* **The simulator.** Graph-controlled string rewriting: numbered components that hold strings, rules that rewrite a string and send
  the result to a component, insertion-deletion systems (`ins`, `del`, `sub`), plain rules `x->y`, regular-expression rules
  `re(...)`, and `send()`; conditions on a rule (`;permit:`, `;forbid:`, `;permit-any:`), classes of symbols, multi-character symbols,
  and the alphabet. The meaning of a step is in [docs/semantics.md](docs/semantics.md), and the exact specification of the plain
  fragment in [SPEC.md](SPEC.md).
* **The model file.** A TOML document with the rules in their own blocks: `[symbols]`, `[model]`, `[run]`, `[axioms]`, `[rules]`,
  `[rules.N]` ([docs/model-syntax.md](docs/model-syntax.md), [docs/configuration.md](docs/configuration.md)).
* **Filters and marks.** Per-component filters (`forbid`, `require`, `max_count` with symbols, classes and patterns), marks with
  expected strings or expected patterns, and derivations of marked strings
  ([docs/marks-and-derivations.md](docs/marks-and-derivations.md)).
* **Python.** A Python file (`--python-filter`) with a filter function `keep`, functions in the filters and marks of the components,
  and `pure(...)` for the functions that `--streaming` can use; the importable package `gcrsim`
  ([docs/python.md](docs/python.md)).
* **The command line.** Output formats `text`, `perl`, `csv` and `jsonl`, a step-by-step mode (`-i`), `--progress`, `--streaming`,
  limits on the size of a step, retention of the steps in memory or in a file, and `--cross-check`, which checks the plain
  fragment against a reference interpreter ([docs/cli.md](docs/cli.md), [docs/interactive.md](docs/interactive.md),
  [docs/checking.md](docs/checking.md)).
* **Tools.** `gcrsim-convert` (models of the Perl version to the new notation) and `gcrsim-retention` (summaries of kept steps).
* **Examples.** A cookbook with one small model for each kind of grammar, examples of single features, models with a Python file,
  and the research models in [`examples/`](examples/) ([docs/grammars.md](docs/grammars.md),
  [docs/grammar-types.md](docs/grammar-types.md)).
