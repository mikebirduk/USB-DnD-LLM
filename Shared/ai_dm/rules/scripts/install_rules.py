#!/usr/bin/env python3
"""Install a starter local rules library for the AI DM.

For this milestone the installer writes short SRD-compatible summary Markdown
files (not copied long SRD text) into the local rules folder and records
install metadata. A later milestone will replace this with a real SRD
downloader/parser. Everything is written locally under the repo; no network
access, no cloud APIs.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

# .../ai_dm/rules/scripts/install_rules.py -> RULES_DIR = .../ai_dm/rules
RULES_DIR = Path(__file__).resolve().parent.parent
SRD_VERSION = "5.2.1"
SRD_DIR = RULES_DIR / "srd" / SRD_VERSION
MARKDOWN_DIR = SRD_DIR / "markdown"
LOOKUP_DIR = SRD_DIR / "lookup"
INSTALLED_RULES = RULES_DIR / "installed-rules.json"

# Repo-relative path recorded in metadata (portable across machines/USB).
LOCAL_PATH = f"Shared/ai_dm/rules/srd/{SRD_VERSION}"

STARTER_RULES = {
    "ability_checks.md": """# Ability Checks

Use an ability check when a character attempts an uncertain task and the outcome matters.

The DM chooses an ability, and may choose a skill proficiency if relevant.

Common examples:
- Wisdom (Perception): noticing danger or hidden details
- Intelligence (Investigation): deducing clues from close inspection
- Strength (Athletics): climbing, jumping, forcing, grappling
- Dexterity (Stealth): moving quietly or hiding

Difficulty Classes:
- DC 10: easy
- DC 13: moderate
- DC 15: hard
- DC 20: very hard
""",
    "combat.md": """# Combat

Combat runs in rounds. At the start, each combatant rolls initiative (a Dexterity
check) to set the turn order.

On your turn you can:
- Move up to your speed.
- Take one action (Attack, Dash, Dodge, Hide, Help, Search, and so on).
- Take one bonus action if something grants it.

Outside your turn you may take one reaction (such as an opportunity attack) when
its trigger occurs. An attack roll adds the relevant modifier and compares to the
target's Armor Class (AC).
""",
    "conditions.md": """# Conditions

Short summaries of common conditions:

- Grappled: speed becomes 0; ends if the grappler is incapacitated or you are
  moved out of reach.
- Prone: you can only crawl; disadvantage on attack rolls; melee attackers have
  advantage against you.
- Restrained: speed 0; disadvantage on attacks and Dexterity saves; attacks
  against you have advantage.
- Stunned: incapacitated, can't move, can barely speak; auto-fail Strength and
  Dexterity saves; attacks against you have advantage.
- Frightened: disadvantage on checks and attacks while the source is in sight;
  can't willingly move closer to it.
- Charmed: can't attack the charmer; the charmer has advantage on social checks
  against you.
""",
    "resting.md": """# Resting and Recovery

- Short rest: at least 1 hour. You may spend Hit Dice to regain hit points,
  rolling each die and adding your Constitution modifier.
- Long rest: at least 8 hours. You regain all lost hit points and recover some
  spent Hit Dice.
- Exhaustion is reduced by one level after a long rest (given food and drink).

Healing generally comes from spending Hit Dice, magic, or completing a long rest.
""",
    "death_and_dying.md": """# Death and Dying

At 0 hit points you fall unconscious and must make death saving throws.

- On your turn, roll a d20: 10 or higher is a success, lower is a failure.
- Three successes: you become stable (unconscious but no longer dying).
- Three failures: you die.
- A natural 20 restores 1 hit point; a natural 1 counts as two failures.

Taking any damage while at 0 hit points causes a failed death save, and healing
above 0 hit points returns you to consciousness.
""",
}


def main() -> int:
    MARKDOWN_DIR.mkdir(parents=True, exist_ok=True)
    LOOKUP_DIR.mkdir(parents=True, exist_ok=True)

    for filename, content in STARTER_RULES.items():
        (MARKDOWN_DIR / filename).write_text(content, encoding="utf-8")
        print(f"  wrote {LOCAL_PATH}/markdown/{filename}")

    metadata = {
        "ruleset": "dnd-srd",
        "version": SRD_VERSION,
        "source": "starter local rules summaries",
        "license": "CC-BY-4.0 compatible placeholder summaries",
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "local_path": LOCAL_PATH,
    }
    INSTALLED_RULES.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  wrote Shared/ai_dm/rules/installed-rules.json")
    print(
        f"\nInstalled {len(STARTER_RULES)} starter rule docs for "
        f"dnd-srd {SRD_VERSION}."
    )
    print("Next: python3 Shared/ai_dm/rules/scripts/build_rules_lookup.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
