"""The sections of the TOML part of a model file and of a configuration file.

``[symbols]`` (``alphabet`` or ``lexemes``, and ``[symbols.classes]``) says how the model text is read, so it only belongs to
a model; it also declares the ``terminals``, the symbols that a word of the language is made of (used by the search). ``[model]`` (``description``, ``history``, ``derivation``, ``reject_strings``, ``reject_max_len`` and the tables
``[model.components.N.filters]`` and ``[model.components.N.marks]``, with ``[model.filters]`` for every component and ``[model.marks]`` for component 1)
says what is simulated, and ``[run]`` (``steps``, ``print_*``,
``show_detailed_application``, ``hash_history``) how it is executed and shown. A configuration file may hold ``[model]`` and
``[run]`` only.
"""

from __future__ import annotations

from typing import Any, Dict

SYMBOL_KEYS = ("alphabet", "lexemes", "classes", "terminals", "ranges")
MODEL_KEYS = ("description", "history", "derivation", "reject_strings", "reject_max_len", "max_expanded_rules", "components", "filters", "marks")
RUN_KEYS = ("steps", "print_hide", "print_max_len", "print_sep", "word_sep", "show_detailed_application", "hash_history")
SECTIONS = {"symbols": SYMBOL_KEYS, "model": MODEL_KEYS, "run": RUN_KEYS}
_INTERNAL = {"lexemes": "symbols"}  # the name used inside the program for the multi-character symbols


FILTER_KEYS = ("forbid", "require", "max_count")


def header_words(head: str, parts: "list[str]") -> "list[str]":
    """The words after the first one of a section header, with the fixed words of the format in lower case
    (``[SYMBOLS.CLASSES]`` is ``[symbols.classes]``). Names chosen by the user (classes, ranges, mark labels, the symbols of
    ``max_count``) and component numbers keep their spelling. ``head`` is already in lower case."""
    out: "list[str]" = []
    path = [head]
    for word in parts:
        low = word.lower() if word[:1] not in "\"'" else word  # a quoted key is a name, never a fixed word
        n = len(path)
        fixed = ((n == 1 and low in SECTIONS.get(head, ()))
                 or (n == 2 and path == ["model", "components"] and low == "all")
                 or (n == 3 and path[:2] == ["model", "components"] and low in ("filters", "marks"))
                 or (path == ["model", "filters"] and low in FILTER_KEYS)
                 or (n == 4 and path[:2] == ["model", "components"] and path[3] == "filters" and low in FILTER_KEYS)
                 or (n >= 3 and path[-1] == "max_count" and path[-2] == "filters" and low in ("class", "re")))
        word = low if fixed else word
        out.append(word)
        path.append(word)
    return out


def section_of(key: str) -> str:
    """The section a setting belongs to, or ``""``."""
    for name, keys in SECTIONS.items():
        if key in keys:
            return name
    return ""


def flatten(doc: Dict[str, Any], where: str, from_model: bool, error: Any) -> Dict[str, Any]:
    """The settings of the TOML sections ``doc`` as one flat dictionary; ``error(message)`` raises the right exception."""
    out: Dict[str, Any] = {}
    where = where + ": " if where else ""
    for name, body in doc.items():
        if name == "config":
            error("%sthere is no [config] section: use [symbols] (alphabet, lexemes, classes), [model] and [run]" % where)
        if name not in SECTIONS:
            error("%sunknown section [%s] (the sections are [symbols], [model] and [run])" % (where, name))
        if name == "symbols" and not from_model:
            error("%s[symbols] belongs to the model: it changes how the model text is read, so a configuration file cannot hold it" % where)
        if not isinstance(body, dict):
            error("%s[%s] must be a table" % (where, name))
        for key, value in body.items():
            if key not in SECTIONS[name]:
                home = section_of(key)
                if home:
                    error("%s'%s' belongs in [%s], not in [%s]" % (where, key, home, name))
                error("%sunknown setting '%s' in [%s]" % (where, key, name))
            if key == "max_expanded_rules" and not from_model:
                error("%s'max_expanded_rules' is read when the model is loaded, so a configuration file cannot hold it" % where)
            if name == "model" and key in ("components", "filters", "marks"):
                continue  # the per-component tables, below
            out[_INTERNAL.get(key, key)] = value
        if name == "model":
            _components(body, where, out, error)
    if "symbols" in out and "alphabet" in out:
        error("%s`lexemes` and `alphabet` are exclusive: the alphabet already lists every symbol of the model, "
              "and its multi-character words are the multi-character symbols (remove `lexemes`)" % where)
    return out


def _component_number(key: Any) -> str:
    return "0" if key == "all" else str(key)


def _components(body: Dict[str, Any], where: str, out: Dict[str, Any], error: Any) -> None:
    """``[model.components.N.filters]`` and ``[model.components.N.marks]`` (``0`` or ``all``: every component) as the nested
    dictionary ``components``; ``[model.filters]`` is the filters of every component (``0``) and ``[model.marks]`` the marks of
    component 1, the two cases that real models almost always mean."""
    comps: Dict[str, Dict[str, Any]] = {}
    for key, home in (("filters", "0"), ("marks", "1")):
        if key in body:
            if not isinstance(body[key], dict):
                error("%s[model.%s] must be a table" % (where, key))
            comps.setdefault(home, {})[key] = body[key]
    given = body.get("components", {})
    if not isinstance(given, dict):
        error("%s[model.components] must be a table of component numbers" % where)
    for number, entry in given.items():
        if not (number == "all" or number.isdigit()):
            error("%s[model.components.%s]: a component is a number (0 or all: every component)" % (where, number))
        if not isinstance(entry, dict):
            error("%s[model.components.%s] must be a table" % (where, number))
        n = _component_number(number)
        for kind, table in entry.items():
            if kind not in ("filters", "marks"):
                error("%sunknown setting '%s' in [model.components.%s] (it has filters and marks)" % (where, kind, number))
            if kind in comps.get(n, {}):
                error("%scomponent %s has its %s twice (in [model.%s] and in [model.components.%s.%s])" % (where, n, kind, kind, number, kind))
            comps.setdefault(n, {})[kind] = table
    if comps:
        out["components"] = comps
