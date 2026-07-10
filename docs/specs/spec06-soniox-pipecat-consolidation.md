# Spec spec06 - Soniox Streaming Voice Agent on a Single Pipecat Lane

> Governed by `docs/runbooks/spec-rules.md`. A spec is a stable contract, not a
> changelog. Daily progress belongs in `PLANS.md`.

- **Status:** Draft
- **Owner:** operator
- **Created:** 2026-07-10
- **Supersedes:** `docs/specs/spec04-livekit-pipecat-fair-comparison.md`
  (the two-lane comparison mission ends; Pipecat becomes the single lane)
- **Inherits:** the multi-turn Turkish corpus and scoring fixtures from
  `docs/specs/spec05-realistic-multiturn-test-corpus.md`

## Goal

A caller dials extension 1098 through the SBC and talks to a voicebot that
feels live: the bot starts speaking within about one second after the caller
stops, speech is wideband-clean, the caller can interrupt the bot mid-sentence
(barge-in), and long caller sentences are never cut off mid-speech. The
LiveKit lane no longer exists; Pipecat is the single, maintained lane, using
Soniox streaming STT and TTS with the LLM kept as a swappable OpenAI service.

## Problem Statement

The current turn loop is batch: whisper-1 (full-clip HTTP) -> gpt-4o-mini
(full completion) -> tts-1 (full synthesis, roughly 10 s for a 40-word
Turkish reply). Effective audio is 8 kHz narrowband despite wideband codec
offers, and the Pipecat sink downsamples 24 kHz TTS output with a
nearest-neighbour resampler. Turn-end is guessed from VAD silence thresholds
(stop_secs=0.35), which cuts callers off mid-sentence, and echo-driven false
barge-in required heuristic filters. The LiveKit lane multiplies the ops
surface (SIP GW + SFU + Redis + agent, WebRTC/ICE/STUN) for no benefit in a
SIP-only lab; its SIP gateway's 15 s RTP watchdog forced a keepalive hack
into the test suite, and the stack has been down on the VM since 2026-07-08.

## Scope

1. Remove the LiveKit lane: repo tree, Asterisk trunk and dialplan entries,
   Makefile targets, deploy filter entries, env names, suite code paths, and
   the VM containers/images.
2. Move the Pipecat audio path to 16 kHz end to end: chan_audiosocket
   (Dial form) with slin16 on extension 1098, a sample-rate-parameterized
   AudioSocket transport, and no resampler (Soniox TTS emits 16 kHz PCM
   natively).
3. Replace batch STT/TTS with Soniox streaming services in the Pipecat
   agent: SonioxSTTService (model stt-rt-v5, Turkish language hints, domain
   context, semantic endpoint detection) and SonioxTTSService (16 kHz,
   Turkish). The OpenAI LLM service and the lookup_docs tool remain.
4. Restructure turn taking: Soniox endpoint detection (the final "<end>"
   token) owns turn-end and triggers the LLM; Silero VAD is kept only as the
   barge-in trigger that stops bot audio.
5. Update shared policy surfaces: voicebot profile (stt/tts provider and
   model fields), usage pricing rows for Soniox, measured per-stage
   durations in trace events, SONIOX_API_KEY plumbing.
6. Keep the dashboard read-only and functional with a single lane; the
   comparison panels must degrade gracefully (historical livekit rows stay
   readable, no hard requirement for two live lanes).
7. Adjust the test-caller suite for the single lane and remove the
   LiveKit-specific RTP keepalive re-arm; revisit the per-turn settle budget
   now that replies are streaming-fast.

## Non-Goals

- No new framework evaluation (LiveKit re-adoption, OpenAI Realtime,
  Gemini Live). The reference architecture is the Soniox voice-agent demo
  implemented with Pipecat's native Soniox services.
- No vendoring of the Soniox demo app or its Twilio bridge; Asterisk
  AudioSocket is the transport.
- No dashboard redesign beyond single-lane graceful degradation.
- No change to the SBC (DEC-005 branch untouched) or monitoring VM.
- No LLM provider migration; the LLM stays an OpenAI chat model behind the
  existing profile switch.
