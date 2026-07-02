"""Local AI campaign generator.

Uses the installed local model (via Ollama) to generate an engine-ready
campaign pack — campaign metadata, a starting scene, NPCs, locations,
factions, rumours, and a first-session outline — and writes it as JSON/Markdown
files under ``Shared/ai_dm/campaigns/<slug>/``. Everything stays local; the
generated packs are private runtime data and are not committed to Git.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

import campaign_linter
import dm_engine
import ollama_client
import state_store

# JSON contract appended to the campaign-generator prompt.
_JSON_CONTRACT = """
Return a single valid JSON object (no markdown, no commentary) with exactly
these top-level keys:

{
  "campaign": {
    "campaign_title": "...",
    "slug": "kebab-case-slug",
    "tone": "...",
    "ruleset": "dnd-srd-5.2.1",
    "starting_level": 1,
    "target_level": 3,
    "party_size": "1-3 players",
    "summary": "...",
    "central_mystery": "...",
    "starting_scene": "the-port",
    "open_threads": ["...", "..."],
    "themes": ["...", "..."],
    "safety_notes": ["...", "..."]
  },
  "scenes": [
    {
      "scene_id": "the-port",
      "scene_title": "...",
      "location": "...",
      "player_visible": "...",
      "sensory_details": ["...", "..."],
      "current_situation": "...",
      "hidden_truths": ["secret 1", "secret 2", "secret 3"],
      "obvious_interactions": ["...", "...", "..."],
      "default_checks": [
        {"trigger": "...", "ability": "Intelligence", "skill": "Investigation",
         "dc": 13, "success": "...", "failure": "..."},
        {"trigger": "...", "ability": "Wisdom", "skill": "Perception",
         "dc": 13, "success": "...", "failure": "..."}
      ],
      "scene_clocks": [
        {"name": "Danger Clock", "value": 0, "max": 4, "description": "..."}
      ],
      "exits": [
        {"label": "...", "target_scene_id": "smugglers-tunnels",
         "description": "..."}
      ]
    }
  ],
  "npcs": [
    {"npc_id": "kebab-name", "name": "...", "role": "...",
     "public_description": "...", "motive": "...", "secret": "...",
     "attitude": "...", "knows": ["...", "..."], "voice": "..."}
  ],
  "locations": [
    {"location_id": "kebab-name", "name": "...", "description": "...",
     "secrets": ["..."], "linked_scene_ids": ["starting_scene"]}
  ],
  "factions": [
    {"faction_id": "kebab-name", "name": "...", "public_role": "...",
     "true_agenda": "...", "resources": ["...", "..."],
     "relationship_to_party": "unknown"}
  ],
  "rumours": [
    {"rumour": "...", "truth": "partly true", "source": "...",
     "related_thread": "..."}
  ],
  "session_01_outline": {
    "opening_situation": "...",
    "key_npcs": ["...", "..."],
    "likely_player_actions": ["...", "..."],
    "possible_checks": ["...", "..."],
    "secrets_that_can_be_discovered": ["...", "..."],
    "escalation": "...",
    "ending_options": ["...", "..."]
  }
}

Provide exactly 3 scenes in "scenes". "campaign.starting_scene" must be the
scene_id of the first scene. The starting scene must have at least 3
hidden_truths. Every scene must have at least 2 obvious_interactions and at
least 2 default_checks, and every default check must include trigger, ability,
skill, dc, success, and failure. Each non-final scene must include at least one
exit with label, target_scene_id (an existing scene_id), and description.
"""

_REQUIRED_CHECK_FIELDS = ("trigger", "ability", "skill", "dc", "success", "failure")


class CampaignValidationError(ValueError):
    """Raised when a generated campaign pack fails structural validation."""


def slugify(text: str) -> str:
    """Turn arbitrary text into a safe kebab-case slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug or "campaign"


def build_generation_messages(seed: str):
    """Build the messages list for the campaign-generation call."""
    base_prompt = state_store.load_campaign_generator_prompt().strip()
    system_content = "\n\n".join(filter(None, [base_prompt, _JSON_CONTRACT.strip()]))
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": f"Campaign seed:\n{seed.strip()}"},
    ]


def _get_scenes(pack: Dict[str, Any]) -> list:
    """Return the scenes list, tolerating an older single starting_scene shape."""
    scenes = pack.get("scenes")
    if isinstance(scenes, list) and scenes:
        return [s for s in scenes if isinstance(s, dict)]
    legacy = pack.get("starting_scene")
    return [legacy] if isinstance(legacy, dict) else []


