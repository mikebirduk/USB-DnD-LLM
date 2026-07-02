#!/usr/bin/env python3
"""Download the official D&D SRD 5.2.1 PDF locally (standard library only).

The PDF URL and filename come from the manifest, not hard-coded here. The
downloaded PDF is a local runtime file (git-ignored) and is never committed.
No cloud APIs are used — this only fetches the CC-BY-4.0 SRD PDF.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

# .../ai_dm/rules/scripts/download_srd.py -> RULES_DIR = .../ai_dm/rules
RULES_DIR = Path(__file__).resolve().parent.parent
MANIFEST = RULES_DIR / "manifests" / "srd_5_2_1.json"


def _load_manifest() -> dict:
    if not MANIFEST.exists():
        raise FileNotFoundError(f"Manifest not found: {MANIFEST}")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _paths(manifest: dict):
    version = manifest.get("version", "5.2.1")
    pdf_filename = manifest.get("pdf_filename", "SRD.pdf")
    source_dir = RULES_DIR / "srd" / version / "source"
    return source_dir, source_dir / pdf_filename


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Download the SRD 5.2.1 PDF.")
    parser.add_argument(
        "--force", action="store_true", help="Re-download even if the PDF exists."
    )
    parser.add_argument(
        "--no-network",
        action="store_true",
        help="Do not download; only verify whether the local PDF exists.",
    )
    args = parser.parse_args(argv)

    try:
        manifest = _load_manifest()
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"Could not read manifest: {exc}", file=sys.stderr)
        return 1

    pdf_url = manifest.get("pdf_url")
    source_dir, dest = _paths(manifest)

    if args.no_network:
        if dest.exists():
            size = dest.stat().st_size
            print(f"Local SRD PDF present: {dest} ({size:,} bytes)")
            return 0
        print(f"No local SRD PDF found at {dest}", file=sys.stderr)
        print("Run without --no-network to download it.", file=sys.stderr)
        return 1

    if dest.exists() and not args.force:
        size = dest.stat().st_size
        print(f"SRD PDF already present: {dest} ({size:,} bytes)")
        print("Use --force to re-download.")
        return 0

    if not pdf_url:
        print("Manifest has no 'pdf_url' to download.", file=sys.stderr)
        return 1

    source_dir.mkdir(parents=True, exist_ok=True)
    print(f"Source URL : {pdf_url}")
    print(f"Destination: {dest}")

    request = urllib.request.Request(pdf_url, headers={"User-Agent": "USB-DnD-LLM/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        print(f"\nDownload failed: {exc}", file=sys.stderr)
        print(
            "Check your connection, or download the SRD PDF manually from "
            f"{manifest.get('source_page_url', 'the SRD page')} and place it at:\n"
            f"  {dest}",
            file=sys.stderr,
        )
        return 1

    dest.write_bytes(data)
    print(f"File size  : {len(data):,} bytes")
    print("\nDownloaded SRD PDF. Next:")
    print("  python3 -m pip install pypdf")
    print("  python3 Shared/ai_dm/rules/scripts/extract_srd_text.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
