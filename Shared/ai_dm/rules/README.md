# Rules Library

Local, private rules layer for the AI DM. This milestone uses short **starter
local rules summaries** and simple keyword lookup — full SRD import/parsing and
vector search will come later.

## What is tracked vs. generated

Tracked in git (source tooling and metadata):

- `manifests/` — ruleset manifests (e.g. `srd_5_2_1.json`)
- `attribution/` — license/attribution notes for each ruleset
- `house_rules/house_rules.example.md` — example house rules to copy
- `scripts/` — the installer and lookup builder
- `srd/.gitkeep` — placeholder for the (generated) SRD content folder

Generated locally and **git-ignored** (never committed):

- `srd/<version>/markdown/` — installed rule summary Markdown
- `srd/<version>/lookup/` — the built lookup index
- `installed-rules.json` — install metadata

## Install and build the lookup index

```bash
python3 Shared/ai_dm/rules/scripts/install_rules.py
python3 Shared/ai_dm/rules/scripts/build_rules_lookup.py
```

Then, inside the DM runner, use `/rules-status` and `/rule <query>`.

## Licensing

SRD content is available under CC-BY-4.0 — see `attribution/srd_5_2_1.md`. Do
not add non-SRD copyrighted D&D books, adventures, or settings unless you have
the legal right to use them.
