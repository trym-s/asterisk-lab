# Voicebot Domain Spec

The voicebot domain compares two agent lanes behind Asterisk:

- LiveKit lane on extension `1099`;
- Pipecat AudioSocket lane on extension `1098`.

Both lanes should use the same business prompt, OpenAI STT/LLM/TTS model
choices, `lookup_docs` behavior, usage logging, and turn logging unless a
contract or decision records an accepted divergence.

## Supported Behavior

- LiveKit stack runs on the Asterisk VM using Docker Compose, LiveKit server,
  SIP gateway, and agent worker.
- Pipecat stack runs on the Asterisk VM using Docker Compose and an AudioSocket
  TCP listener on port `8090`.
- `services/common` provides shared doc lookup, usage accounting, and turn log
  rendering.
- `services/test-caller` provides fixed utterance WAVs and a baresip control
  suite for repeatable lane comparison.

## Source Files

- `services/livekit/`
- `services/pipecat/`
- `services/common/`
- `services/test-caller/`
- voicebot entries in `asterisk/extensions.conf.tmpl`
