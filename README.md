# USB-DnD-LLM 🎲

**USB-DnD-LLM** is a fully offline, zero-dependency, plug-and-play local AI environment for playing Dungeons & Dragons with a private AI Dungeon Master. It runs entirely from your **local hard drive** or a **portable USB/SSD** — the language model, the game engine, and your campaign data all stay on the drive, with no internet required after setup and no cloud APIs ever.

Initialize your models once and either keep them on your machine or carry the whole setup with you across Windows, macOS, and Linux.

## 🚀 Core Features

* **Private AI Dungeon Master:** A local, structured DM that narrates scenes, tracks campaign state, requests ability checks, rolls dice, resolves outcomes, and answers rules questions — all from a terminal. See [`Shared/ai_dm/README.md`](Shared/ai_dm/README.md).
* **Local D&D SRD rules:** Optionally import the official CC-BY-4.0 SRD 5.2.1 (or use built-in starter summaries) for local `/rule` and `/rules-context` lookups. No cloud search.
* **Zero-dependency setup:** Ships with a portable Python and isolated engine binaries. No system permissions, registry edits, or package managers required.
* **Cross-platform:** A shared `Shared/` volume lets you download your models *once* and use them natively on Windows, macOS, and Linux without duplication.
* **Everything stays local:** Runs against a local Ollama engine on `127.0.0.1` — no telemetry, no analytics, no external calls. Campaigns, saves, logs, and downloaded models live only on your drive.
* **Optional chat UI:** A lightweight Python HTTP server also serves a dark-mode chat UI you can reach from a phone or tablet on the same WiFi.
* **Hardware accelerated:** Uses a portable Ollama engine that takes advantage of AVX CPU instructions, NVIDIA CUDA, or Apple Metal dynamically on whatever host it's plugged into.

---

## 💻 System Requirements

- **Storage:** A USB 3.0+ flash drive or SSD with at least **8 GB** free (16 GB+ recommended once you add models and campaigns).
- **RAM:** At least **8 GB** of system memory for small 2B–4B models; **16 GB+** for 8B–12B models.
- **Python 3:** Required for the AI Dungeon Master (`run_dm.py`) and the rules scripts. The chat UI ships its own portable Python.

---

## 📂 Folder Architecture

The project isolates per-OS executables while unifying heavy model weights and shared data to save portable storage.

```text
[Portable USB Drive / Local Folder]
 ├── 📁 Android    # Native Android (Termux) installers & launchers
 ├── 📁 Linux      # Native Ubuntu/Debian installers & launchers
 ├── 📁 Mac        # Native macOS installers & launchers
 ├── 📁 Windows    # Native Windows installers & launchers
 └── 📁 Shared     # Unified data system
      ├── 📁 bin         (Isolated engine executables: ollama-darwin, ollama-windows.exe ...)
      ├── 📁 models      (Downloaded GGUF weights + installed-models.txt)
      ├── 📁 chat_data   (Persistent chat-UI conversation history)
      ├── 📁 python      (Isolated portable Python environment)
      └── 📁 ai_dm       (The AI Dungeon Master: app, prompts, rules, campaigns, saves)
```

Downloaded models, generated campaigns, saves, logs, and imported rules are **local runtime data** and are never committed to Git.

---

## ⚙️ Quick Start

### Step 1 — Initialize the engine and download a model

Open the folder for the OS you're plugged into and run its installer. This downloads the small Ollama engine for that OS into `Shared/bin`, then lets you pick and download one or more local models into `Shared/models`.

* **Windows:** double-click `Windows/install.bat`
* **macOS:** open Terminal, drag in `Mac/install.command`, press Enter
* **Linux:** `bash Linux/install.sh`
* **Android:** open Termux, `bash Android/install.sh` (see the Android section)

The installer records your chosen models in `Shared/models/installed-models.txt`. For the AI Dungeon Master, a small, fast instruct model is a good default (e.g. **Phi-3.5 Mini** or **Qwen2.5**); larger models give richer narration if your RAM allows.

### Step 2 — Start the engine

Run the `start` script for your OS to launch the local engine (and the chat UI):

* **Windows:** `Windows/start-fast-chat.bat`
* **macOS:** `Mac/start.command`
* **Linux:** `bash Linux/start.sh`
* **Android:** `bash Android/start.sh` (in Termux)

The engine serves locally on `http://127.0.0.1:11434`. The chat UI opens automatically in your browser.

### Step 3 — Play

You can use USB-DnD-LLM two ways:

**A) AI Dungeon Master (terminal)** — with the engine running:

```bash
python3 Shared/ai_dm/app/run_dm.py
```

