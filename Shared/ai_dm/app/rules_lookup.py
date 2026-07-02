"""Simple local rules lookup (keyword overlap, no embeddings, no network).

Loads the lookup index built by ``build_rules_lookup.py`` and scores each rule
doc against a query by keyword/text overlap. This is deliberately minimal;
vector search will come in a later milestone.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

import state_store

# Shown when the lookup index has not been built yet.
NOT_INSTALLED_MESSAGE = (
    "No rules lookup index found. Build the local rules library first:\n"
    "  python3 Shared/ai_dm/rules/scripts/install_rules.py\n"
    "  python3 Shared/ai_dm/rules/scripts/build_rules_lookup.py"
)

_SNIPPET_LIMIT = 800

# Player-input keyword -> rules search query. Longer/more specific keys are
# matched first (see build_rules_query) so "short rest" beats a bare "rest".
RULE_QUERY_HINTS = {
    "grapple": "grappled combat athletics",
    "grappled": "grappled condition combat",
    "prone": "prone condition",
    "restrained": "restrained condition",
    "stunned": "stunned condition",
    "frightened": "frightened condition",
    "charmed": "charmed condition",

    "attack": "combat attack action",
    "initiative": "combat initiative",
    "reaction": "combat reaction",
    "bonus action": "combat bonus action",
    "dash": "combat action movement",
    "disengage": "combat action movement",
    "dodge": "combat action",
    "help": "combat action help",

    "short rest": "short rest healing hit dice",
    "long rest": "long rest healing recovery",
    "hit dice": "short rest hit dice healing",

    "death save": "death saving throw dying zero hit points",
    "death saving throw": "death saving throw dying zero hit points",
    "unconscious": "unconscious dying hit points",
    "zero hit points": "zero hit points dying death saving throw",

    "grab": "grappled combat athletics",
    "grabbing": "grappled combat athletics",
    "grappling": "grappled combat athletics",
    "wrestle": "grappled combat athletics",

    "search": "ability checks investigation perception dc",
    "inspect": "ability checks investigation perception dc",
    "investigate": "ability checks investigation perception dc",
    "look for": "ability checks investigation perception dc",
    "hidden markings": "ability checks investigation perception dc",
    "listen": "ability checks perception dc",
    "perception": "ability checks perception dc",
    "investigation": "ability checks investigation dc",
    "stealth": "ability checks stealth dc",
    "athletics": "ability checks athletics dc",
    "persuasion": "ability checks persuasion dc",
}

# Question openers that signal a rules/mechanics query, not an in-fiction action.
_RULES_QUESTION_STARTERS = (
    "can i", "can you", "how do", "how does", "what happens", "what does",
    "what do i roll", "do i need to roll", "do i roll", "is it possible",
)

# Rules/mechanics keywords; a rules question must mention at least one.
_RULES_MECHANICS_KEYWORDS = (
    "grapple", "grappling", "grab", "wrestle", "attack", "short rest",
    "long rest", "condition", "restrained", "prone", "stunned", "frightened",
    "charmed", "death save", "zero hit points", "unconscious", "dying",
    "perception", "investigation", "stealth", "sneak", "hide", "athletics",
    "ability check", "skill check", "saving throw", "initiative", "roll",
)


def _tokens(text: str) -> List[str]:
    """Lower-case alphanumeric word tokens."""
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def load_rules_lookup() -> List[Dict[str, Any]]:
    """Return the list of indexed rule docs, or [] if the index is missing."""
    return _load_json_list(state_store.RULES_LOOKUP_INDEX)


def load_rules_glossary() -> List[Dict[str, Any]]:
    """Return the canonical glossary entries, or [] if none are built."""
    return _load_json_list(state_store.RULES_GLOSSARY_INDEX)


def _load_json_list(path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


# Multi-word rule phrases; an exact phrase match scores much higher than loose
# single-token overlap, so rule-relevant chunks beat incidental keyword hits.
RULE_PHRASES = (
    "ability check", "saving throw", "attack roll", "difficulty class",
    "short rest", "long rest", "hit dice", "death saving throw",
    "zero hit points", "bonus action", "opportunity attack",
    "grapple", "grappled", "prone", "restrained", "stunned", "frightened",
    "charmed", "incapacitated", "unconscious", "advantage", "disadvantage",
    "proficiency", "initiative", "spellcasting", "athletics", "perception",
    "investigation", "stealth",
)


def _looks_like_toc(text: str) -> bool:
    """True if text is dominated by table-of-contents dotted-leader lines."""
    lines = [line for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return False
    leader_lines = sum(1 for line in lines if re.search(r"\.{5,}", line))
    return leader_lines / len(lines) > 0.25


# Cues that a chunk is a feat/item/ancestry body rather than a rule definition.
_INCIDENTAL_CUES = (
    "prerequisite", "this feat", "martial weapon", "this weapon", "ancestry",
    "lineage", "powerful build", "you gain the following",
)


def _score(query: str, query_tokens: List[str], doc: Dict[str, Any]) -> int:
    """Score a chunk doc: phrase + position matter more than loose overlap."""
    if not query_tokens:
        return 0
    lowered_query = query.lower()
    text = str(doc.get("text", ""))
    lowered_text = text.lower()
    keyword_tokens = set()
    keyword_blob = " ".join(str(k) for k in doc.get("keywords", [])).lower()
    for keyword in doc.get("keywords", []):
        keyword_tokens.update(_tokens(str(keyword)))
    text_tokens = set(_tokens(text))
    title_tokens = set(_tokens(doc.get("title", "")))

    score = 0
    for phrase in RULE_PHRASES:
        if phrase in lowered_query and (
            phrase in lowered_text or phrase in keyword_blob
        ):
            score += 6
            pos = lowered_text.find(phrase)
            if 0 <= pos < 200:
                score += 4  # definition-like: term near the start
            elif pos > 500:
                score -= 2  # likely an incidental mention deep in the body
            if lowered_text.count(phrase) == 1 and pos > 500:
                score -= 2  # mentioned once, late — probably incidental

    for token in query_tokens:
        if token in keyword_tokens:
            score += 3
        elif token in title_tokens:
            score += 2
        elif token in text_tokens:
            score += 1

    # Demote feat/item/ancestry bodies and TOC-only snippets.
    if any(cue in lowered_text for cue in _INCIDENTAL_CUES):
        score -= 5
    if _looks_like_toc(text):
        score -= 8

    return score


def _glossary_doc(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Shape a glossary entry as a result doc for formatting/display."""
    source = entry.get("source", "SRD 5.2.1 glossary")
    return {
        "id": entry.get("id"),
        "title": entry.get("title", entry.get("term", "Rule")),
        "path": source,
        "source": source,
        "license": entry.get("license", "CC-BY-4.0"),
        "text": entry.get("text", ""),
        "keywords": [entry.get("term", "")] + list(entry.get("aliases", [])),
        "glossary": True,
    }


