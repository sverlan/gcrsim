"""Shared helpers: run gcrsim (Python), run the original Perl simulator, compare."""

from __future__ import annotations

import hashlib
import re
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional, Sequence

import pytest

import gcrsim

ROOT = Path(__file__).resolve().parent.parent
CLI_ENV = dict(os.environ, PYTHONPATH=str(ROOT))
EXAMPLES = ROOT / "tests" / "fixtures" / "examples"
CONVERT = [sys.executable, "-c", "import sys; from gcrsim.convert import main_convert; sys.exit(main_convert(sys.argv[1:]))"]
RETENTION = [sys.executable, "-c", "import sys; from gcrsim.retention import main; sys.exit(main(sys.argv[1:]))"]
PERL_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "perl"
PERL_SCRIPT = Path(os.environ.get("GCRSIM_PERL_SCRIPT", PERL_FIXTURES / "gcrsim.pl"))  # the frozen original, version 1.11
PERL = shutil.which("perl")

HAVE_PERL = bool(PERL) and PERL_SCRIPT.exists()
needs_perl = pytest.mark.skipif(not HAVE_PERL, reason="Perl or gcrsim.pl not available")

# Perl configuration lines that make the printed listing show every accepted
# string (so that the listing equals the full content, independent of display
# filters).
PERL_PRINT_ALL = '\n$print_skip = "(?!)";\n$print_len = 100000000;\n1;\n'


# --------------------------------------------------------------------------
# running programs
# --------------------------------------------------------------------------


def run_py(args: Sequence[str], cwd: Path, stdin: Optional[str] = None, timeout: int = 300, trusted: bool = True) -> SimpleNamespace:
    """Run ``python -m gcrsim ARGS`` and return text (UTF-8) output."""
    args = list(args)
    if "--format" not in args and "--help" not in args and "--version" not in args:
        args += ["--format", "perl"]  # the layout of the Perl simulator; the text layout has its own tests
    if trusted and args and "--python-filter" not in args and "--config" not in args:  # a Python configuration is never found by name: select it
        model = Path(args[0]) if Path(args[0]).is_absolute() else Path(cwd) / args[0]
        conf = model.with_name(model.stem + "_conf.py")
        if conf.is_file():
            args += ["--python-filter", str(conf)]
    proc = subprocess.run(
        [sys.executable, "-m", "gcrsim", *args, ],
        cwd=str(cwd),
        env=CLI_ENV,
        input=None if stdin is None else stdin.encode("utf-8"),
        capture_output=True,
        timeout=timeout,
    )
    return SimpleNamespace(
        stdout=proc.stdout.decode("utf-8"),
        stderr=proc.stderr.decode("utf-8"),
        returncode=proc.returncode,
    )


def run_perl(model: str, steps: int, cwd: Path, timeout: int = 600) -> str:
    """Run the original simulator in ``cwd`` (it reads its config from there)."""
    proc = subprocess.run(
        [PERL, PERL_SCRIPT.as_posix(), model, str(steps)],
        cwd=str(cwd),
        capture_output=True,
        timeout=timeout,
    )
    assert proc.returncode == 0, proc.stderr.decode("latin-1")
    return proc.stdout.decode("latin-1").replace("\r\n", "\n")   # a Perl for Windows writes CRLF


# --------------------------------------------------------------------------
# configuration text for both implementations
# --------------------------------------------------------------------------


def perl_cfg(history=1, print_hide="(?!)", print_max_len=16, reject_strings="(?!)", reject_max_len=16, detailed=0, extra="") -> str:
    return (
        "$history = %d;\n$show_detailed_application = %d;\n"
        '$print_skip = "%s";\n$print_len = %d;\n$add_skip = "%s";\n$add_skip_len = %d;\n%s\n1;\n'
        % (history, detailed, print_hide, print_max_len, reject_strings, reject_max_len, extra)
    )


def py_cfg(history=True, print_hide="", print_max_len=16, reject_strings="", reject_max_len=16, detailed=False, extra="") -> str:
    return (
        "history = %r\nshow_detailed_application = %r\nprint_hide = %r\nprint_max_len = %d\n"
        "reject_strings = %r\nreject_max_len = %d\n%s\n"
        % (history, detailed, print_hide, print_max_len, reject_strings, reject_max_len, extra)
    )


# --------------------------------------------------------------------------
# parsing the printed listing
# --------------------------------------------------------------------------


def parse_listing(text: str) -> List[List[List[str]]]:
    """Parse the printed output into ``steps[k][component] = [strings]``.

    Works on the output of both implementations.  The blank lines separating
    the blocks are removed (one before a ``Component`` header, two before a
    step banner); an empty string is a genuine blank line inside a block.
    """
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    steps: List[List[List[str]]] = []
    comps: Optional[List[List[str]]] = None
    block: Optional[List[str]] = None

    def close(blanks: int) -> None:
        nonlocal block
        if block is not None:
            for _ in range(blanks):
                if block and block[-1] == "":
                    block.pop()
            comps.append(block)  # type: ignore[union-attr]
            block = None

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if line == "The initial configuration (at STEP 0):":
            close(2)
            comps = []
            steps.append(comps)
        elif line == "============" and i + 2 < n and lines[i + 1].startswith("STEP ") and lines[i + 2] == "============":
            close(2)
            comps = []
            steps.append(comps)
            i += 2
        elif (
            comps is not None
            and line.startswith("Component ")
            and line.endswith(":")
            and line[10:-1].isdigit()
            and int(line[10:-1]) == len(comps) + (0 if block is None else 1) + 1
        ):
            close(1)
            block = []
        elif block is not None:
            block.append(line)
        i += 1
    close(2)
    return steps