The DM automatically uses the first model in `Shared/models/installed-models.txt`. To force a specific one:

```bash
export AI_DM_MODEL="phi35-mini-local"
python3 Shared/ai_dm/app/run_dm.py
```

Type actions to play. Useful in-loop commands include `/roll 1d20+3`, `/rollcheck`, `/character`, `/scene`, `/rule <query>`, `/askrule <question>`, `/recap`, and `/quit`. Full details and the design are in [`Shared/ai_dm/README.md`](Shared/ai_dm/README.md).

**B) Chat UI (browser)** — just use the page opened by the `start` script for free-form local chat.

### Optional — Install the local rules library

Give the DM local D&D rules to consult. Starter summaries (offline):

```bash
python3 Shared/ai_dm/rules/scripts/install_rules.py --starter
python3 Shared/ai_dm/rules/scripts/build_rules_lookup.py
```

Or import the official CC-BY-4.0 SRD 5.2.1 PDF:

```bash
python3 Shared/ai_dm/rules/scripts/download_srd.py
python3 -m pip install pypdf
python3 Shared/ai_dm/rules/scripts/extract_srd_text.py
python3 Shared/ai_dm/rules/scripts/build_rules_lookup.py
```

Then, inside the runner, try `/rules-status` and `/rule grappled`. See [`Shared/ai_dm/rules/README.md`](Shared/ai_dm/rules/README.md).

---

## 🧠 Local Model Library

The installer presents an interactive catalog of small, locally runnable GGUF models and downloads them into `Shared/models` — pick one during Step 1. For the AI Dungeon Master a compact instruct model keeps turns fast; a larger model produces richer prose if you have the RAM. You can also point the installer at **any** `.gguf` weight from Hugging Face, or drop a `.gguf` into `Shared/models` manually.

---

## 🏠 Local Disk Installation

USB-DnD-LLM also works as a lightweight local AI setup on your primary computer.

1. **Download/clone** this repository into a folder on your internal drive.
2. Open the **Windows** (or **Mac**/**Linux**) folder.
3. Run the installer (`install.bat` / `install.command` / `install.sh`) and choose your model(s).
4. Run the `start` script to launch the engine, then run `python3 Shared/ai_dm/app/run_dm.py` to play.

Running from an internal SSD loads models significantly faster than a USB drive.

---

## 📱 Android Native (Termux)

Run the engine **directly on an Android phone or tablet** — no PC required.

### Requirements
- **Termux** from [F-Droid](https://f-droid.org/en/packages/com.termux/) (not the outdated Play Store build)
- **6 GB+ RAM** (8 GB+ recommended; only the smallest models run well on 6 GB)
- **WiFi/mobile data** for the initial engine + model download
- **ARM64** processor (virtually all modern devices)

### Setup & launch
1. Copy the USB-DnD-LLM folder to your device (USB OTG, file transfer, or `git clone`).
2. Open **Termux**, navigate to the project folder.
3. `bash Android/install.sh` and choose a small model.
4. `bash Android/start.sh` to launch.

### Performance tips
- Run `termux-wake-lock` before starting to stop Android killing the process.
- Keep Termux in the foreground and close other apps to free RAM.
- Use the smallest model on devices with under 12 GB RAM, and keep the charger plugged in.

---

## 📶 LAN Mobile Access

To use the chat UI from your phone on the same network:
1. Ensure the host running the `start` script and your phone are on the same WiFi.
2. The terminal prints a **Network Access** URL (e.g. `http://192.168.1.15:3333`).
3. Open that URL in your mobile browser. *(If it doesn't load, allow incoming connections on port `3333` in your firewall.)*

---

## 🛠️ Troubleshooting

- **"Ollama engine not found":** You ran a `start` script before running the OS installer. Run your OS's installer first.
- **The script instantly closes on Windows:** Disable the Windows App Execution Aliases, or run the `.bat` from a command prompt (or "Run as Administrator").
- **Slow generation:** The model is too large for your host's RAM. Re-run the installer and pick a smaller model.
- **AI DM says "No AI model found":** Run the OS installer to download a model (it writes `Shared/models/installed-models.txt`), then start the engine before running `run_dm.py`.
- **`/rule` returns nothing:** Install the rules library (see the optional step above), then run `build_rules_lookup.py`.

---

> *Privacy: USB-DnD-LLM runs entirely on your own hardware against a local engine on `127.0.0.1`. No cloud APIs, telemetry, or analytics — your campaigns, saves, and chats never leave your drive. Do not add non-SRD D&D books or other proprietary material unless you have the right to use them.*
