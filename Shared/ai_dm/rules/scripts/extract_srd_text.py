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
from collections import Counter
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

# Rule terms boosted into chunk keywords (mirrored in build_rules_lookup.py).
BOOSTED_RULE_TERMS = [
    "ability check", "saving throw", "attack roll", "advantage", "disadvantage",
    "proficiency", "dc", "difficulty class",
    "grapple", "grappled", "prone", "restrained", "stunned", "frightened",
    "charmed", "incapacitated", "unconscious",
    "short rest", "long rest", "hit dice", "death saving throw",
    "zero hit points", "initiative", "attack", "action", "bonus action",
    "reaction", "movement", "spellcasting",
]

# Chunking parameters.
_CHUNK_SIZE = 1200
_CHUNK_OVERLAP = 200
_CHUNK_MIN = 200


def clean_srd_text(text: str) -> str:
    """Remove TOC dotted leaders, isolated page numbers, and excess whitespace."""
    cleaned_lines = []
    for raw in (text or "").split("\n"):
        line = raw.strip()
        if not line:
            cleaned_lines.append("")
            continue
        # Table-of-contents dotted leader (e.g. "Ability Checks ...... 6").
        if re.search(r"\.{5,}", line):
            continue
        # Line that is mostly dots.
        if line.count(".") / max(len(line), 1) > 0.4:
            continue
        # Isolated page number.
        if re.fullmatch(r"\d{1,4}", line):
            continue
        # Common footer/boilerplate.
        if "©" in line or re.match(r"(?i)^system reference document", line):
            continue
        cleaned_lines.append(line)

    result = "\n".join(cleaned_lines)
    result = re.sub(r"[ \t]{2,}", " ", result)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def is_toc_page(text: str) -> bool:
    """True if >25% of non-empty lines are TOC-style dotted-leader lines."""
    lines = [line for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return False
    leaders = sum(1 for line in lines if re.search(r"\.{5,}", line))
    return leaders / len(lines) > 0.25


def _chunk_text(text: str):
    """Yield overlapping ~1200-char chunks; drop tiny ones lacking rule terms."""
    text = text.strip()
    if not text:
        return
    length = len(text)
    start = 0
    step = max(_CHUNK_SIZE - _CHUNK_OVERLAP, 1)
    while start < length:
        chunk = text[start: start + _CHUNK_SIZE].strip()
        if len(chunk) >= _CHUNK_MIN or _has_rule_term(chunk):
            yield chunk
        if start + _CHUNK_SIZE >= length:
            break
        start += step


def _has_rule_term(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in BOOSTED_RULE_TERMS)


def chunk_keywords(text: str):
    """Keywords for a chunk: boosted rule terms present + frequent long words."""
    lowered = text.lower()
    keywords = [term for term in BOOSTED_RULE_TERMS if term in lowered]
    counts = Counter(
        w for w in re.findall(r"[a-z][a-z']+", lowered)
        if len(w) > 3 and w not in _STOP_WORDS
    )
    for word, _count in counts.most_common(15):
        if word not in keywords:
            keywords.append(word)
    return keywords


_STOP_WORDS = {
    "the", "and", "for", "with", "you", "your", "are", "may", "can", "when",
    "each", "one", "any", "such", "that", "this", "from", "into", "out",
    "its", "their", "them", "they", "not", "but", "all", "some", "than",
    "then", "must", "make", "have", "has", "while", "also", "which", "these",
    "there", "other", "more", "only", "who", "whom", "does",
}


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

    source_name = manifest.get("source_name", "Dungeons & Dragons SRD 5.2.1")
    license_name = manifest.get("license", "CC-BY-4.0")

    srd_dir = RULES_DIR / "srd" / version
    pdf_path = srd_dir / "source" / pdf_filename
    extracted_dir = srd_dir / "extracted"
    markdown_dir = srd_dir / "markdown"
    chunks_dir = srd_dir / "chunks"

    if not pdf_path.exists():
        print(f"SRD PDF not found at {pdf_path}", file=sys.stderr)
        print(
            "Run: python3 Shared/ai_dm/rules/scripts/download_srd.py",
            file=sys.stderr,
        )
        return 1

    extracted_dir.mkdir(parents=True, exist_ok=True)
    markdown_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir.mkdir(parents=True, exist_ok=True)

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

    # Raw full text (unmodified) for reference.
    full_text = "\n".join(page_texts)
    full_path.write_text(full_text, encoding="utf-8")

    # Cleaned text drives markdown sections and chunks (no TOC leaders).
    cleaned_full = clean_srd_text(full_text)
    sections = _split_sections(cleaned_full, markdown_dir)

    chunks_path = chunks_dir / "rules_chunks.jsonl"
    n_chunks, skipped_toc = _write_chunks(
        page_texts, chunks_path, source_name, license_name
    )

    print(f"Extracted {len(page_texts)} pages -> extracted/srd_5_2_1_full.txt")
    print("Wrote per-page JSONL -> extracted/pages.jsonl")
    print(f"Wrote {sections} Markdown sections -> markdown/")
    print(
        f"Wrote {n_chunks} cleaned chunks -> chunks/rules_chunks.jsonl "
        f"({skipped_toc} TOC pages skipped)"
    )
    print("Next: python3 Shared/ai_dm/rules/scripts/build_rules_lookup.py")
    return 0


def _write_chunks(page_texts, chunks_path: Path, source_name: str, license_name: str):
    """Write cleaned, non-TOC page text as overlapping chunks. Returns counts."""
    n_chunks = 0
    skipped_toc = 0
    with chunks_path.open("w", encoding="utf-8") as chunks_file:
        for page_number, raw in enumerate(page_texts, start=1):
            if not raw.strip():
                continue
            if is_toc_page(raw):
                skipped_toc += 1
                continue
            cleaned = clean_srd_text(raw)
            if not cleaned:
                continue
            for chunk_index, chunk in enumerate(_chunk_text(cleaned), start=1):
                entry = {
                    "id": f"srd_5_2_1_page_{page_number}_chunk_{chunk_index}",
                    "title": f"SRD 5.2.1 page {page_number}",
                    "page": page_number,
                    "source": source_name,
                    "license": license_name,
                    "text": chunk,
                    "keywords": chunk_keywords(chunk),
                }
                chunks_file.write(json.dumps(entry, ensure_ascii=False) + "\n")
                n_chunks += 1
    return n_chunks, skipped_toc


if __name__ == "__main__":
    raise SystemExit(main())
