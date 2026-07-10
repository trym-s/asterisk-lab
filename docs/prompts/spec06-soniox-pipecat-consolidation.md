# Kickoff Prompt - spec06 soniox pipecat consolidation

Read `AGENTS.md`, `PLANS.md`, and the governing spec:

```text
docs/specs/spec06-soniox-pipecat-consolidation.md
```

Implement the spec end to end: remove the LiveKit lane (repo and VM), move
the Pipecat lane to 16 kHz chan_audiosocket, replace batch STT/TTS with
Soniox streaming services (semantic endpointing owns turn-end, VAD owns
barge-in only), and prove the result with a live call and a corpus suite
run. Keep `PLANS.md` updated after meaningful work, preserve user changes,
keep secrets and runtime data out of git, run the relevant checks, and
commit all agent-made changes with English Conventional Commits.
