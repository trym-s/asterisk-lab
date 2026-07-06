# VAL-VOICEBOT-MODEL-002: Cost calculator records pricing version

Surface: artifact and CLI/API.
Needs: Passing `VAL-VOICEBOT-USAGE-001`.
Behavior: Cost estimates are computed from a recorded pricing table version that
names provider, model, unit type, rate, source URL, and date checked. Usage
summaries and observer APIs display estimated cost with that version.
Evidence: Validator records pricing table metadata, representative usage rows,
summary/API output, and calculation samples for STT, LLM, TTS, and tool-call
events.
Fail: Stale undocumented rates, missing pricing version, missing source/date, or
unattributed estimated USD values means failure.
