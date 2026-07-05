# Voicebot Benchmark Spec

The benchmark compares LiveKit and Pipecat with identical user utterances and
shared logging.

## Inputs

- WAV files under `services/test-caller/audio/`.
- `services/test-caller/utterances.tsv` as the corpus index.
- Host baresip with `ctrl_tcp` and `aufile` modules enabled.

## Execution

```bash
services/test-caller/run-suite.sh 1099
services/test-caller/run-suite.sh 1098
```

## Outputs

- `/var/lib/voicebot/turns.jsonl` on the Asterisk VM.
- `/var/lib/voicebot/usage.jsonl` on the Asterisk VM.
- Local test-caller run directory under `services/test-caller/runs/`.

## Comparison Rules

- Do not compare lanes unless both are deployed from the same repo revision.
- Do not compare lanes unless both use the same prompt, STT/LLM/TTS models, and
  doc lookup corpus, or an accepted decision records the divergence.
- Treat missing logs, failed calls, or missing usage records as blocked evidence,
  not as zero-cost or zero-latency outcomes.
