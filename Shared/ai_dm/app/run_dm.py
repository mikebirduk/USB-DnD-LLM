#!/usr/bin/env python3
"""Terminal runner for the Milestone 1 AI Dungeon Master loop.

Run with:

    python3 Shared/ai_dm/app/run_dm.py

Loads the campaign and character templates, then loops: read a player
action, send it to the local Ollama model with campaign context, print the
DM reply, and append the exchange to the local session log.

Commands:
    /campaigns        list generated campaign packs
    /load-campaign <slug>   load a generated campaign as active
    /active-campaign  show the active campaign and current scene
    /reset-campaign   reset to the example campaign and default scene
    /new-campaign <seed>   generate a local campaign pack from a seed
    /roll <formula>   roll dice; resolves a pending check if one is active
    /rollcheck        roll the active character's modifier for the pending check
    /character        show the active character sheet
    /mod <ability> [skill]   show the character's modifier for an ability/skill
    /rule <query>     look up local rules by keyword
    /rules-context <action>   show the rules context that would be sent to the DM
    /askrule <question>   answer a rules question via the Rules Helper path
    /rules-status     show whether the local rules library is installed
    /new-campaign <seed>   generate a local campaign pack from a seed
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
from pathlib import Path

# Allow running as a plain script (python3 .../run_dm.py) by ensuring the
# app package directory is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import action_detector
import campaign_generator
import character
import dice
import dm_engine
import ollama_client
import rules_lookup
import state_store

# Everything a DM turn needs: resolved model plus loaded game context. Mutable
# so campaign commands (e.g. /load-campaign) can swap the active campaign live.
class Ctx:
    def __init__(self, model, system_prompt, campaign, character):
        self.model = model
        self.system_prompt = system_prompt
        self.campaign = campaign
        self.character = character


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
    print("  Type an action to play, or /help for the full command list.")
    print(
        "  Campaigns: /campaigns  /load-campaign <slug>  /active-campaign  "
        "/reset-campaign  /new-campaign <seed>"
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
    """Route a normal player input: rules question, scene check, or DM turn.

    Rules/mechanics questions go to the dedicated Rules Helper path. Otherwise
    a detected check creates a pending check; anything else is a DM turn.
    """
    if rules_lookup.is_rules_question(player_input):
        _rules_answer_turn(player_input, ctx)
        return

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


def _handle_rule(query: str) -> None:
    """Look up local rules by keyword and print up to 3 matching snippets."""
    query = query.strip()
    if not query:
        print("Usage: /rule <query>   e.g. /rule perception\n")
        return
    if not rules_lookup.load_rules_lookup():
        print(f"{rules_lookup.NOT_INSTALLED_MESSAGE}\n")
        return
    results = rules_lookup.search_rules(query, limit=3)
    print(f"\n{rules_lookup.format_rule_results(results)}\n")


def _handle_campaigns() -> None:
    """List generated campaign packs under campaigns/."""
    packs = state_store.list_campaign_packs()
    if not packs:
        print("No generated campaigns found.")
        print("Use /new-campaign <seed> or run generate_campaign.py.\n")
        return
    print("\nAvailable campaigns:\n")
    for pack in packs:
        print(f"- {pack['slug']}")
        print(f"  Title: {pack['title']}")
        print(f"  Tone: {pack['tone']}")
        print(f"  Starting level: {pack['starting_level']}")
    print()


def _handle_load_campaign(slug: str, ctx: Ctx) -> None:
    """Load a generated campaign pack as the active campaign (no model call)."""
    slug = slug.strip()
    if not slug:
        print("Usage: /load-campaign <slug>   (see /campaigns)\n")
        return

    pack = state_store.load_campaign_pack(slug)
    if pack is None:
        print(f"Campaign not found: {slug}")
        print("Use /campaigns to list available campaigns.\n")
        return

    campaign = pack["campaign"]
    scene = pack["scene"]
    if not isinstance(scene, dict):
        print(f"Campaign '{slug}' has no readable starting scene; not loaded.\n")
        return

    state_store.save_active_campaign({"slug": slug, "campaign": campaign})
    state_store.save_current_scene(scene)
    state_store.clear_pending_check()
    title = campaign.get("campaign_title", slug)
    scene_title = scene.get("scene_title", "Untitled scene")
    state_store.append_note(f"Campaign switched to: {title} — scene: {scene_title}")

    # Update the in-memory campaign used by the current runner loop.
    ctx.campaign = campaign

    print(f"\nLoaded campaign: {title}")
    print(f"Current scene: {scene_title}\n")


def _handle_active_campaign(ctx: Ctx) -> None:
    """Show the active campaign and current scene (no model call)."""
    active = state_store.load_active_campaign()
    scene = state_store.load_current_scene() or {}
    scene_title = scene.get("scene_title", "(none)")
    print("\nActive campaign:")
    if active and isinstance(active.get("campaign"), dict):
        print(active["campaign"].get("campaign_title", active.get("slug", "?")))
        print(f"Slug: {active.get('slug', '?')}")
    else:
        print(ctx.campaign.get("campaign_title", "Example Campaign"))
    print(f"Current scene: {scene_title}\n")


def _handle_reset_campaign(ctx: Ctx) -> None:
    """Reset to the example campaign and the default scene (no model call)."""
    state_store.clear_active_campaign()
    scene = state_store.load_scene_template(state_store.DEFAULT_SCENE_TEMPLATE)
    state_store.save_current_scene(scene)
    state_store.clear_pending_check()
    ctx.campaign = state_store.load_campaign()
    scene_title = scene.get("scene_title", "Untitled scene")
    state_store.append_note("Campaign reset to the example campaign.")
    print("\nReset to example campaign.")
    print(f"Current scene: {scene_title}\n")


def _handle_help() -> None:
    """Print the available commands."""
    print(
        "\nCommands:\n"
        "  /campaigns                 list generated campaigns\n"
        "  /load-campaign <slug>      load a generated campaign\n"
        "  /active-campaign           show the active campaign and scene\n"
        "  /reset-campaign            reset to the example campaign\n"
        "  /new-campaign <seed>       generate a new campaign pack\n"
        "  /rule <query>              look up local rules\n"
        "  /rules-context <text>      preview rules context for text\n"
        "  /askrule <question>        answer a rules question\n"
        "  /rules-status              show rules library status\n"
        "  /character                 show the character sheet\n"
        "  /mod <ability> [skill]     show a modifier\n"
        "  /check                     show the pending check\n"
        "  /roll <formula>            roll dice / resolve a pending check\n"
        "  /rollcheck                 roll the pending check for the character\n"
        "  /scene                     show the current scene\n"
        "  /scene-debug               show the full scene JSON\n"
        "  /reset-scene               reload the default scene\n"
        "  /detect <action>           preview the scene check for an action\n"
        "  /narrate <action>          narrate without scene detection\n"
        "  /debug-last                show last DM/rules debug data\n"
        "  /recap                     print the session log\n"
        "  /quit                      exit\n"
    )


def _handle_new_campaign(seed: str, ctx: Ctx) -> None:
    """Generate a campaign pack from a seed and print where it was written.

    Does not switch the active campaign/scene — this only generates the pack.
    """
    seed = seed.strip()
    if not seed:
        print("Usage: /new-campaign <seed text>\n")
        return

    print("\nGenerating campaign pack (this can take a while on local models)...")
    result = campaign_generator.generate_campaign_pack(seed, model=ctx.model)

    if not result.get("ok"):
        print(f"Campaign generation failed: {result.get('error')}", file=sys.stderr)
        if result.get("raw_path"):
            print(f"Raw model response saved to: {result['raw_path']}", file=sys.stderr)
        print()
        return

    print(f"\nCampaign: {result['title']}")
    print(f"Folder:   {result['folder']}")
    print("(Generated locally; not committed to Git. Not auto-loaded yet.)\n")


def _handle_rules_context(text: str) -> None:
    """Show the rules context that would be sent to the DM for an action/question.

    Does not modify game state.
    """
    text = text.strip()
    if not text:
        print("Usage: /rules-context <action or question>\n")
        return
    if not rules_lookup.load_rules_lookup():
        print(f"{rules_lookup.NOT_INSTALLED_MESSAGE}\n")
        return

    query = rules_lookup.build_rules_query(player_input=text)
    results = rules_lookup.search_rules(query, limit=3) if query else []

    print(f"\nRules context for:\n{text}\n")
    if not results:
        print("Matched snippets: (none)\n")
        return
    print("Matched snippets:")
    for doc in results:
        print(f"- {doc.get('title', doc.get('id', 'Unknown'))}")
    print(f"\n{rules_lookup.format_rule_results(results)}\n")


def _handle_rules_status() -> None:
    """Report whether rules are installed and how many docs are indexed."""
    installed = state_store.load_installed_rules()
    if installed:
        print("Rules installed: yes")
        print(f"Ruleset: {installed.get('ruleset', '?')} {installed.get('version', '?')}")
    else:
        print("Rules installed: no")

    docs = rules_lookup.load_rules_lookup()
    print(f"Lookup index: {'yes' if docs else 'no'}")
    print(f"Indexed docs: {len(docs)}")
    if not installed or not docs:
        print(
            "\nBuild the rules library with:\n"
            "  python3 Shared/ai_dm/rules/scripts/install_rules.py\n"
            "  python3 Shared/ai_dm/rules/scripts/build_rules_lookup.py"
        )
    print()


def _handle_debug_last() -> None:
    """Show debug data for the last DM/rules response."""
    data = state_store.load_last_dm_response()
    if not data:
        print("No debug data yet.\n")
        return

    if data.get("mode") == "rules_question":
        print("\nmode: rules_question")
        print(f"rules_context_included: {str(bool(data.get('rules_context_included'))).lower()}")
        print(f"model_response_used: {str(bool(data.get('model_response_used'))).lower()}")
        print(f"fallback_used: {str(bool(data.get('fallback_used'))).lower()}")
        print("\nlast parsed response:")
        print(json.dumps(data.get("parsed_response"), indent=2, ensure_ascii=False))
        print()
        return

    print("\nmode: narration")
    print("\nraw requested_check:")
    print(json.dumps(data.get("raw_requested_check"), indent=2, ensure_ascii=False))
    print("\nnormalised requested_check:")
    print(json.dumps(data.get("normalised_requested_check"), indent=2, ensure_ascii=False))
    print("\nlast parsed response:")
    print(json.dumps(data.get("parsed_response"), indent=2, ensure_ascii=False))
    print()


def _print_roll(result: dict) -> None:
    """Print a dice-roll result in the standard readable format."""
    print(f"\nRoll: {result['formula']}")
    print(f"Dice: {result['rolls']}")
    print(f"Modifier: {result['modifier']:+d}")
    print(f"Total: {result['total']}")


def _resolve_pending(result: dict, pending: dict, ctx: Ctx) -> None:
    """Resolve a rolled result against a pending check and hand off to the DM.

    Determines success/failure vs the DC, applies scene-defined authoritative
    outcome text, logs the resolution, clears the pending check, and asks the
    DM to narrate (with follow-up checks disabled).
    """
    dc = _coerce_dc(pending.get("dc"))
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

    prompt = dm_engine.build_roll_resolution_prompt(
        pending, result, outcome, authoritative_outcome
    )
    _dm_turn(
        prompt,
        ctx,
        player_label="(rolled for the pending check)",
        allow_requested_check=False,
        resolved_check=pending,
    )


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

    _print_roll(result)

    pending = state_store.load_pending_check()
    dc = _coerce_dc(pending.get("dc")) if pending else None

    if not pending or dc is None:
        # No resolvable pending check — behave as a normal manual roll.
        print()
        state_store.append_roll_entry(result)
        return

    _resolve_pending(result, pending, ctx)


def _load_character_safe():
    """Load the active character, returning None (with a message) on error."""
    try:
        return state_store.load_character()
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        print(f"Could not load character: {exc}\n", file=sys.stderr)
        return None


def _format_score(score) -> str:
    """Render an ability score for display, or 'unknown' if missing."""
    return str(score) if score is not None else "unknown"


def _handle_rollcheck(ctx: Ctx) -> None:
    """Roll the active character's modifier for the pending check and resolve it."""
    pending = state_store.load_pending_check()
    if not pending:
        print("No pending check.\n")
        return

    char = _load_character_safe()
    if char is None:
        return

    ability = pending.get("ability")
    skill = pending.get("skill")
    mod = character.get_skill_modifier(char, ability, skill)
    name = char.get("name", "the character")
    check_summary = dm_engine.format_check_summary(pending)

    print(f"\nRolling pending check for {name}:")
    print(f"Check: {check_summary}")
    print(f"Ability score: {ability} {_format_score(mod['ability_score'])}")
    print(f"Ability modifier: {mod['ability_modifier']:+d}")
    print(f"Proficient: {'yes' if mod['is_proficient'] else 'no'}")
    print(f"Expertise: {'yes' if mod['has_expertise'] else 'no'}")
    print(f"Total modifier: {mod['total_modifier']:+d}")
    print(f"Formula: {mod['formula']}")

    try:
        result = dice.roll_dice(mod["formula"])
    except ValueError as exc:
        print(f"\nCould not roll computed formula {mod['formula']!r}: {exc}\n")
        return

    _print_roll(result)

    if _coerce_dc(pending.get("dc")) is None:
        print("\nPending check has no valid DC; logged as a plain roll.\n")
        state_store.append_roll_entry(result)
        state_store.clear_pending_check()
        return

    _resolve_pending(result, pending, ctx)


