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

import sys
from pathlib import Path

# Allow running as a plain script (python3 .../run_dm.py) by ensuring the
# app package directory is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent))

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
    print("  Type an action to play. Commands: /recap  /quit")
    print("=" * 60)
    print()


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
            dm_response = ollama_client.chat(messages, model=model)
        except ollama_client.OllamaError as exc:
            print(f"\n[Ollama error] {exc}\n", file=sys.stderr)
            continue

        print(f"\nDM  > {dm_response.strip()}\n")
        state_store.append_session_entry(player_input, dm_response)


if __name__ == "__main__":
    raise SystemExit(main())
