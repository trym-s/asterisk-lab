# VAL-VOICEBOT-OBSERVER-004: Observer shows audio integrity evidence

Surface: browser, HTTP API, and artifact.
Needs: Passing `VAL-VOICEBOT-AUDIO-005` and `VAL-VOICEBOT-OBSERVER-002`.
Behavior: The observer shows audio integrity status for calls and utterances,
including source duration, received caller duration, returned bot duration,
truncation or inconclusive flags, and links or identifiers for recording
evidence.
Evidence: Validator records browser/API evidence and matches displayed status to
audio integrity summary artifacts.
Fail: Missing audio status, passing calls with missing audio evidence, broken
recording references, or no inconclusive state means failure.