def _validate(pack: Dict[str, Any]) -> None:
    """Validate the parsed campaign pack, raising CampaignValidationError."""
    campaign = pack.get("campaign")
    if not isinstance(campaign, dict) or not campaign.get("campaign_title"):
        raise CampaignValidationError("Missing 'campaign' object or campaign_title.")

    scenes = _get_scenes(pack)
    if len(scenes) < 3:
        raise CampaignValidationError("Campaign needs at least 3 scenes.")

    for i, scene in enumerate(scenes):
        label = scene.get("scene_id") or scene.get("scene_title") or f"scene {i + 1}"
        for field in ("scene_id", "scene_title", "player_visible"):
            if not str(scene.get(field, "")).strip():
                raise CampaignValidationError(f"Scene '{label}' missing '{field}'.")

        interactions = scene.get("obvious_interactions") or []
        if not isinstance(interactions, list) or len(interactions) < 2:
            raise CampaignValidationError(
                f"Scene '{label}' needs at least 2 obvious_interactions."
            )

        checks = scene.get("default_checks") or []
        if not isinstance(checks, list) or len(checks) < 2:
            raise CampaignValidationError(
                f"Scene '{label}' needs at least 2 default_checks."
            )
        for index, check in enumerate(checks, start=1):
            if not isinstance(check, dict):
                raise CampaignValidationError(
                    f"Scene '{label}' default_check {index} is not an object."
                )
            missing = [f for f in _REQUIRED_CHECK_FIELDS if not str(check.get(f, "")).strip()]
            if missing:
                raise CampaignValidationError(
                    f"Scene '{label}' default_check {index} missing: {', '.join(missing)}."
                )

    starting = scenes[0]
    hidden = starting.get("hidden_truths") or []
    if not isinstance(hidden, list) or len(hidden) < 3:
        raise CampaignValidationError("Starting scene needs at least 3 hidden_truths.")


def _render_session_outline(outline: Any, campaign: Dict[str, Any]) -> str:
    """Render the session-1 outline object into the fixed Markdown skeleton."""
    outline = outline if isinstance(outline, dict) else {}

    def block(value: Any) -> str:
        if isinstance(value, list):
            return "\n".join(f"- {item}" for item in value) if value else "_(TBD)_"
        text = str(value).strip()
        return text if text else "_(TBD)_"

    return (
        "# Session 1 Outline\n\n"
        "## Opening Situation\n\n"
        f"{block(outline.get('opening_situation'))}\n\n"
        "## Key NPCs\n\n"
        f"{block(outline.get('key_npcs'))}\n\n"
        "## Likely Player Actions\n\n"
        f"{block(outline.get('likely_player_actions'))}\n\n"
        "## Possible Checks\n\n"
        f"{block(outline.get('possible_checks'))}\n\n"
        "## Secrets That Can Be Discovered\n\n"
        f"{block(outline.get('secrets_that_can_be_discovered'))}\n\n"
        "## Escalation\n\n"
        f"{block(outline.get('escalation'))}\n\n"
        "## Ending Options\n\n"
        f"{block(outline.get('ending_options'))}\n"
    )


