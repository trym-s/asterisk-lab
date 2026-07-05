# VAL-VOICEBOT-001: LiveKit lane answers and logs turns

Surface: SIP call, Docker, and artifact.
Needs: Passing Asterisk deployment, Asterisk VM `.env` with OpenAI and LiveKit
credentials, and LiveKit stack deployed.
Behavior: A call to extension `1099` reaches the LiveKit SIP gateway, joins a
room, starts the agent, plays the greeting, processes caller speech, and writes
turn/usage logs.
Evidence: Validator records compose/container status, `docker logs` for
`lk-agent`, Asterisk call evidence, and new entries in `/var/lib/voicebot`
logs.
Fail: No answer, no room/agent log, no greeting, no turn log, or missing usage
record for a completed interaction means failure.
