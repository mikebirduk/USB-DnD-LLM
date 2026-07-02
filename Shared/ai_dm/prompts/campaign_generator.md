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

Generate a small connected mini-campaign of 3 scenes:
- Provide 3 scenes total in "scenes".
- Each scene needs at least 2 obvious interactions and at least 2 default checks.
- Each non-final scene needs at least 1 exit linking to another scene by its scene_id.
- The starting scene must link to at least one other scene.
- Give scenes descriptive kebab-case scene_id values (e.g. "the-port", "smugglers-tunnels").
