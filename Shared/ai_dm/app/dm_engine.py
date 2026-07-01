"""DM engine.

Builds the prompt/context sent to the local model for a single Dungeon
Master turn. Assembles campaign state, character state, the recent session
log, and the latest player input into an Ollama-style ``messages`` list.
"""

from __future__ import annotations

from typing import Any, Dict, List

# Behavioural instructions layered on top of the base system prompt.
DM_TURN_INSTRUCTIONS = """\
Turn instructions:
- Respond only as the Dungeon Master.
- Do not decide the player character's actions, thoughts, or dialogue.
- Do not reveal hidden DM-only context unless the player has discovered it in play.
- Keep the response concise but atmospheric.
- Ask for a dice roll only when a roll is actually appropriate.
- End with a clear prompt inviting the player's next action."""


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


def build_messages(
    system_prompt: str,
    campaign: Dict[str, Any],
    character: Dict[str, Any],
    player_input: str,
    recent_log: str = "",
) -> List[Dict[str, str]]:
    """Assemble the full messages list for one DM turn.

    The system message combines the base DM system prompt, the turn
    instructions, the visible context block, and a clearly labelled hidden
    DM-only section containing the campaign secrets.
    """
    system_content = "\n\n".join(
        [
            system_prompt.strip(),
            DM_TURN_INSTRUCTIONS,
            build_context_block(campaign, character, recent_log),
            build_hidden_dm_section(campaign),
        ]
    )

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": player_input.strip()},
    ]
