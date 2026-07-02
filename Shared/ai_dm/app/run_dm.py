#!/usr/bin/env python3
"""Terminal runner for the Milestone 1 AI Dungeon Master loop.

Run with:

    python3 Shared/ai_dm/app/run_dm.py

Loads the campaign and character templates, then loops: read a player
action, send it to the local Ollama model with campaign context, print the
DM reply, and append the exchange to the local session log.

Commands:
    /roll <formula>   roll dice; resolves a pending check if one is active
    /check            show the current pending check, if any
    /scene            show the player-facing view of the current scene
    /scene-debug      show the full current scene JSON (dev only)
    /reset-scene      reload the default scene template as the active scene
    /detect <action>  show the check the action detector would create
    /narrate <action> send an action to the DM, skipping check detection
    /debug-last       show raw vs normalised check and last parsed response
    /recap            print the current saved session log
    /quit             exit
"""

from __future__ import annotations

import json
import sys
from collections import namedtuple
from pathlib import Path

# Allow running as a plain script (python3 .../run_dm.py) by ensuring the
# app package directory is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import action_detector
import dice
import dm_engine
import ollama_client
import state_store

# Everything a DM turn needs: resolved model plus loaded game context.
Ctx = namedtuple("Ctx", ["model", "system_prompt", "campaign", "character"])


def _print_welcome(campaign, character, model, scene) -> None:
    title = campaign.get("campaign_title", "Untitled Campaign")
    name = character.get("name", "Unknown Hero")
    scene_title = scene.get("scene_title", "Untitled scene") if scene else "(none)"
    print("=" * 60)
    print("  AI Dungeon Master — Milestone 1 prototype")
    print("=" * 60)
    print(f"  Campaign : {title}")
    print(f"  Character: {name}")
    print(f"Current scene: {scene_title}")
    print("-" * 60)
    print(f"Using model: {model}")
    print(f"Ollama endpoint: {ollama_client.OLLAMA_HOST}")
    print("-" * 60)
    print(
        "  Type an action to play. Commands: /roll <formula>  /check  /scene  "
        "/scene-debug  /reset-scene  /detect <action>  /narrate <action>  "
        "/debug-last  /recap  /quit"
    )
    print("=" * 60)
    print()


