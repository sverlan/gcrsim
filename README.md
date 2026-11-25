# gcrsim

Graph Controlled string Rewriting SIMulator. It simulates the derivation of regulated rewriting systems, in particular
insertion-deletion systems with graph control: components (states) hold sets of strings, rules rewrite a string in one component
and send the result to another one, and the simulator advances all components synchronously, step by step.

**Main features**

* **Simulation of many variants of regulated rewriting and of insertion-deletion systems.** Graph-controlled, matrix, programmed,
  time-varying, random-context and ordered grammars, Marcus contextual grammars, evolutionary processors, networks of processors and
  insertion-deletion systems are all written with the same few rule forms (see [docs/grammar-types.md](docs/grammar-types.md)).
* **Catching wrong derivations and the stage where they happen.** *Marks* flag the strings you care about, for example every terminal
  string that is not in the language you intended, at the step and component where they appear. The *traceback* then prints the full
  derivation, rule by rule from the axiom, of any marked string or of any string you name (see
  [docs/marks-and-derivations.md](docs/marks-and-derivations.md)).

gcrsim is a complete rewrite, in Python, of the earlier Perl simulator of the same name, and its evolution: the model language is
new, the semantics are written down and checked against an independent reference interpreter, and it adds marks, derivation
sequences and resource limits. The Perl version is kept at [github.com/sverlan/gcrsim-perl](https://github.com/sverlan/gcrsim-perl);
models written for it are migrated with `gcrsim-convert`, see [docs/migration.md](docs/migration.md).

* a small package, standard library only, Python 3.11+;
* rule forms `ins`, `del`, `sub`, plain rules, `send()` and regular-expression rules, permitting / forbidding words, multi-character
  symbols and symbol classes, UTF-8;
* for the part of the language without regular expressions, a written specification, an independent reference interpreter,
  differential tests and `--cross-check` (see [docs/checking.md](docs/checking.md));
* for long experiments: declarative component conditions, resource limits, progress reporting, `csv` and `jsonl` output.

## Installation

Python 3.11 or later; there are no other dependencies. The package installs three programs: `gcrsim` (the simulator),
`gcrsim-convert` (migration of Perl-era models) and `gcrsim-retention` (look into a retention file).

```
pip install gcrsim                    # into the current environment
pipx install gcrsim                   # as an isolated command-line tool
uv tool install gcrsim                # the same, with uv
uvx gcrsim model.txt 10               # run the simulator once, without installing
```

## Running

```
gcrsim model.txt [steps]
python -m gcrsim model.txt [steps]      # the same, from a checkout of the repository without installing
gcrsim model.txt -i                   # run in the interactive mode (with a tui)
```

With `steps` (on the command line or in the configuration) the simulator runs that many steps and exits; with `-i` it waits for a command after each step (Enter for the next step, `q` to quit, more commands in [docs/interactive.md](docs/interactive.md)).

## A first model

A matrix grammar for aⁿbⁿcⁿ, a language that needs several components. A matrix is a chain of rules applied one after the other, so
each rule gets its own component; the first rules of all the matrices are in component 1, and the last rules of `m2` and `m3` return to it:

```
# matrix m1 = (S -> ABC), m2 = (A -> aA, B -> bB, C -> cC), m3 = (A -> a, B -> b, C -> c)
[axioms]
1 = ["S"]

[rules.1]
# m1 (one rule), and the first rules of m2 and m3
S -> A B C, 1
A -> a A, 2
A -> a, 4
# m2: B -> bB in component 2, C -> cC in component 3, then back to component 1
[rules.2]
B -> b B, 3
[rules.3]
C -> c C, 1
# m3: B -> b in component 4, C -> c in component 5, then back to component 1, where the word is
[rules.4]
B -> b, 5
[rules.5]
C -> c, 1
```

Save the model as `matrix.txt` and run `gcrsim matrix.txt 12`; it prints, at every step, the strings of each component; `abc`, `aabbcc`, ... appear
in component 1. The same model is in the repository as [`examples/cookbook/08_matrix_direct.txt`](examples/cookbook/08_matrix_direct.txt).

## Documentation

| Document | Content |
| --- | --- |
| [docs/model-syntax.md](docs/model-syntax.md) | the model language: sections, rule forms, conditions, symbols and classes |
| [docs/semantics.md](docs/semantics.md) | what a step does, in plain words (exact version: [SPEC.md](SPEC.md)) |
| [docs/grammars.md](docs/grammars.md) | cookbook: one example for each kind of grammar, in classical notation and as a model |
| [docs/grammar-types.md](docs/grammar-types.md) | the types of grammars and systems that are supported, and how each is written |
| [docs/configuration.md](docs/configuration.md) | settings, configuration files, the filters of the components |
| [docs/python.md](docs/python.md) | the Python interface: the filter file, callbacks, marks from Python, the package API |
| [docs/marks-and-derivations.md](docs/marks-and-derivations.md) | marking strings and getting the derivation sequence of a string |
| [docs/cli.md](docs/cli.md) | command line options, output, limits, exit statuses |
| [docs/interactive.md](docs/interactive.md) | the step-by-step mode (`-i`): looking at the strings, searching, tracing, marking |
| [docs/checking.md](docs/checking.md) | how the results are checked, `--cross-check` |
| [docs/migration.md](docs/migration.md) | moving from the Perl simulator, `gcrsim-convert` |
| [examples/](examples/README.md) | the cookbook models and the research models |

## Supported grammars

A summary; the full table, with one sentence on how each grammar is written, is in [docs/grammar-types.md](docs/grammar-types.md), and
[docs/grammars.md](docs/grammars.md) gives an example of each in the classical notation and as a model.

| Grammars and systems | How it is written |
| --- | --- |
| unrestricted, monotone, context-free and pure grammars; internal Marcus contextual grammars; insertion-deletion systems; evolutionary processors; graph-controlled grammars; random-context and semi-conditional grammars; grammars with derivations of bounded index | directly, with the rule forms |
| external Marcus contextual grammars; networks of evolutionary processors; matrix grammars and matrix insertion-deletion systems; appearance checking (failure fields) in graph-controlled and matrix grammars; programmed grammars; time-varying grammars; regular control; ordered grammars; counter and register machines | with a small encoding (components and `send()`) |
| scattered-context grammars | in part, with `re(...)`: exact when each symbol occurs once in the word |
| valence grammars | with a Python filter |
| parallel rewriting (L systems, ET0L), splicing and communicating grammar systems, leftmost and rightmost derivations, control by a pushdown automaton or a Petri net | not supported |

## Using gcrsim with AI agents

gcrsim comes with an agent skill: a `SKILL.md` file in the open Agent Skills format, for AI coding tools such as Claude Code
or Codex. It teaches an agent the model syntax, the limits to set so that a run does not exhaust the memory, and which
operation (describe, search, language listing, replay) answers which question. Install it in the skills folder of your tool,
in a folder named `gcrsim`:

```
# Claude Code, for one project (or ~/.claude/skills/gcrsim for every project)
mkdir -p .claude/skills/gcrsim
gcrsim --print-skill > .claude/skills/gcrsim/SKILL.md

# Codex and other tools that read .agents/skills, for one project (or ~/.codex/skills/gcrsim for every project)
mkdir -p .agents/skills/gcrsim
gcrsim --print-skill > .agents/skills/gcrsim/SKILL.md
```

Other tools have their own skills folder. The skill links to the documentation of the latest
release; see [docs/cli.md](docs/cli.md#using-gcrsim-with-ai-agents).

## How it is developed

The development is AI-assisted, and the work is shared between the human author and the AI. The plan is discussed and validated by
the human author. The AI implements the code and writes the tests; the human rereads the code. The examples are written by the AI
and the human together, and the results are verified by the human. Independent AI reviews of the plan and of the code were used as
an additional check; they do not replace the human steps. What the automatic checks do and do not guarantee is described in
[docs/checking.md](docs/checking.md).

## Development

```
uv run pytest                 # fast tests, plus the Perl comparisons when perl is on PATH
```

The Perl comparison tests use the original models and configurations in `tests/fixtures/perl`.
