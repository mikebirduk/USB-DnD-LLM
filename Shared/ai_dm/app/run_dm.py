#!/usr/bin/env python3
"""Terminal runner for the Milestone 1 AI Dungeon Master loop.

Run with:

    python3 Shared/ai_dm/app/run_dm.py

Loads the campaign and character templates, then loops: read a player
action, send it to the local Ollama model with campaign context, print the
DM reply, and append the exchange to the local session log.

Commands:
    /quit    exit
    /recap   print the current saved session log
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running as a plain script (python3 .../run_dm.py) by ensuring the
# app package directory is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import dice
import dm_engine
import ollama_client
import state_store


def _print_welcome(campaign, character, model) -> None:
    title = campaign.get("campaign_title", "Untitled Campaign")
    name = character.get("name", "Unknown Hero")
    print("=" * 60)
    print("  AI Dungeon Master — Milestone 1 prototype")
    print("=" * 60)
    print(f"  Campaign : {title}")
    print(f"  Character: {name}")
    print("-" * 60)
    print(f"Using model: {model}")
    print(f"Ollama endpoint: {ollama_client.OLLAMA_HOST}")
    print("-" * 60)
    print("  Type an action to play. Commands: /roll <formula>  /recap  /quit")
    print("=" * 60)
    print()


def _handle_roll(formula: str) -> None:
    """Roll a dice formula, print the result, and log it.

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

    modifier = result["modifier"]
    print(f"\nRoll: {result['formula']}")
    print(f"Dice: {result['rolls']}")
    print(f"Modifier: {modifier:+d}")
    print(f"Total: {result['total']}\n")

    state_store.append_roll_entry(result)


def _handle_dm_response(player_input: str, raw_response: str) -> None:
    """Parse a structured DM response, show it to the player, and log it.

    On a parse failure, prints a friendly error and the raw response, saves
    the raw output for debugging, and does not crash.
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
    check = data.get("requested_check")
    check_summary = dm_engine.format_check_summary(check)
    prompt_to_player = str(data.get("prompt_to_player", "")).strip()

    # Player-visible output only. dm_notes are never printed.
    print(f"\nDM  > {narration}\n" if narration else "\nDM  > (no narration)\n")

    if check_summary:
        print(f"Suggested check: {check_summary}")
        reason = str(check.get("reason", "")).strip() if isinstance(check, dict) else ""
        if reason:
            print(f"Reason: {reason}")
        print("Use: /roll 1d20+<modifier>\n")

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
        model = ollama_client.get_model()
    except FileNotFoundError as exc:
        print(f"Startup error: {exc}", file=sys.stderr)
        return 1
    except ollama_client.OllamaError as exc:
        print(f"Startup error: {exc}", file=sys.stderr)
        return 1

    _print_welcome(campaign, character, model)

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
            _handle_roll(player_input[len("/roll"):])
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

        recent_log = state_store.read_session_log()
        messages = dm_engine.build_messages(
            system_prompt=system_prompt,
            campaign=campaign,
            character=character,
            player_input=player_input,
            recent_log=recent_log,
        )

        try:
            dm_response = ollama_client.chat(messages, model=model, json_mode=True)
        except ollama_client.OllamaError as exc:
            print(f"\n[Ollama error] {exc}\n", file=sys.stderr)
            continue

        _handle_dm_response(player_input, dm_response)


if __name__ == "__main__":
    raise SystemExit(main())
