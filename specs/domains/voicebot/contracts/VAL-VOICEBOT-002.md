# VAL-VOICEBOT-002: Pipecat lane answers through AudioSocket and logs turns

Surface: SIP call, TCP listener, Docker, and artifact.
Needs: Passing Asterisk deployment, Asterisk VM `.env` with `OPENAI_API_KEY`,
Pipecat stack deployed, and extension `1098` present in the dialplan.
Behavior: A call to extension `1098` connects Asterisk AudioSocket to the
Pipecat agent on port `8090`, plays the greeting, processes caller speech, and
writes turn/usage logs compatible with the LiveKit lane.
Evidence: Validator records `ss -ltnp` listener evidence, `docker logs pc-agent`,
Asterisk call evidence, and new entries in `/var/lib/voicebot` logs.
Fail: No AudioSocket connection, no greeting, no STT/LLM/TTS response, or log
schema divergence means failure.
