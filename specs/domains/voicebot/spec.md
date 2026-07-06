# Voicebot Domain Spec

The voicebot domain compares two Turkish voice-agent lanes behind Asterisk:

- LiveKit lane on extension `1099`;
- Pipecat AudioSocket lane on extension `1098`.

Both lanes must use the same assistant behavior, model profile, Turkish doc
lookup corpus, trace schema, usage/cost accounting, benchmark corpus, and
reporting rules unless a contract or decision records an accepted divergence.
The supported workflow is Turkish VoIP audio through STT -> LLM/tool use -> TTS,
with enough evidence to inspect what each stage received, produced, cost, and
sent over audio.

## Mission Slices

- Parity baseline: LiveKit and Pipecat differ only by framework and media
  transport.
- Full observability: STT, LLM, doc tool, TTS, audio, usage, and errors are
  traceable per call and per turn.
- Grounded document answers: doc-backed customer questions call `lookup_docs`
  before answering and do not hallucinate on no-hit results.
- Audio integrity: benchmark runs prove caller audio reached the VM/lane and bot
  audio returned toward the caller without obvious truncation.
- Operator UI: a small FastAPI observer is the supported way to inspect calls,
  traces, usage, audio evidence, and comparison reports.
- Benchmark reports: LiveKit/Pipecat comparisons are generated as Markdown and
  JSON from trace, usage, audio, and corpus evidence.
- Model/cost policy: model choices are shared, configurable, visible in traces,
  and tied to a recorded pricing decision.

## Supported Behavior

- LiveKit stack runs on the Asterisk VM using Docker Compose, LiveKit server,
  SIP gateway, and agent worker.
- Pipecat stack runs on the Asterisk VM using Docker Compose and an AudioSocket
  TCP listener on port `8090`.
- `services/common` provides shared doc lookup, trace writing/parsing, usage
  accounting, cost estimation, and report helpers.
- `services/test-caller` provides fixed utterance WAVs and a baresip control
  suite for repeatable lane comparison.
- `services/observer` provides a FastAPI web UI and JSON API for operator
  inspection of calls, stage traces, usage, audio evidence, and reports.
- Both lanes answer in Turkish and keep responses short and clear.
- Both lanes call `lookup_docs` before answering questions about store hours,
  products, prices, shipping, returns, exchanges, contact, branch, or location.
- Both lanes answer from retrieved corpus facts and say the knowledge base lacks
  the information when lookup has no matching result.
- Both lanes expose model/profile identity in traces and reports.
- Both lanes write enough runtime artifacts for validators to distinguish a real
  end-to-end interaction from a container that merely started.

## Shared Model Profile

The model profile is per-VM runtime configuration. Supported optional variables:

```text
VOICEBOT_MODEL_PROFILE
VOICEBOT_STT_MODEL
VOICEBOT_LLM_MODEL
VOICEBOT_TTS_MODEL
VOICEBOT_TTS_VOICE
```

LiveKit and Pipecat must read the same profile for comparable runs. A benchmark
or report must refuse or mark a comparison inconclusive when lanes use different
profiles. Default model names and pricing rates must be chosen from current
official provider documentation at implementation time and recorded in
`decisions.md` with the date, source URLs, and rationale.

## Document Corpus

The current supported `lookup_docs` corpus is the Turkish Mavi Kapi store corpus
under `services/common/docs/magaza/`:

- `hakkinda.md`
- `urunler.md`
- `kargo-iade.md`
- `iletisim.md`

The corpus list is deterministic. Adding, removing, or auto-discovering corpus
files changes benchmark comparability and requires an explicit decision.

## Observability Artifacts

The canonical runtime artifacts live under `/var/lib/voicebot` on the Asterisk
VM:

- `events.jsonl`: append-only stage trace events.
- `usage.jsonl`: append-only usage and estimated-cost events.
- `reports/*.json`: machine-readable benchmark/comparison reports.
- `reports/*.md`: human-readable benchmark/comparison reports.

`turns.jsonl` is a legacy/debug rendering artifact only. New acceptance must use
`events.jsonl`, `usage.jsonl`, report files, or observer API output.

Every trace event must include:

- `ts`: epoch timestamp.
- `lane`: `livekit` or `pipecat`.
- `call_id`: stable per phone call.
- `turn_id`: stable per user turn within a call when applicable.
- `stage`: `call`, `audio`, `stt`, `llm`, `tool`, `tts`, or `error`.
- `event`: specific event name.
- `provider`: provider or framework name when applicable.
- `model`: model name when applicable.
- `duration_ms`: stage duration when known.
- `payload`: structured JSON payload.

Required stage evidence:

- STT records identify the audio receive boundary, STT model, language, final
  transcript, and audio duration when available.
- LLM request records show the prompt/profile, message list sent to the model,
  available tool schemas, tool policy, and model.
- Tool records show the `lookup_docs` query, source files/sections, scores, and
  no-hit result.
- LLM response records show assistant text, requested tool calls, finish reason
  when exposed, and input/output token counts when exposed.
- TTS records show text sent to TTS, model, voice, output format, character
  count, and audio byte/duration evidence when available.
- Audio records show caller send/receive timing, Asterisk recording evidence,
  and Pipecat AudioSocket byte/duration counters where applicable.
- Usage records are attributable by lane, call, turn, stage, provider, model,
  unit type, units, estimated USD, and pricing table version.

Trace data intentionally includes user utterances, STT transcripts, prompt
context, retrieved snippets, LLM output, and TTS text. It must never include API
keys, SIP passwords, `.env` contents, bearer tokens, LiveKit API secrets, or
other runtime credentials.

## Observer Web UI

The supported operator interface is a FastAPI app using server-rendered
Bootstrap 5 + HTMX pages. It binds to `127.0.0.1:8088` by default and is reached
through SSH port forwarding. It reads `/var/lib/voicebot` artifacts and does not
receive provider credentials.

The observer must provide:

- Calls: recent calls, lane, extension, status, duration, turn count, total
  estimated cost, and audio integrity status.
- Call detail: per-turn STT transcript, LLM input, tool request/result, LLM
  output, TTS text, usage, audio counters/recording links, and raw JSON.
- Usage: cost grouped by lane, provider, model, stage, and time window.
- Compare: side-by-side LiveKit/Pipecat evidence for the same utterance or run.
- Reports: generated Markdown and JSON comparison reports.
- Raw events: filterable event table.
- JSON APIs for health, calls, events, usage, comparisons, and reports.

## Audio Integrity

Commanding baresip to play a WAV is not enough evidence that audio reached the
agent or returned to the caller. Supported benchmark validation requires:

- a test-caller run manifest with utterance timing and source WAV durations;
- Asterisk-side recording evidence that caller audio reached the VM;
- Asterisk-side or framework evidence that bot TTS audio returned toward the
  caller;
- Pipecat AudioSocket inbound/outbound byte and duration counters;
- STT transcript evidence that the intended utterance, not only its tail, was
  processed;
- a truncation/inconclusive flag when timing, recordings, or trace evidence are
  missing or inconsistent.

## Source Files

- `services/livekit/`
- `services/pipecat/`
- `services/common/`
- `services/observer/`
- `services/test-caller/`
- voicebot entries in `asterisk/extensions.conf.tmpl`