def _render_campaign_readme(campaign: Dict[str, Any], scene: Dict[str, Any]) -> str:
    title = campaign.get("campaign_title", "Untitled Campaign")
    summary = campaign.get("summary", "").strip() or "_(no summary)_"
    scene_title = scene.get("scene_title", "Starting scene")
    scene_desc = scene.get("player_visible", "").strip() or "_(no description)_"
    return (
        f"# {title}\n\n"
        "Generated by USB-DnD-LLM.\n\n"
        "## Summary\n\n"
        f"{summary}\n\n"
        "## Starting Scene\n\n"
        f"**{scene_title}** — {scene_desc}\n\n"
        "## How to load\n\n"
        "This campaign pack is stored locally and is not committed to Git.\n"
    )


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def generate_campaign_pack(
    seed: str,
    output_slug: Optional[str] = None,
    model: Optional[str] = None,
    lint: bool = True,
    repair: bool = True,
) -> Dict[str, Any]:
    """Generate an engine-ready campaign pack from a seed.

    After writing the pack, optionally lints it and applies deterministic
    repairs, writing ``lint_report.json``. Returns a metadata dict: on success
    ``{"ok": True, "slug", "folder", "title", "files", "warnings", "repaired"}``;
    on failure ``{"ok": False, "error": ...}`` (with ``"raw_path"`` when a raw
    model response was captured). Never raises.
    """
    seed = (seed or "").strip()
    if not seed:
        return {"ok": False, "error": "Empty campaign seed."}

    messages = build_generation_messages(seed)
    try:
        raw = ollama_client.chat(messages, model=model, json_mode=True, timeout=300.0)
    except ollama_client.OllamaError as exc:
        return {"ok": False, "error": f"Model call failed: {exc}"}

    # Resolve the target folder as early as possible so we can save raw output.
    provisional_slug = slugify(output_slug or seed)[:60]
    state_store.CAMPAIGNS_DIR.mkdir(parents=True, exist_ok=True)

    def _save_raw(slug: str) -> Path:
        folder = state_store.CAMPAIGNS_DIR / slug
        folder.mkdir(parents=True, exist_ok=True)
        raw_path = folder / "raw_generation_failed.txt"
        raw_path.write_text(raw, encoding="utf-8")
        return raw_path

    try:
        pack = dm_engine.parse_dm_response(raw)
    except ValueError as exc:
        raw_path = _save_raw(provisional_slug)
        return {
            "ok": False,
            "error": f"Could not parse model JSON: {exc}",
            "raw_path": str(raw_path),
        }

    campaign = pack.get("campaign") if isinstance(pack, dict) else None
    slug = slugify(
        output_slug
        or (campaign.get("slug") if isinstance(campaign, dict) else "")
        or (campaign.get("campaign_title") if isinstance(campaign, dict) else "")
        or seed
    )[:60]

    try:
        _validate(pack)
    except CampaignValidationError as exc:
        raw_path = _save_raw(slug)
        return {"ok": False, "error": f"Validation failed: {exc}", "raw_path": str(raw_path)}

    # Ensure the slug is recorded in the campaign object.
    campaign.setdefault("slug", slug)
    scenes = _get_scenes(pack)
    starting_scene = scenes[0]
    # Record the starting scene id so loaders can resolve it.
    campaign["starting_scene"] = starting_scene.get("scene_id") or "starting_scene"

    folder = state_store.CAMPAIGNS_DIR / slug
    scenes_dir = folder / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)

    scene_files = []
    used_names = set()
    for i, scene in enumerate(scenes):
        stem = slugify(scene.get("scene_id") or scene.get("scene_title") or f"scene-{i + 1}")
        # Avoid collisions if two scenes slug to the same name.
        name = stem
        suffix = 2
        while name in used_names:
            name = f"{stem}-{suffix}"
            suffix += 1
        used_names.add(name)
        _write_json(scenes_dir / f"{name}.json", scene)
        scene_files.append(f"scenes/{name}.json")

    _write_json(folder / "campaign.json", campaign)
    _write_json(folder / "npcs.json", pack.get("npcs", []))
    _write_json(folder / "locations.json", pack.get("locations", []))
    _write_json(folder / "factions.json", pack.get("factions", []))
    _write_json(folder / "rumours.json", pack.get("rumours", []))
    (folder / "session_01_outline.md").write_text(
        _render_session_outline(pack.get("session_01_outline"), campaign),
        encoding="utf-8",
    )
    (folder / "README.md").write_text(
        _render_campaign_readme(campaign, starting_scene), encoding="utf-8"
    )

    files = ["campaign.json"] + scene_files + [
        "npcs.json",
        "locations.json",
        "factions.json",
        "rumours.json",
        "session_01_outline.md",
        "README.md",
    ]

    # Post-write validation: every JSON file must exist and parse.
    for name in files:
        path = folder / name
        if not path.exists():
            return {"ok": False, "error": f"Expected file missing after write: {name}"}
        if name.endswith(".json"):
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                return {"ok": False, "error": f"Written JSON did not parse: {name} ({exc})"}

    result = {
        "ok": True,
        "slug": slug,
        "folder": str(folder),
        "title": campaign.get("campaign_title", "Untitled Campaign"),
        "files": files,
    }

    if lint:
        report = campaign_linter.process_pack(folder, do_repair=repair)
        result["warnings"] = len(report["warnings_before"])
        result["repaired"] = len(report["repairs"])
        result["lint_report"] = str(folder / "lint_report.json")

    return result
