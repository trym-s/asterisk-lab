# VAL-VOICEBOT-001: LiveKit lane answers with complete baseline evidence

Surface: SIP call, Docker, artifact, and trace.
Needs: Passing Asterisk deployment, Asterisk VM `.env` with OpenAI and LiveKit
credentials, and LiveKit stack deployed.
Behavior: A call to extension `1099` reaches the LiveKit SIP gateway, joins a
room, starts the agent, plays the greeting, processes caller speech, returns a
spoken answer, and writes complete call, STT, LLM, tool, TTS, audio, and usage
evidence for the interaction.
Evidence: Validator records compose/container status, `docker logs` for
`lk-agent`, Asterisk call evidence, relevant `/var/lib/voicebot/events.jsonl`
rows, and linked `/var/lib/voicebot/usage.jsonl` rows for the new call.
Fail: No answer, no room/agent log, no greeting, no STT/LLM/TTS response,
missing stage trace, missing usage attribution, or trace schema divergence means
failure.
