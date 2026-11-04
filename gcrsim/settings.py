"""Settings and configuration loading (`.toml`, gated `.py`)."""

from __future__ import annotations

import os
import re
from typing import Any, Callable, Dict, Optional, Sequence, Union
from .errors import ConfigError, GcrsimError
from .model import Model
from .sections import flatten


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class Settings:
    """Simulation settings."""

    def __init__(
        self,
        history: bool = True,
        print_hide: str = "",
        print_max_len: Optional[int] = None,   # None: no limit
        reject_strings: str = "",
        reject_max_len: Optional[int] = None,   # None: no limit
        show_detailed_application: bool = False,
        print_sep: str = "",
        steps: Optional[int] = None,
        hash_history: bool = False,
        description: str = "",
        derivation: str = "any",
        filters: Optional[Dict[Any, Dict[str, Any]]] = None,
        filter_next: Optional[Callable[..., Any]] = None,
        config_name: str = "",
        config_notice: Optional[str] = None,
        marks: Optional[Dict[Any, Dict[str, Any]]] = None,
    ):
        self.marks = {} if marks is None else marks
        self.history = history
        self.print_hide = print_hide
        self.print_max_len = print_max_len
        self.reject_strings = reject_strings
        self.reject_max_len = reject_max_len
        self.show_detailed_application = show_detailed_application
        self.print_sep = print_sep
        self.steps = steps
        self.hash_history = hash_history
        self.description = description
        self.derivation = derivation
        self.filters = {} if filters is None else filters
        self.filter_next = filter_next
        self.config_name = config_name
        self.config_notice = config_notice


_RUN_KEYS = (
    "history",
    "print_hide",
    "print_max_len",
    "reject_strings",
    "reject_max_len",
    "show_detailed_application",
    "print_sep",
    "steps",
    "hash_history",
    "description",
    "derivation",
)
_TYPES = {
    "history": bool,
    "print_hide": str,
    "print_max_len": int,
    "reject_strings": str,
    "reject_max_len": int,
    "show_detailed_application": bool,
    "print_sep": str,
    "steps": int,
    "hash_history": bool,
    "description": str,
}
_TABLE_KEYS = ("filters", "marks")  # the settings of each component, keyed by component number
_MODEL_ONLY_KEYS = ("symbols", "classes", "alphabet")  # they change how the model text is read
_KNOWN_KEYS = _RUN_KEYS + ("components",) + _MODEL_ONLY_KEYS + ("filter_next",)


def _component_key(k: Any) -> Any:
    """``"all"``, ``"0"`` and ``0`` mean every component; a digit string is a component number."""
    if k == "all":
        return 0
    return int(k) if isinstance(k, str) and k.isdigit() else k


def _normalise_tables(data: Dict[str, Any]) -> None:
    """Component keys written as TOML table names (``"2"``) become integers."""
    for table in _TABLE_KEYS:
        t = data.get(table)
        if isinstance(t, dict):
            data[table] = {_component_key(k): v for k, v in t.items()}


def _split_components(components: Any, where: str) -> Dict[str, Dict[Any, Any]]:
    """``{N: {"filters": ..., "marks": ...}}`` (the shape of ``[model.components.N.filters]``) as one table per kind."""
    if not isinstance(components, dict):
        raise ConfigError("%s: components must be a table of component numbers" % where)
    out: Dict[str, Dict[Any, Any]] = {"filters": {}, "marks": {}}
    for number, entry in components.items():
        if not isinstance(entry, dict):
            raise ConfigError("%s: components[%r] must be a table with filters and marks" % (where, number))
        for kind, table in entry.items():
            if kind not in out:
                raise ConfigError("%s: unknown setting '%s' for component %s (it has filters and marks)" % (where, kind, number))
            out[kind][number] = table
    return {kind: table for kind, table in out.items() if table}


def apply_settings(st: Settings, data: Dict[str, Any], where: str, *, from_model: bool = False, strict: bool = True) -> None:
    """Apply one layer of settings to ``st``: only the keys present in ``data`` change.

    Later layers win; the ``filters`` and ``marks`` of the components (written under ``components``) are merged by component key (a layer that sets
    component 1 replaces the earlier entry for component 1 and leaves the other components alone).
    Keys that change how the model text is read (``symbols``, ``classes``, ``alphabet``) belong to the
    model's own ``[symbols]`` and are refused anywhere else; a model can never bring a filter function.
    """
    data = dict(data)
    for key in data:
        if key in _MODEL_ONLY_KEYS and not from_model:
            raise ConfigError("%s: '%s' belongs to the model's [symbols] section, not to a configuration file" % (where, key))
        if key == "filter_next" and from_model:
            raise ConfigError("%s: a model cannot bring a filter function (use --python-filter FILE.py)" % where)
        if strict and key not in _KNOWN_KEYS:
            raise ConfigError("%s: unknown setting '%s'" % (where, key))
    if "components" in data:
        data.update(_split_components(data.pop("components"), where))
    _normalise_tables(data)
    for key, kind in _TYPES.items():
        if key in data:
            value = data[key]
            if kind is int and (isinstance(value, bool) or not isinstance(value, int)):
                raise ConfigError("%s: '%s' must be an integer, not %r" % (where, key, value))
            if kind is int and key in ("print_max_len", "steps") and value < 0:
                raise ConfigError("%s: '%s' cannot be negative" % (where, key))
            if kind is not int and not isinstance(value, kind):
                raise ConfigError("%s: '%s' must be %s, not %r" % (where, key, "true or false" if kind is bool else "a string", value))
            setattr(st, key, value)
    if "derivation" in data:
        if data["derivation"] != "any":
            raise ConfigError("%s: derivation = %r is not supported yet (only 'any')" % (where, data["derivation"]))
        st.derivation = "any"
    for table in _TABLE_KEYS:
        t = data.get(table)
        if t:
            if not isinstance(t, dict):
                raise ConfigError("%s: %s must be a table" % (where, table))
            merged = dict(getattr(st, table))
            merged.update(t)
            setattr(st, table, merged)
    fn = data.get("filter_next")
    if fn is not None:
        if not callable(fn):
            raise ConfigError("%s: filter_next is not callable" % where)
        _callback_arity(fn)
        st.filter_next = fn