def _handle_character() -> None:
    """Print the active character sheet."""
    char = _load_character_safe()
    if char is None:
        return

    hp = char.get("hp") or {}
    hp_text = (
        f"{hp.get('current', '?')}/{hp.get('max', '?')}"
        if isinstance(hp, dict)
        else str(hp)
    )
    print(f"\nName: {char.get('name', 'Unknown')}")
    print(f"Ancestry: {char.get('ancestry', 'Unknown')}")
    print(f"Class: {char.get('class', 'Unknown')}")
    print(f"Level: {char.get('level', '?')}")
    print(f"HP: {hp_text}")
    print(f"AC: {char.get('ac', '?')}")

    print("\nAbility scores:")
    abilities = char.get("abilities") or {}
    for ability in character.ABILITY_ORDER:
        score = character.get_ability_score(char, ability)
        if score is None:
            continue
        mod = character.ability_modifier(score)
        print(f"- {ability.capitalize()}: {score} ({mod:+d})")

    try:
        prof_bonus = int(char.get("proficiency_bonus", 0))
    except (TypeError, ValueError):
        prof_bonus = 0
    print(f"\nProficiency bonus: {prof_bonus:+d}")
    profs = char.get("skill_proficiencies") or []
    expertise = char.get("skill_expertise") or []
    print(f"Skill proficiencies: {', '.join(profs) if profs else '(none)'}")
    print(f"Skill expertise: {', '.join(expertise) if expertise else '(none)'}")
    print()


