# VAL-VOICEBOT-AUDIO-005: Audio integrity summary flags truncation and gaps

Surface: artifact, API, and report.
Needs: Passing `VAL-VOICEBOT-AUDIO-001`, `VAL-VOICEBOT-AUDIO-002`, and
`VAL-VOICEBOT-AUDIO-003`.
Behavior: Benchmark outputs and observer APIs summarize audio integrity per
call/utterance with source duration, received caller duration, returned bot
duration, transcript intent status, hangup timing, and pass/fail/inconclusive
status.
Evidence: Validator records generated summary JSON or observer API output and
matches it to source manifest, recording evidence, and trace rows.
Fail: Missing summary, no inconclusive state for missing evidence, or passing a
call with known truncation means failure.
