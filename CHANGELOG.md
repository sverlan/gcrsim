# Changelog

All notable changes of each released version are listed here, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

* The continuous integration keeps one `uv` cache for each Python version (no more warning about a cache that is already being saved).
* The tests of the continuous integration run in parallel (`pytest-xdist`, now in the development dependencies).
* The message about a Perl configuration points to `docs/migration.md`.
* The test workflow runs on pushes to branches and on pull requests, not on a tag push: the release workflow runs the tests itself.

## [0.1.1] - 2026-11-04

### Changed

* `gcrsim`, `gcrsim-convert` and `gcrsim-retention` started without their file argument show their help (exit status 2); `gcrsim` no
  longer asks for the name of the model.
* A missing model file is reported as `cannot read the model FILE: no such file`, in place of `Bad input filename: FILE !`.
* The message about a Perl configuration names the program `gcrsim`.
* The first model of the README is saved and run from its own file; the examples folder is not part of the installed package.
* The release workflow no longer sets up a cache in the upload job, which has no checkout (this removes a warning).

## [0.1.0] - 2026-11-04

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
