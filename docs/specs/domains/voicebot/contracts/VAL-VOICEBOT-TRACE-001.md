# VAL-VOICEBOT-TRACE-001: LiveKit emits stage-level trace for a real call

Surface: SIP call, Docker, and artifact.
Needs: Passing `VAL-VOICEBOT-001`.
Behavior: A real call to `1099` with a doc-backed Turkish question produces
ordered `events.jsonl` records for call start, audio receive, STT final
transcript, LLM request, `lookup_docs` request/result, LLM response, TTS
request/output, and call end/error status when applicable.
Evidence: Validator records the dialed question, `lk-agent` logs, and the exact
new trace rows grouped by `lane=livekit`, `call_id`, and `turn_id`.
Fail: Missing stages, ungrouped events, no final transcript, no LLM input, no
tool result for a doc-backed question, no TTS text, or malformed JSON means
failure.
