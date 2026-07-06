# Voicebot Benchmark Spec

The benchmark compares LiveKit and Pipecat with identical user utterances,
shared trace/usage schema, shared model profile, shared document corpus, and
audio integrity evidence.

## Inputs

- WAV files under `services/test-caller/audio/`.
- `services/test-caller/utterances.tsv` as the corpus index.
- Host baresip with `ctrl_tcp` and `aufile` modules enabled.
- Shared voicebot model profile.
- Shared `lookup_docs` corpus version/hash.
- Asterisk voicebot dialplan that records enough evidence to prove caller and
  bot audio paths.

## Execution

```bash
services/test-caller/run-suite.sh 1099
services/test-caller/run-suite.sh 1098
```

## Outputs

- test-caller run manifest under `services/test-caller/runs/`.
- `/var/lib/voicebot/events.jsonl` on the Asterisk VM.
- `/var/lib/voicebot/usage.jsonl` on the Asterisk VM.
- Asterisk recording files or recording metadata for caller and bot audio.
- `/var/lib/voicebot/reports/*.json` on the Asterisk VM.
- `/var/lib/voicebot/reports/*.md` on the Asterisk VM.

## Test Caller Manifest

Every run records:

- run ID and target extension;
- lane (`livekit` or `pipecat`);
- repo revision;
- utterance ID and expected text;
- source WAV path and duration;
- dial timestamp;
- source-switch timestamp;
- hangup timestamp;
- VM target used for remote evidence.

The manifest is the timing anchor for matching source WAVs to Asterisk
recordings, trace events, and reports.

## Audio Integrity Rules

- Scheduling a WAV through baresip is not proof that it reached the agent.
- Source WAV duration must be compared with receive-side audio evidence.
- Asterisk-side recording evidence proves caller audio reached the VM and bot
  audio returned toward the caller.
- Pipecat reports AudioSocket inbound/outbound byte and duration counters.
- LiveKit is validated with Asterisk recording evidence plus LiveKit room/STT
  traces.
- STT transcript must contain the utterance's main intent, not only a tail
  fragment.
- Hangup must occur after returned bot audio finishes, or the run is failed or
  inconclusive.

## Comparison Rules

- Do not compare lanes unless both are deployed from the same repo revision.
- Do not compare lanes unless both use the same prompt, STT/LLM/TTS models, and
  doc lookup corpus, or an accepted decision records the divergence.
- Treat missing trace, failed calls, missing usage records, missing manifest
  entries, or missing audio evidence as blocked or failed evidence, not as
  zero-cost or zero-latency outcomes.
- Refuse or flag comparisons when prompt, model profile, corpus, or repo
  revision differs.

## Report Criteria

Reports include per-utterance and aggregate comparison for:

- STT transcript and intent match.
- Required doc-tool call behavior.
- Retrieved sources and grounding.
- LLM input/output visibility.
- TTS text and returned audio evidence.
- Stage latency.
- Token, character, second, and tool-call usage.
- Estimated cost by lane, provider, model, and stage.
- Audio truncation or missing-evidence status.
- Pass, fail, or inconclusive verdict.

Required doc-backed benchmark scenarios:

- Store hours: `Magazaniz Pazar gunu kacta aciliyor?`
- Product price: `Banyo havlusu ne kadar?`
- Shipping: `Izmir'e kargo kac gunde geliyor?`
- Return policy: `Iade sureniz ne kadar?`
- No-hit scenario once added to the utterance corpus.
