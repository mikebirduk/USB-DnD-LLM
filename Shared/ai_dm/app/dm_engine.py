"""DM engine.

Builds the prompt/context sent to the local model for a single Dungeon
Master turn. Assembles campaign state, character state, the recent session
log, and the latest player input into an Ollama-style ``messages`` list.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

# Behavioural instructions layered on top of the base system prompt.
DM_TURN_INSTRUCTIONS = """\
Turn instructions:
- Respond only as the Dungeon Master.
- Return valid JSON only. Do not wrap the JSON in markdown and do not add
  any commentary outside the JSON object.
- Do not decide the player character's actions, thoughts, or dialogue.
- Do not reveal hidden DM-only context unless the player has discovered it in play.
- Keep narration concise but atmospheric.
- Only request a check (set "requested_check") when failure would be interesting;
  otherwise set "requested_check" to null.
- Always end with a clear "prompt_to_player"."""

# Standard 5e skill -> default governing ability. Used to correct checks like
# "Dexterity (Perception)" back to the conventional "Wisdom (Perception)".
SKILL_DEFAULT_ABILITIES = {
    "Acrobatics": "Dexterity",
    "Animal Handling": "Wisdom",
    "Arcana": "Intelligence",
    "Athletics": "Strength",
    "Deception": "Charisma",
    "History": "Intelligence",
    "Insight": "Wisdom",
    "Intimidation": "Charisma",
    "Investigation": "Intelligence",
    "Medicine": "Wisdom",
    "Nature": "Intelligence",
    "Perception": "Wisdom",
    "Performance": "Charisma",
    "Persuasion": "Charisma",
    "Religion": "Intelligence",
    "Sleight of Hand": "Dexterity",
    "Stealth": "Dexterity",
    "Survival": "Wisdom",
}

# Case-insensitive lookup: lower-cased skill -> (canonical skill, ability).
_SKILL_LOOKUP = {
    skill.lower(): (skill, ability)
    for skill, ability in SKILL_DEFAULT_ABILITIES.items()
}


def normalise_check(check: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return a copy of ``check`` with a standard skill/ability pairing.

    If the check names a known skill, its ``ability`` is set to that skill's
    default governing ability and the ``skill`` name is canonicalised. Checks
    with no skill (e.g. a raw saving throw) are returned unchanged. The input
    dict is not mutated.
    """
    if not isinstance(check, dict):
        return check

    normalised = dict(check)
    skill = str(check.get("skill", "")).strip()
    if skill:
        match = _SKILL_LOOKUP.get(skill.lower())
        if match:
            canonical_skill, default_ability = match
            normalised["skill"] = canonical_skill
            normalised["ability"] = default_ability
    return normalised


