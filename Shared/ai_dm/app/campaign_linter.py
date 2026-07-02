"""Deterministic campaign pack linter and repair layer.

Generated campaign packs are valid JSON but can be mechanically weak: wrong
skill/ability pairings, title-style check triggers, clocks that start hot,
success text that reveals too much, or messy session outlines. This module
lints those issues and applies safe deterministic repairs before a pack is
considered playable. It is not a substitute for human review.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

# Standard 5e skill -> governing ability.
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

_REQUIRED_CHECK_FIELDS = ("trigger", "ability", "skill", "dc", "success", "failure")

# Ordered trigger keyword -> suggested skill (first match wins). "old" is
# intentionally excluded from History to avoid "old woman" false positives.
_TRIGGER_SKILL_RULES = [
    (["talk", "ask", "convince", "negotiate", "bargain", "persuade"], "Persuasion"),
    (["lie", "bluff", "deceive"], "Deception"),
    (["threaten", "intimidate"], "Intimidation"),
    (["read", "motive", "suspicious", "believe", "truthful"], "Insight"),
    (["search", "inspect", "examine", "investigate", "clues", "signs"], "Investigation"),
    (["listen", "notice", "spot", "watch", "hear"], "Perception"),
    (["recall", "legend", "cult", "religion", "ritual"], "Religion"),
    (["history", "ancient", "local lore"], "History"),
    (["climb", "force", "swim", "jump", "lift"], "Athletics"),
]

# Words indicating a social interaction (used to flag physical skills on them).
_SOCIAL_WORDS = (
    "talk", "ask", "convince", "persuade", "negotiate", "bargain", "tavern",
    "keeper", "widow", "woman", "merchant", "innkeep", "rumour", "rumor",
    "gossip", "barter", "old man", "elder",
)
_PHYSICAL_SKILLS = ("Athletics", "Acrobatics")

# Title-style trigger openers (e.g. "Meeting the Tavern Keeper").
_TITLE_PREFIX_RE = re.compile(
    r"^(meeting|talking to|speaking (to|with)|visiting|approaching|encountering)\b",
    re.IGNORECASE,
)

_REVEALS_TOO_MUCH = (
    "learns everything", "reveals everything", "all the secrets", "full truth",
    "everything about", "the whole truth", "learns about a long-forgotten",
)

_OUTLINE_ARTEFACTS = ("{'", "'}", "[{", "}]", "': [", "_that_can_be_discovered :")


# ---------------------------------------------------------------------------
# Loading helpers
# ---------------------------------------------------------------------------


def _load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _scene_path(pack_dir: Path) -> Path:
    return pack_dir / "scenes" / "starting_scene.json"


def _issue(severity, file, path, message, suggested_fix="") -> Dict[str, Any]:
    return {
        "severity": severity,
        "file": file,
        "path": path,
        "message": message,
        "suggested_fix": suggested_fix,
    }


def _suggested_skill(trigger: str) -> Optional[str]:
    lowered = (trigger or "").lower()
    for keywords, skill in _TRIGGER_SKILL_RULES:
        if any(re.search(rf"\b{re.escape(k)}\b", lowered) for k in keywords):
            return skill
    return None


def _is_title_trigger(trigger: str) -> bool:
    trigger = (trigger or "").strip()
    if not trigger:
        return False
    if _TITLE_PREFIX_RE.match(trigger):
        return True
    # Title Case with no comma and no obvious action verb -> looks like a title.
    if "," not in trigger:
        words = [w for w in re.findall(r"[A-Za-z']+", trigger)]
        caps = [w for w in words if w[:1].isupper()]
        if len(words) >= 2 and len(caps) >= max(2, len(words) - 1):
            return True
    return False


# ---------------------------------------------------------------------------
# Scene loading helpers
# ---------------------------------------------------------------------------


def _load_all_scenes(pack_dir: Path) -> list:
    """Return [(relpath, path, scene_dict)] for each scene JSON in the pack."""
    scenes_dir = Path(pack_dir) / "scenes"
    out = []
    if scenes_dir.exists():
        for path in sorted(scenes_dir.glob("*.json")):
            data = _load_json(path)
            if isinstance(data, dict):
                out.append((f"scenes/{path.name}", path, data))
    return out


def _scene_id_set(scenes) -> set:
    ids = set()
    for _rel, path, data in scenes:
        ids.add(str(data.get("scene_id", "")).strip().lower())
        ids.add(path.stem.lower())
    ids.discard("")
    return ids


def _starting_scene_stem(pack_dir: Path, scenes) -> Optional[str]:
    """Return the filename stem of the starting scene (by campaign.starting_scene)."""
    campaign = _load_json(Path(pack_dir) / "campaign.json") or {}
    target = str(campaign.get("starting_scene", "")).strip().lower()
    if target:
        for _rel, path, data in scenes:
            if str(data.get("scene_id", "")).strip().lower() == target or path.stem.lower() == target:
                return path.stem
    return scenes[0][1].stem if scenes else None


# ---------------------------------------------------------------------------
# Linting (read-only)
# ---------------------------------------------------------------------------


def _lint_check(check: Any, index: int, scene_file: str) -> List[Dict[str, Any]]:
    """Lint a single default check; returns issues."""
    issues: List[Dict[str, Any]] = []
    base = f"default_checks[{index}]"
    if not isinstance(check, dict):
        issues.append(_issue("error", scene_file, base, "Check is not an object."))
        return issues

    for field in _REQUIRED_CHECK_FIELDS:
        if not str(check.get(field, "")).strip():
            issues.append(_issue(
                "error", scene_file, f"{base}.{field}",
                f"Missing required field '{field}'.",
            ))

    skill = str(check.get("skill", "")).strip()
    ability = str(check.get("ability", "")).strip()
    trigger = str(check.get("trigger", "")).strip()
    success = str(check.get("success", "")).strip()
    failure = str(check.get("failure", "")).strip()

    try:
        dc = int(check.get("dc"))
        if dc < 10 or dc > 20:
            issues.append(_issue(
                "warning", scene_file, f"{base}.dc",
                f"DC {dc} is outside the usual 10-20 range.", "Clamp the DC to 10-20.",
            ))
    except (TypeError, ValueError):
        issues.append(_issue("warning", scene_file, f"{base}.dc", "DC is not numeric."))

    if skill in SKILL_DEFAULT_ABILITIES:
        expected = SKILL_DEFAULT_ABILITIES[skill]
        if ability != expected:
            issues.append(_issue(
                "warning", scene_file, base,
                f"{ability} ({skill}) is a non-standard pairing.",
                f"Use {expected} ({skill}).",
            ))

    social = any(w in trigger.lower() or w in success.lower() for w in _SOCIAL_WORDS)
    if skill in _PHYSICAL_SKILLS and social:
        issues.append(_issue(
            "warning", scene_file, base,
            f"Social interaction uses {ability} ({skill}); a Charisma skill may "
            "be more appropriate.",
            "Use Charisma (Persuasion), Charisma (Deception), Charisma "
            "(Intimidation), or Wisdom (Insight).",
        ))

    suggested = _suggested_skill(trigger)
    if suggested and skill and suggested != skill and not (skill in _PHYSICAL_SKILLS and social):
        issues.append(_issue(
            "warning", scene_file, f"{base}.trigger",
            f"Trigger wording suggests {SKILL_DEFAULT_ABILITIES[suggested]} "
            f"({suggested}) rather than {skill}.",
            f"Consider {SKILL_DEFAULT_ABILITIES[suggested]} ({suggested}).",
        ))

    if _is_title_trigger(trigger):
        issues.append(_issue(
            "warning", scene_file, f"{base}.trigger",
            f"Trigger '{trigger}' reads like a scene title, not a player action "
            "phrase.",
            "Rewrite as comma-separated player actions (e.g. 'talk to X, ask X "
            "about Y').",
        ))

    if any(p in success.lower() for p in _REVEALS_TOO_MUCH):
        issues.append(_issue(
            "warning", scene_file, f"{base}.success",
            "Success may reveal a major secret too early.",
            "Reveal a partial clue; keep deeper secrets for later.",
        ))
    if success and len(success) < 15:
        issues.append(_issue(
            "warning", scene_file, f"{base}.success", "Success text is very vague.",
        ))

    if success and failure and success.lower() == failure.lower():
        issues.append(_issue(
            "warning", scene_file, f"{base}.failure",
            "Failure text is identical to success.",
            "On failure preserve uncertainty, add delay/ambiguity, or increase "
            "risk instead of revealing the same information.",
        ))
    return issues


def _lint_scene(scene_file, scene, is_starting, scene_ids) -> List[Dict[str, Any]]:
    """Lint a single scene; returns issues."""
    issues: List[Dict[str, Any]] = []

    for field in ("scene_id", "scene_title", "player_visible"):
        if not str(scene.get(field, "")).strip():
            issues.append(_issue("error", scene_file, field, f"Missing '{field}'."))

    interactions = scene.get("obvious_interactions") or []
    if not isinstance(interactions, list) or len(interactions) < 2:
        issues.append(_issue(
            "warning", scene_file, "obvious_interactions",
            "Scene has fewer than 2 obvious_interactions.",
        ))

    checks = scene.get("default_checks") or []
    if not isinstance(checks, list) or len(checks) < 2:
        issues.append(_issue(
            "warning", scene_file, "default_checks",
            "Scene has fewer than 2 default_checks.",
        ))
    for index, check in enumerate(checks if isinstance(checks, list) else []):
        issues += _lint_check(check, index, scene_file)

    # Exits.
    exits = scene.get("exits") or []
    for index, exit_ in enumerate(exits):
        base = f"exits[{index}]"
        if not isinstance(exit_, dict):
            issues.append(_issue("error", scene_file, base, "Exit is not an object."))
            continue
        for field in ("label", "target_scene_id", "description"):
            if not str(exit_.get(field, "")).strip():
                issues.append(_issue(
                    "warning", scene_file, f"{base}.{field}",
                    f"Exit missing '{field}'.",
                ))
        target = str(exit_.get("target_scene_id", "")).strip().lower()
        if target and target not in scene_ids:
            issues.append(_issue(
                "warning", scene_file, f"{base}.target_scene_id",
                f"Exit target '{target}' does not match any scene.",
                "Point target_scene_id at an existing scene_id.",
            ))
    if is_starting and not exits:
        issues.append(_issue(
            "warning", scene_file, "exits",
            "Starting scene has no exits; players can't travel onward.",
            "Add at least one exit to another scene.",
        ))

    for index, clock in enumerate(scene.get("scene_clocks") or []):
        if isinstance(clock, dict):
            try:
                value = int(clock.get("value", 0))
            except (TypeError, ValueError):
                value = 0
            if value > 0 and not clock.get("starts_active"):
                issues.append(_issue(
                    "warning", scene_file, f"scene_clocks[{index}].value",
                    f"Scene clock '{clock.get('name', '?')}' starts at {value} "
                    "without 'starts_active'.",
                    "Start the clock at 0, or set \"starts_active\": true.",
                ))

    for index, truth in enumerate(scene.get("hidden_truths") or []):
        low = str(truth).lower()
        if any(cue in low for cue in ("some say", "rumour", "rumor", "people say",
                                      "legend has it", "it is said", "locals believe")):
            issues.append(_issue(
                "warning", scene_file, f"hidden_truths[{index}]",
                "Hidden truth is phrased like a rumour; it may belong in "
                "rumours.json (player-visible).",
                "Move rumour-style hearsay to rumours.json.",
            ))
    return issues


def lint_campaign_pack(pack_dir: Path) -> List[Dict[str, Any]]:
    """Return a list of lint issues for a campaign pack (read-only)."""
    pack_dir = Path(pack_dir)
    issues: List[Dict[str, Any]] = []

    scenes = _load_all_scenes(pack_dir)
    if not scenes:
        issues.append(_issue(
            "error", "scenes/", "", "No scene files found.", "Re-generate the pack.",
        ))
        return issues

    if len(scenes) < 3:
        issues.append(_issue(
            "warning", "scenes/", "",
            f"Campaign has {len(scenes)} scene(s); at least 3 is recommended.",
            "Regenerate or add scenes (the linter does not invent scenes).",
        ))

    scene_ids = _scene_id_set(scenes)
    starting_stem = _starting_scene_stem(pack_dir, scenes)
    for relpath, path, scene in scenes:
        is_starting = path.stem == starting_stem
        issues += _lint_scene(relpath, scene, is_starting, scene_ids)

    outline_path = pack_dir / "session_01_outline.md"
    if outline_path.exists():
        text = outline_path.read_text(encoding="utf-8")
        if any(a in text for a in _OUTLINE_ARTEFACTS):
            issues.append(_issue(
                "warning", "session_01_outline.md", "",
                "Session outline contains JSON/Python artefacts.",
                "Regenerate the outline as clean Markdown.",
            ))

    return issues


# ---------------------------------------------------------------------------
# Repair (mutating)
# ---------------------------------------------------------------------------


def _rewrite_title_trigger(trigger: str) -> str:
    """Turn a title-style trigger into comma-separated player-action phrases."""
    subject = _TITLE_PREFIX_RE.sub("", trigger).strip()
    subject = re.sub(r"^(the|a|an)\s+", "", subject, flags=re.IGNORECASE).strip()
    subject = subject.lower() or "them"
    return f"talk to {subject}, ask {subject} about the situation, read their motives"


def _repair_scene(scene: Dict[str, Any], scene_file: str) -> List[Dict[str, Any]]:
    """Apply deterministic repairs to a single scene dict; returns actions."""
    repairs: List[Dict[str, Any]] = []

    for index, check in enumerate(scene.get("default_checks") or []):
        if not isinstance(check, dict):
            continue
        base = f"default_checks[{index}]"
        trigger = str(check.get("trigger", "")).strip()

        # 1. Title-style trigger -> action phrases.
        if _is_title_trigger(trigger):
            new_trigger = _rewrite_title_trigger(trigger)
            check["trigger"] = new_trigger
            repairs.append(_issue(
                "repair", scene_file, f"{base}.trigger",
                f"Rewrote title-style trigger to action phrases: '{new_trigger}'.",
            ))
            trigger = new_trigger

        skill = str(check.get("skill", "")).strip()
        ability = str(check.get("ability", "")).strip()
        success = str(check.get("success", "")).strip()

        # 2. Social interaction on a physical skill -> Persuasion (Charisma).
        social = any(w in trigger.lower() or w in success.lower() for w in _SOCIAL_WORDS)
        if skill in _PHYSICAL_SKILLS and social:
            check["skill"] = "Persuasion"
            check["ability"] = "Charisma"
            repairs.append(_issue(
                "repair", scene_file, base,
                f"Changed {ability} ({skill}) to Charisma (Persuasion) for a "
                "social interaction.",
            ))
            skill, ability = "Persuasion", "Charisma"

        # 3. Fix skill/ability mismatch to the standard governing ability.
        if skill in SKILL_DEFAULT_ABILITIES:
            expected = SKILL_DEFAULT_ABILITIES[skill]
            if ability != expected:
                check["ability"] = expected
                repairs.append(_issue(
                    "repair", scene_file, base,
                    f"Set ability to {expected} to match {skill}.",
                ))

        # 4. Clamp DC into 10-20.
        try:
            dc = int(check.get("dc"))
            clamped = max(10, min(20, dc))
            if clamped != dc:
                check["dc"] = clamped
                repairs.append(_issue(
                    "repair", scene_file, f"{base}.dc",
                    f"Clamped DC {dc} to {clamped}.",
                ))
        except (TypeError, ValueError):
            check["dc"] = 13
            repairs.append(_issue(
                "repair", scene_file, f"{base}.dc", "Set missing/invalid DC to 13.",
            ))

    # 5. Reset scene clocks that start hot without starts_active.
    for index, clock in enumerate(scene.get("scene_clocks") or []):
        if not isinstance(clock, dict):
            continue
        try:
            value = int(clock.get("value", 0))
        except (TypeError, ValueError):
            value = 0
        if value > 0 and not clock.get("starts_active"):
            clock["value"] = 0
            repairs.append(_issue(
                "repair", scene_file, f"scene_clocks[{index}].value",
                f"Reset clock '{clock.get('name', '?')}' from {value} to 0.",
            ))

    return repairs


def repair_campaign_pack(pack_dir: Path) -> List[Dict[str, Any]]:
    """Apply safe deterministic repairs across all scenes; return actions."""
    pack_dir = Path(pack_dir)
    repairs: List[Dict[str, Any]] = []

    for relpath, path, scene in _load_all_scenes(pack_dir):
        scene_repairs = _repair_scene(scene, relpath)
        if scene_repairs:
            _write_json(path, scene)
            repairs += scene_repairs

    # Regenerate the session outline deterministically from the whole pack.
    if rebuild_session_outline(pack_dir):
        repairs.append(_issue(
            "repair", "session_01_outline.md", "",
            "Regenerated the session outline as clean Markdown from the pack.",
        ))

    return repairs


def _scene_flow(pack_dir: Path, scenes) -> list:
    """Order scene titles by following exits from the starting scene."""
    by_stem = {path.stem: data for _rel, path, data in scenes}
    by_id = {}
    for _rel, path, data in scenes:
        by_id[str(data.get("scene_id", "")).strip().lower()] = data
        by_id[path.stem.lower()] = data

    start_stem = _starting_scene_stem(pack_dir, scenes)
    order = []
    visited = set()
    current = by_stem.get(start_stem)
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        order.append(current.get("scene_title", "Untitled scene"))
        nxt = None
        for exit_ in current.get("exits") or []:
            if isinstance(exit_, dict):
                target = str(exit_.get("target_scene_id", "")).strip().lower()
                candidate = by_id.get(target)
                if candidate is not None and id(candidate) not in visited:
                    nxt = candidate
                    break
        current = nxt

    # Append any scenes not reachable by exits, in file order.
    for _rel, _path, data in scenes:
        title = data.get("scene_title", "Untitled scene")
        if title not in order:
            order.append(title)
    return order


def rebuild_session_outline(pack_dir: Path) -> bool:
    """Rebuild session_01_outline.md from all scenes. Returns True if written."""
    pack_dir = Path(pack_dir)
    campaign = _load_json(pack_dir / "campaign.json") or {}
    npcs = _load_json(pack_dir / "npcs.json") or []
    scenes = _load_all_scenes(pack_dir)

    starting_stem = _starting_scene_stem(pack_dir, scenes)
    starting = {}
    for _rel, path, data in scenes:
        if path.stem == starting_stem:
            starting = data
            break

    def bullets(items):
        items = [str(i).strip() for i in (items or []) if str(i).strip()]
        return "\n".join(f"- {i}" for i in items) if items else "_(TBD)_"

    npc_lines = bullets([n.get("name") for n in npcs if isinstance(n, dict)])

    check_lines = []
    for check in starting.get("default_checks") or []:
        if not isinstance(check, dict):
            continue
        trigger = str(check.get("trigger", "")).strip()
        label = trigger.split(",")[0].strip().capitalize() or "Check"
        check_lines.append(
            f"- **{label}** — {check.get('ability', '')} ({check.get('skill', '')}), "
            f"DC {check.get('dc', '')}  \n"
            f"  Success: {str(check.get('success', '')).strip()}  \n"
            f"  Failure: {str(check.get('failure', '')).strip()}"
        )
    checks_block = "\n".join(check_lines) if check_lines else "_(TBD)_"

    scene_titles = [data.get("scene_title", "Untitled scene") for _r, _p, data in scenes]
    flow = _scene_flow(pack_dir, scenes)
    flow_line = " → ".join(flow) if flow else "_(TBD)_"

    opening = str(starting.get("current_situation") or campaign.get("summary") or "").strip()
    outline = (
        "# Session 1 Outline\n\n"
        "## Opening Situation\n\n"
        f"{opening or '_(TBD)_'}\n\n"
        "## Scenes\n\n"
        f"{bullets(scene_titles)}\n\n"
        "## Possible Scene Flow\n\n"
        f"{flow_line}\n\n"
        "## Key NPCs\n\n"
        f"{npc_lines}\n\n"
        "## Likely Player Actions\n\n"
        f"{bullets(starting.get('obvious_interactions'))}\n\n"
        "## Possible Checks\n\n"
        f"{checks_block}\n\n"
        "## Secrets That Can Be Discovered\n\n"
        f"{bullets(starting.get('hidden_truths'))}\n\n"
        "## Escalation\n\n"
        f"{bullets([c.get('description') for c in (starting.get('scene_clocks') or []) if isinstance(c, dict)])}\n\n"
        "## Ending Options\n\n"
        f"{bullets(campaign.get('open_threads'))}\n"
    )
    (pack_dir / "session_01_outline.md").write_text(outline, encoding="utf-8")
    return True


def process_pack(pack_dir: Path, do_repair: bool = True) -> Dict[str, Any]:
    """Lint, optionally repair, and write lint_report.json. Returns a summary."""
    pack_dir = Path(pack_dir)
    issues = lint_campaign_pack(pack_dir)
    repairs = repair_campaign_pack(pack_dir) if do_repair else []
    issues_after = lint_campaign_pack(pack_dir) if do_repair else issues

    report = {
        "pack": pack_dir.name,
        "repaired": bool(do_repair),
        "warnings_before": issues,
        "repairs": repairs,
        "warnings_after": issues_after,
        "summary": f"{len(issues)} warnings, {len(repairs)} repaired",
    }
    _write_json(pack_dir / "lint_report.json", report)
    return report
