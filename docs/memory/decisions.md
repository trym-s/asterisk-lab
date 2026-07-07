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
