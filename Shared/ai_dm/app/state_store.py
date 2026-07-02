"""State store.

Loads local campaign/character/prompt files and appends session entries
to the local session log. All paths stay inside ``Shared/ai_dm/`` so that
private runtime data never leaves the repo folder on the USB/SSD.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

# Shared/ai_dm/ — the package root, resolved from this file's location.
AI_DM_ROOT = Path(__file__).resolve().parent.parent

CAMPAIGN_TEMPLATE = AI_DM_ROOT / "templates" / "campaigns" / "example_campaign.json"
CHARACTER_TEMPLATE = AI_DM_ROOT / "templates" / "characters" / "example_character.json"
SCENES_TEMPLATE_DIR = AI_DM_ROOT / "templates" / "scenes"
DEFAULT_SCENE_TEMPLATE = "old_well_scene"
DM_SYSTEM_PROMPT = AI_DM_ROOT / "prompts" / "dm_system.md"

SAVES_DIR = AI_DM_ROOT / "saves"
SESSION_LOG = SAVES_DIR / "current_session.md"
PENDING_CHECK = SAVES_DIR / "pending_check.json"
LAST_DM_RESPONSE = SAVES_DIR / "last_dm_response.json"
CURRENT_SCENE = SAVES_DIR / "current_scene.json"

# Local rules library (generated content is git-ignored).
RULES_DIR = AI_DM_ROOT / "rules"
RULES_SRD_VERSION = "5.2.1"
RULES_SRD_DIR = RULES_DIR / "srd" / RULES_SRD_VERSION
RULES_LOOKUP_INDEX = RULES_SRD_DIR / "lookup" / "rules_lookup.json"
INSTALLED_RULES = RULES_DIR / "installed-rules.json"


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


# ---------------------------------------------------------------------------
# Scene state — the concrete scenario the DM narrates from. The active scene
# is copied from a template into saves/current_scene.json (git-ignored).
# ---------------------------------------------------------------------------


def load_scene_template(scene_name: str) -> Dict[str, Any]:
    """Load a scene template by name (with or without the .json suffix)."""
    name = scene_name[:-5] if scene_name.endswith(".json") else scene_name
    return load_json(SCENES_TEMPLATE_DIR / f"{name}.json")


def load_current_scene() -> Optional[Dict[str, Any]]:
    """Return the active scene, or None if there is none or it is unreadable."""
    if not CURRENT_SCENE.exists():
        return None
    try:
        data = json.loads(CURRENT_SCENE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def save_current_scene(scene: Dict[str, Any]) -> None:
    """Persist the active scene to saves/current_scene.json."""
    SAVES_DIR.mkdir(parents=True, exist_ok=True)
    CURRENT_SCENE.write_text(
        json.dumps(scene, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def ensure_current_scene() -> Dict[str, Any]:
    """Return the active scene, initialising it from the default template.

    If saves/current_scene.json exists and is readable it is returned as-is;
    otherwise the default scene template is loaded, saved as the active scene,
    and returned.
    """
    scene = load_current_scene()
    if scene is not None:
        return scene
    scene = load_scene_template(DEFAULT_SCENE_TEMPLATE)
    save_current_scene(scene)
    return scene


def read_session_log() -> str:
    """Return the current session log, or an empty string if none exists."""
    if not SESSION_LOG.exists():
        return ""
    return SESSION_LOG.read_text(encoding="utf-8")


def load_installed_rules() -> Optional[Dict[str, Any]]:
    """Return the installed-rules metadata, or None if absent/unreadable."""
    if not INSTALLED_RULES.exists():
        return None
    try:
        data = json.loads(INSTALLED_RULES.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


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


# ---------------------------------------------------------------------------
# Pending check state — a single check the DM has requested but not resolved.
# Stored as local runtime JSON under saves/ (git-ignored).
# ---------------------------------------------------------------------------


def save_pending_check(check: Dict[str, Any]) -> None:
    """Persist the current pending check to ``pending_check.json``."""
    SAVES_DIR.mkdir(parents=True, exist_ok=True)
    PENDING_CHECK.write_text(
        json.dumps(check, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_pending_check() -> Optional[Dict[str, Any]]:
    """Return the pending check, or None if there is none or it is unreadable.

    Never raises on a missing or corrupt file — a broken pending check simply
    means "no pending check" rather than crashing the loop.
    """
    if not PENDING_CHECK.exists():
        return None
    try:
        data = json.loads(PENDING_CHECK.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def clear_pending_check() -> None:
    """Remove the pending check file if it exists."""
    PENDING_CHECK.unlink(missing_ok=True)


def save_last_dm_response(debug: Dict[str, Any]) -> None:
    """Persist the last parsed DM response and check debug data locally."""
    SAVES_DIR.mkdir(parents=True, exist_ok=True)
    LAST_DM_RESPONSE.write_text(
        json.dumps(debug, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_last_dm_response() -> Optional[Dict[str, Any]]:
    """Return the last DM response debug data, or None if unavailable."""
    if not LAST_DM_RESPONSE.exists():
        return None
    try:
        data = json.loads(LAST_DM_RESPONSE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def append_detected_check(
    player_action: str,
    check_summary: str,
    reason: str,
) -> None:
    """Append a player action and an engine-detected pending check to the log."""
    parts = [
        f"## Player\n\n{player_action.strip()}\n\n",
        "### Pending Check (engine-detected)\n\n",
        f"Check: {check_summary}  \n",
    ]
    if reason:
        parts.append(f"Reason: {reason}  \n")
    parts.append("\n---\n\n")
    _write_log("".join(parts))


def append_check_resolution(
    check_summary: str,
    reason: str,
    roll: Dict[str, Any],
    outcome: str,
    authoritative_outcome: str = "",
) -> None:
    """Append a resolved check (check details + roll + outcome) to the log.

    When ``authoritative_outcome`` is provided (scene-defined success/failure
    text), it is recorded as the definitive outcome of the check.
    """
    lines = [
        "### Resolved Check\n\n",
        f"Check: {check_summary}  \n",
    ]
    if reason:
        lines.append(f"Reason: {reason}  \n")
    lines += [
        f"Formula: `{roll['formula']}`  \n",
        f"Rolls: `{roll['rolls']}`  \n",
        f"Modifier: `{roll['modifier']}`  \n",
        f"Total: `{roll['total']}`  \n",
        f"Outcome: `{outcome}`  \n",
    ]
    if authoritative_outcome.strip():
        lines.append(f"\nAuthoritative outcome:\n{authoritative_outcome.strip()}\n")
    lines.append("\n---\n\n")
    _write_log("".join(lines))


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
