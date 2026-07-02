# AI DM

This folder contains the local/private AI Dungeon Master system.

The repo tracks source files, prompts, templates, and examples.

Private runtime data such as generated campaigns, saves, logs, vector indexes, SQLite databases, and downloaded models should stay local on the USB/SSD and should not be committed.

## Milestone 1: basic DM turn loop

A minimal terminal prototype. You type a player action, it is sent to a
local Ollama model with campaign context, and the Dungeon Master's reply is
printed and appended to a local session log.

This uses the repo's portable Mac install flow — it downloads the models and
a portable Ollama runtime into `Shared/`, so you do not need a system-wide
Ollama install or a manual `ollama pull`.

```bash
chmod +x Mac/install.command
./Mac/install.command

chmod +x Mac/start.command
./Mac/start.command

python3 Shared/ai_dm/app/run_dm.py
```

`install.command` writes the installed model names to
`Shared/models/installed-models.txt`, and the runner automatically uses the
first one. You can check what was installed with:

```bash
cat Shared/models/installed-models.txt
```

To override which model is used, set `AI_DM_MODEL`:

```bash
export AI_DM_MODEL="phi3-local"
python3 Shared/ai_dm/app/run_dm.py
```

Everything runs locally against `http://127.0.0.1:11434` — no cloud APIs,
telemetry, or analytics. Session logs are written only to
`Shared/ai_dm/saves/current_session.md`, which stays out of Git.

The DM replies with a structured JSON response. Only the player-visible parts
(narration, any suggested check, and the prompt back to you) are printed;
hidden DM notes are kept in the session log, not shown. When the DM suggests a
check, roll it manually with `/roll`.

```text
I listen at the cellar door.

DM:
The wood is damp and cold beneath your ear...

Suggested check: Wisdom (Perception), DC 12
Use: /roll 1d20+<modifier>
```

If the model returns something that is not valid JSON, the runner prints a
friendly error plus the raw response and saves it to the session log for
debugging — it does not crash.

When the DM requests a check, it is remembered as the current *pending check*
(stored locally in `Shared/ai_dm/saves/pending_check.json`, git-ignored). Your
next `/roll` is compared against its DC: total ≥ DC is a success, otherwise a
failure. The result is logged, the pending check is cleared, and the DM is
asked to narrate the outcome. A `/roll` with no pending check is just a plain
manual roll.

Example flow:

```text
I listen at the old well.

DM suggests:
Wisdom (Perception), DC 13

/check
/roll 1d20+2
```

`/check` shows the pending check; `/roll 1d20+2` resolves it, e.g.:

```text
Roll: 1d20+2
Dice: [14]
Modifier: +2
Total: 16

Resolved check: Wisdom (Perception), DC 13
Outcome: Success
```

followed by the DM's narrated outcome.

Requested checks are normalised to standard DnD skill abilities. For example,
Perception uses Wisdom by default. If the model asks for `Dexterity
(Perception)`, it is corrected to `Wisdom (Perception)` before being shown,
saved, and resolved. On a **failed** check the DM is instructed not to reveal
the same useful information a success would have given — failure may instead
bring uncertainty, delay, noise, or a complication.

The app also detects obvious uncertain actions itself, before calling the LLM,
and creates the pending check directly. Detection is **scene-aware**: it first
matches your action against the current scene's `default_checks` (by
meaningful-word overlap with each check's `trigger`), falling back to a generic
keyword detector for actions the scene does not define. Scene checks carry the
scene's own `success`/`failure` outcome text, which is passed to the DM when
the roll resolves so success and failure read differently.

```text
/detect I search the stones around the well.

/narrate I sit quietly beside the well.

I search the stones around the well for hidden markings.

System:
This action calls for a check:
Intelligence (Investigation), DC 13
Use: /roll 1d20+<modifier>
```

When a check is detected the LLM is not called yet; you roll first, then the
DM narrates the outcome. Use `/detect <action>` to preview the scene check an
action would trigger without saving it, and `/narrate <action>` to skip
detection and send the action straight to the DM.

Scene-defined checks may include success/failure outcome guidance. When
present, the app treats this guidance as authoritative and prevents the model
from immediately requesting another check after resolution.

### Scene state

