# Decisions

Durable product and process decisions. IDs are never reused or renumbered.
Superseded decisions stay here and point to their replacement.

## DEC-001 - Repository governance follows the agent-workflow-template

- **Decision:** This repository uses the agent-workflow-template governance model:
  `AGENTS.md` as the single source of truth, `PLANS.md` for live state,
  spec-driven execution, and repo-tracked memory under `docs/memory/`.
- **Reason:** A single, shared operating discipline keeps every agent harness
  (Claude Code, Codex, others) aligned and makes work auditable.
- **Impact:** Agents must follow the read order and workflow in `AGENTS.md`.
  Changes to the governance model are made in `AGENTS.md` and recorded here.

## DEC-002 - specs/ decommissioned; docs/specs/ is the single spec surface

- **Decision:** The legacy `specs/` directory (domain contracts, runbooks,
  decisions) has been decommissioned. All spec work now lives under
  `docs/specs/specNN-topic.md`, created from `docs/templates/spec-template.md`,
  paired with a kickoff prompt under `docs/prompts/`. The former dual-surface
  model (DEC-002 original, 2026-07-06) is superseded by this entry.
- **Reason:** Two spec surfaces created confusion and maintenance overhead.
  Consolidating into `docs/specs/` gives a single place to find governing
  specs and keeps the AGENTS.md read order simpler.
- **Impact:** Agents read `docs/specs/` when `PLANS.md` names a governing
  spec. `docs/runbooks/spec-rules.md` documents the single-surface rules.
  Removed legacy `specs/` deploy exclusions because the directory no longer
  exists.

## DEC-003 - Transcriber dependencies pinned; systemd hardening applied

- **Decision:** `scripts/requirements.txt` pins `openai-whisper` and `torch`
  versions. `asterisk/transcriber.service` carries the systemd hardening
  set (`ProtectSystem=strict`, `ProtectHome=true`, `PrivateTmp=true`,
  `NoNewPrivileges`, `RestrictNamespaces`, `RestrictRealtime`,
  `RestrictSUIDSGID`, `LockPersonality`, `SystemCallArchitectures=native`)
  but not `MemoryDenyWriteExecute` because PyTorch / numba JIT generates
  executable pages at runtime.
- **Reason:** An unpinned dep means the box that worked yesterday is not
  the box you provision tomorrow. Systemd hardening is the cheapest
  blast-radius reduction on Linux and the first thing a security
  reviewer checks.
- **Impact:** Do not bump `openai-whisper` or `torch` without re-verifying
  `/opt/transcriber/venv` builds and `systemd-analyze security transcriber`
  stays at or below `5.8 MEDIUM`. Do not enable
  `MemoryDenyWriteExecute=true`. Whisper uses date-based versions
  (`20250625`); verify on PyPI before assuming a typo.

## DEC-004 - Lab env is host-local and never transported by `make deploy`

- **Decision:** Deploy filters exclude `.env` and `.env.*`. VM runtime
  secrets live in `/etc/asterisk-lab/env`; repo-local `.env` remains only a
  host fallback for local workflows.
- **Reason:** Rsyncing real env files into a VM is a leak surface and would
  silently overwrite per-VM secrets. Deploy must never touch credential
  material.
- **Impact:** New deploy flows must keep env files out of payload filters.
  Bootstrap new VMs by creating `/etc/asterisk-lab/env` manually or by using
  a controlled secret mechanism such as systemd-creds.

## DEC-005 - The SBC initial-INVITE branch must be direction-aware

- **Decision:** The initial-INVITE branch in `sbc/opensips.cfg.tmpl` sets
  `$du` to the Asterisk address only when the request source is not
  Asterisk itself. Asterisk-originated INVITEs (B2BUA outbound legs from
  `Dial(PJSIP/<ext>)`) fall through to their R-URI so they can reach
  the registered softphone.
- **Reason:** A direction-blind `$du = "sip:${ASTERISK_IP}:5060"` loops
  Asterisk-originated INVITEs back to Asterisk. The Path/Route return
  handling by `loose_route()` alone does not save this case because the
  `received=<uri>` parameter on the Path can trip its self-recognition
  and the request lands back in the initial-INVITE branch.