def parse_dm_response(text: str) -> Dict[str, Any]:
    """Parse a model response into the structured DM response dict.

    Tolerates a stray ```json fenced code block in case the model ignores
    the "no markdown" instruction. Raises ``ValueError`` if the text is not
    valid JSON or is not a JSON object.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Drop the opening fence (``` or ```json) and the closing fence.
        cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else ""
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[: -len("```")]
        cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model response was not valid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Model response JSON was not an object.")

    return parsed


def format_check_summary(check: Optional[Dict[str, Any]]) -> str:
    """Format a ``requested_check`` dict as e.g. ``Wisdom (Perception), DC 13``.

    Returns an empty string when there is no check.
    """
    if not check:
        return ""

    ability = str(check.get("ability", "")).strip() or "Check"
    skill = str(check.get("skill", "")).strip()
    dc = check.get("dc")

    summary = f"{ability} ({skill})" if skill else ability
    if dc is not None:
        summary += f", DC {dc}"
    return summary


def build_roll_resolution_prompt(
    check: Dict[str, Any],
    roll: Dict[str, Any],
    outcome: str,
    authoritative_outcome: str = "",
) -> str:
    """Build the follow-up player message telling the DM how a check resolved.

    The DM should narrate the outcome and continue the scene rather than
    requesting the same check again. When ``authoritative_outcome`` is given
    (scene-defined success/failure text), it is presented as already-resolved
    fact the DM must narrate without contradiction or a new check.
    """
    prompt = (
        "The player rolled for the pending check.\n\n"
        "Check:\n"
        f"- Ability: {check.get('ability', '')}\n"
        f"- Skill: {check.get('skill', '')}\n"
        f"- DC: {check.get('dc', '')}\n"
        f"- Reason: {check.get('reason', '')}\n\n"
        "Roll:\n"
        f"- Formula: {roll['formula']}\n"
        f"- Rolls: {roll['rolls']}\n"
        f"- Modifier: {roll['modifier']}\n"
        f"- Total: {roll['total']}\n"
        f"- Outcome: {outcome}\n\n"
        "Important:\n"
        "- Narrate the outcome based on the roll result.\n"
        "- If the outcome is success, reveal useful information, progress, or "
        "advantage.\n"
        "- If the outcome is failure, do NOT reveal the hidden clue or the "
        "same useful information a success would have provided.\n"
        "- On failure, you may narrate uncertainty, delay, misleading "
        "impressions, increased danger, noise, lost time, or a complication.\n"
        "- Do not contradict the roll outcome.\n"
        "- Do not ask for the same check again.\n"
        "- Continue the scene naturally.\n\n"
        "Examples of GOOD failure narration (for a Perception/Investigation "
        "check):\n"
        "- You find only old moss, damp stone, and scratches too weathered to "
        "understand.\n"
        "- You cannot tell whether the marks are recent.\n"
        "- As you search, a small stone drops into the well, echoing loudly "
        "below.\n"
        "- You spend several minutes searching, but the dark and damp hide "
        "whatever truth might be there.\n\n"
        "Examples of BAD failure narration (never do this — it leaks the "
        "clue):\n"
        "- You fail, but discover the hidden loose stone.\n"
        "- You fail, but clearly see fresh rope marks.\n"
        "- You fail, but notice the secret latch."
    )

    success_text = str(check.get("success", "")).strip()
    failure_text = str(check.get("failure", "")).strip()
    if success_text or failure_text:
        prompt += (
            "\n\nScene-defined outcome guidance:\n"
            f"Success: {success_text}\n"
            f"Failure: {failure_text}\n\n"
            "Use the correct outcome guidance based on the roll result.\n"
            "Do not reveal success-only information on failure."
        )

    if authoritative_outcome.strip():
        prompt += (
            "\n\nThe game engine has already resolved the check.\n\n"
            "Authoritative outcome:\n"
            f"{authoritative_outcome.strip()}\n\n"
            "You must narrate this outcome.\n"
            "Do not contradict it.\n"
            "Do not reveal success-only information on failure.\n"
            "Do not request a new check in this response.\n"
            "Set requested_check to null.\n"
            "Continue the scene naturally after the resolved outcome."
        )

    return prompt


def _format_hp(hp: Any) -> str:
    """Render an HP value that may be a dict ({current,max}) or a scalar."""
    if isinstance(hp, dict):
        return f"{hp.get('current', '?')}/{hp.get('max', '?')}"
    return str(hp)


def _format_list(items: Any) -> str:
    """Render a list of threads/strings as a compact bulleted block."""
    if not items:
        return "(none)"
    if isinstance(items, list):
        return "\n".join(f"- {item}" for item in items)
    return str(items)


def build_context_block(
    campaign: Dict[str, Any],
    character: Dict[str, Any],
    recent_log: str = "",
) -> str:
    """Build the visible campaign/character context block."""
    lines = [
        "# Campaign Context",
        f"Title: {campaign.get('campaign_title', 'Untitled')}",
        f"Tone: {campaign.get('tone', 'unspecified')}",
        f"Current location: {campaign.get('current_location', 'unknown')}",
        "",
        "Player-visible summary:",
        campaign.get("player_visible_summary", "(none)"),
        "",
        "Open threads:",
        _format_list(campaign.get("open_threads")),
        "",
        "# Player Character",
        f"Name: {character.get('name', 'Unknown')}",
        f"Class: {character.get('class', 'Unknown')}",
        f"Level: {character.get('level', '?')}",
        f"HP: {_format_hp(character.get('hp'))}",
        f"AC: {character.get('ac', '?')}",
    ]

    if recent_log.strip():
        lines += [
            "",
            "# Recent Session Log",
            recent_log.strip(),
        ]

    return "\n".join(lines)


def build_hidden_dm_section(campaign: Dict[str, Any]) -> str:
    """Build the clearly-labelled hidden DM-only section.

    The DM secrets are wrapped in an explicit warning so the model treats
    them as private context that must not be revealed directly.
    """
    secrets = campaign.get("dm_secrets") or []
    return (
        "# HIDDEN DM-ONLY CONTEXT (DO NOT REVEAL DIRECTLY)\n"
        "The following is secret knowledge available only to you as the "
        "Dungeon Master. Never state it outright to the player. Only let it "
        "surface gradually through the fiction if the player earns or "
        "discovers it in play.\n"
        f"{_format_list(secrets)}"
    )


SCENE_INSTRUCTION = (
    "Respond directly to the latest player action using the current scene. Do "
    "not repeat the full scene description on every turn. Use the scene's "
    "hidden truths only when discovered through player action, successful "
    "checks, or appropriate consequences."
)


def build_scene_block(scene: Dict[str, Any]) -> str:
    """Build the player-visible current-scene context block."""
    interactions = scene.get("obvious_interactions") or []
    lines = [
        "# Current Scene",
        SCENE_INSTRUCTION,
        "",
        f"Title: {scene.get('scene_title', 'Untitled scene')}",
        f"Location: {scene.get('location', 'unknown')}",
        "",
        "Player-visible description:",
        scene.get("player_visible", "(none)"),
        "",
        "Sensory details:",
        _format_list(scene.get("sensory_details")),
        "",
        "Current situation:",
        scene.get("current_situation", "(none)"),
        "",
        "Obvious interactions:",
        _format_list(interactions),
    ]
    return "\n".join(lines)


def _format_default_checks(checks: Any) -> str:
    """Render the scene's default checks as mechanics guidance."""
    if not checks or not isinstance(checks, list):
        return "(none)"
    blocks = []
    for check in checks:
        if not isinstance(check, dict):
            continue
        skill = check.get("skill", "")
        ability = check.get("ability", "")
        dc = check.get("dc", "")
        blocks.append(
            f"- Trigger: {check.get('trigger', '')}\n"
            f"  Check: {ability} ({skill}), DC {dc}\n"
            f"  On success: {check.get('success', '')}\n"
            f"  On failure: {check.get('failure', '')}"
        )
    return "\n".join(blocks) if blocks else "(none)"