def digests(steps: Sequence[Sequence[Sequence[str]]]) -> List[str]:
    return [gcrsim.digest_contents(hashlib.sha256(), k, fr).hexdigest() for k, fr in enumerate(steps)]


def first_difference(a: Sequence, b: Sequence) -> str:
    """Describe the first step where two content sequences differ."""
    for k, (x, y) in enumerate(zip(a, b)):
        if x != y:
            for c, (cx, cy) in enumerate(zip(x, y)):
                if cx != cy:
                    for j, (sx, sy) in enumerate(zip(cx, cy)):
                        if sx != sy:
                            return "step %d component %d string %d: %r != %r" % (k, c + 1, j, sx, sy)
                    return "step %d component %d: lengths %d != %d" % (k, c + 1, len(cx), len(cy))
            return "step %d: component counts differ" % k
    return "step counts differ: %d != %d" % (len(a), len(b))


def parse_old(text: str, path: str = "<string>"):
    """Parse a model written in the Perl-era syntax (converted on the fly)."""
    new, _warnings = gcrsim.convert_model(text)
    return gcrsim.parse_model(new, path)


_OLD_AXIOM_LINE = re.compile(r"(?m)^[ \t]*\[[^\]\n]*\][ \t]*$")


def old_to_new(text: str) -> str:
    """Convert a model written in the Perl-era syntax; texts already in the current syntax pass through."""
    if "Axioms" in text and _OLD_AXIOM_LINE.search(text):
        return gcrsim.convert_model(text)[0]
    return text


def legacy_model_text(config: str, axioms: str, rules: str) -> str:
    """A model in the current notation from three short pieces, as the unit tests write them: ``config`` is a TOML body
    (``symbols = [...]``, ``alphabet = ...``, ``[classes]``, settings), ``axioms`` has lines ``N: s1, s2``, ``rules`` has rule lines."""
    import json

    from gcrsim.sections import section_of

    sections = {"symbols": [], "model": [], "run": []}
    tables = []
    in_table = False
    for line in config.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("["):
            in_table = True
            head, _, rest = stripped[1:-1].partition(".")
            home = {"classes": "symbols.classes", "component_filters": "model.filters", "marks": "model.marks"}.get(head, head)
            tables.append("[" + home + ("." + rest if rest else "") + "]")
        elif in_table:
            tables.append(line)
        else:
            line = re.sub(r"^\s*symbols\b", "lexemes", line)
            key = line.split("=")[0].split(".")[0].strip()
            home = "symbols" if key in ("lexemes", "alphabet", "classes") else (section_of(key) or "model")
            sections[home].append(line)
    out = []
    for name, lines in sections.items():
        if lines:
            out += ["[%s]" % name] + lines
    out += tables + ["[axioms]"]
    for line in axioms.split("\n"):
        m = re.match(r"\s*(\d+):(.*)", line)
        if m:
            body = m.group(2).strip()
            items = ([""] if body.startswith(",") else []) + [i.strip() for i in body.split(",") if i.strip()]
            out.append("%s = [%s]" % (m.group(1), ", ".join(json.dumps(i, ensure_ascii=False) for i in items)))
    out += ["[rules]", rules]
    return "\n".join(out) + "\n"


def write_model(path, text: str):
    path.write_bytes(text.encode("utf-8"))
    return path


def without_configfile(text: str) -> str:
    """Perl-format fixtures start with a ConfigFile line, which the Python parser rejects."""
    return re.sub(r"(?mi)^ConfigFile.*\r?\n", "", text)


def python_contents(model_text: str, config_path: Optional[Path] = None, steps: int = 1, *, settings=None, **sim_kwargs):
    """Run the engine through the API and return ``steps[k][component]``."""
    model = parse_old(model_text)
    if settings is None:
        settings = gcrsim.load_config(str(config_path)) if config_path else gcrsim.Settings()
    sim = gcrsim.Simulator(model, settings, write=lambda text: None, **sim_kwargs)
    out = [[list(c) for c in sim.cur]]
    for _ in range(steps):
        sim.step()
        out.append([list(c) for c in sim.cur])
    return out


def perl_contents(model_text: str, cfg_text: str, steps: int, workdir: Path) -> List[List[List[str]]]:
    """Run Perl on a synthetic model with its own config; parse the listing."""
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "m.txt").write_bytes(model_text.encode("latin-1"))
    (workdir / "gcrsim.cfg").write_bytes((cfg_text + PERL_PRINT_ALL).encode("latin-1"))
    return parse_listing(run_perl("m.txt", steps, workdir))


def normalize_header(text: str) -> str:
    """Apply the header allowlist: drop version, input and config path lines."""
    head, sep, body = text.partition("The initial configuration (at STEP 0):")
    kept = [
        ln
        for ln in head.split("\n")
        if not (ln.startswith("gcrsim simulator v.") or ln.startswith("Input file:") or ln.startswith("Configuration file:") or ln.startswith("Configuration:") or ln.startswith("Print_skip =") or ln.startswith("Add_skip=") or ln.startswith("Print_hide =") or ln.startswith("Reject_strings ="))
    ]
    return "\n".join(kept) + sep + body


@pytest.fixture
def work(tmp_path: Path) -> Path:
    return tmp_path