- No VM rebuild; VMs remain reproducible from installers.

## Architecture Contract

- Call path: baresip (host) -> OpenSIPS SBC (+ rtpengine) -> Asterisk 22
  ext 1098 -> chan_audiosocket slin16 @ 16 kHz, 20 ms ptime (640-byte
  frames) -> Pipecat agent (pc-agent container, TCP 8090).
- Agent pipeline (Soniox demo processor chain in Pipecat terms):
  AudioSocket source -> Silero VAD (barge-in only) -> SonioxSTTService
  (streaming WebSocket, endpoint detection on) -> OpenAI LLM (token
  streaming, lookup_docs tool) -> SonioxTTSService (streaming WebSocket,
  pcm_s16le @ 16 kHz) -> AudioSocket sink.
- Turn-end authority is Soniox's semantic endpoint token, not VAD silence.
  VAD's only job is interrupting bot playback when the caller speaks.
- There is exactly one voicebot lane. `lane` remains a field in trace
  events (value `pipecat`) so historical multi-lane data stays readable.
- The dashboard stays a read-only consumer of `/var/lib/voicebot/*.jsonl`
  and `/var/spool/asterisk/monitor/` (DEC-008 unchanged).
- MixMonitor recording and the offline transcriber flow are unchanged.

## Config Contract

- Tracked templates: `vms/asterisk/etc/asterisk/extensions.conf.tmpl`
  (ext 1098 Dial(AudioSocket/...) form), `pjsip.conf.tmpl` (livekit-trunk
  removed), Pipecat compose/install under `vms/asterisk/services/pipecat/`.
- Env (names in `.env.example`, values in `/etc/asterisk-lab/env` on the
  VM): `SONIOX_API_KEY` (new, secret), `OPENAI_API_KEY` (kept),
  `VOICEBOT_STT_MODEL` / `VOICEBOT_TTS_MODEL` / `VOICEBOT_TTS_VOICE` /
  `VOICEBOT_LLM_MODEL` (profile overrides, Soniox-aware defaults). All
  `LIVEKIT_*` names are removed.
- `requirements.txt` pins `pipecat-ai[silero,soniox]==1.4.*`.
- Deploy filters no longer ship a livekit payload.

## API Contract

- No new customer-facing endpoints. Existing dashboard `/api/*` endpoints
  keep their shapes; comparison endpoints may return single-lane results
  without erroring.

## Observability Contract

- Trace events keep the `voicebot-events-v1` schema. New requirement:
  stt/llm/tts stage events carry measured `duration_ms` (streaming
  first-token / first-audio timings), replacing timestamp-delta
  approximations. Existing `latency_basis` labeling stays truthful.
- Usage rows for Soniox: STT audio-seconds and TTS characters with a dated
  `pricing_version`.
- No secrets or raw API keys in events, logs, or dashboards.
- Live evidence for acceptance lands under ignored
  `runtime/spec06-live-evidence/`.

## Acceptance Criteria

- LiveKit is gone: no `vms/asterisk/services/livekit/` tree, no
  livekit-trunk endpoint, no ext 1099, no LiveKit Makefile targets or
  deploy filter entries, no LiveKit containers or images on the Asterisk
  VM. `rg -i livekit` over application source returns only historical docs,
  archives, and dashboard compatibility references.
- A live call (baresip -> SBC -> 1098) demonstrates, with captured
  evidence: bot first audio within ~1.5 s after caller stop on short turns;
  no mid-speech cutoff on a long multi-clause Turkish sentence; barge-in
  stops bot audio promptly; audio path negotiated at 16 kHz (slin16) end
  to end.
- The spec05 corpus suite completes both 4-turn conversations on the
  Pipecat lane with dashboard reliability checks green and measured (not
  approx) per-stage latency populated.
- `make verify` passes on the Asterisk VM; `ruff check` passes on
  `infra/scripts/` and `vms/asterisk/services/`; `shellcheck` passes on
  changed scripts; dashboard unit tests pass.
- No secrets or runtime artifacts tracked by git; `PLANS.md` reflects final
  state; all changes committed.
