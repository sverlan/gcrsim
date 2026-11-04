"""The relative links of the documents point to files that exist, and the anchors to headings that exist."""
import re
from pathlib import Path

import pytest

from conftest import ROOT

ROOT = Path(ROOT)
DOCS = [ROOT / "README.md", ROOT / "examples" / "README.md", *sorted((ROOT / "docs").glob("*.md"))]


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_relative_links_exist(doc):
    for m in re.finditer(r"\]\(([^)#]+)(#[^)]*)?\)", doc.read_text(encoding="utf-8")):
        target = m.group(1)
        if target.startswith("http"):
            continue
        assert (doc.parent / target).exists(), (doc.name, target)


def anchors(path):
    """The anchors GitHub makes for the headings of a Markdown file (code blocks are skipped)."""
    out = set()
    in_code = False
    for line in path.read_text(encoding="utf-8").split("\n"):
        if line.startswith("```"):
            in_code = not in_code
            continue
        m = re.match(r"#+ (.*)", line)
        if m and not in_code:
            text = re.sub(r"[^\w\- ]", "", m.group(1).strip().lower().replace("`", ""))
            out.add(text.replace(" ", "-"))
    return out


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_anchors_exist(doc):
    text = doc.read_text(encoding="utf-8")
    for m in re.finditer(r"\]\(([^)#]*)#([^)]+)\)", text):
        target, fragment = m.group(1), m.group(2)
        if target.startswith("http"):
            continue
        linked = doc if not target else doc.parent / target
        assert fragment in anchors(linked), (doc.name, target, fragment)
