#!/usr/bin/env python3
"""Extract text from the local SRD PDF and build rough Markdown sections.

Reads the downloaded PDF, writes full text + per-page JSONL, then splits the
text into rough Markdown section files by keyword heuristics. All outputs are
local runtime files (git-ignored). Requires the `pypdf` package for PDF text
extraction.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RULES_DIR = Path(__file__).resolve().parent.parent
MANIFEST = RULES_DIR / "manifests" / "srd_5_2_1.json"

# Attribution header prepended to every generated Markdown section.
SOURCE_HEADER = """\
<!--
Source: Dungeons & Dragons SRD 5.2.1
License: CC-BY-4.0
Generated locally from SRD_CC_v5.2.1.pdf
-->
"""

# Rough section splitter: (id, title, [search keywords in priority order]).
SECTION_SPECS = [
    ("ability_checks", "Ability Checks",
     ["ability check", "ability checks", "skill check"]),
    ("combat", "Combat",
     ["the order of combat", "making an attack", "combat"]),
    ("conditions", "Conditions",
     ["conditions", "grappled", "restrained"]),
    ("resting", "Resting and Recovery",
     ["short rest", "long rest", "resting"]),
    ("death_and_dying", "Death and Dying",
     ["death saving throw", "dropping to 0 hit points", "death saves"]),
    ("spells", "Spellcasting",
     ["spellcasting", "casting a spell", "spell slots"]),
    ("equipment", "Equipment",
     ["equipment", "armor class", "weapons"]),
    ("monsters", "Monsters",
     ["monsters", "stat block", "challenge rating"]),
    ("glossary", "Glossary",
     ["rules glossary", "glossary"]),
]

_BLOCK_CHARS = 4000


def _load_manifest() -> dict:
    if not MANIFEST.exists():
        return {}
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _require_pypdf():
    try:
        import pypdf  # noqa: F401
        return pypdf
    except ImportError:
        print(
            "pypdf is required for PDF extraction.\n"
            "Install it locally or add it to the portable Python environment:\n"
            "python3 -m pip install pypdf",
            file=sys.stderr,
        )
        return None


def _write_section(markdown_dir: Path, section_id: str, title: str, body: str) -> None:
    content = f"{SOURCE_HEADER}\n# {title}\n\n{body.strip()}\n"
    (markdown_dir / f"{section_id}.md").write_text(content, encoding="utf-8")


def _split_sections(full_text: str, markdown_dir: Path) -> int:
    lowered = full_text.lower()
    written = 0
    for section_id, title, keywords in SECTION_SPECS:
        idx = -1
        for keyword in keywords:
            idx = lowered.find(keyword)
            if idx != -1:
                break
        if idx == -1:
            body = (
                "Section extraction pending. See full extracted text at "
                "extracted/srd_5_2_1_full.txt."
            )
        else:
            block = full_text[idx: idx + _BLOCK_CHARS]
            body = re.sub(r"\n{3,}", "\n\n", block).strip()
        _write_section(markdown_dir, section_id, title, body)
        written += 1
    return written


def main() -> int:
    pypdf = _require_pypdf()
    if pypdf is None:
        return 1

    manifest = _load_manifest()
    version = manifest.get("version", "5.2.1")
    pdf_filename = manifest.get("pdf_filename", "SRD_CC_v5.2.1.pdf")

    srd_dir = RULES_DIR / "srd" / version
    pdf_path = srd_dir / "source" / pdf_filename
    extracted_dir = srd_dir / "extracted"
    markdown_dir = srd_dir / "markdown"

    if not pdf_path.exists():
        print(f"SRD PDF not found at {pdf_path}", file=sys.stderr)
        print(
            "Run: python3 Shared/ai_dm/rules/scripts/download_srd.py",
            file=sys.stderr,
        )
        return 1

    extracted_dir.mkdir(parents=True, exist_ok=True)
    markdown_dir.mkdir(parents=True, exist_ok=True)

    try:
        reader = pypdf.PdfReader(str(pdf_path))
    except Exception as exc:  # pypdf raises various read errors
        print(f"Could not read PDF: {exc}", file=sys.stderr)
        return 1

    full_path = extracted_dir / "srd_5_2_1_full.txt"
    pages_path = extracted_dir / "pages.jsonl"

    page_texts = []
    with pages_path.open("w", encoding="utf-8") as pages_file:
        for number, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            page_texts.append(text)
            pages_file.write(
                json.dumps({"page": number, "text": text}, ensure_ascii=False) + "\n"
            )

    full_text = "\n".join(page_texts)
    full_path.write_text(full_text, encoding="utf-8")

    sections = _split_sections(full_text, markdown_dir)

    print(f"Extracted {len(page_texts)} pages -> extracted/srd_5_2_1_full.txt")
    print(f"Wrote per-page JSONL -> extracted/pages.jsonl")
    print(f"Wrote {sections} Markdown sections -> markdown/")
    print("Next: python3 Shared/ai_dm/rules/scripts/build_rules_lookup.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
