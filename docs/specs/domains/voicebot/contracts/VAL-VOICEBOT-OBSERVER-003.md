# VAL-VOICEBOT-OBSERVER-003: Observer shows STT, LLM, tool, TTS, and usage data

Surface: browser and HTTP API.
Needs: Passing `VAL-VOICEBOT-OBSERVER-002` and a doc-backed traced call.
Behavior: The Call Detail view shows STT transcript, LLM input, tool
request/result, LLM output, TTS text, model names, tokens/characters/seconds,
estimated cost, and raw JSON expanders for the selected turn.
Evidence: Validator records browser or API evidence for a real LiveKit or
Pipecat call and matches displayed values to trace/usage rows.
Fail: Hiding any required STT/LLM/tool/TTS stage, missing cost/usage attribution,
or displaying values not present in artifacts means failure.
