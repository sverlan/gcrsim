# How the results are checked

The *plain fragment* is the part of the language without regular expressions: plain rules, `ins`/`del`/`sub`, `send()`,
`permit`/`forbid`/`permit-any` words, components, the history and the length filter. It has a precise specification, [SPEC.md](../SPEC.md).
The specification starts from sequences of symbols; how model *text* becomes symbols (lexemes, classes, the alphabet, longest-match
tokenisation) is outside it and is tested separately.

## What exists

* **An independent reference interpreter** (`gcrsim/_reference.py`), written from SPEC.md alone by a different author without access
  to the engine. It uses no regular expressions and works on tuples of symbols.
* **Differential tests.** The engine is compared with it on: every `sub` rule with operands of up to one item over a small alphabet
  (one lexeme, two classes, `{any}`, `{start}`, `{end}`) on every string up to length four, edit by edit and candidate by candidate;
  hand-picked two-item operand shapes; guards and `send()`; and seeded random multi-component models step by step (contents in
  order, candidate counts, history on and off, length limit), written in every surface form (`plain`, `ins`, `del`, `sub`, numbered
  and general `[rules]` sections, optional prefixes and targets) and run in the default, the streaming and the candidate-limit
  paths. Overlapping lexemes are checked against a separate tokeniser.
* **`--cross-check`.** `gcrsim model.txt 20 --cross-check` runs the reference next to the engine on your model, compares the
  contents and the number of candidates after every step, and stops with exit status 5 at the first difference. It refuses models
  outside the fragment (regular-expression rules, `reject_strings`, `filters`, filter functions, `--no-mark-rejected`).
* **The cookbook and the real examples.** `tests/test_cookbook.py` checks that each cookbook model generates the language its header
  states; `tests/test_real_examples.py` checks that each research model, rebuilt from its `# old:` comments, gives the same
  contents as the ins/del/sub version, and runs `--cross-check` on those without regular expressions.

## What this means

These are evidence, not a proof of correctness for all models: they show agreement between two independent readings of the
specification on the cases they cover, and on the run `--cross-check` executes.

Not covered by the reference: regular-expression rules (ordinary tests only), marks, the detailed rule trace, `trace_many` and the
printed output. `--cross-check` re-executes the rules the engine parsed; it does not read the model text a second time, so a parsing
mistake is not caught by it (the parser has its own tests).

The setting `hash_history` (off by default) replaces the exact duplicate test by a test on 128-bit digests; a run that uses it is
outside the guarantee above (a collision is extremely unlikely, not impossible).

Regular expressions have a known cost: a pathological pattern can take very long. Use `--max-step-candidates` and the other limits when
experimenting.
