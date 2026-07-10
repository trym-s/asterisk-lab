# Test caller

Play pre-baked utterances into an active call so the voicebot lane
(Pipecat, ext 1098) can be exercised with identical user input without a
human at the mic.

## Generate WAVs

```bash
# Ensure ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID are set in ../../.env
./gen-utterances.sh          # produces audio/<id>.wav
FORCE=1 ./gen-utterances.sh  # regenerate even if files exist
```

The script also logs character spend to `/var/lib/voicebot/usage.jsonl` —
same log the agent lanes write to, so `make usage-summary` shows both.

## Dial and play (host baresip)

Assuming baresip is already registered as 1001 on the host:

```bash
# 1. add /aufile module if not loaded (once):
#    put `aufile` on its own line in ~/.baresip/config under `module`.
# 2. start a call and switch audio source to file:
baresip -e '/aufile services/test-caller/audio/01-greeting.wav' \
        -e '/dial 1098'
```

Or interactively inside a running baresip:
```
/aufile /path/to/services/test-caller/audio/01-greeting.wav
/dial 1098
```

Full automation lives in `run-suite.sh`: it drives the running baresip
via ctrl_tcp and plays every conversation's turns at ext 1098 in
sequence.
