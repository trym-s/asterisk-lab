# Voicebot Runbook

## Required Asterisk VM `.env`

```text
OPENAI_API_KEY=...
LIVEKIT_API_KEY=...       # LiveKit only
LIVEKIT_API_SECRET=...    # LiveKit only
```

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

## Usage Summary

```bash
make VM=deb@<asterisk-ip> usage-summary
```
