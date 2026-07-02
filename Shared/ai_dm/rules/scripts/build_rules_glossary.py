#!/usr/bin/env python3
"""Build a canonical rules glossary for common D&D terms.

For conditions, rests, death/dying, core roll mechanics, and actions, this
writes one authoritative entry per term to
``srd/<version>/lookup/rules_glossary.json``. Entries are extracted from the
cleaned SRD chunks when a confident definition is found, otherwise a short
starter fallback summary is used. The glossary lets the lookup return the
*definition* for e.g. "grappled" instead of incidental mentions in feats,
items, or ancestry traits.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

RULES_DIR = Path(__file__).resolve().parent.parent
SRD_VERSION = "5.2.1"
SRD_DIR = RULES_DIR / "srd" / SRD_VERSION
CHUNKS_PATH = SRD_DIR / "chunks" / "rules_chunks.jsonl"
LOOKUP_DIR = SRD_DIR / "lookup"
GLOSSARY_INDEX = LOOKUP_DIR / "rules_glossary.json"
MANIFEST = RULES_DIR / "manifests" / "srd_5_2_1.json"

FALLBACK_SOURCE = "starter local fallback summary"

# term definitions: (id, term, title, category, aliases, fallback_text)
TERMS = [
    ("condition_grappled", "grappled", "Grappled", "condition",
     ["grapple", "grappling", "grab", "grabbed"],
     "Grappled: the creature's Speed becomes 0 and it can't benefit from any "
     "bonus to Speed. The condition ends if the grappler is Incapacitated, or "
     "if an effect moves the grappled creature outside the grappler's reach."),
    ("condition_restrained", "restrained", "Restrained", "condition",
     ["restrain"],
     "Restrained: the creature's Speed becomes 0. Attack rolls against it have "
     "Advantage, and its own attack rolls and Dexterity saving throws have "
     "Disadvantage."),
    ("condition_prone", "prone", "Prone", "condition", ["knocked prone"],
     "Prone: the creature can only crawl unless it stands up. It has "
     "Disadvantage on attack rolls. An attack roll against it has Advantage if "
     "the attacker is within 5 feet, otherwise Disadvantage."),
    ("condition_stunned", "stunned", "Stunned", "condition", ["stun"],
     "Stunned: the creature is Incapacitated, can't move, and can speak only "
     "falteringly. It automatically fails Strength and Dexterity saving "
     "throws, and attack rolls against it have Advantage."),
    ("condition_frightened", "frightened", "Frightened", "condition",
     ["fear", "afraid"],
     "Frightened: the creature has Disadvantage on ability checks and attack "
     "rolls while the source of its fear is within line of sight, and it can't "
     "willingly move closer to that source."),
    ("condition_charmed", "charmed", "Charmed", "condition", ["charm"],
     "Charmed: the creature can't attack the charmer or target it with "
     "harmful effects, and the charmer has Advantage on ability checks to "
     "interact socially with it."),
    ("condition_incapacitated", "incapacitated", "Incapacitated", "condition",
     [],
     "Incapacitated: the creature can't take actions, Bonus Actions, or "
     "Reactions, and can't concentrate."),
    ("condition_unconscious", "unconscious", "Unconscious", "condition",
     ["knocked out"],
     "Unconscious: the creature is Incapacitated, can't move or speak, and is "
     "unaware of its surroundings. It drops what it's holding and falls Prone, "
     "automatically fails Strength and Dexterity saving throws, and attack "
     "rolls against it have Advantage."),
    ("condition_invisible", "invisible", "Invisible", "condition",
     ["invisibility"],
     "Invisible: the creature can't be seen without special senses. It has "
     "Advantage on attack rolls, attack rolls against it have Disadvantage, "
     "and it is effectively Heavily Obscured for being found."),
    ("condition_poisoned", "poisoned", "Poisoned", "condition", ["poison"],
     "Poisoned: the creature has Disadvantage on attack rolls and ability "
     "checks."),
    ("condition_exhaustion", "exhaustion", "Exhaustion", "condition",
     ["exhausted"],
     "Exhaustion: measured in levels (1-6). Each level gives a cumulative "
     "penalty to d20 rolls and reduces Speed; at level 6 the creature dies. A "
     "Long Rest removes one level of Exhaustion."),
    ("rest_short", "short rest", "Short Rest", "rest", ["shortrest"],
     "Short Rest: a period of downtime of at least 1 hour. A creature can "
     "spend Hit Dice to regain hit points, rolling each die and adding its "
     "Constitution modifier. Some features recharge on a Short Rest."),
    ("rest_long", "long rest", "Long Rest", "rest", ["longrest"],
     "Long Rest: at least 8 hours of rest. A creature regains all lost hit "
     "points and recovers spent Hit Dice (up to half its total). Features that "
     "recharge on a Long Rest reset."),
    ("death_saving_throw", "death saving throw", "Death Saving Throw", "death",
     ["death save", "death saves"],
     "Death Saving Throw: made at the start of your turn while at 0 hit "
     "points. Roll a d20: 10 or higher is a success, 9 or lower a failure. "
     "Three successes make you Stable; three failures mean death. A natural 20 "
     "restores 1 hit point; a natural 1 counts as two failures."),
    ("death_zero_hp", "zero hit points", "Zero Hit Points", "death",
     ["0 hit points", "dying", "dropping to 0"],
     "Zero Hit Points: when you drop to 0 hit points you fall Unconscious and "
     "are dying. Each turn you make a Death Saving Throw. Taking damage at 0 "
     "HP causes a failed save (a critical hit causes two), and healing above 0 "
     "HP returns you to consciousness."),
    ("mech_ability_check", "ability check", "Ability Check", "roll_mechanic",
     ["skill check", "check"],
     "Ability Check: a d20 roll plus an ability modifier (and Proficiency "
     "Bonus if proficient) against a Difficulty Class (DC). Used when the "
     "outcome of an uncertain task matters."),
    ("mech_saving_throw", "saving throw", "Saving Throw", "roll_mechanic",
     ["save", "saving throws"],
     "Saving Throw: a d20 roll plus the relevant ability modifier (and "
     "Proficiency Bonus if proficient in that save) to resist an effect, "
     "against a DC set by that effect."),
    ("mech_attack_roll", "attack roll", "Attack Roll", "roll_mechanic",
     ["attack rolls", "to hit"],
     "Attack Roll: a d20 plus your attack modifier versus the target's Armor "
     "Class (AC). Meeting or beating the AC is a hit; a natural 20 is a "
     "critical hit and a natural 1 an automatic miss."),
    ("mech_advantage", "advantage", "Advantage", "roll_mechanic", [],
     "Advantage: roll two d20s and use the higher result. Advantage doesn't "
     "stack, and it cancels out with Disadvantage."),
    ("mech_disadvantage", "disadvantage", "Disadvantage", "roll_mechanic", [],
     "Disadvantage: roll two d20s and use the lower result. Disadvantage "
     "doesn't stack, and it cancels out with Advantage."),
    ("mech_proficiency", "proficiency", "Proficiency Bonus", "roll_mechanic",
     ["proficiency bonus", "proficient"],
     "Proficiency Bonus: added to d20 rolls you're proficient with (attacks, "
     "ability checks, saving throws) and increases with level, starting at "
     "+2."),
    ("mech_initiative", "initiative", "Initiative", "roll_mechanic", [],
     "Initiative: a Dexterity check made at the start of combat to determine "
     "turn order, from highest result to lowest."),
    ("action_action", "action", "Action", "action", ["actions"],
     "Action: on your turn you can take one action, such as Attack, Dash, "
     "Disengage, Dodge, Help, Hide, Ready, Search, or Magic (Cast a Spell)."),
    ("action_bonus", "bonus action", "Bonus Action", "action", [],
     "Bonus Action: a limited extra action you can take on your turn only when "
     "a feature, spell, or ability specifically lets you take one."),
    ("action_reaction", "reaction", "Reaction", "action", [],
     "Reaction: an instant response taken when its trigger occurs, usable once "
     "per round (for example, an Opportunity Attack)."),
]

_DEFINITION_CUES = (
    "speed becomes 0", "the creature", "a creature", "condition ends",
    "hit points", "a d20", "roll a d20", "roll two d20", "rest is",
    "at least 1 hour", "at least 8 hours", "turn order", "difficulty class",
)
# Cues that a chunk is a feat/item/ancestry body, not a definition.
_NON_DEF_CUES = (
    "prerequisite", "this feat", "martial weapon", "this weapon", "ancestry",
    "lineage", "you gain the following", "powerful build",
)
# Cues that a chunk is a monster stat block, not a rule definition.
_STATBLOCK_RE = re.compile(
    r"\(\d+d\d+\)|escape dc|multiattack|melee attack roll|ranged attack roll|\bhit:",
    re.IGNORECASE,
)
# The SRD glossary formats entries as "Grappled [Condition]" / "Dash [Action]".
_NEXT_ENTRY_RE = re.compile(r"[A-Z][A-Za-z ]+\[[^\]]+\]")


def _load_chunks() -> list:
    if not CHUNKS_PATH.exists():
        return []
    chunks = []
    with CHUNKS_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                chunks.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return chunks


def _extract_canonical(term: str, chunks: list):
    """Return (text, source, page) for a confident canonical definition, or None.

    Strongly prefers the SRD glossary "Term [Condition]"/"Term [Action]" format;
    otherwise accepts a term used as a label near a chunk's start. Monster stat
    blocks and feat/item/ancestry bodies are penalised so incidental mentions
    do not win.
    """
    term_lower = term.lower()
    bracket_re = re.compile(rf"{re.escape(term)}\s*\[[^\]]+\]", re.IGNORECASE)
    best = None
    best_score = -1
    for chunk in chunks:
        text = str(chunk.get("text", ""))
        lowered = text.lower()

        match = bracket_re.search(text)
        if match:
            start = match.start()
            score = 500  # canonical glossary heading format
        else:
            pos = lowered.find(term_lower)
            if pos == -1 or pos > 200:
                continue
            start = pos
            score = 200 - pos
            before = text[max(0, pos - 2):pos].strip()
            if pos == 0 or before in ("", ".", ":", "\n"):
                score += 100
            after = lowered[pos: pos + 200]
            if any(cue in after for cue in _DEFINITION_CUES):
                score += 60

        if _STATBLOCK_RE.search(text):
            score -= 300
        if any(bad in lowered for bad in _NON_DEF_CUES):
            score -= 150
        # Prefer the copy with the most definition text after the term, so a
        # heading near a chunk's end loses to the overlapping chunk that has
        # the full definition.
        score += min(len(text) - start, 600) // 10

        if score > best_score:
            best_score = score
            best = (text, start, chunk)

    if best and best_score >= 300:
        text, start, chunk = best
        block = text[start: start + 600]
        # Cut at the next glossary entry heading, if any (skip our own term).
        nxt = _NEXT_ENTRY_RE.search(block, len(term) + 2)
        if nxt:
            block = block[: nxt.start()]
        block = re.sub(r"\s+", " ", block).strip()
        return block, chunk.get("source", "Dungeons & Dragons SRD 5.2.1"), chunk.get("page")
    return None


def _license() -> str:
    if MANIFEST.exists():
        try:
            return json.loads(MANIFEST.read_text(encoding="utf-8")).get(
                "license", "CC-BY-4.0"
            )
        except json.JSONDecodeError:
            pass
    return "CC-BY-4.0"


def build_glossary() -> int:
    """Build the glossary JSON; returns the number of entries written."""
    chunks = _load_chunks()
    license_name = _license()
    entries = []
    extracted = 0
    for entry_id, term, title, category, aliases, fallback in TERMS:
        found = _extract_canonical(title, chunks) or _extract_canonical(term, chunks)
        if found:
            text, source, page = found
            extracted += 1
        else:
            text, source, page = fallback, FALLBACK_SOURCE, None
        entries.append(
            {
                "id": entry_id,
                "term": term,
                "title": title,
                "category": category,
                "source": source,
                "license": license_name,
                "text": text,
                "aliases": aliases,
                "priority": 100,
                "page": page,
            }
        )

    LOOKUP_DIR.mkdir(parents=True, exist_ok=True)
    GLOSSARY_INDEX.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"Wrote {len(entries)} glossary entries ({extracted} extracted, "
        f"{len(entries) - extracted} fallback) -> "
        f"Shared/ai_dm/rules/srd/{SRD_VERSION}/lookup/rules_glossary.json"
    )
    return len(entries)


def main() -> int:
    build_glossary()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
