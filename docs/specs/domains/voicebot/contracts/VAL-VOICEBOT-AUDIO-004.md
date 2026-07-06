# VAL-VOICEBOT-AUDIO-004: Pipecat records AudioSocket byte and duration counters

Surface: TCP listener, Docker, and trace artifact.
Needs: Passing `VAL-VOICEBOT-002`.
Behavior: For each Pipecat AudioSocket call, trace evidence records inbound and
outbound audio byte counts, derived durations, first/last audio timestamps, and
call UUID/call ID mapping.
Evidence: Validator records `pc-agent` logs and `events.jsonl` audio rows for a
real call, including inbound/outbound byte and duration counters.
Fail: No counters, zero inbound audio on a spoken utterance, zero outbound audio
after TTS, or missing call mapping means failure.
