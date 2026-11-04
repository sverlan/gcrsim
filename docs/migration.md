# Migrating from the Perl simulator

The model and configuration syntax is new. `gcrsim-convert OLD_MODEL -o NEW_MODEL` (or `gcrsim.convert_model(text)` from
Python) translates a Perl-era model and its `.cfg`; the settings of the configuration are written in the `[model]` and `[run]` sections of
`NEW_MODEL`. Rules the converter cannot translate are kept as `# not converted:` comments and listed as warnings.

The differential tests against `gcrsim.pl` 1.11 (they need Perl and are skipped without it) run the Perl-era fixtures through
the converter, so they also check the converter:

* 38 replacement/pattern cases (captures, `$`, `@`, quotes, backslashes, empty and zero-width matches);
* for four real models (`tests/fixtures/examples/`), the full ordered content of every component at every step is
  identical (hashed with unambiguous framing, up to depth 24/22/20/10), and the printed output is
  identical apart from the version, input and configuration lines of the header;
* callback message ordering and the detailed rule trace.

**Differences, on purpose:**

* A rule applies at *every* occurrence of its left-hand side, overlapping ones included. The Perl
  `s///g` skipped overlapping occurrences (`aa -> b` on `aaa` gave only `ba`). The converter warns about
  plain left-hand sides that can overlap themselves; on the four example models the contents are identical.
* The end anchor: Perl's `$` also matches before a final newline, the converted `\Z` does not. Model
  strings cannot contain newlines unless a `re(...)` right-hand side writes one (`\x0a`).
* `$` is a literal symbol in every pattern; anchors are `\A` and `\Z`. A Perl pattern's `$` anchor is
  rewritten to `\Z` in converted configurations.
* Python regular expressions: Perl-only syntax is not translated (`(?<n>..)` is reported by the converter).
* Text is UTF-8 with one code point per symbol; Perl read bytes.
* `show_detailed_application` prints every rule application that produced results. (The original printed an
  application only if the string differed from an internal substitution result containing match counts,
  so `1 -> a` on `1` was silently missing and `a -> a` was shown; that bug is not reproduced.)
* Python configurations replace Perl ones; a Perl `filter_next` is reported by the converter, not converted.
* Unsupported Perl right-hand side escapes (`\c`, `\N`, case escapes, `$0`, `@-`, `@+`, `@:`) are reported
  by the converter and the rule is kept as a comment.
* The early stop when all components are empty (`--run-empty` restores Perl's behaviour); an empty `print_hide` or
  `reject_strings` means "no skip" (Perl would silently reuse the previous pattern).

**Renamed settings.** The converter writes the new names: Perl `$add_skip` is `reject_strings`, `$add_skip_len` is `reject_max_len`,
`$print_skip` is `print_hide` and `$print_len` is `print_max_len`. `history` and `show_detailed_application` keep their names.
