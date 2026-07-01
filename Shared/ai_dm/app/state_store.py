"""State store.

Loads local campaign/character/prompt files and appends session entries
to the local session log. All paths stay inside ``Shared/ai_dm/`` so that
private runtime data never leaves the repo folder on the USB/SSD.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

# Shared/ai_dm/ — the package root, resolved from this file's location.
AI_DM_ROOT = Path(__file__).resolve().parent.parent

CAMPAIGN_TEMPLATE = AI_DM_ROOT / "templates" / "campaigns" / "example_campaign.json"
CHARACTER_TEMPLATE = AI_DM_ROOT / "templates" / "characters" / "example_character.json"
DM_SYSTEM_PROMPT = AI_DM_ROOT / "prompts" / "dm_system.md"

SAVES_DIR = AI_DM_ROOT / "saves"
SESSION_LOG = SAVES_DIR / "current_session.md"


def load_json(path: Path) -> Dict[str, Any]:
    """Load and parse a JSON file, raising a clear error if missing."""
    if not path.exists():
        raise FileNotFoundError(f"Required JSON file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_text(path: Path) -> str:
    """Load a text/markdown file, raising a clear error if missing."""
    if not path.exists():
        raise FileNotFoundError(f"Required text file not found: {path}")
    return path.read_text(encoding="utf-8")


def load_campaign() -> Dict[str, Any]:
    """Load the campaign template."""
    return load_json(CAMPAIGN_TEMPLATE)


def load_character() -> Dict[str, Any]:
    """Load the character template."""
    return load_json(CHARACTER_TEMPLATE)


def load_dm_system_prompt() -> str:
    """Load the DM system prompt markdown."""
    return load_text(DM_SYSTEM_PROMPT)


def read_session_log() -> str:
    """Return the current session log, or an empty string if none exists."""
    if not SESSION_LOG.exists():
        return ""
    return SESSION_LOG.read_text(encoding="utf-8")


def append_session_entry(player_action: str, dm_response: str) -> None:
    """Append one player/DM exchange to the local session log.

    Creates the saves folder and log file if they do not yet exist.
    """
    SAVES_DIR.mkdir(parents=True, exist_ok=True)

    is_new = not SESSION_LOG.exists()
    with SESSION_LOG.open("a", encoding="utf-8") as handle:
        if is_new:
            handle.write("# Current Session Log\n\n")
        handle.write(f"## Player\n\n{player_action.strip()}\n\n")
        handle.write(f"## Dungeon Master\n\n{dm_response.strip()}\n\n")
        handle.write("---\n\n")


def _write_log(blocks: str) -> None:
    """Append pre-formatted markdown to the session log, creating it if new."""
    SAVES_DIR.mkdir(parents=True, exist_ok=True)
    is_new = not SESSION_LOG.exists()
    with SESSION_LOG.open("a", encoding="utf-8") as handle:
        if is_new:
            handle.write("# Current Session Log\n\n")
        handle.write(blocks)


def append_structured_turn(
    player_action: str,
    narration: str,
    check_summary: str,
    structured_json: str,
) -> None:
    """Append one structured DM turn to the local session log.

    Writes the player action, the player-visible narration (plus an optional
    "Suggested check" line), and the full structured JSON response. Hidden
    ``dm_notes`` are part of the structured block only, never shown as
    player-facing narration.
    """
    parts = [
        f"## Player\n\n{player_action.strip()}\n\n",
        f"## DM\n\n{narration.strip()}\n\n",
    ]
    if check_summary:
        parts.append(f"Suggested check: {check_summary}\n\n")
    parts.append(
        "## DM Structured Response\n\n"
        f"```json\n{structured_json.strip()}\n```\n\n---\n\n"
    )
    _write_log("".join(parts))


def append_failed_turn(player_action: str, raw_response: str) -> None:
    """Append a DM turn whose response could not be parsed as JSON.

    Saves the raw model output for debugging without crashing the loop.
    """
    _write_log(
        f"## Player\n\n{player_action.strip()}\n\n"
        "## DM (unparsed response)\n\n"
        "The model did not return valid JSON. Raw response saved below:\n\n"
        f"```\n{raw_response.strip()}\n```\n\n---\n\n"
    )


def append_roll_entry(result: Dict[str, Any]) -> None:
    """Append a dice-roll result to the local session log.

    ``result`` is the structured dict returned by ``dice.roll_dice`` with
    ``formula``, ``rolls``, ``modifier`` and ``total`` keys.
    """
    SAVES_DIR.mkdir(parents=True, exist_ok=True)

    is_new = not SESSION_LOG.exists()
    with SESSION_LOG.open("a", encoding="utf-8") as handle:
        if is_new:
            handle.write("# Current Session Log\n\n")
        handle.write("### Dice Roll\n\n")
        handle.write(f"Formula: `{result['formula']}`  \n")
        handle.write(f"Rolls: `{result['rolls']}`  \n")
        handle.write(f"Modifier: `{result['modifier']}`  \n")
        handle.write(f"Total: `{result['total']}`\n\n")
        handle.write("---\n\n")
