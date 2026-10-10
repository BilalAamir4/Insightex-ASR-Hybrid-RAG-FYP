"""Keeps docs/adr/ well-formed: template sections, status values, gates, index, numbering."""

import re
from pathlib import Path

ADR_DIR = Path(__file__).resolve().parents[2] / "docs" / "adr"
SECTIONS = [
    "## Context",
    "## Decision",
    "## Alternatives considered",
    "## Consequences",
    "## Evidence",
    "## Gate / revisit when",
]
# "Accepted; <part> amended by ADR-XXXX" is the status-line pointer of a partly amended ADR (ADR-0039 -> ADR-0040).
STATUS_RE = re.compile(
    r"^Status: (Proposed|Accepted(; [^\n]* amended by ADR-\d{4})?|Deprecated|Superseded by ADR-\d{4})$", re.MULTILINE
)
NAME_RE = re.compile(r"^(\d{4})-[a-z0-9-]+\.md$")
INDEX_ROW_RE = re.compile(r"^\| \[(\d{4})\]\(([^)]+)\) \|", re.MULTILINE)


def adr_files() -> list[Path]:
    return sorted(p for p in ADR_DIR.glob("*.md") if NAME_RE.match(p.name))


def section_body(text: str, heading: str) -> str:
    start = text.index(heading) + len(heading)
    nxt = re.search(r"^## ", text[start:], re.MULTILINE)
    return text[start : start + nxt.start()] if nxt else text[start:]


def test_adr_dir_exists_and_has_files():
    assert ADR_DIR.is_dir()
    assert adr_files()


def test_every_adr_has_template_sections_and_status():
    for path in adr_files():
        text = path.read_text(encoding="utf-8")
        number = NAME_RE.match(path.name).group(1)
        assert text.startswith(f"# ADR-{number}: "), f"{path.name}: title line"
        assert STATUS_RE.search(text), f"{path.name}: missing or invalid Status line"
        for field in ("Date decided:", "Date recorded:", "Module:"):
            assert re.search(rf"^{field} \S", text, re.MULTILINE), f"{path.name}: missing {field}"
        positions = []
        for heading in SECTIONS:
            assert re.search(rf"^{re.escape(heading)}$", text, re.MULTILINE), f"{path.name}: {heading}"
            positions.append(text.index(heading))
        assert positions == sorted(positions), f"{path.name}: sections out of order"


def test_proposed_adrs_have_a_gate():
    for path in adr_files():
        text = path.read_text(encoding="utf-8")
        if re.search(r"^Status: Proposed$", text, re.MULTILINE):
            body = section_body(text, "## Gate / revisit when").strip()
            assert body, f"{path.name}: Proposed ADR has an empty gate section"


def test_index_matches_files():
    index = (ADR_DIR / "README.md").read_text(encoding="utf-8")
    rows = INDEX_ROW_RE.findall(index)
    linked = [name for _, name in rows]
    assert len(linked) == len(set(linked)), "a file appears in the index more than once"
    for number, name in rows:
        assert (ADR_DIR / name).is_file(), f"index row points at missing file {name}"
        assert name.startswith(number), f"index number {number} does not match {name}"
    assert sorted(linked) == [p.name for p in adr_files()], "index and ADR files differ"


def test_numbers_unique_and_contiguous_from_0001():
    numbers = [int(NAME_RE.match(p.name).group(1)) for p in adr_files()]
    assert len(numbers) == len(set(numbers)), "duplicate ADR number"
    assert numbers == list(range(1, len(numbers) + 1)), "ADR numbers are not contiguous from 0001"
