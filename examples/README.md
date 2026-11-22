# Examples

* [`cookbook/`](cookbook/) — one small model for each kind of grammar, with the grammar in the usual notation in the header comment.
  Explained in [docs/grammars.md](../docs/grammars.md); checked by `tests/test_cookbook.py`.
* [`features/`](features/) — small models that show one feature of the language, not a kind of grammar: marks that check a grammar
  ([docs/marks-and-derivations.md](../docs/marks-and-derivations.md)), multi-character symbols and classes, overlapping symbols, and ranges ([`features/ranges.txt`](features/ranges.txt) with indexed symbols and rules, [`features/ranges_components.txt`](features/ranges_components.txt) with the component numbers of a chain)
  ([docs/model-syntax.md](../docs/model-syntax.md)). Checked by `tests/test_cookbook.py`.
* [`python/`](python/) — models that come with a Python file (a function in a filter or in a mark, or the filter function `keep`):
  checking against an infinite language, a valence grammar with a gate (two ways), expected words read from a file, marking what a
  filter cuts, a beam, and the filter of a search for a word (the same pruning as the options of `--search`). Explained in
  [docs/python.md](../docs/python.md) and in [docs/grammars.md](../docs/grammars.md#examples-with-python); checked by
  `tests/test_python_examples.py`.
* [`real/`](real/) — the research models, written as insertions, deletions and substitutions. A line `# old: RULE` shows the original rule
  above its translation; `tests/test_real_examples.py` rebuilds the original model from those comments and checks that both give the
  same contents. The settings of a model are in the model file itself.

| Folder | Models | What they are |
| --- | --- | --- |
| [`real/LR/`](real/LR/) | `LR`, `LR_erase`, `LR_rot`, `LR_ab-c` | left-right insertion-deletion rules; the variants cover different stages of the derivation |
| [`real/mat_insdel/`](real/mat_insdel/) | `mat_insdel_110110a`, `_110200a`, `_110200b`, `_200110a` | matrix insertion-deletion systems of the given sizes; symbols with an index (`S1`, `R2`, `p1`, `C1`) are single symbols, declared in `[symbols]` |
| [`real/ins/`](real/ins/) | `ins222` | insertion-only system of size (2,2,2); every symbol is one character (the original already wrote K1 as `K` and K2 as `L`), so the rules insert up to two symbols |
| [`real/noncf110110/`](real/noncf110110/) | `noncf110110` | an insertion-deletion system of size 110110 that accepts a non-context-free language (the axiom is the input, the mark `accepted` reports acceptance); symbols of two or three characters (`a0`, `B1`, `X00`, `D01`, ...), declared in `[symbols]`; the filters of the original run are reduced to the limit on the identifiers (its `require` patterns made acceptance impossible, its `forbid` patterns only shrink the run) |
| [`real/rcanbncn/`](real/rcanbncn/) | `rcanbncn` | random-context grammar for a^n b^n c^n (plain rules with `permit` / `forbid`) |

A regular-expression rule with alternatives in its left context became several `ins` rules (one per alternative). Both forms give
the same candidates in the cases tested and the same contents, but on a string where several alternatives match at the same place
the candidates can appear in a different order.

Run a model with the installed program, `gcrsim MODEL STEPS`, or, from a checkout, with `python -m gcrsim MODEL STEPS`:

```
gcrsim examples/cookbook/08_matrix.txt 12
gcrsim examples/real/ins/ins222.txt 5
python -m gcrsim examples/cookbook/08_matrix.txt 12      # the same, from a checkout without installing
```
