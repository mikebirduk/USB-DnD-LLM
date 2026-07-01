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

Commands inside the loop:

- `/roll <formula>` — roll dice (e.g. `1d20+3`, `2d6`, `1d8-1`), print the
  structured result, and append it to the session log
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