def settings_for_model(model: Model) -> Settings:
    """Defaults, then the model's own sections."""
    st = Settings()
    apply_settings(st, model.config, model.path, from_model=True)
    st.config_name = "model"
    return st


def declare_pure(function: Callable[..., Any]) -> Callable[..., Any]:
    """Declare that a function has no state and depends only on its arguments, as ``--streaming`` needs: ``pure(lambda s: ...)``."""
    function.pure = True  # type: ignore[attr-defined]
    return function


def read_config_data(path: str, allow_python: bool = True) -> Dict[str, Any]:
    """The settings written in a configuration file (a ``.toml`` file is data only; a ``.py`` file runs code)."""
    if str(path).lower().endswith(".toml"):
        return _read_toml(path)
    if not allow_python:
        raise ConfigError(
            "%s is a Python configuration: it runs code. Use --python-filter if you trust it, "
            "or write a declarative .toml configuration" % path
        )
    try:
        import runpy

        ns = runpy.run_path(str(path), init_globals={"lit": re.escape, "pure": declare_pure})
    except GcrsimError:
        raise
    except Exception as exc:  # user code: report any failure with its file name
        raise ConfigError("%s: %s: %s" % (path, type(exc).__name__, exc)) from exc
    found = {k: v for k, v in ns.items() if k in _KNOWN_KEYS}  # a Python file may hold other names
    if "keep" in ns and "filter_next" not in found:  # `keep` is the documented name of the filter function
        found["filter_next"] = ns["keep"]
    return found


def load_config(path: str, allow_python: bool = True, model: Optional[Model] = None) -> Settings:
    """Load a configuration file and return its settings (defaults for what it does not set).

    With ``model`` the result is what the command line would use: the defaults, then the model's own
    sections, then the file.

    A ``.toml`` file is purely declarative (data only).  A ``.py`` file is executable user code and
    is refused unless ``allow_python`` is true (the command line needs ``--allow-python-config``).
    """
    st = Settings() if model is None else settings_for_model(model)
    apply_settings(st, read_config_data(path, allow_python), str(path))
    st.config_name = str(path)
    return st


def _read_toml(path: str) -> Dict[str, Any]:
    """Read a declarative configuration (the sections ``[model]`` and ``[run]``) as flat settings."""
    import tomllib

    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError("%s: %s" % (path, exc)) from exc

    def reject(message: str) -> None:
        raise ConfigError(message)

    return flatten(data, str(path), False, reject)


def _callback_arity(fn: Callable[..., Any]) -> bool:
    """True if ``fn`` takes the context argument; validates the signature."""
    try:
        import inspect

        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return False
    positional = [
        p
        for p in sig.parameters.values()
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    varargs = any(p.kind == p.VAR_POSITIONAL for p in sig.parameters.values())
    if len(positional) < 2 and not varargs:
        raise ConfigError("filter_next must accept (s, component) or (s, component, ctx)")
    return len(positional) >= 3 or varargs


def resolve_config(
    model: Model,
    cli_config: Union[None, str, Sequence[str]] = None,
    cwd: Optional[str] = None,
) -> Settings:
    """The settings for ``model``: the defaults, the model's own sections, then each ``--config`` file in turn.

    A later file overrides an earlier layer setting by setting. Nothing is looked up by name: a configuration is
    used only if it is given. A Python file is never a configuration (``--python-filter`` runs it), a Perl one never is.
    """
    cwd = cwd or os.getcwd()
    files = [cli_config] if isinstance(cli_config, str) else list(cli_config or ())
    st = settings_for_model(model)
    for name in files:
        path = name if os.path.isabs(name) else os.path.join(cwd, name)
        if not os.path.isfile(path):
            raise ConfigError("configuration file not found: %s" % name)
        if name.lower().endswith(".py"):
            raise ConfigError("%s is Python code: select it with --python-filter, not --config" % name)
        if not name.lower().endswith(".toml"):
            _migration_error(name)
        apply_settings(st, read_config_data(path, False), name)
    st.config_name = " + ".join(["model"] + files)
    return st


def _migration_error(name: str) -> None:
    raise ConfigError(
        "%s is a Perl configuration, which gcrsim never executes. Translate it to a "
        "declarative .toml configuration (see docs/migration.md) and select it with "
        "--config translated.toml" % name
    )
