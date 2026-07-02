#!/usr/bin/env python3
"""Install the local rules library for the AI DM.

Two modes:
  --starter  : write short SRD-compatible summary Markdown (no long SRD text).
  --official : download + extract the official SRD 5.2.1 PDF, then build.
Default: use the official PDF if it is already present, else starter fallback.

Everything is written locally under the repo; the official workflow downloads
the CC-BY-4.0 SRD PDF only. No cloud APIs.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# .../ai_dm/rules/scripts/install_rules.py -> RULES_DIR = .../ai_dm/rules
SCRIPTS_DIR = Path(__file__).resolve().parent
RULES_DIR = SCRIPTS_DIR.parent
MANIFEST = RULES_DIR / "manifests" / "srd_5_2_1.json"
SRD_VERSION = "5.2.1"
SRD_DIR = RULES_DIR / "srd" / SRD_VERSION
SOURCE_DIR = SRD_DIR / "source"
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


def _pdf_path() -> Path:
    pdf_filename = "SRD_CC_v5.2.1.pdf"
    if MANIFEST.exists():
        try:
            pdf_filename = json.loads(MANIFEST.read_text(encoding="utf-8")).get(
                "pdf_filename", pdf_filename
            )
        except json.JSONDecodeError:
            pass
    return SOURCE_DIR / pdf_filename


def _write_installed(mode: str, source: str) -> None:
    metadata = {
        "ruleset": "dnd-srd",
        "version": SRD_VERSION,
        "source": source,
        "license": "CC-BY-4.0",
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "local_path": LOCAL_PATH,
        "mode": mode,
    }
    INSTALLED_RULES.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("  wrote Shared/ai_dm/rules/installed-rules.json")


def _run(script: str, extra=None) -> int:
    """Run a sibling script with the same interpreter; return its exit code."""
    cmd = [sys.executable, str(SCRIPTS_DIR / script)] + (extra or [])
    return subprocess.run(cmd).returncode


def install_starter() -> int:
    MARKDOWN_DIR.mkdir(parents=True, exist_ok=True)
    LOOKUP_DIR.mkdir(parents=True, exist_ok=True)
    for filename, content in STARTER_RULES.items():
        (MARKDOWN_DIR / filename).write_text(content, encoding="utf-8")
        print(f"  wrote {LOCAL_PATH}/markdown/{filename}")
    _write_installed("starter", "starter local rules summaries")
    print(
        f"\nInstalled {len(STARTER_RULES)} starter rule docs for dnd-srd "
        f"{SRD_VERSION}."
    )
    print("Next: python3 Shared/ai_dm/rules/scripts/build_rules_lookup.py")
    return 0


def install_official(no_network: bool) -> int:
    pdf = _pdf_path()

    if not pdf.exists():
        if no_network:
            print(f"No local SRD PDF at {pdf} and --no-network was set.", file=sys.stderr)
            print(
                "Download it first: python3 Shared/ai_dm/rules/scripts/download_srd.py",
                file=sys.stderr,
            )
            return 1
        print("Downloading official SRD PDF...")
        if _run("download_srd.py") != 0:
            print("Download failed; official install aborted.", file=sys.stderr)
            return 1

    print("Extracting SRD text and building Markdown sections...")
    if _run("extract_srd_text.py") != 0:
        print(
            "Extraction failed. If pypdf is missing, install it:\n"
            "  python3 -m pip install pypdf",
            file=sys.stderr,
        )
        return 1

    print("Building rules lookup index...")
    if _run("build_rules_lookup.py") != 0:
        print("Lookup build failed.", file=sys.stderr)
        return 1

    _write_installed("official_pdf", "Dungeons & Dragons SRD 5.2.1")
    print("\nInstalled official SRD 5.2.1 rules from local PDF.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Install the AI DM rules library.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--starter", action="store_true", help="Generate starter summary files only."
    )
    group.add_argument(
        "--official", action="store_true", help="Use the official SRD PDF workflow."
    )
    parser.add_argument(
        "--no-network",
        action="store_true",
        help="Do not download; use an existing local PDF if present.",
    )
    args = parser.parse_args(argv)

    if args.starter:
        return install_starter()
    if args.official:
        return install_official(no_network=args.no_network)

    # Default: official if the PDF is already present, else starter fallback.
    if _pdf_path().exists():
        print("Official SRD PDF found — importing from PDF.")
        return install_official(no_network=True)
    print("No official SRD PDF found — installing starter summaries.")
    return install_starter()


if __name__ == "__main__":
    raise SystemExit(main())