def _handle_mod(args: str) -> None:
    """Print the modifier for an ability (and optional skill): /mod <ability> [skill]."""
    parts = args.split()
    if not parts:
        print("Usage: /mod <ability> [skill]   e.g. /mod Wisdom Perception\n")
        return

    ability = parts[0]
    skill = " ".join(parts[1:]) if len(parts) > 1 else None

    char = _load_character_safe()
    if char is None:
        return

    mod = character.get_skill_modifier(char, ability, skill)
    header = f"{ability} ({skill})" if skill else ability
    print(f"\n{header}")
    print(f"Ability score: {_format_score(mod['ability_score'])}")
    print(f"Ability modifier: {mod['ability_modifier']:+d}")
    print(f"Proficiency bonus: {mod['proficiency_bonus']:+d}")
    print(f"Proficient: {'yes' if mod['is_proficient'] else 'no'}")
    print(f"Expertise: {'yes' if mod['has_expertise'] else 'no'}")
    print(f"Total modifier: {mod['total_modifier']:+d}")
    print()


def _load_rules_prompt() -> str:
    """Load the rules-helper prompt, returning "" on any error."""
    try:
        return state_store.load_rules_lawyer_prompt()
    except OSError:
        return ""


def _emit_rules_answer(
    question: str,
    answer: str,
    prompt_to_player: str,
    rules_context: str,
    model_used: bool,
    fallback_used: bool,
    structured: dict | None,
) -> None:
    """Print, log, and record debug for a rules-helper answer."""
    if fallback_used:
        print(f"\nRules answer:\n{answer}\n")
    else:
        print(f"\nDM (rules) > {answer}\n")
        if prompt_to_player:
            print(f"{prompt_to_player}\n")

    if structured is not None:
        structured_json = json.dumps(structured, indent=2, ensure_ascii=False)
    else:
        structured_json = json.dumps(
            {
                "narration": answer,
                "requested_check": None,
                "dm_notes": [],
                "state_updates": [],
                "prompt_to_player": prompt_to_player,
            },
            indent=2,
            ensure_ascii=False,
        )
    state_store.append_structured_turn(
        player_action=question,
        narration=answer,
        check_summary="",
        structured_json=structured_json,
    )
    state_store.save_last_dm_response(
        {
            "mode": "rules_question",
            "question": question,
            "rules_context_included": bool(rules_context.strip()),
            "model_response_used": model_used,
            "fallback_used": fallback_used,
            "parsed_response": structured,
        }
    )