- **Impact:** Every future SBC routing change that touches the
  initial-INVITE branch must preserve the direction gate (or an
  equivalent) and be verified by exercising `Dial(PJSIP/<registered-ext>)`
  end-to-end. Future validation must guard this behavior explicitly.

## DEC-006 - Shared skill store lives outside the repo; provider trees alias it

- **Decision:** `.agents/skills` and `.codex/skills` are symlinks into a
  zenith-managed skill store outside the repository
  (`~/.zenith/projects/<project>/.zenith/skills`). `.claude/skills/` is
  a real directory holding the Claude Code-side working copy.
- **Reason:** The zenith orchestrator manages a shared skill catalogue
  across projects and multiple providers; symlinks let this project pick
  up new or updated skills without a per-project sync commit. The
  agent-workflow-template's "three trees byte-identical" rule assumes
  in-repo copies, but the current setup is a deliberate operator choice.
- **Impact:** Changes to the shared skill catalogue happen through the
  zenith store, not by editing files under `.agents/skills` or
  `.codex/skills` here. If the operator later decides to move to
  in-repo copies, the symlinks must be replaced with real directories
  and all three trees kept byte-identical in the same commit.

## DEC-007 - VM deploy payloads live under /opt, secrets under /etc

- **Decision:** Makefile deploy targets rsync role-specific payloads to
  `/opt/asterisk-lab/current` using filters under `deploy/rsync/`. The
  target directory is disposable output and does not need to be a git
  checkout. Per-VM env lives in `/etc/asterisk-lab/env`.
- **Reason:** Keeping payload under `~/asterisk-lab` made the VM directory
  look like a source repository even when it was only rsync output. The new
  layout follows Linux boundaries: source on the host, deploy bundle under
  `/opt`, secrets under `/etc`, build cache under `/usr/local/src`, runtime
  state under `/var`.
- **Impact:** Installers load `/etc/asterisk-lab/env` first and fall back to
  repo-local `.env` for host workflows. Verification should treat host git as
  source of truth and VM `/opt/asterisk-lab/current` as rendered payload.

## DEC-008 - Read-only consumers of services/common must not reuse its default-path helpers

- **Decision:** `trace_events.default_events_path()` and
  `usage.py`'s `_default_log_path()` fall back to a per-user XDG state path
  when the caller lacks *write* access to `/var/lib/voicebot`. A read-only
  consumer (the dashboard, running as `asterisk`, which can read but not
  write that root-owned directory) must resolve its own read paths from the
  `VOICEBOT_EVENTS_LOG` / `VOICEBOT_USAGE_LOG` override names plus a hardcoded
  canonical default, and must not call those helpers directly.
- **Reason:** The helpers exist to let writer agents work from an
  unprivileged host during local dev without sudo; write-access is the
  correct signal for a writer's fallback decision. For a reader that never
  writes, checking `os.access(..., os.W_OK)` produces a false negative on the
  VM (dir is `root:root 0755`) and silently serves an empty per-user path
  instead of the real canonical log, with no error. Discovered when the
  dashboard's `/api/calls` returned `[]` against 1043 real events on disk.
- **Impact:** Any future service that reads (but does not write)
  `/var/lib/voicebot/*.jsonl` must resolve its own read paths rather than
  importing `default_events_path()` / `LOG_PATH` from `services/common`.
  See `vms/asterisk/services/dashboard/app/config.py` for the pattern.

## DEC-009 - AudioSocket UUID correlation accepts compact and hyphenated forms

- **Decision:** Dashboard recording correlation treats AudioSocket UUIDs as
  equivalent whether they are logged compact (`32` hex chars) or hyphenated
  (`8-4-4-4-12`). The recording index stores both lookup keys for the same
  MixMonitor file.
- **Reason:** Asterisk recording filenames carry `${UNIQUEID}` and the
  dashboard derives a hyphenated AudioSocket UUID from that value. The
  Pipecat lane emits the same AudioSocket UUID in compact form as its
  `call_id` / `uuid`, so a literal string join misses real recordings even
  when the ids represent the same value.
