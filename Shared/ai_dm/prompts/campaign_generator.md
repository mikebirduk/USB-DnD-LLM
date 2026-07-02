# Campaign Generator Prompt

Generate a structured campaign pack for a private local AI Dungeon Master.

Generate engine-ready campaign data, not just prose.

Use grounded, low-level stakes.
Avoid world-ending threats unless explicitly requested.
Prefer mystery, consequences, NPC motives, secrets, and interactive scenes.
Every starting scene must include default checks with success and failure outcomes.
Do not reveal all secrets in player-visible text.
Use SRD-compatible assumptions.
Avoid non-SRD proprietary DnD monsters, settings, or named IP.
Return valid JSON only.

Default check triggers must be player-action phrases, not scene titles.

Use sensible skill/ability pairings:
- social persuasion: Charisma (Persuasion)
- reading motives: Wisdom (Insight)
- searching clues: Intelligence (Investigation)
- noticing danger: Wisdom (Perception)
- recalling cult/religious lore: Intelligence (Religion)
- local history: Intelligence (History)
- climbing/swimming/forcing: Strength (Athletics)

Do not reveal major secrets too early in a single success.
Failures should not reveal the same information as successes.
Session outline must be clean Markdown, not JSON or Python dictionaries.