The AI-DM narrates from a concrete active scene stored in
`Shared/ai_dm/saves/current_scene.json` (runtime/private, git-ignored). On
startup the app copies the default scene template
(`templates/scenes/old_well_scene.json`) into that file if it does not already
exist. Each scene carries a player-visible description, sensory details,
obvious interactions, DM-only hidden truths, and default checks (with DCs and
success/failure outcomes) — all of which are fed into the DM context so the
model responds to concrete detail instead of generic atmosphere.

- `/scene` — show the player-facing view of the current scene (no hidden
  truths)
- `/scene-debug` — show the full current scene JSON, including hidden truths
  and default checks (developer testing)
- `/reset-scene` — reload `old_well_scene.json` from templates and make it the
  active scene

### Character-aware rolling

`/rollcheck` computes the correct dice formula from the pending check and the
active character sheet — the relevant ability modifier plus the proficiency
bonus (and expertise, if any) when the check's skill is one the character is
proficient in — then rolls and resolves it. `/roll <formula>` still works for
manual rolls.

```text
I search the stones around the well for hidden markings.

System:
This action calls for a check:
Intelligence (Investigation), DC 13

/rollcheck
```

Use `/character` to view the sheet and `/mod <ability> [skill]` (e.g.
`/mod Intelligence Investigation`) to preview a modifier without rolling.

### Local rules library

Install a rules library and build the keyword lookup index, then run the DM
loop. Use the **starter** summaries (offline) or import the **official** SRD
5.2.1 PDF (CC-BY-4.0).

Starter rules:

```bash
python3 Shared/ai_dm/rules/scripts/install_rules.py --starter
python3 Shared/ai_dm/rules/scripts/build_rules_lookup.py
python3 Shared/ai_dm/app/run_dm.py
```

Official SRD import:

```bash
python3 Shared/ai_dm/rules/scripts/download_srd.py
python3 -m pip install pypdf
python3 Shared/ai_dm/rules/scripts/extract_srd_text.py
python3 Shared/ai_dm/rules/scripts/build_rules_lookup.py
```

Or run the whole official workflow at once (falls back to starter if no PDF):

```bash
python3 Shared/ai_dm/rules/scripts/install_rules.py --official
```

No-network mode (use an already-downloaded PDF):

```bash
python3 Shared/ai_dm/rules/scripts/install_rules.py --official --no-network
```

The downloaded SRD PDF and all extracted/generated text are local runtime
files, ignored by Git. Do not add non-SRD D&D books or proprietary material.

Official extraction cleans out table-of-contents lines and splits the SRD into
overlapping text chunks, and the lookup prefers those chunks — so `/rule` and
`/rules-context` return real rule prose, not table-of-contents listings. The
lookup also builds a **canonical rules glossary** and consults it first for
common terms (conditions, rests, death saves, core roll mechanics), so
`/rule grappled` returns the definition rather than incidental mentions in
feats, items, or ancestry traits. You can test the index directly:

```bash
python3 Shared/ai_dm/rules/scripts/build_rules_lookup.py --test-query "grapple"
```

Inside the runner:

```text
/rules-status
/rule perception
/rule grappled
/rule short rest
```

This milestone uses short starter local rules summaries and simple keyword
lookup. Full SRD import/parsing and vector search will come later. Generated
rules content (Markdown summaries, the lookup index, and `installed-rules.json`)
stays local under `Shared/ai_dm/rules/` and is git-ignored; only the manifests,
attribution, example house rules, and scripts are tracked.

The AI-DM can now retrieve local rules snippets and include them in the DM
prompt. This uses simple local keyword lookup, not cloud search or vector
search. Relevant snippets are pulled automatically from the player's action, a
pending check, or a resolved roll.

