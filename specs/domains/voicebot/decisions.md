# Voicebot Decisions

## Parity First

LiveKit and Pipecat lanes should differ by framework and media transport, not
by prompt, model profile, document corpus, tool behavior, trace schema, usage
schema, or benchmark corpus.

## Narrowband Baseline

The current comparison baseline is 8 kHz telephony audio. Wideband experiments
belong in explicit benchmark changes so codec and framework effects do not mix.

## Stage Trace Replaces Loose Turn Logs

Both lanes write stage-level events and usage records to `/var/lib/voicebot` so
operators can inspect STT input/output, LLM input/output, doc tool
request/result, TTS input/output, audio evidence, tokens, cost, and latency.
Legacy turn rendering can remain for debugging, but contracts use the canonical
trace, usage, observer, audio, and report artifacts.

## Doc Lookup Corpus Is Fixed For Comparable Runs

The current corpus is the Turkish Mavi Kapi store corpus under
`services/common/docs/magaza/`. Corpus files are listed deterministically.
Changing the corpus changes retrieval behavior and must be captured in a
decision and benchmark report metadata.

## Test Caller Timing Is Not Audio Proof

The baresip control script proves that a source WAV was scheduled, but not that
the whole utterance reached the agent or that the whole response returned to the
caller. Audio integrity validation requires test-caller timing, Asterisk-side
recording evidence, STT transcript evidence, and framework audio counters where
available.

## Observer Stack

The voicebot observer uses FastAPI with server-rendered Bootstrap 5 + HTMX. It
binds to `127.0.0.1:8088` by default and is accessed with SSH port forwarding.
The observer reads `/var/lib/voicebot` artifacts and must not receive OpenAI,
LiveKit, ElevenLabs, SIP, or other runtime credentials.

## Model Profile Decision Must Be Fresh

Default STT, LLM, and TTS model choices must be selected during implementation
from current official provider documentation and pricing. Record the check date,
source URLs, selected models, pricing units, and rationale here before claiming
model/cost contracts pass. Both lanes must use the same profile for comparable
reports.
