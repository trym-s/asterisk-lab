# VAL-VOICEBOT-002: Pipecat lane answers through AudioSocket with complete evidence

Surface: SIP call, TCP listener, Docker, artifact, and trace.
Needs: Passing Asterisk deployment, Asterisk VM `.env` with `OPENAI_API_KEY`,
Pipecat stack deployed, and extension `1098` present in the dialplan.
Behavior: A call to extension `1098` connects Asterisk AudioSocket to the
Pipecat agent on port `8090`, plays the greeting, processes caller speech, and
writes complete call, STT, LLM, tool, TTS, AudioSocket audio, and usage
evidence compatible with the LiveKit lane.
Evidence: Validator records `ss -ltnp` listener evidence, `docker logs pc-agent`,
Asterisk call evidence, relevant `/var/lib/voicebot/events.jsonl` rows, and
linked `/var/lib/voicebot/usage.jsonl` rows for the new call.
Fail: No AudioSocket connection, no greeting, no STT/LLM/TTS response, missing
AudioSocket audio counters, missing usage attribution, or trace schema
divergence means failure.
