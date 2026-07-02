#!/usr/bin/env python3
"""Standalone campaign generator + linter CLI.

Generate a new pack from a seed, or lint/repair an existing pack folder:

    python3 Shared/ai_dm/app/generate_campaign.py "<seed text>" [slug] [--repair|--no-repair]
    python3 Shared/ai_dm/app/generate_campaign.py --lint-only <pack_dir>
    python3 Shared/ai_dm/app/generate_campaign.py --repair <pack_dir>

Default (seed): generate, validate, lint, repair, write lint_report.json.
Everything is local and private; nothing is sent to any cloud service.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as a plain script.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import campaign_generator
import campaign_linter


def _print_issues(issues) -> None:
    for issue in issues:
        loc = issue.get("path") or issue.get("file", "")
        print(f"  [{issue.get('severity', 'warning')}] {loc}: {issue.get('message')}")
        fix = issue.get("suggested_fix")
        if fix:
            print(f"      fix: {fix}")


def _run_existing(pack_dir: Path, do_repair: bool) -> int:
    if not (pack_dir / "campaign.json").exists():
        print(f"Not a campaign pack (no campaign.json): {pack_dir}", file=sys.stderr)
        return 2
    report = campaign_linter.process_pack(pack_dir, do_repair=do_repair)
    print(f"\n{pack_dir}")
    print(f"Warnings ({len(report['warnings_before'])}):")
    _print_issues(report["warnings_before"])
    if do_repair:
        print(f"\nRepairs ({len(report['repairs'])}):")
        _print_issues(report["repairs"])
    print(f"\n{report['summary']} — report: {pack_dir / 'lint_report.json'}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate or lint a campaign pack.")
    parser.add_argument("target", help="Seed text, or a path to an existing pack folder.")
    parser.add_argument("slug", nargs="?", default=None, help="Optional output slug (seed mode).")
    parser.add_argument("--lint-only", action="store_true", help="Lint without repairing.")
    parser.add_argument("--repair", action="store_true", help="Apply deterministic repairs.")
    parser.add_argument("--no-repair", action="store_true", help="Generate and lint but skip repair.")
    args = parser.parse_args(argv)

    target_path = Path(args.target)

    # Existing-pack mode: target is a folder that holds a campaign.
    if target_path.is_dir():
        do_repair = args.repair and not args.lint_only
        return _run_existing(target_path, do_repair=do_repair)

    # Seed mode.
    repair = not (args.lint_only or args.no_repair)
    print("Generating campaign pack (this can take a while on local models)...")
    result = campaign_generator.generate_campaign_pack(
        args.target, output_slug=args.slug, lint=True, repair=repair
    )

    if not result.get("ok"):
        print(f"\nCampaign generation failed: {result.get('error')}", file=sys.stderr)
        if result.get("raw_path"):
            print(f"Raw model response saved to: {result['raw_path']}", file=sys.stderr)
        return 1

    print(f"\nCampaign: {result['title']}")
    print(f"Folder:   {result['folder']}")
    if "warnings" in result:
        print(
            f"Campaign generated with {result['warnings']} warnings, "
            f"{result['repaired']} repaired."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
