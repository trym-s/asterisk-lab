# PLANS.md - asterisk-lab live execution state

> Governed by `docs/runbooks/plan-rules.md`. Keep around 100 to 250 lines.
> Update after every meaningful step. Link artifacts; never paste long output.
> Always carry a state.
> When the governing spec is complete, archive this file under `docs/archive/plan/`.
> The next spec starts with a fresh root `PLANS.md` from `docs/templates/PLANS.md`.

**Status:** spec07 drafted, awaiting kickoff. The spec redesigns the
per-call dashboard page into a voice-to-voice console (chat-bubble
conversation + pipeline-pulse strip) and removes the retired LiveKit-era
comparison surface. No implementation started.
**Governing spec:** `docs/specs/spec07-voicebot-call-console.md`
**Kickoff prompt:** `docs/prompts/spec07-voicebot-call-console.md`
**Last updated:** 2026-07-16

## Active milestones

- [ ] Call console page redesign: chat-bubble conversation with per-bubble
      latency badges, pipeline-pulse strip (stage state, live timer, last
      event label), barge-in/echo-filter event strip.
- [ ] Finished-call mode: same view with a call summary (duration, turn
      count, per-stage avg/p95 latency) replacing the pulse strip.
- [ ] Additive pulse/summary fields on `/api/calls/{call_id}/turns`,
      derived server-side in `app/data.py`; 1 s console polling
      (env-overridable).
- [ ] Remove `/parity` and `/comparison`: routes, API endpoints, templates,
      nav link, comparison-only `app/data.py` helpers, and their tests.
- [ ] Gates and live evidence: dashboard tests, ruff, `make verify`, real
      call watched end to end, evidence under
      `runtime/spec07-live-evidence/`.

## Blockers

- none

## Canonical evidence

- none

## Recent updates

- 2026-07-16 - Off-spec feature: connected a real DID on a remote FreePBX
  (Sangoma FreePBX 17 / Asterisk 22.8.2, public) to the voicebot. The
  Asterisk VM is behind three NAT layers (libvirt/WSL2/ISP) and
  unreachable inbound, so it REGISTERS OUTBOUND to FreePBX as an ordinary
  extension (1003); FreePBX's Inbound Route sends the DID down that
  registration into a new `[from-freepbx]` -> `[voicebot]` dialplan path.
  Commit `e871543`: `pjsip-trunk.conf.tmpl` (registration/endpoint/aor/auth,
  `line=yes` for inbound matching, `qualify_frequency=30` + short
  `expiration` to hold the NAT pinhole, back-off retries to dodge FreePBX
  fail2ban), `pjsip.conf.tmpl` includes a separate `pjsip.trunks.d/`
  (kept out of the `SIP_EXTENSIONS`-pruned, verify-scanned `pjsip.d/`),
  `install.sh` renders when `FREEPBX_HOST` set / removes when unset,
  `extensions.conf.tmpl` extracts the 1098 AudioSocket block into a shared
  `[voicebot]` context, `verify.sh` gains trunk-conditional checks,
  runbook `docs/runbooks/freepbx-trunk.md`. Tracked here per "small tasks
  skip specs". Proven live: real inbound call, 4-turn Turkish conversation
  end to end (greeting -> STT stt-rt-v5 -> gpt-4o-mini + doc lookup -> TTS
  tts-rt-v1), two-way RTP confirmed via audiosocket counters (1903 inbound
  / 1823 outbound frames), `make verify` 14/14. Findings worth carrying:
  (1) FreePBX SIP port is 7201, not 5060 (scanner avoidance) -- do not
  assume 5060. (2) Symmetric RTP latching alone carried audio both ways
  behind double NAT; `external_media_address` deliberately NOT set and
  confirmed unnecessary. (3) The DID's Sippy softswitch (Cloudcell's own,
  195.14.104.23 upstream) OFFERS G722 in its INVITE, but the trunk pins
  `allow=ulaw,alaw` so the call negotiated ulaw 8 kHz -- adding g722 to the
  trunk endpoint MIGHT get wideband to STT (untested; caller was mobile so
  the upstream leg may cap at 8 kHz anyway). (4) On the FreePBX box, a
  root-owned `pjsip.auth.conf`/`agents.conf` silently blocked `Apply
  Config` from writing new extension secrets (log: `Permission denied` /
  `chown(): Operation not permitted`); fix is `fwconsole chown` +
  `fwconsole reload`. All four are captured in the runbook.
- 2026-07-13 - Off-spec infra chore: brought up the full three-VM lab
  (Asterisk, SBC, monitoring) from a bare host under WSL2 - installed
  libvirt/qemu, fixed a missing +x bit on `infra/libvirt/setup-host.sh`,
  raised the WSL2 `.wslconfig` memory/CPU ceiling so all three VMs fit, and
  added `infra/libvirt/create-lab-vms.sh` (+ `make lab-provision`) as a
  one-shot idempotent create-all-three-and-SSH-check script, documented in
  `README.md` and `docs/runbooks/local-development.md`. Unrelated to
  spec07; tracked here per the "small tasks skip specs" rule.
- 2026-07-10 - Drafted spec07 (voicebot call console redesign) with the
  operator: chat-bubble layout, pulse detail level, no-replay finished-call
  mode, light Tabler theme, additive turns-API fields, 1 s console polling
  all confirmed interactively. Comparison surface removal is in scope;
  implementation deferred to the spec07 kickoff.
- 2026-07-10 - Closed spec06: LiveKit lane removed, Pipecat lane moved to
  Soniox streaming STT/TTS at 16 kHz with semantic endpointing owning
  turn-end and VAD limited to barge-in. Proven live: both 4-turn Turkish
  corpus conversations completed cleanly, first bot audio ~1.2-2.4 s after
  caller stop (vs 10+ s on the old batch pipeline). All gates green
  (`make verify` 11/11, ruff, shellcheck, 25 dashboard + 6 common tests).
  Two bugs found and fixed during the live run: AudioSocket slin16 KIND
  byte (0x12, not 0x10) and streaming-STT interim frames poisoning the
  echo filter. Archived to
  `docs/archive/plan/2026-07-10-spec06-soniox-pipecat-consolidation.md`.
  Deferred, non-blocking follow-ups (not tracked as TODO - no operator
  approval sought yet): pick the Turkish TTS voice from the three
  captured samples (default stays `Adrian`); tune
  `VOICEBOT_STT_ENDPOINT_SENSITIVITY` against a real human call; reconcile
  the Soniox TTS per-char cost estimate against a real invoice.

## Archive pointers

- `docs/archive/plan/2026-07-07-spec01-deploy-sbc-monitoring.md`
- `docs/archive/plan/2026-07-07-spec02-voicebot-observability-dashboard.md`
- `docs/archive/plan/2026-07-07-spec03-voicebot-dashboard-redesign.md`
- `docs/archive/plan/2026-07-10-spec05-realistic-multiturn-test-corpus.md`
- `docs/archive/plan/2026-07-10-spec06-soniox-pipecat-consolidation.md`