def _rules_answer_turn(question: str, ctx: Ctx) -> None:
    """Answer a rules/mechanics question via the dedicated Rules Helper path.

    Uses a small rules-only prompt (not the atmospheric DM prompt). If the
    model ignores the question and a local fallback exists, the fallback is
    used instead. Does not create a pending check.
    """
    question = question.strip()
    if not question:
        print("Usage: /askrule <question>\n")
        return

    rules_context = rules_lookup.get_relevant_rules_context(player_input=question)
    scene = state_store.load_current_scene()
    messages = dm_engine.build_rules_answer_messages(
        question, rules_context, current_scene=scene, rules_prompt=_load_rules_prompt()
    )
    fallback = rules_lookup.rules_fallback(question)

    try:
        raw = ollama_client.chat(messages, model=ctx.model, json_mode=True)
    except ollama_client.OllamaError as exc:
        if fallback:
            print(
                f"[Ollama unavailable — using local rules fallback: {exc}]",
                file=sys.stderr,
            )
            _emit_rules_answer(
                question, fallback["answer"], "", rules_context,
                model_used=False, fallback_used=True, structured=None,
            )
        else:
            print(f"\n[Ollama error] {exc}\n", file=sys.stderr)
        return

    try:
        data = dm_engine.parse_dm_response(raw)
    except ValueError:
        data = None

    narration = str(data.get("narration", "")).strip() if data else ""
    prompt_to_player = str(data.get("prompt_to_player", "")).strip() if data else ""

    model_failed = data is None or rules_lookup.response_missing_answer(question, narration)
    if fallback and model_failed:
        _emit_rules_answer(
            question, fallback["answer"], "", rules_context,
            model_used=False, fallback_used=True, structured=data,
        )
        return

    if data is None:
        # No usable answer and no fallback — show raw, do not crash.
        print(
            "\n[Could not read the rules answer as JSON — showing raw output.]\n",
            file=sys.stderr,
        )
        print(raw.strip() + "\n")
        state_store.append_failed_turn(question, raw)
        state_store.save_last_dm_response(
            {
                "mode": "rules_question",
                "question": question,
                "rules_context_included": bool(rules_context.strip()),
                "model_response_used": False,
                "fallback_used": False,
                "parsed_response": None,
            }
        )
        return

    _emit_rules_answer(
        question, narration or "(no answer)", prompt_to_player, rules_context,
        model_used=True, fallback_used=False, structured=data,
    )