def build_scene_dm_section(scene: Dict[str, Any]) -> str:
    """Build the DM-only scene section: hidden truths and mechanics guidance."""
    return (
        "# CURRENT SCENE — DM-ONLY (DO NOT REVEAL DIRECTLY)\n"
        "Hidden truths. Reveal these only when the player discovers them "
        "through action, a successful check, or a consequence:\n"
        f"{_format_list(scene.get('hidden_truths'))}\n\n"
        "Mechanics guidance — default checks for this scene. Use these DCs and "
        "success/failure outcomes when the matching action occurs:\n"
        f"{_format_default_checks(scene.get('default_checks'))}"
    )


def build_messages(
    system_prompt: str,
    campaign: Dict[str, Any],
    character: Dict[str, Any],
    player_input: str,
    recent_log: str = "",
    scene: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    """Assemble the full messages list for one DM turn.

    The system message combines the base DM system prompt, the turn
    instructions, the visible context block, the current scene (if any), and
    clearly labelled DM-only sections for campaign secrets and scene truths.
    """
    sections = [
        system_prompt.strip(),
        DM_TURN_INSTRUCTIONS,
        build_context_block(campaign, character, recent_log),
    ]
    if scene:
        sections.append(build_scene_block(scene))
    sections.append(build_hidden_dm_section(campaign))
    if scene:
        sections.append(build_scene_dm_section(scene))

    return [
        {"role": "system", "content": "\n\n".join(sections)},
        {"role": "user", "content": player_input.strip()},
    ]
