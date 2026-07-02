"""Simple local rules lookup (keyword overlap, no embeddings, no network).

Loads the lookup index built by ``build_rules_lookup.py`` and scores each rule
doc against a query by keyword/text overlap. This is deliberately minimal;
vector search will come in a later milestone.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

import state_store

# Shown when the lookup index has not been built yet.
NOT_INSTALLED_MESSAGE = (
    "No rules lookup index found. Build the local rules library first:\n"
    "  python3 Shared/ai_dm/rules/scripts/install_rules.py\n"
    "  python3 Shared/ai_dm/rules/scripts/build_rules_lookup.py"
)

_SNIPPET_LIMIT = 800


def _tokens(text: str) -> List[str]:
    """Lower-case alphanumeric word tokens."""
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def load_rules_lookup() -> List[Dict[str, Any]]:
    """Return the list of indexed rule docs, or [] if the index is missing."""
    path = state_store.RULES_LOOKUP_INDEX
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def _score(query_tokens: List[str], doc: Dict[str, Any]) -> int:
    """Score a doc: keyword matches weighted higher than body-text matches."""
    if not query_tokens:
        return 0
    keyword_tokens = set()
    for keyword in doc.get("keywords", []):
        keyword_tokens.update(_tokens(str(keyword)))
    text_tokens = set(_tokens(doc.get("text", "")))
    title_tokens = set(_tokens(doc.get("title", "")))

    score = 0
    for token in query_tokens:
        if token in keyword_tokens:
            score += 3
        elif token in title_tokens:
            score += 2
        elif token in text_tokens:
            score += 1
    return score


def search_rules(query: str, limit: int = 3) -> List[Dict[str, Any]]:
    """Return up to ``limit`` rule docs best matching the query, by overlap."""
    docs = load_rules_lookup()
    if not docs:
        return []
    query_tokens = _tokens(query)
    scored = [(doc, _score(query_tokens, doc)) for doc in docs]
    matches = [doc for doc, score in scored if score > 0]
    matches.sort(key=lambda doc: _score(query_tokens, doc), reverse=True)
    return matches[:limit]


def format_rule_results(results: List[Dict[str, Any]]) -> str:
    """Format search results as readable snippets (truncated per result)."""
    if not results:
        return "No matching rules found."
    blocks = []
    for doc in results:
        text = str(doc.get("text", "")).strip()
        if len(text) > _SNIPPET_LIMIT:
            text = text[:_SNIPPET_LIMIT].rstrip() + " ..."
        blocks.append(
            f"Rule result: {doc.get('title', doc.get('id', 'Unknown'))}\n"
            f"Source: {doc.get('path', '(unknown path)')}\n\n"
            f"{text}"
        )
    return "\n\n---\n\n".join(blocks)
