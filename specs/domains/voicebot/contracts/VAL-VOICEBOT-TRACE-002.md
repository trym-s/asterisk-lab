# VAL-VOICEBOT-TRACE-002: Pipecat emits stage-level trace for a real call

Surface: SIP call, TCP listener, Docker, and artifact.
Needs: Passing `VAL-VOICEBOT-002`.
Behavior: A real call to `1098` with a doc-backed Turkish question produces
ordered `events.jsonl` records for call start, AudioSocket audio receive, STT
final transcript, LLM request, `lookup_docs` request/result, LLM response, TTS
request/output, AudioSocket output, and call end/error status when applicable.
Evidence: Validator records the dialed question, `pc-agent` logs, AudioSocket
session evidence, and the exact new trace rows grouped by `lane=pipecat`,
`call_id`, and `turn_id`.
Fail: Missing stages, missing AudioSocket counters, ungrouped events, no final
transcript, no LLM input, no tool result for a doc-backed question, no TTS text,
or malformed JSON means failure.
