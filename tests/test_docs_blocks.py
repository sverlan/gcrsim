"""Every complete model quoted in README.md and docs/ parses (the cookbook models are also run by test_cookbook.py)."""
import re
from pathlib import Path

import pytest

import gcrsim
from conftest import ROOT

FILES = [Path(ROOT) / "README.md", *sorted((Path(ROOT) / "docs").glob("*.md"))]
BLOCKS = []
for f in FILES:
    for i, m in enumerate(re.finditer(r"```[a-z]*\n(.*?)```", f.read_text(encoding="utf-8"), re.S)):
        if re.search(r"(?mi)^\[axioms\]", m.group(1)):
            BLOCKS.append(pytest.param(m.group(1), id="%s#%d" % (f.name, i)))


@pytest.mark.parametrize("block", BLOCKS)
def test_quoted_models_parse(block):
    gcrsim.parse_model(block)


TOML_BLOCKS = []
for _f in FILES:
    for _i, _m in enumerate(re.finditer(r"```toml\n(.*?)```", _f.read_text(encoding="utf-8"), re.S)):
        if not re.search(r"(?mi)^\[(axioms|rules)", _m.group(1)):  # a model is checked above
            TOML_BLOCKS.append(pytest.param(_m.group(1), id="%s#%d" % (_f.name, _i)))


@pytest.mark.parametrize("block", TOML_BLOCKS)
def test_quoted_toml_settings_are_valid_settings(block):
    import tomllib

    from gcrsim.errors import ConfigError
    from gcrsim.sections import flatten
    from gcrsim.settings import apply_settings

    def reject(message):
        raise ConfigError(message)

    flat = flatten(tomllib.loads(block), "the documentation", True, reject)
    apply_settings(gcrsim.Settings(), flat, "the documentation", from_model=True)