def _glossary_matches(query: str, query_tokens: List[str]) -> List[Dict[str, Any]]:
    """Return glossary entries matching the query, best (most specific) first."""
    entries = load_rules_glossary()
    if not entries:
        return []
    lowered_query = query.lower()
    token_set = set(query_tokens)

    scored = []
    for entry in entries:
        term = str(entry.get("term", "")).lower()
        aliases = [str(a).lower() for a in entry.get("aliases", [])]
        title = str(entry.get("title", "")).lower()
        score = 0
        if term and (term in lowered_query or term in token_set):
            score = max(score, 1000)
        for alias in aliases:
            if alias and (alias in lowered_query or alias in token_set):
                score = max(score, 900)
        if title and title in lowered_query:
            score = max(score, 500)
        if score > 0:
            scored.append((entry, score, len(term)))

    # Highest score first; break ties toward the more specific (longer) term.
    scored.sort(key=lambda item: (item[1], item[2]), reverse=True)
    return [_glossary_doc(entry) for entry, _score_val, _len in scored]


def search_rules(query: str, limit: int = 3) -> List[Dict[str, Any]]:
    """Return up to ``limit`` results, canonical glossary entries first.

    Order: (1) canonical glossary term/alias matches, then (2) chunk lookup by
    phrase/position scoring. TOC snippets are filtered from chunk results.
    """
    query_tokens = _tokens(query)
    results: List[Dict[str, Any]] = []
    seen_ids = set()

    for doc in _glossary_matches(query, query_tokens):
        if doc.get("id") in seen_ids:
            continue
        results.append(doc)
        seen_ids.add(doc.get("id"))
        if len(results) >= limit:
            return results

    docs = load_rules_lookup()
    if docs:
        scored = [(doc, _score(query, query_tokens, doc)) for doc in docs]
        matches = [
            doc for doc, score in scored
            if score > 0 and not _looks_like_toc(doc.get("text", ""))
        ]
        matches.sort(key=lambda doc: _score(query, query_tokens, doc), reverse=True)
        for doc in matches:
            if doc.get("id") in seen_ids:
                continue
            results.append(doc)
            seen_ids.add(doc.get("id"))
            if len(results) >= limit:
                break

    return results[:limit]


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


def is_rules_question(text: str) -> bool:
    """Return True if the input reads as a rules/mechanics question.

    Requires a question signal (a "?" or a known question opener) *and* a
    rules/mechanics keyword, so ordinary questions like "Do you trust me?"
    are not misclassified.
    """
    if not text:
        return False
    lowered = text.strip().lower()
    has_signal = "?" in lowered or any(
        lowered.startswith(starter) for starter in _RULES_QUESTION_STARTERS
    )
    if not has_signal:
        return False
    return any(keyword in lowered for keyword in _RULES_MECHANICS_KEYWORDS)


# Backwards-compatible alias for the earlier name.
looks_like_rules_question = is_rules_question