- **Impact:** Future trace readers and correlation code must normalize
  AudioSocket UUID formatting before comparing values. Do not assume the
  hyphenated display form is the only serialized form in `events.jsonl`.

## DEC-010 - LiveKit lane retired; Pipecat is the single lane on Soniox streaming

- **Decision:** The LiveKit voicebot lane is removed (repo and VM). Pipecat
  is the single maintained lane, using Soniox streaming STT
  (SonioxSTTService, stt-rt-v5) and streaming TTS (SonioxTTSService) with
  the LLM kept as a swappable OpenAI chat service. The audio path is
  16 kHz end to end via chan_audiosocket (Dial form, slin16). Turn-end is
  owned by Soniox semantic endpoint detection (the final "<end>" token);
  Silero VAD is kept only as the barge-in trigger.
- **Reason:** In a SIP-only lab the LiveKit WebRTC stack (SIP gateway,
  SFU, Redis, agent worker) is pure operational surface: its SIP gateway's
  hardcoded ~15 s RTP-inactivity watchdog forced a keepalive hack into the
  test suite, an Opus/G.722 wideband attempt deadlocked on ICE/STUN, and
  the stack sat down on the VM for two days unnoticed. The batch
  whisper-1/tts-1 pipeline caused 10+ s turn latency, and VAD
  silence-threshold endpointing cut callers off mid-sentence. Streaming
  STT/TTS plus semantic endpointing removes those failure classes;
  single-hop AudioSocket removes the codec-negotiation and ICE surface.
- **Impact:** No new lane or framework is added without a fresh decision.
  The comparison mission (spec04 surface) is closed as superseded;
  dashboard comparison panels must degrade gracefully with one live lane.
  Turn-taking changes must preserve the endpointing-vs-barge-in ownership
  split. Re-evaluating LiveKit (or a speech-to-speech provider such as
  OpenAI Realtime) requires web/mobile WebRTC clients or scale needs that
  AudioSocket cannot serve.

## DEC-011 - AudioSocket wideband framing and streaming-STT interim frames need explicit handling

- **Decision:** (a) `chan_audiosocket`'s audio message type byte encodes
  the sample rate, not just "audio present": 0x10 is 8 kHz slin, 0x12 is
  16 kHz slin16, per `include/asterisk/res_audiosocket.h`. Any non-8 kHz
  AudioSocket transport must send and expect the rate-matched KIND byte
  (`vms/asterisk/services/pipecat/agent/audiosocket.py`'s
  `AUDIO_KIND_BY_RATE` table), not the old hardcoded 0x10. (b) In a
  Pipecat pipeline using a streaming STT service (Soniox), both the final
  `TranscriptionFrame` and the per-word `InterimTranscriptionFrame`
  subclass `TextFrame`. Any processor with a generic `isinstance(frame,
  TextFrame)` branch (used to catch LLM/TTS text) must explicitly exclude
  transcription frame types, or it will treat the caller's own in-progress
  words as bot speech.
- **Reason:** Both were discovered the same session moving the Pipecat
  lane to 16 kHz + Soniox streaming (spec06). (a) silently corrupted
  audio: Asterisk read 16 kHz frames as 8 kHz with the old KIND byte, so
  the call proceeded but audio was garbled/wrong-speed with no error.
  (b) silently broke functionality: `BotEchoFilter`'s recent-bot-text set
  got poisoned with the caller's own interim words, so every subsequent
  real user turn matched as an "echo" and was dropped - the agent
  appeared to work but never heard the caller again after turn one.
- **Impact:** Any future AudioSocket sample-rate change must update the
  KIND byte alongside `AUDIOSOCKET_SAMPLE_RATE`. Any future FrameProcessor
  added to a pipeline with a streaming STT service must check for
  `TranscriptionFrame`/`InterimTranscriptionFrame` explicitly before a
  broad `TextFrame` match, not assume `TextFrame` means "assistant text".