def _coerce_dc(value) -> int | None:
    """Return the DC as an int, or None if it is missing/not numeric."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _handle_check() -> None:
    """Show the current pending check, if any."""
    pending = state_store.load_pending_check()
    if not pending:
        print("No pending check.\n")
        return
    summary = dm_engine.format_check_summary(pending)
    print("Pending check:")
    print(summary)
    reason = str(pending.get("reason", "")).strip()
    if reason:
        print(f"Reason: {reason}")
    print()


def _handle_scene() -> None:
    """Print the player-facing view of the current scene (no hidden truths)."""
    scene = state_store.load_current_scene()
    if not scene:
        print("No current scene.\n")
        return
    print(f"\nScene: {scene.get('scene_title', 'Untitled scene')}")
    print(f"Location: {scene.get('location', 'unknown')}\n")
    print(scene.get("player_visible", "(no description)"))
    situation = str(scene.get("current_situation", "")).strip()
    if situation:
        print(f"\nSituation: {situation}")
    interactions = scene.get("obvious_interactions") or []
    if interactions:
        print("\nObvious interactions:")
        for item in interactions:
            print(f"- {item}")
    print()


def _handle_scene_debug() -> None:
    """Print the full current scene JSON, including hidden truths (dev only)."""
    scene = state_store.load_current_scene()
    if not scene:
        print("No current scene.\n")
        return
    print(json.dumps(scene, indent=2, ensure_ascii=False))
    print()


def _handle_reset_scene() -> None:
    """Reload the default scene template and make it the active scene."""
    try:
        scene = state_store.load_scene_template(state_store.DEFAULT_SCENE_TEMPLATE)
    except FileNotFoundError as exc:
        print(f"Could not reset scene: {exc}\n", file=sys.stderr)
        return
    state_store.save_current_scene(scene)
    print(f"Scene reset to: {scene.get('scene_title', 'Untitled scene')}\n")


def _detect_check(player_input: str):
    """Detect a check for the action: scene default checks first, then the
    generic keyword detector as a fallback. Returns a normalised check or None.
    """
    scene = state_store.load_current_scene()
    check = action_detector.detect_scene_check(player_input, scene)
    if not check:
        check = action_detector.detect_required_check(player_input)
    return dm_engine.normalise_check(check) if check else None


def _handle_detect(action: str) -> None:
    """Print the scene check the action would trigger, without saving it."""
    action = action.strip()
    if not action:
        print("Usage: /detect <action>\n")
        return
    scene = state_store.load_current_scene()
    check = action_detector.detect_scene_check(action, scene)
    if not check:
        print("No scene check detected.\n")
        return
    check = dm_engine.normalise_check(check)
    print("Detected scene check:")
    print(dm_engine.format_check_summary(check))
    trigger = str(check.get("trigger", "")).strip()
    if trigger:
        print(f"Trigger: {trigger}")
    print()


def _handle_player_action(player_input: str, ctx: Ctx) -> None:
    """Detect a scene/keyword check, else send the action to the DM.

    If a check is detected, the app creates the pending check itself and waits
    for the player to roll rather than calling the LLM.
    """
    check = _detect_check(player_input)
    if not check:
        _dm_turn(player_input, ctx)
        return

    check_summary = dm_engine.format_check_summary(check)
    reason = str(check.get("reason", "")).strip()

    state_store.save_pending_check(check)
    state_store.append_detected_check(player_input, check_summary, reason)

    print("\nThis action calls for a check:")
    print(check_summary)
    if reason:
        print(f"Reason: {reason}")
    print("Use: /roll 1d20+<modifier>\n")


def _handle_debug_last() -> None:
    """Show debug data for the last DM response: raw vs normalised check."""
    data = state_store.load_last_dm_response()
    if not data:
        print("No debug data yet.\n")
        return
    print("\nraw requested_check:")
    print(json.dumps(data.get("raw_requested_check"), indent=2, ensure_ascii=False))
    print("\nnormalised requested_check:")
    print(json.dumps(data.get("normalised_requested_check"), indent=2, ensure_ascii=False))
    print("\nlast parsed response:")
    print(json.dumps(data.get("parsed_response"), indent=2, ensure_ascii=False))
    print()


def _handle_roll(formula: str, ctx: Ctx) -> None:
    """Roll a dice formula, print the result, and either log it as a plain
    roll or resolve it against a pending check.

    Shows a clear error and does not crash on an invalid formula.
    """
    formula = formula.strip()
    if not formula:
        print("Usage: /roll <formula>   e.g. /roll 1d20+3\n")
        return

    try:
        result = dice.roll_dice(formula)
    except ValueError as exc:
        print(f"Invalid dice formula: {exc}\n")
        return

    print(f"\nRoll: {result['formula']}")
    print(f"Dice: {result['rolls']}")
    print(f"Modifier: {result['modifier']:+d}")
    print(f"Total: {result['total']}")

    pending = state_store.load_pending_check()
    dc = _coerce_dc(pending.get("dc")) if pending else None

    if not pending or dc is None:
        # No resolvable pending check — behave as a normal manual roll.
        print()
        state_store.append_roll_entry(result)
        return

    outcome = "success" if result["total"] >= dc else "failure"
    check_summary = dm_engine.format_check_summary(pending)
    reason = str(pending.get("reason", "")).strip()

    # For scene-defined checks the success/failure text is authoritative.
    if outcome == "success":
        authoritative_outcome = str(pending.get("success", "")).strip()
    else:
        authoritative_outcome = str(pending.get("failure", "")).strip()

    print(f"\nResolved check: {check_summary}")
    print(f"Outcome: {outcome.capitalize()}")
    if authoritative_outcome:
        print(f"\nOutcome:\n{authoritative_outcome}")
    print()

    state_store.append_check_resolution(
        check_summary, reason, result, outcome, authoritative_outcome
    )
    state_store.clear_pending_check()

    # Ask the DM to narrate the (already-resolved) outcome. Follow-up checks
    # are not allowed immediately after resolution.
    prompt = dm_engine.build_roll_resolution_prompt(
        pending, result, outcome, authoritative_outcome
    )
    _dm_turn(
        prompt,
        ctx,
        player_label="(rolled for the pending check)",
        allow_requested_check=False,
    )


def _dm_turn(
    player_input: str,
    ctx: Ctx,
    player_label: str | None = None,
    allow_requested_check: bool = True,
) -> None:
    """Send one player message to the DM and handle the structured response.

    ``player_label`` overrides what is written to the session log's Player
    block (used for internal follow-ups like roll resolution).
    ``allow_requested_check`` controls whether a model-requested check may be
    saved as pending (disabled for roll-resolution follow-ups).
    """
    recent_log = state_store.read_session_log()
    scene = state_store.load_current_scene()
    messages = dm_engine.build_messages(
        system_prompt=ctx.system_prompt,
        campaign=ctx.campaign,
        character=ctx.character,
        player_input=player_input,
        recent_log=recent_log,
        scene=scene,
    )

    try:
        dm_response = ollama_client.chat(messages, model=ctx.model, json_mode=True)
    except ollama_client.OllamaError as exc:
        print(f"\n[Ollama error] {exc}\n", file=sys.stderr)
        return

    _handle_dm_response(
        player_label if player_label is not None else player_input,
        dm_response,
        allow_requested_check=allow_requested_check,
    )


def _handle_dm_response(
    player_input: str,
    raw_response: str,
    allow_requested_check: bool = True,
) -> None:
    """Parse a structured DM response, show it to the player, and log it.

    On a parse failure, prints a friendly error and the raw response, saves
    the raw output for debugging, and does not crash. When
    ``allow_requested_check`` is False (e.g. immediately after a roll
    resolution), any model-requested check is suppressed rather than saved.
    """
    try:
        data = dm_engine.parse_dm_response(raw_response)
    except ValueError as exc:
        print(
            "\n[Could not read the DM response as JSON — showing raw output.]",
            file=sys.stderr,
        )
        print(f"[{exc}]\n", file=sys.stderr)
        print(raw_response.strip() + "\n")
        state_store.append_failed_turn(player_input, raw_response)
        return

    narration = str(data.get("narration", "")).strip()
    raw_check = data.get("requested_check")
    # Correct e.g. "Dexterity (Perception)" -> "Wisdom (Perception)".
    check = dm_engine.normalise_check(raw_check) if raw_check else None
    prompt_to_player = str(data.get("prompt_to_player", "")).strip()

    debug = {
        "parsed_response": data,
        "raw_requested_check": raw_check,
        "normalised_requested_check": check,
    }

    # Suppress model-requested checks when not allowed (post roll-resolution).
    if check and not allow_requested_check:
        debug["suppressed_requested_check"] = check
        debug["suppression_reason"] = (
            "Requested checks are disabled immediately after roll resolution."
        )
        check = None

    check_summary = dm_engine.format_check_summary(check)

    # Keep debug data for /debug-last (raw vs normalised check, full response).
    state_store.save_last_dm_response(debug)

    # Player-visible output only. dm_notes are never printed.
    print(f"\nDM  > {narration}\n" if narration else "\nDM  > (no narration)\n")

    if check_summary:
        # Display only the corrected (normalised) check.
        print(f"Suggested check: {check_summary}")
        reason = str(check.get("reason", "")).strip() if isinstance(check, dict) else ""
        if reason:
            print(f"Reason: {reason}")
        print("Use: /roll 1d20+<modifier>\n")
        # Remember the normalised check as the current pending check.
        state_store.save_pending_check(check)

    if prompt_to_player:
        print(f"{prompt_to_player}\n")

    structured_json = json.dumps(data, indent=2, ensure_ascii=False)
    state_store.append_structured_turn(
        player_action=player_input,
        narration=narration,
        check_summary=check_summary,
        structured_json=structured_json,
    )


def main() -> int:
    try:
        campaign = state_store.load_campaign()
        character = state_store.load_character()
        system_prompt = state_store.load_dm_system_prompt()
        scene = state_store.ensure_current_scene()
        model = ollama_client.get_model()
    except FileNotFoundError as exc:
        print(f"Startup error: {exc}", file=sys.stderr)
        return 1
    except ollama_client.OllamaError as exc:
        print(f"Startup error: {exc}", file=sys.stderr)
        return 1

    ctx = Ctx(
        model=model,
        system_prompt=system_prompt,
        campaign=campaign,
        character=character,
    )

    _print_welcome(campaign, character, model, scene)

    while True:
        try:
            player_input = input("You > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return 0

        if not player_input:
            continue

        if player_input == "/quit":
            print("Goodbye.")
            return 0

        if player_input == "/roll" or player_input.startswith("/roll "):
            _handle_roll(player_input[len("/roll"):], ctx)
            continue

        if player_input == "/check":
            _handle_check()
            continue

        if player_input == "/scene":
            _handle_scene()
            continue

        if player_input == "/scene-debug":
            _handle_scene_debug()
            continue

        if player_input == "/reset-scene":
            _handle_reset_scene()
            continue

        if player_input == "/detect" or player_input.startswith("/detect "):
            _handle_detect(player_input[len("/detect"):])
            continue

        if player_input == "/narrate" or player_input.startswith("/narrate "):
            action = player_input[len("/narrate"):].strip()
            if not action:
                print("Usage: /narrate <action>\n")
            else:
                # Bypass deterministic detection; narrate directly.
                _dm_turn(action, ctx)
            continue

        if player_input == "/debug-last":
            _handle_debug_last()
            continue

        if player_input == "/recap":
            log = state_store.read_session_log()
            if log.strip():
                print("\n----- Session recap -----\n")
                print(log.strip())
                print("\n-------------------------\n")
            else:
                print("(No session log yet.)\n")
            continue

        _handle_player_action(player_input, ctx)


if __name__ == "__main__":
    raise SystemExit(main())
