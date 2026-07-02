# Rules Library

Local, private rules layer for the AI DM. It supports two sources: short
**starter local rules summaries**, or the **official D&D SRD 5.2.1** imported
from the CC-BY-4.0 PDF. Lookup is simple keyword search (vector search comes
later).

## What is tracked vs. generated

Tracked in git (source tooling and metadata):

- `manifests/` — ruleset manifests (e.g. `srd_5_2_1.json`, incl. the PDF URL)
- `attribution/` — license/attribution notes for each ruleset
- `house_rules/house_rules.example.md` — example house rules to copy
- `scripts/` — the installer, downloader, extractor, and lookup builder
- `srd/.gitkeep` — placeholder for the (generated) SRD content folder

Generated locally and **git-ignored** (never committed):

- `srd/<version>/source/` — the downloaded SRD PDF
- `srd/<version>/extracted/` — extracted full text + per-page JSONL
- `srd/<version>/markdown/` — rule section Markdown
- `srd/<version>/lookup/` — the built lookup index
- `installed-rules.json` — install metadata

## Starter rules (offline, no download)

```bash
python3 Shared/ai_dm/rules/scripts/install_rules.py --starter
python3 Shared/ai_dm/rules/scripts/build_rules_lookup.py
```

## Official SRD 5.2.1 import

```bash
python3 Shared/ai_dm/rules/scripts/download_srd.py
python3 -m pip install pypdf
python3 Shared/ai_dm/rules/scripts/extract_srd_text.py
python3 Shared/ai_dm/rules/scripts/build_rules_lookup.py
```

Or run the whole official workflow at once:

```bash
python3 Shared/ai_dm/rules/scripts/install_rules.py --official
```

No-network mode (use an already-downloaded PDF, never fetch):

```bash
python3 Shared/ai_dm/rules/scripts/install_rules.py --official --no-network
```

With no flags, the installer imports from the official PDF if it is already
present, otherwise it falls back to the starter summaries.

## How official SRD extraction works

Official SRD extraction creates:

- raw page text (`extracted/pages.jsonl`, `extracted/srd_5_2_1_full.txt`)
- cleaned chunk JSONL (`chunks/rules_chunks.jsonl`)
- lookup index (`lookup/rules_lookup.json`)

Extraction cleans the text (removing table-of-contents dotted-leader lines,
isolated page numbers, and footer boilerplate), skips TOC-dominated pages, and
splits the rest into overlapping ~1200-character chunks with rule-term
keywords. `build_rules_lookup.py` prefers these chunks over the rough Markdown
sections, so lookup returns real rule prose instead of table-of-contents
listings. The first extraction is heuristic and may need refinement, but lookup
should prefer real rule text over table-of-contents text.

### Canonical rules glossary

`build_rules_lookup.py` also builds a **canonical rules glossary**
(`lookup/rules_glossary.json`, via `build_rules_glossary.py`) with one
authoritative entry per common term — conditions (Grappled, Restrained, Prone,
…), rests, death/dying, and core roll mechanics. Each entry's definition is
extracted from the SRD glossary (`Term [Condition]` headings) when found, or a
short starter fallback summary otherwise. The lookup consults the glossary
**first**, so `/rule grappled` returns the *Grappled condition definition*
rather than incidental mentions in feats, items, or ancestry traits; general
chunks may still appear as later results.

Test the index directly:

```bash
python3 Shared/ai_dm/rules/scripts/build_rules_lookup.py --test-query "grapple"
```

Useful test queries: `grapple`, `grappled`, `restrained`, `short rest`,
`zero hit points`, `death saving throw`, `attack roll`, `advantage`,
`investigation`, `perception`.

## Notes on local/private data and licensing

- The downloaded SRD PDF and all extracted/generated text are **local runtime
  files** and are ignored by Git — they are never committed.
- The SRD is available under CC-BY-4.0 — see `attribution/srd_5_2_1.md`.
- Do **not** add non-SRD D&D books, adventures, campaign settings, or other
  proprietary material unless you have the legal right to use them.
