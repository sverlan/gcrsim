"""Build and install smoke test (slow; needs uv and its build backend)."""

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from conftest import write_model, ROOT

UV = shutil.which("uv")
pytestmark = [pytest.mark.slow, pytest.mark.skipif(UV is None, reason="uv not installed")]


def run(cmd, **kw):
    proc = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kw)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc


def test_wheel_and_sdist_build_install_and_run(tmp_path):
    dist = tmp_path / "dist"
    run([UV, "build", "--no-sources", "--out-dir", dist, ROOT])
    wheel = next(dist.glob("*.whl"))
    sdist = next(dist.glob("*.tar.gz"))

    names = zipfile.ZipFile(wheel).namelist()
    assert "gcrsim/__init__.py" in names and "gcrsim/__main__.py" in names
    assert not [n for n in names if n.endswith(".py") and not n.startswith("gcrsim/")]
    meta = zipfile.ZipFile(wheel).read([n for n in names if n.endswith("METADATA")][0]).decode()
    assert "Requires-Dist" not in meta  # no runtime dependencies
    assert "License-Expression: MIT" in meta
    assert any(n.endswith("licenses/LICENSE") for n in names)

    # the wheel can be rebuilt from the sdist
    run([UV, "build", "--no-sources", "--wheel", "--out-dir", tmp_path / "again", sdist])
    assert list((tmp_path / "again").glob("*.whl"))

    venv = tmp_path / "venv"
    run([UV, "venv", venv])
    py = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    run([UV, "pip", "install", "--python", py, wheel])
    work = tmp_path / "work"
    work.mkdir()
    write_model(work / "m.txt", """[axioms]
1 = ["S"]

[rules]
S->aS,2
2,S->Sb
S->
""")
    command = venv / ("Scripts/gcrsim.exe" if sys.platform == "win32" else "bin/gcrsim")
    a = run([command, "m.txt", "3", "--format", "perl"], cwd=work).stdout
    b = run([py, "-m", "gcrsim", "m.txt", "3", "--format", "perl"], cwd=work).stdout
    assert a == b and "aaSb" in a
    assert run([command, "--version"]).stdout.startswith("gcrsim ")


def test_the_version_is_the_same_in_pyproject_and_in_the_package():
    import re
    import tomllib

    import gcrsim

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["version"] == gcrsim.__version__
    assert project["build-system"]["build-backend"] == "uv_build"
    assert re.fullmatch(r"\d+\.\d+\.\d+(\.dev\d+)?", gcrsim.__version__)
