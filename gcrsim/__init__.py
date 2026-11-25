"""gcrsim - Graph Controlled string Rewriting SIMulator.

Importing this package has no side effects: it does not read files, print,
or start the command line interface."""

from __future__ import annotations

from ._meta import __version__
from .cli import main
from ._describe import Description, describe
from ._language import LanguageResult, language
from .convert import convert_model
from .engine import Context, DerivationStep, Mark, Simulator, format_derivation
from .errors import CallbackError, ConfigError, GcrsimError, LimitReached, ModelError, TraceError
from .measures import Measures, measure_derivation as measure
from .model import Model, parse_model, parse_model_file
from .output import Output, digest_contents, format_conf
from ._replay import ReplayFailure, ReplayReport, ReplayStep, replay, replay_file
from ._search import SearchResult, search
from .rules import Rule
from ._skill import skill_text
from .settings import Settings, apply_settings, load_config, resolve_config

__all__ = [
    "__version__",
    "GcrsimError",
    "ModelError",
    "ConfigError",
    "LimitReached",
    "TraceError",
    "CallbackError",
    "Model",
    "Rule",
    "Settings",
    "Simulator",
    "Output",
    "DerivationStep",
    "ReplayStep",
    "ReplayReport",
    "ReplayFailure",
    "replay",
    "replay_file",
    "search",
    "SearchResult",
    "language",
    "describe",
    "Description",
    "LanguageResult",
    "parse_model",
    "parse_model_file",
    "load_config",
    "resolve_config",
    "format_conf",
    "format_derivation",
    "measure",
    "Measures",
    "digest_contents",
    "skill_text",
    "main",
]
