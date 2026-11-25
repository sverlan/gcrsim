"""The agent skill (gcrsim/skill/SKILL.md) and `gcrsim --print-skill`.

Fence convention in SKILL.md: a model is a fence tagged `gcrsim-model` (optionally followed by the cookbook file it copies, which
must have the same content apart from comment and blank lines); a fence tagged `sh` holds command lines, and every line that starts
with `gcrsim ` and names a file of `examples/` is run (exit 0, or the code of a trailing `# exit N`); the following lines
`# => TEXT` state a line that the standard output must contain. A fence tagged `python` is run, with `insdel.txt` standing for the
cookbook file `examples/cookbook/02_insdel.txt`.
"""
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

import gcrsim
from gcrsim import skill_text, parse_model
from gcrsim import operations
from conftest import CLI_ENV, ROOT
from test_doc_links import anchors

ROOT = Path(ROOT)
SKILL = ROOT / "gcrsim" / "skill" / "SKILL.md"
TEXT = skill_text()
LINK = re.compile(r"https://github\.com/sverlan/gcrsim/blob/main/((?:docs|examples)/[\w./-]+?)(#[\w-]+)?(?=[)\s]|$)")


def cli(*args):
    proc = subprocess.run([sys.executable, "-m", "gcrsim", *args], cwd=ROOT, env=CLI_ENV, capture_output=True, timeout=120)
    return proc.returncode, proc.stdout.decode("utf-8"), proc.stderr.decode("utf-8")


def fences():
    """(info string, body) of every fenced block of the skill."""
    return [(m.group(1).strip(), m.group(2)) for m in re.finditer(r"^```([^\n]*)\n(.*?)^```$", TEXT, re.S | re.M)]


def test_print_skill_is_the_file():
    code, out, err = cli("--print-skill")
    assert code == 0 and err == ""
    assert out == TEXT == SKILL.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert cli("--mode", "search", "--print-skill")[1] == TEXT
    assert cli("--print-skill", "--mode=describe")[1] == TEXT


@pytest.mark.parametrize("args", [
    ["examples/cookbook/02_insdel.txt", "--print-skill"],
    ["--print-skill", "3"],
    ["--print-skill", "--quiet"],
    ["--print-skill", "--mode", "bogus"],
    ["--print-skill", "--print-skill"],
])
def test_print_skill_with_other_arguments_is_an_error(args):
    code, out, err = cli(*args)
    assert code == 2 and out == "" and err.startswith("gcrsim: ")


@pytest.mark.parametrize("args", [["--describe", "--print-skill"], ["--language", "--print-skill"],
                                  ["--print-skill", "--mode", "language"], ["--print-s"], ["--print-ski", "--mode=search"]])
def test_print_skill_with_operand_free_aliases_and_abbreviations(args):
    assert cli(*args)[:2] == (0, TEXT)


@pytest.mark.parametrize("args", [["--print-s", "examples/cookbook/02_insdel.txt", "1"], ["--print-skill", "--replay", "f"],
                                  ["--print-skill", "--search", "ab"], ["--print-skill", "--print-sk"]])
def test_print_skill_abbreviation_follows_the_same_path(args):
    code, out, err = cli(*args)
    assert code == 2 and out == "" and err.startswith("gcrsim: ")


