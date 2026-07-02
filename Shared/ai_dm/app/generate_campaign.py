#!/usr/bin/env python3
"""Standalone campaign generator CLI.

Usage:
    python3 Shared/ai_dm/app/generate_campaign.py "<seed text>" [slug]

Generates an engine-ready campaign pack under Shared/ai_dm/campaigns/<slug>/
using the local model. Prints the output folder and campaign title. Local and
private — nothing is sent to any cloud service.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running as a plain script.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import campaign_generator


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print('Usage: generate_campaign.py "<seed text>" [slug]', file=sys.stderr)
        return 2

    seed = argv[0]
    output_slug = argv[1] if len(argv) > 1 else None

    print("Generating campaign pack (this can take a while on local models)...")
    result = campaign_generator.generate_campaign_pack(seed, output_slug=output_slug)

    if not result.get("ok"):
        print(f"\nCampaign generation failed: {result.get('error')}", file=sys.stderr)
        if result.get("raw_path"):
            print(f"Raw model response saved to: {result['raw_path']}", file=sys.stderr)
        return 1

    print(f"\nCampaign: {result['title']}")
    print(f"Folder:   {result['folder']}")
    print("Files:")
    for name in result["files"]:
        print(f"  - {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