Rules questions use a dedicated Rules Helper path rather than the normal DM
narration prompt. When the input reads like a rules/mechanics question (e.g.
"Can I grapple the creature in the well?", "How does short rest work?", "What
happens at zero hit points?"), a small rules-only prompt answers the question
directly and concisely from the local rules, then relates it to the scene —
instead of the atmospheric DM prompt. This applies to typed input, to
`/narrate` (which skips scene-check detection but still answers rules
questions), and to `/askrule` (which always uses the Rules Helper path). If the
model still ignores the question, a deterministic local fallback answer is used
instead.

```text
/askrule Can I grapple the creature in the well?
/narrate Can I grapple the creature in the well?
/rules-context Can I grapple the creature in the well?
/rule grappled
/rule short rest
```

### Campaign generation

Generate an **engine-ready** campaign pack (not just prose) from a short seed,
using the installed local model. Either run the standalone script:

```bash
python3 Shared/ai_dm/app/generate_campaign.py "low magic coastal folk horror, strange lights at sea"
```

or, inside the runner:

```text
/new-campaign low magic coastal folk horror, strange lights at sea
```

Each pack is written to `Shared/ai_dm/campaigns/<slug>/` as `campaign.json`,
`scenes/starting_scene.json`, `npcs.json`, `locations.json`, `factions.json`,
`rumours.json`, `session_01_outline.md`, and a `README.md`. The starting scene
follows the same structure as the built-in scenes (hidden truths, obvious
interactions, and default checks with success/failure outcomes). If the model
returns something invalid, the raw response is saved as
`raw_generation_failed.txt` and a clear error is printed — the app does not
crash.

Generated campaigns are **local and private**, stored under
`Shared/ai_dm/campaigns/`, and are **ignored by Git**. Campaign generation does
**not** auto-load the pack as the active campaign/scene yet.

#### Linting and repair

Generated packs are automatically **linted** and get safe **deterministic
repairs** before they're considered playable (pass `--no-repair` to lint
only). Repairs fix common model mistakes: non-standard skill/ability pairings,
social interactions mistakenly using a physical skill (e.g. a tavern-keeper
chat set to Strength (Athletics) → Charisma (Persuasion)), title-style check
triggers rewritten into player-action phrases, out-of-range DCs, scene clocks
that start above 0, and messy `session_01_outline.md` files (regenerated as
clean Markdown from the pack). Warnings that need judgment — a success that
reveals too much, or a hidden truth that reads like a rumour — are reported but
not auto-changed. The linter does **not** replace human review.

```bash
# generate with repair (default)
python3 Shared/ai_dm/app/generate_campaign.py "low magic coastal folk horror" --repair

# lint an existing pack without changing it
python3 Shared/ai_dm/app/generate_campaign.py --lint-only Shared/ai_dm/campaigns/whispers-in-the-tide

# repair an existing pack
python3 Shared/ai_dm/app/generate_campaign.py --repair Shared/ai_dm/campaigns/whispers-in-the-tide
```

Each pack gets a `lint_report.json` (warnings before, repairs applied, warnings
after). Like the rest of the pack, it stays local and is ignored by Git.

Commands inside the loop:

- `/roll <formula>` — roll dice (e.g. `1d20+3`, `2d6`, `1d8-1`); resolves the
  pending check if one is active, otherwise a plain manual roll
- `/rollcheck` — roll the **active character's** modifier for the pending
  check (ability modifier + proficiency/expertise), then resolve it
- `/character` — show the active character sheet (abilities with modifiers,
  proficiency bonus, skill proficiencies, and expertise)
- `/mod <ability> [skill]` — show the character's modifier for an ability, or
  an ability + skill (e.g. `/mod Wisdom Perception`)
- `/rule <query>` — look up local rules by keyword (e.g. `/rule perception`)
- `/rules-context <action>` — preview the local rules snippets that would be
  injected into the DM prompt for an action or question
- `/askrule <question>` — always answer a rules/mechanics question via the
  dedicated Rules Helper path
- `/rules-status` — show whether the local rules library is installed and
  indexed
- `/new-campaign <seed>` — generate a local campaign pack from a seed (written
  under `Shared/ai_dm/campaigns/`, not auto-loaded)
- `/check` — show the current pending check, if any
- `/detect <action>` — preview the scene check an action would trigger,
  without saving it
- `/narrate <action>` — send an action to the DM, skipping check detection
- `/debug-last` — show the raw vs normalised requested check and the last
  parsed DM response (written to `Shared/ai_dm/saves/last_dm_response.json`)
- `/recap` — print the current saved session log
- `/quit` — exit

Example session:

```bash
python3 Shared/ai_dm/app/run_dm.py
```

```text
/roll 1d20+3
/recap
/quit
```

A `/roll 1d20+3` prints something like:

```text
Roll: 1d20+3
Dice: [14]
Modifier: +3
Total: 17
```

and is logged to `Shared/ai_dm/saves/current_session.md` as:

```markdown
### Dice Roll

Formula: `1d20+3`  
Rolls: `[14]`  
Modifier: `3`  
Total: `17`
```