def _dm_turn(
    player_input: str,
    ctx: Ctx,
    player_label: str | None = None,
    allow_requested_check: bool = True,
    resolved_check: dict | None = None,
) -> None:
    """Send one player message to the DM and handle the structured response.

    ``player_label`` overrides what is written to the session log's Player
    block (used for internal follow-ups like roll resolution).
    ``allow_requested_check`` controls whether a model-requested check may be
    saved as pending (disabled for roll-resolution follow-ups).
    ``resolved_check`` supplies the just-resolved check so rules context is
    drawn from it rather than from the (internal) resolution prompt text.
    """
    recent_log = state_store.read_session_log()
    scene = state_store.load_current_scene()

    # Retrieve relevant local rules snippets for the DM prompt.
    if resolved_check is not None:
        rules_context = rules_lookup.get_relevant_rules_context(
            resolved_check=resolved_check
        )
        rules_question = False
    else:
        pending = state_store.load_pending_check()
        rules_context = rules_lookup.get_relevant_rules_context(
            player_input=player_input, pending_check=pending
        )
        rules_question = rules_lookup.is_rules_question(player_input)

    messages = dm_engine.build_messages(
        system_prompt=ctx.system_prompt,
        campaign=ctx.campaign,
        character=ctx.character,
        player_input=player_input,
        recent_log=recent_log,
        scene=scene,
        rules_context=rules_context,
        rules_question=rules_question,
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
        character = state_store.load_character()
        system_prompt = state_store.load_dm_system_prompt()
        campaign, scene = state_store.ensure_campaign_state()
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

        if player_input == "/help":
            _handle_help()
            continue

        # --- Campaign commands (handled before any narration/model call) ---
        if player_input == "/campaigns":
            _handle_campaigns()
            continue

        if player_input == "/load-campaign" or player_input.startswith("/load-campaign "):
            _handle_load_campaign(player_input[len("/load-campaign"):], ctx)
            continue

        if player_input == "/active-campaign":
            _handle_active_campaign(ctx)
            continue

        if player_input == "/reset-campaign":
            _handle_reset_campaign(ctx)
            continue

        if player_input == "/new-campaign" or player_input.startswith("/new-campaign "):
            _handle_new_campaign(player_input[len("/new-campaign"):], ctx)
            continue

        if player_input == "/roll" or player_input.startswith("/roll "):
            _handle_roll(player_input[len("/roll"):], ctx)
            continue

        if player_input == "/rollcheck":
            _handle_rollcheck(ctx)
            continue

        if player_input == "/character":
            _handle_character()
            continue

        if player_input == "/mod" or player_input.startswith("/mod "):
            _handle_mod(player_input[len("/mod"):])
            continue

        if player_input == "/rules-context" or player_input.startswith("/rules-context "):
            _handle_rules_context(player_input[len("/rules-context"):])
            continue

        if player_input == "/rule" or player_input.startswith("/rule "):
            _handle_rule(player_input[len("/rule"):])
            continue

        if player_input == "/rules-status":
            _handle_rules_status()
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

        if player_input == "/askrule" or player_input.startswith("/askrule "):
            _rules_answer_turn(player_input[len("/askrule"):], ctx)
            continue

        if player_input == "/narrate" or player_input.startswith("/narrate "):
            action = player_input[len("/narrate"):].strip()
            if not action:
                print("Usage: /narrate <action>\n")
            elif rules_lookup.is_rules_question(action):
                # Bypass scene detection but still answer rules questions.
                _rules_answer_turn(action, ctx)
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

        # Any other slash input is an unknown command — never sent to the model.
        if player_input.startswith("/"):
            print(f"Unknown command: {player_input.split()[0]}")
            print("Type /help for commands.\n")
            continue

        _handle_player_action(player_input, ctx)


if __name__ == "__main__":
    raise SystemExit(main())
