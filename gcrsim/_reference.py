"""Independent reference interpreter for the plain fragment, written from SPEC.md.

It was written by a different author (Codex, from the text of SPEC.md alone, without access to the
engine) and is used by the tests and by ``--cross-check`` to check the engine.  It uses no regular
expressions and works on tuples of symbols; clarity matters more than speed.
"""
# reference.py
from typing import NamedTuple


START = object()
END = object()
ANY = object()


class Rule(NamedTuple):
    kind: str
    source: int
    target: int
    u: tuple = ()
    x: tuple = ()  # items that are matched and replaced
    y: tuple = ()  # the string that replaces them
    v: tuple = ()
    permit: tuple = ()
    forbid: tuple = ()
    permit_any: tuple = ()


def _validate_rule(rule):
    if rule.kind not in ("sub", "send"):
        raise ValueError("rule kind must be 'sub' or 'send'")
    for word in rule.permit + rule.forbid + rule.permit_any:
        if len(word) == 0:
            raise ValueError("permit and forbid words must be non-empty")


def _occurs(word, s):
    for i in range(len(s) - len(word) + 1):
        if s[i:i + len(word)] == word:
            return True
    return False


def _match(items, s, pos):
    """Return the final cursor, or None on failure."""
    for item in items:
        if item is START:
            if pos != 0:
                return None
        elif item is END:
            if pos != len(s):
                return None
        else:
            if pos == len(s):
                return None
            if item is ANY:
                pass
            elif isinstance(item, frozenset):
                if s[pos] not in item:
                    return None
            elif s[pos] != item:
                return None
            pos += 1
    return pos


def edits(rule, s):
    _validate_rule(rule)

    for word in rule.permit:
        if not _occurs(word, s):
            return []
    for word in rule.forbid:
        if _occurs(word, s):
            return []
    if rule.permit_any and not any(_occurs(word, s) for word in rule.permit_any):
        return []

    if rule.kind == "send":
        return [(0, 0, ())]

    result = []
    for i in range(len(s) + 1):
        p = _match(rule.u, s, i)
        if p is None:
            continue
        q = _match(rule.x, s, p)
        if q is None:
            continue
        if _match(rule.v, s, q) is None:
            continue
        result.append((p, q, rule.y))
    return result


def candidates(rule, s):
    return [
        s[:p] + replacement + s[q:]
        for p, q, replacement in edits(rule, s)
    ]


def step(contents, history, rules, use_history, max_len):
    rules = tuple(rules)
    for rule in rules:
        _validate_rule(rule)

    if use_history:
        if history is None or any(h is None for h in history):
            raise ValueError("history must contain a set for each component")
        new_history = [set(h) for h in history]
    else:
        new_history = None

    raw_candidates = [[] for _ in contents]
    for c, content in enumerate(contents):
        for s in content:
            for rule in rules:
                if rule.source == c:
                    raw_candidates[rule.target].extend(candidates(rule, s))

    new_contents = [[] for _ in contents]
    for target, generated in enumerate(raw_candidates):
        seen = new_history[target] if use_history else set()
        for word in generated:
            if word in seen:
                continue
            seen.add(word)
            if max_len is not None and len(word) > max_len:
                continue
            new_contents[target].append(word)

    raw_candidate_count = sum(len(words) for words in raw_candidates)
    return new_contents, new_history, raw_candidate_count


def run(axioms, rules, steps, use_history=True, max_len=None):
    if steps < 0:
        raise ValueError("steps must be non-negative")

    rules = tuple(rules)
    for rule in rules:
        _validate_rule(rule)

    contents = [list(content) for content in axioms]
    history = [set(content) for content in contents] if use_history else None
    result = [{"contents": contents, "raw": 0}]

    for _ in range(steps):
        contents, history, raw = step(
            contents, history, rules, use_history, max_len
        )
        result.append({"contents": contents, "raw": raw})

    return result
