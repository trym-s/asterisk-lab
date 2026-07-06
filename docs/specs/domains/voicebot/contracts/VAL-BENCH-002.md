# VAL-BENCH-002: Report includes trace, cost, latency, audio, and grounding

Surface: CLI benchmark and generated artifacts.
Needs: Passing `VAL-BENCH-001`, `VAL-VOICEBOT-USAGE-001`, and
`VAL-VOICEBOT-AUDIO-005`.
Behavior: The report generator writes Markdown and JSON reports that include
repo revision, run IDs, model profile, corpus version/hash, utterance list,
per-utterance STT transcript, tool use, grounding verdict, LLM answer, TTS text,
stage latency, usage/cost, audio integrity status, and failure notes.
Evidence: Validator records report command, generated `.md` and `.json` paths,
and excerpts for store-hours, product-price, shipping/return, and no-hit
scenarios when present.
Fail: Missing required sections, missing machine-readable JSON, or reports that
omit failed/inconclusive evidence means failure.
