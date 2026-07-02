"""Character-sheet helpers.

Reads ability scores, proficiencies, and expertise from a character dict and
computes DnD-style ability/skill modifiers and dice formulas. All lookups are
case-insensitive and tolerant of missing or malformed data — callers should
never crash on a bad character sheet.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# Canonical display order for the six ability scores.
ABILITY_ORDER = [
    "strength",
    "dexterity",
    "constitution",
    "intelligence",
    "wisdom",
    "charisma",
]


def ability_modifier(score: int) -> int:
    """Return the standard DnD ability modifier for a score: (score - 10) // 2."""
    return (score - 10) // 2


def get_ability_score(character: Dict[str, Any], ability: str) -> Optional[int]:
    """Return the integer ability score, or None if missing/unparseable.

    Ability lookup is case-insensitive (e.g. "Intelligence" -> "intelligence").
    """
    if not ability:
        return None
    abilities = character.get("abilities") or {}
    if not isinstance(abilities, dict):
        return None
    target = ability.strip().lower()
    for name, score in abilities.items():
        if str(name).strip().lower() == target:
            try:
                return int(score)
            except (TypeError, ValueError):
                return None
    return None


def _coerce_int(value: Any, default: int = 0) -> int:
    """Best-effort int coercion with a fallback default."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _contains_skill(skill: Optional[str], names: List[Any]) -> bool:
    """Case-insensitive membership test for a skill name in a list."""
    if not skill or not isinstance(names, list):
        return False
    target = skill.strip().lower()
    return any(str(name).strip().lower() == target for name in names)


def get_skill_modifier(
    character: Dict[str, Any],
    ability: str,
    skill: Optional[str] = None,
) -> Dict[str, Any]:
    """Compute the modifier and 1d20 formula for an ability/skill check.

    Starts from the ability modifier, adds the proficiency bonus if the skill
    is a proficiency, and adds it again for expertise. With no skill, only the
    ability modifier applies. Returns structured data including the formula.
    """
    score = get_ability_score(character, ability)
    ability_mod = ability_modifier(score) if score is not None else 0
    prof_bonus = _coerce_int(character.get("proficiency_bonus", 0))

    proficiencies = character.get("skill_proficiencies") or []
    expertise = character.get("skill_expertise") or []
    is_proficient = _contains_skill(skill, proficiencies)
    has_expertise = _contains_skill(skill, expertise)

    total = ability_mod
    if skill:
        if is_proficient:
            total += prof_bonus
        if has_expertise:
            total += prof_bonus

    return {
        "ability": ability,
        "skill": skill,
        "ability_score": score,
        "ability_modifier": ability_mod,
        "proficiency_bonus": prof_bonus,
        "is_proficient": is_proficient,
        "has_expertise": has_expertise,
        "total_modifier": total,
        "formula": f"1d20{total:+d}",
    }
