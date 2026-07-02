"""Deterministic player-action check detection.

Before sending a player action to the LLM, the app inspects it for obvious
uncertain actions (searching, sneaking, persuading, ...) and creates the
matching ability check itself. This makes the app behave more like a game
engine: the app decides obvious mechanics, the LLM narrates the results.

Rules are simple, ordered keyword matches. The first matching rule wins, so
more specific rules are listed before broader ones.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_DC = 13

# Common words ignored when matching a player action against a scene trigger.
STOP_WORDS = {
    "i", "the", "a", "an", "and", "or", "to", "for", "of", "that", "someone",
    "has", "have", "had", "it", "is", "are", "was", "were", "around", "into",
    "at", "on", "in", "with", "by", "recently",
}

# Minimum number of shared meaningful words for a scene trigger to match.
_MIN_TRIGGER_OVERLAP = 2


def _meaningful_tokens(text: str) -> set:
    """Lower-case word tokens with stop words removed."""
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {word for word in words if word not in STOP_WORDS}


def detect_scene_check(
    player_input: str,
    current_scene: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Return a pending check derived from the scene's ``default_checks``.

    Matches by meaningful-word overlap between the player action and each
    check's ``trigger``. A check matches when at least ``_MIN_TRIGGER_OVERLAP``
    trigger words appear in the input; the highest-overlap check wins. Returns
    None when there is no scene or no check clears the threshold.
    """
    if not current_scene:
        return None

    checks = current_scene.get("default_checks") or []
    input_tokens = _meaningful_tokens(player_input)

    best_check = None
    best_score = 0
    for check in checks:
        if not isinstance(check, dict):
            continue
        overlap = _meaningful_tokens(check.get("trigger", "")) & input_tokens
        if len(overlap) >= _MIN_TRIGGER_OVERLAP and len(overlap) > best_score:
            best_score = len(overlap)
            best_check = check

    if not best_check:
        return None

    trigger = best_check.get("trigger", "")
    return {
        "ability": best_check.get("ability"),
        "skill": best_check.get("skill"),
        "dc": best_check.get("dc", DEFAULT_DC),
        "reason": f"Scene check: {trigger}",
        "source": "scene_default_check",
        "trigger": trigger,
        "success": best_check.get("success", ""),
        "failure": best_check.get("failure", ""),
    }

# Ordered rules: (keywords, ability, skill, reason). Keywords are matched
# case-insensitively on word boundaries, so "hide" will not match "hidden".
_RULES: List[Tuple[List[str], str, str, str]] = [
    (
        ["search", "inspect", "examine", "investigate",
         "check for hidden", "look for signs", "search for"],
        "Intelligence", "Investigation",
        "To search the area for hidden markings, loose blocks, or signs of recent use.",
    ),
    (
        ["listen", "hear", "look around", "watch", "spot", "notice", "peer into"],
        "Wisdom", "Perception",
        "To notice details in the surroundings.",
    ),
    (
        ["sneak", "hide", "move quietly", "creep"],
        "Dexterity", "Stealth",
        "To move without being seen or heard.",
    ),
    (
        ["climb", "force", "lift", "break", "shove"],
        "Strength", "Athletics",
        "To apply physical force or overcome a physical obstacle.",
    ),
    (
        ["balance", "dodge", "slip past", "move carefully"],
        "Dexterity", "Acrobatics",
        "To move with balance and agility.",
    ),
    (
        ["persuade", "convince", "negotiate"],
        "Charisma", "Persuasion",
        "To influence someone through reason or charm.",
    ),
    # Insight is checked before Deception so "read their face for a lie"
    # reads as sensing motive rather than telling one.
    (
        ["read their face", "sense motive", "do i believe", "sense their intent"],
        "Wisdom", "Insight",
        "To read someone's true intentions.",
    ),
    (
        ["lie", "deceive", "bluff"],
        "Charisma", "Deception",
        "To mislead someone convincingly.",
    ),
    (
        ["threaten", "intimidate"],
        "Charisma", "Intimidation",
        "To pressure someone through threats.",
    ),
    (
        ["know about magic", "recall magic", "arcane", "magical", "magic"],
        "Intelligence", "Arcana",
        "To recall magical or arcane lore.",
    ),
    (
        ["know about history", "recall history", "historical", "ancient", "history"],
        "Intelligence", "History",
        "To recall relevant historical knowledge.",
    ),
    (
        ["track", "tracks", "follow tracks", "forage", "navigate"],
        "Wisdom", "Survival",
        "To track, forage, or navigate the wilderness.",
    ),
]


def detect_required_check(player_input: str) -> Optional[Dict[str, object]]:
    """Return an ability check for an obvious player action, or None.

    The returned dict is tagged with ``"source": "action_detector"`` so the
    rest of the app can tell app-created checks from LLM-requested ones.
    """
    text = (player_input or "").lower()
    for keywords, ability, skill, reason in _RULES:
        for keyword in keywords:
            if re.search(rf"\b{re.escape(keyword)}\b", text):
                return {
                    "ability": ability,
                    "skill": skill,
                    "dc": DEFAULT_DC,
                    "reason": reason,
                    "source": "action_detector",
                }
    return None