def test_print_skill_into_a_closed_pipe():
    for _ in range(3):
        proc = subprocess.Popen([sys.executable, "-m", "gcrsim", "--print-skill"], cwd=ROOT, env=CLI_ENV,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proc.stdout.close()
        err = proc.stderr.read()
        assert proc.wait() in (0, 1) and b"Traceback" not in err


def test_front_matter():
    m = re.match(r"---\n(.*?)\n---\n", TEXT, re.S)
    assert m
    fields = dict(re.match(r"(\w+):\s*(.*)", line).groups() for line in m.group(1).split("\n"))
    assert fields["name"] == "gcrsim" and set(fields) == {"name", "description"}
    assert 0 < len(fields["description"]) <= 1024
    assert "{{" not in TEXT


def test_the_text_keeps_clear_of_the_old_simulator():
    assert "perl" not in TEXT.lower() and "gcrsim-convert" not in TEXT


def parser_options(mode):
    op = {o.name: o for o in operations.operations()}[mode]
    return {o for action in op.build_parser()._actions for o in action.option_strings if o.startswith("--")} | {operations.MODE_OPTION}


def test_every_long_option_exists():
    known = set().union(*(parser_options(op.name) for op in operations.operations()))
    used = set(re.findall(r"(?<![\w-])(--[a-z][a-z-]*)", TEXT))
    assert not (used - known), used - known


def mode_of(args):
    """The mode a command line selects: --mode NAME or the alias of a mode, else run."""
    aliases = {op.alias: op.name for op in operations.operations() if op.alias}
    for i, a in enumerate(args):
        if a == "--mode":
            return args[i + 1]
        if a in aliases:
            return aliases[a]
    return "run"


def test_the_commands_of_the_table_use_options_of_their_mode():
    for m in re.finditer(r"^\| .*? \| `(gcrsim MODEL [^`]*)` ", TEXT, re.M):
        args = shlex.split(m.group(1))[1:]
        assert set(re.findall(r"--[a-z][a-z-]*", m.group(1))) <= parser_options(mode_of(args)), m.group(1)


def comment_free(text):
    return [ln for ln in text.split("\n") if ln.strip() and not ln.lstrip().startswith("#")]


def test_model_blocks_parse_and_copy_the_cookbook():
    blocks = [(info, body) for info, body in fences() if info.startswith("gcrsim-model")]
    assert len(blocks) >= 5
    for info, body in blocks:
        parse_model(body)
        parts = info.split()
        if len(parts) > 1:
            original = (ROOT / parts[1]).read_text(encoding="utf-8").replace("\r\n", "\n")
            assert comment_free(body) == comment_free(original), parts[1]


def commands():
    """(line, expected exit status, expected output lines) of every command of a `sh` fence."""
    for info, body in fences():
        if info != "sh":
            continue
        current = None
        for line in body.split("\n"):
            if line.startswith("gcrsim ") and "examples/" in line:
                m = re.search(r"#\s*exit (\d+)\s*$", line)
                current = (re.sub(r"\s+#.*$", "", line), int(m.group(1)) if m else 0, [])
                yield current
            elif line.startswith("# => ") and current:
                current[2].append(line[5:])


def test_commands_exist():
    found = list(commands())
    assert len(found) >= 8 and sum(len(c[2]) for c in found) >= 8


@pytest.mark.parametrize("line,expected,lines", list(commands()), ids=lambda v: v if isinstance(v, str) else "")
def test_commands_run(line, expected, lines):
    args = shlex.split(line)[1:]
    assert set(re.findall(r"--[a-z][a-z-]*", line)) <= parser_options(mode_of(args)), line  # each option exists in its mode
    code, out, err = cli(*args)
    assert code == expected, (line, out[-500:], err)
    shown = out.split("\n")
    for text in lines:
        assert text in shown, (line, text, out[-800:])  # a whole line of the output


def test_python_blocks_run():
    blocks = [body for info, body in fences() if info == "python"]
    assert blocks
    for body in blocks:
        code = body.replace("insdel.txt", "examples/cookbook/02_insdel.txt")
        proc = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=CLI_ENV, capture_output=True, timeout=120)
        assert proc.returncode == 0, proc.stderr.decode()
        out = proc.stdout.decode()
        assert "1 1 4" in out and "partial depth_bound {2: 1, 4: 1, 6: 1}" in out.splitlines()


def test_doc_links_exist():
    links = LINK.findall(TEXT)
    assert len(links) >= 15
    for path, frag in links:
        target = ROOT / path
        assert target.exists(), path
        if frag:
            assert target.suffix == ".md" and frag[1:] in anchors(target), (path, frag)
    assert len(links) == TEXT.count("https://github.com/sverlan/gcrsim/blob/main/")  # no link of another shape


def test_the_encoding_table_links_every_cookbook_model():
    named = set(re.findall(r"\]\(https://github\.com/sverlan/gcrsim/blob/main/examples/cookbook/(\d\d_[a-z0-9_]+)\.txt\)", TEXT))
    on_disk = {p.stem for p in (ROOT / "examples" / "cookbook").glob("*.txt")}
    assert named == on_disk and len(on_disk) == 28
    assert "/tree/" not in TEXT


def test_expected_steps_of_the_model_blocks(tmp_path):
    """A model block with a line `# => after N steps: w1 w2 ...` has exactly these words in component 1 after N steps."""
    checked = 0
    for info, body in fences():
        m = re.search(r"^# => after (\d+) steps?: (.*)$", body, re.M)
        if not (info.startswith("gcrsim-model") and m):
            continue
        model = tmp_path / ("m%d.txt" % checked)
        model.write_text(body, encoding="utf-8")
        code, out, err = cli(str(model), m.group(1), "--format", "jsonl", "--max-time", "20")
        assert code == 0, err
        last = [json.loads(line) for line in out.splitlines() if line.startswith('{"type": "step"')][-1]
        assert sorted(last["components_string"][0]) == sorted(m.group(2).split())
        checked += 1
    assert checked >= 1


def test_skill_text_is_a_public_function():
    assert gcrsim.skill_text is skill_text and "skill_text" in gcrsim.__all__


def test_a_bare_dollar_in_a_pattern_needs_the_symbol(tmp_path):
    ok = tmp_path / "ok.txt"
    ok.write_text('[axioms]\n1 = ["a$"]\n[rules]\nre(a$) -> X\n', encoding="utf-8")
    code, out, err = cli(str(ok), "1", "--max-time", "10")
    assert code == 0 and "X" in out.splitlines()
    bad = tmp_path / "bad.txt"
    bad.write_text('[axioms]\n1 = ["ab"]\n[rules]\nre(b$) -> X\n', encoding="utf-8")
    assert cli(str(bad), "1", "--max-time", "10")[0] == 2
