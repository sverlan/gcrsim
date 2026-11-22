# A filter that makes a breadth-first search aim at a target word: it drops the strings that can no longer become the target.
# Settings first; change them to search for another word (the file reads the symbols from target_pruning.txt, next to it).
TARGET = "abbabaababbaabbaba"      # the word to search for
TERMINALS = "a b"                  # the terminal symbols of the model, separated by white space
MAX_NONTERMINALS = None            # K: drop the strings with more than K non-terminals (None: no limit); see below

# What it does. The terminals of TARGET, in order, are its projection. If no rule deletes or rewrites a terminal, the terminals of a
# string never disappear and never change places: they stay in order, and new terminals can only be inserted between them. So a
# string whose terminals are not a subsequence of the projection of TARGET can never become TARGET, and it is safe to drop it.
# That is sound pruning: the answer of the search does not change, only the work does. It holds only under that condition on the rules
# (here: no rule deletes or rewrites a, b; the only deletion removes S, which is not a terminal). Check it for your model: a rule that
# deletes a terminal, or a class, {any} or a regular expression in the part a rule replaces, breaks it or hides it.
#
# MAX_NONTERMINALS is different: it is a restriction, not sound pruning. A string with many non-terminals may still be needed for a
# derivation, so with a limit K a "not found" holds only within it, and K must be at least the largest number of non-terminals that
# the derivation needs (the search then finds it quickly; a larger K only costs time). Use it on purpose, and say so when you report it.
# K applies to the strings that are derived, not to the axioms: an axiom with more than K non-terminals is still rewritten.
#
# Two limits of a filter written like this one. It receives the strings with the real names of the symbols written together, so it can
# tokenize them only when that spelling reads in one way: a model whose symbols include a, b and ab cannot be told apart from a b (the
# call to encode below then raises an error or reads the wrong symbols). The built-in search has no such limit, since it works on the
# symbols themselves. And the filter must be declared pure (keep.pure = True, as at the end): the search then keeps its own pruning on;
# with a filter that is not declared pure the search switches its pruning off and says so, because a filter with state can accept a
# string or not depending on which strings it has seen before, and pruning changes that.
#
# The built-in search does the same, without this file:
#   gcrsim target_pruning.txt --search abbabaababbaabbaba --max-nonterminals K
# takes the terminals from the setting `terminals` of the model (or --terminals "a b"), checks the condition on the rules for you and
# switches the pruning off, saying why, when it does not hold. Use a file like this one to go further: with --search the built-in
# pruning runs first and then keep, so keep can add tests of its own (repeating the subsequence test is harmless); a "not found" is
# then conditional on the filter, and the outcome says so.
#
# A refinement that needs knowledge of the model, written as a comment because it does not hold in general: a non-terminal that no
# rule can delete and that TARGET does not contain can never disappear, so a string that holds one can be dropped. Here is the test
# for a set of such symbols (none in this model):
#   UNDELETABLE = set()
#   if UNDELETABLE.intersection(symbols): return False
import os

import gcrsim

_lexicon = gcrsim.parse_model_file(os.path.join(os.path.dirname(os.path.abspath(__file__)), "target_pruning.txt")).lexicon
_terminals = {_lexicon.encode(name) for name in TERMINALS.split()}
# the strings are cut into symbols with the lexicon of the model: in the internal form every symbol, a multi-character one too, is
# one character (a greedy regular expression would cut symbols that have a common beginning in the wrong places)
_projection = [ch for ch in _lexicon.encode(TARGET) if ch in _terminals]


def keep(s, component):
    symbols = _lexicon.encode(s)       # s is written with the real names of the symbols; one character per symbol now
    projection = [ch for ch in symbols if ch in _terminals]
    if MAX_NONTERMINALS is not None and len(symbols) - len(projection) > MAX_NONTERMINALS:
        return False
    rest = iter(_projection)
    return all(ch in rest for ch in projection)      # a subsequence: each symbol is looked for after the previous one


keep.pure = True      # no state: --streaming can be used
