#!/usr/bin/env python3
"""Build a simple keyword lookup index from the installed rules Markdown.

Scans ``srd/<version>/markdown/*.md`` and writes
``srd/<version>/lookup/rules_lookup.json`` — one entry per doc with an id,
title, repo-relative path, keyword list, and full text. Keyword extraction is
deliberately simple (filename + heading tokens + frequent long words, minus
stop words); no embeddings, no network.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections import Counter
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
RULES_DIR = SCRIPTS_DIR.parent
APP_DIR = RULES_DIR.parent / "app"
SRD_VERSION = "5.2.1"
SRD_DIR = RULES_DIR / "srd" / SRD_VERSION
MARKDOWN_DIR = SRD_DIR / "markdown"
CHUNKS_PATH = SRD_DIR / "chunks" / "rules_chunks.jsonl"
LOOKUP_DIR = SRD_DIR / "lookup"
LOOKUP_INDEX = LOOKUP_DIR / "rules_lookup.json"
MANIFEST = RULES_DIR / "manifests" / "srd_5_2_1.json"

LOCAL_PATH = f"Shared/ai_dm/rules/srd/{SRD_VERSION}"

# Rule terms boosted into keywords (mirrored in extract_srd_text.py).
BOOSTED_RULE_TERMS = [
    "ability check", "saving throw", "attack roll", "advantage", "disadvantage",
    "proficiency", "dc", "difficulty class",
    "grapple", "grappled", "prone", "restrained", "stunned", "frightened",
    "charmed", "incapacitated", "unconscious",
    "short rest", "long rest", "hit dice", "death saving throw",
    "zero hit points", "initiative", "attack", "action", "bonus action",
    "reaction", "movement", "spellcasting",
]

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


def _strip_comments(text: str) -> str:
    """Remove HTML comment blocks (e.g. the source/license header)."""
    return re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)


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

    body = _strip_comments(text)
    counts = Counter(w for w in _tokens(body) if len(w) > 3 and w not in STOP_WORDS)
    for word, _count in counts.most_common():
        if len(keywords) >= _MAX_KEYWORDS:
            break
        add(word)

    return keywords


def _manifest_meta():
    """Return (source_name, license) from the manifest with defaults."""
    source_name = "Dungeons & Dragons SRD 5.2.1"
    license_name = "CC-BY-4.0"
    if MANIFEST.exists():
        try:
            manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
            source_name = manifest.get("source_name", source_name)
            license_name = manifest.get("license", license_name)
        except json.JSONDecodeError:
            pass
    return source_name, license_name


def _augment_keywords(existing, title: str, text: str) -> list:
    """Merge stored keywords with title tokens and boosted rule terms in text."""
    keywords = list(existing or [])
    lowered = text.lower()
    for term in BOOSTED_RULE_TERMS:
        if term in lowered and term not in keywords:
            keywords.append(term)
    for word in _tokens(title):
        if len(word) > 3 and word not in STOP_WORDS and word not in keywords:
            keywords.append(word)
    return keywords


def build_from_chunks(source_name: str, license_name: str) -> list:
    """Build chunk-level lookup docs from rules_chunks.jsonl."""
    docs = []
    chunk_path = f"{LOCAL_PATH}/chunks/rules_chunks.jsonl"
    with CHUNKS_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = chunk.get("text", "")
            title = chunk.get("title", chunk.get("id", "SRD chunk"))
            docs.append(
                {
                    "id": chunk.get("id"),
                    "title": title,
                    "path": chunk_path,
                    "page": chunk.get("page"),
                    "keywords": _augment_keywords(chunk.get("keywords"), title, text),
                    "text": text,
                    "source": chunk.get("source", source_name),
                    "license": chunk.get("license", license_name),
                }
            )
    return docs


def build_from_markdown(source_name: str, license_name: str) -> list:
    """Build section-level lookup docs from markdown/*.md (fallback)."""
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
                "keywords": _augment_keywords(_keywords(doc_id, title, text), title, text),
                "text": text,
                "source": source_name,
                "license": license_name,
            }
        )
    return docs


def _build_glossary() -> None:
    """Run build_rules_glossary.build_glossary() from the sibling script."""
    glossary_script = SCRIPTS_DIR / "build_rules_glossary.py"
    if not glossary_script.exists():
        print("(build_rules_glossary.py not found — skipping glossary)")
        return
    spec = importlib.util.spec_from_file_location("build_rules_glossary", glossary_script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.build_glossary()


def _run_test_query(query: str) -> int:
    """Run the app's real rules search against the built index and print top hits."""
    sys.path.insert(0, str(APP_DIR))
    try:
        import rules_lookup  # noqa: E402
    except ImportError as exc:
        print(f"Could not import rules_lookup for test: {exc}", file=sys.stderr)
        return 1
    results = rules_lookup.search_rules(query, limit=5)
    if not results:
        print(f"No results for {query!r}.")
        return 0
    print(f"Top results for {query!r}:")
    for doc in results:
        snippet = " ".join(str(doc.get("text", "")).split())[:160]
        print(f"- {doc.get('title', doc.get('id'))}: {snippet}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build the rules lookup index.")
    parser.add_argument(
        "--test-query",
        metavar="QUERY",
        help="After building, run this query against the index and print hits.",
    )
    args = parser.parse_args(argv)

    source_name, license_name = _manifest_meta()

    if CHUNKS_PATH.exists():
        docs = build_from_chunks(source_name, license_name)
        origin = "chunks/rules_chunks.jsonl"
    elif MARKDOWN_DIR.exists():
        docs = build_from_markdown(source_name, license_name)
        origin = "markdown/*.md"
    else:
        print(
            f"No chunks or markdown found under {LOCAL_PATH}. "
            "Run install_rules.py or extract_srd_text.py first."
        )
        return 1

    LOOKUP_DIR.mkdir(parents=True, exist_ok=True)
    LOOKUP_INDEX.write_text(
        json.dumps(docs, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"Indexed {len(docs)} rule docs from {origin} -> "
        f"{LOCAL_PATH}/lookup/rules_lookup.json"
    )

    # Also build the canonical rules glossary (definitions for common terms).
    _build_glossary()

    if args.test_query:
        print()
        return _run_test_query(args.test_query)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