# Deterministic local fallbacks used when the model ignores a rules question.
# Each: question keywords -> (tokens a good answer should contain, fallback text).
_FALLBACKS = [
    {
        "match": ["grapple", "grappling", "grab", "grabbing", "wrestle"],
        "expect": ["grapple", "athletics", "strength"],
        "answer": (
            "Yes, if the target is within reach and you have a way to grab it. "
            "Grappling is a physical contest; use Strength (Athletics) unless a "
            "house rule says otherwise. If successful, the target is grappled "
            "and its speed becomes 0.\n\n"
            "In this scene, you would need to be close enough to reach the "
            "creature in the well.\n\n"
            "Do you try to grapple it?"
        ),
    },
    {
        "match": ["short rest"],
        "expect": ["short rest", "hit dice", "rest"],
        "answer": (
            "A short rest is at least 1 hour of light activity. During it you "
            "can spend Hit Dice to regain hit points, rolling each die and "
            "adding your Constitution modifier. Some abilities also recharge on "
            "a short rest.\n\n"
            "Do you want to take a short rest here?"
        ),
    },
    {
        "match": ["zero hit points", "death save", "death saving", "dying"],
        "expect": ["death", "dying", "saving", "unconscious", "zero"],
        "answer": (
            "At 0 hit points you fall unconscious and make a death saving throw "
            "each turn: roll a d20, 10 or higher is a success. Three successes "
            "and you stabilize; three failures and you die. A natural 20 "
            "restores 1 hit point; taking damage while down is a failed save.\n\n"
            "Do you want to keep going?"
        ),
    },
    {
        "match": ["restrained"],
        "expect": ["restrained", "speed"],
        "answer": (
            "While restrained, your speed is 0, you have disadvantage on attack "
            "rolls and Dexterity saving throws, and attacks against you have "
            "advantage.\n\n"
            "Do you want to try to break free?"
        ),
    },
    {
        "match": ["prone"],
        "expect": ["prone", "crawl"],
        "answer": (
            "While prone you can only crawl and have disadvantage on attack "
            "rolls. Melee attackers within reach have advantage against you; "
            "ranged attackers have disadvantage. Standing up costs half your "
            "movement.\n\n"
            "Do you want to drop prone or stand up?"
        ),
    },
    {
        "match": [
            "perception", "investigation", "investigate", "search", "notice",
        ],
        "expect": ["perception", "investigation", "check", "wisdom", "intelligence"],
        "answer": (
            "Noticing something usually calls for a Wisdom (Perception) check, "
            "while deducing clues from close inspection is Intelligence "
            "(Investigation). The DM sets a DC (about 13 for a moderate task).\n\n"
            "Do you want to make the check?"
        ),
    },
]


def rules_fallback(question: str) -> Optional[Dict[str, Any]]:
    """Return the fallback entry matching the question, or None."""
    lowered = (question or "").lower()
    for fallback in _FALLBACKS:
        if any(keyword in lowered for keyword in fallback["match"]):
            return fallback
    return None


def response_missing_answer(question: str, response_text: str) -> bool:
    """True if a fallback applies but the response lacks its expected terms.

    E.g. the question mentions "grapple" but the response contains none of
    "grapple", "athletics", or "strength" — treat it as a failed answer.
    """
    fallback = rules_fallback(question)
    if not fallback:
        return False
    text = (response_text or "").lower()
    return not any(token in text for token in fallback["expect"])


def build_rules_query(
    player_input: Optional[str] = None,
    pending_check: Optional[Dict[str, Any]] = None,
    resolved_check: Optional[Dict[str, Any]] = None,
) -> str:
    """Build a keyword search query from the available turn context.

    Combines player-input keyword hints with ability/skill/DC terms from a
    pending or resolved check. Returns an empty string if nothing matched.
    """
    parts: List[str] = []

    if player_input:
        text = player_input.lower()
        # Match longer keys first so "short rest" wins over any bare token.
        for keyword in sorted(RULE_QUERY_HINTS, key=len, reverse=True):
            if keyword in text:
                parts.append(RULE_QUERY_HINTS[keyword])

    check = resolved_check or pending_check
    if check:
        terms = ["ability checks"]
        skill = str(check.get("skill", "") or "").strip()
        ability = str(check.get("ability", "") or "").strip()
        if skill:
            terms.append(skill)
        if ability:
            terms.append(ability)
        if check.get("dc") is not None:
            terms.append("dc")
        parts.append(" ".join(terms))

    return " ".join(parts).strip()


def get_relevant_rules_context(
    player_input: Optional[str] = None,
    pending_check: Optional[Dict[str, Any]] = None,
    resolved_check: Optional[Dict[str, Any]] = None,
    limit: int = 3,
) -> str:
    """Return formatted rule snippets relevant to the turn, or "" if none.

    Builds a query from the context, runs the simple keyword lookup, and
    formats the top matches for insertion into the DM prompt.
    """
    query = build_rules_query(player_input, pending_check, resolved_check)
    if not query:
        return ""
    results = search_rules(query, limit=limit)
    if not results:
        return ""
    return format_rule_results(results)
