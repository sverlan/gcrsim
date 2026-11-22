"""The jsonl header names the declared terminals (null when the model declares none)."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECLARED = ROOT / "examples" / "python" / "target_pruning.txt"      # terminals = "a b"
UNDECLARED = ROOT / "examples" / "cookbook" / "02_insdel.txt"


def header(*args, cwd=None):
    r = subprocess.run([sys.executable, "-m", "gcrsim", *map(str, args), "--format", "jsonl"], capture_output=True, text=True,
                       cwd=cwd or ROOT)
    first = json.loads(r.stdout.splitlines()[0])
    assert first["type"] == "header", r.stdout
    return first


def test_run_header_has_the_declared_terminals():
    assert header(DECLARED, 1)["terminals"] == ["a", "b"]


def test_run_header_without_a_declaration_has_null():
    assert header(UNDECLARED, 1)["terminals"] is None


def test_replay_header(tmp_path):
    f = tmp_path / "d.txt"
    f.write_text("S\naS\n", encoding="utf-8")
    h = header(DECLARED, "--replay", f)
    assert h["mode"] == "replay" and h["terminals"] == ["a", "b"]


def test_search_header_uses_the_terminals_of_the_option():
    assert header(DECLARED, "--search", "ab")["terminals"] == ["a", "b"]
    assert header(DECLARED, "--search", "ab", "--terminals", "a")["terminals"] == ["a"]


def test_language_header():
    h = header(DECLARED, "--language", "--max-word-len", "0", "--max-steps", "1")
    assert h["mode"] == "language" and h["terminals"] == ["a", "b"]
