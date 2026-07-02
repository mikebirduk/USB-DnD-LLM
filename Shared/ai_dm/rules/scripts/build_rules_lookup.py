#!/usr/bin/env python3
"""Build a simple keyword lookup index from the installed rules Markdown.

Scans ``srd/<version>/markdown/*.md`` and writes
``srd/<version>/lookup/rules_lookup.json`` — one entry per doc with an id,
title, repo-relative path, keyword list, and full text. Keyword extraction is
deliberately simple (filename + heading tokens + frequent long words, minus
stop words); no embeddings, no network.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

RULES_DIR = Path(__file__).resolve().parent.parent
SRD_VERSION = "5.2.1"
SRD_DIR = RULES_DIR / "srd" / SRD_VERSION
MARKDOWN_DIR = SRD_DIR / "markdown"
LOOKUP_DIR = SRD_DIR / "lookup"
LOOKUP_INDEX = LOOKUP_DIR / "rules_lookup.json"

LOCAL_PATH = f"Shared/ai_dm/rules/srd/{SRD_VERSION}"

STOP_WORDS = {
    "the", "and", "for", "with", "you", "your", "are", "may", "can", "when",
    "each", "one", "any", "such", "that", "this", "from", "into", "out", "off",
    "its", "his", "her", "their", "them", "they", "not", "but", "all", "some",
    "than", "then", "must", "make", "makes", "add", "and/or", "per", "use",
    "uses", "used", "have", "has", "become", "becomes", "while", "long",
}

_MAX_KEYWORDS = 20


def _tokens(text: str) -> list:
    """Lower-case alphabetic tokens."""
    return re.findall(r"[a-z][a-z']+", text.lower())


def _title_from_text(text: str, fallback: str) -> str:
    """Return the first Markdown heading, or a title derived from the id."""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return fallback.replace("_", " ").title()


def _keywords(doc_id: str, title: str, text: str) -> list:
    """Build a small keyword list from filename, heading, and frequent words."""
    keywords = []

    def add(word: str) -> None:
        if len(word) > 3 and word not in STOP_WORDS and word not in keywords:
            keywords.append(word)

    for word in _tokens(doc_id.replace("_", " ")):
        add(word)
    for word in _tokens(title):
        add(word)

    counts = Counter(w for w in _tokens(text) if len(w) > 3 and w not in STOP_WORDS)
    for word, _count in counts.most_common():
        if len(keywords) >= _MAX_KEYWORDS:
            break
        add(word)

    return keywords


def main() -> int:
    if not MARKDOWN_DIR.exists():
        print(
            f"No markdown found at {LOCAL_PATH}/markdown. "
            "Run install_rules.py first."
        )
        return 1

    LOOKUP_DIR.mkdir(parents=True, exist_ok=True)

    docs = []
    for md_path in sorted(MARKDOWN_DIR.glob("*.md")):
        text = md_path.read_text(encoding="utf-8")
        doc_id = md_path.stem
        title = _title_from_text(text, doc_id)
        docs.append(
            {
                "id": doc_id,
                "title": title,
                "path": f"{LOCAL_PATH}/markdown/{md_path.name}",
                "keywords": _keywords(doc_id, title, text),
                "text": text,
            }
        )

    LOOKUP_INDEX.write_text(
        json.dumps(docs, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Indexed {len(docs)} rule docs -> {LOCAL_PATH}/lookup/rules_lookup.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
