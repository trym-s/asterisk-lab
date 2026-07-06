# Voicebot Runbook

## Required Asterisk VM `.env`

```text
OPENAI_API_KEY=...
LIVEKIT_API_KEY=...       # LiveKit only
LIVEKIT_API_SECRET=...    # LiveKit only

# Optional but must be shared by LiveKit and Pipecat for comparable runs.
VOICEBOT_MODEL_PROFILE=...
VOICEBOT_STT_MODEL=...
VOICEBOT_LLM_MODEL=...
VOICEBOT_TTS_MODEL=...
VOICEBOT_TTS_VOICE=...
```

## Deploy Order

Deploy the Asterisk baseline first when dialplan or recording behavior changed.
Then deploy the two voicebot lanes from the same repo revision. Deploy the
observer after at least one lane writes artifacts, or before if you want to
watch empty-state behavior.

## Deploy LiveKit

```bash
make VM=deb@<asterisk-ip> deploy-voicebot-livekit
make VM=deb@<asterisk-ip> logs-voicebot-livekit
```

Dial `1099` from a registered softphone.

## Deploy Pipecat

```bash
make VM=deb@<asterisk-ip> deploy-voicebot-pipecat
make VM=deb@<asterisk-ip> logs-voicebot-pipecat
```

Dial `1098` from a registered softphone.

## Deploy Observer

```bash
make VM=deb@<asterisk-ip> deploy-voicebot-observer
make VM=deb@<asterisk-ip> logs-voicebot-observer
```

The observer binds to VM loopback. Access it from the host with:

```bash
ssh -L 8088:127.0.0.1:8088 deb@<asterisk-ip>
```

Then open `http://127.0.0.1:8088/`. The observer must show useful empty states
when no calls have been traced yet.

## Usage Summary

```bash
make VM=deb@<asterisk-ip> usage-summary
```

Command summaries are debug aids. Contract evidence for new work comes from
`events.jsonl`, `usage.jsonl`, observer API/UI output, audio evidence, and
generated reports.

## Run A Manual Trace Check

1. Dial `1099` and ask a doc-backed Turkish question such as:
   `Magazaniz Pazar gunu kacta aciliyor?`
2. Dial `1098` and ask the same question.
3. Confirm `/var/lib/voicebot/events.jsonl` has `stt`, `llm`, `tool`, `tts`,
   `audio`, and `usage`-linkable evidence for both lanes.
4. Confirm the observer Call Detail page shows the STT transcript, LLM input,
   tool result, final answer, TTS text, usage/cost, and audio integrity status.

## Run Benchmark And Report

```bash
services/test-caller/run-suite.sh 1099
services/test-caller/run-suite.sh 1098
python3 services/common/generate_report.py --latest
```

The benchmark report must include run IDs, repo revision, model profile, corpus
hash/version, utterance list, per-utterance trace evidence, usage/cost, latency,
audio integrity, and pass/fail or inconclusive status.

Do not compare lanes when:

- they were deployed from different repo revisions;
- prompt, model profile, corpus, or tool behavior differs without a recorded
  decision;
- trace, usage, or audio evidence is missing;
- the test-caller manifest is missing or cannot be matched to calls.

## Troubleshooting

- Empty observer: check `/var/lib/voicebot/events.jsonl`, container mounts, and
  that calls were made after the trace implementation was deployed.
- No Pipecat audio: check `ss -ltnp | grep 8090`, `docker logs pc-agent`, and
  Asterisk `AudioSocket()` dialplan evidence.
- No LiveKit call: check `docker logs lk-sip lk-agent lk-server` and
  `pjsip show endpoint livekit-trunk`.
- Usage cost missing: confirm usage rows include lane, call ID, turn ID, stage,
  model, units, estimated USD, and pricing version.
- Audio truncation: inspect the test-caller run manifest, Asterisk recordings,
  STT transcript, and TTS/audio end events before treating a lane as passing.
