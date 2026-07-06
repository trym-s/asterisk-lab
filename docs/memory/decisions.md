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

## DEC-002 - Two spec surfaces coexist: specs/ (domain) and docs/specs/ (cross-cutting)

- **Decision:** The pre-existing `specs/` tree (`global/`, `domains/{asterisk,
  sbc,monitoring,voicebot}/`, `changes/`) is the authoritative source of
  supported behavior, VAL-* acceptance criteria, and durable domain
  decisions. New cross-cutting, harness-level, or programme-level specs
  use `docs/specs/specNN-topic.md` per the agent-workflow-template
  convention, paired with `docs/prompts/`.
- **Reason:** The existing `specs/` tree is highly developed and its VAL-*
  based validation model is deeply integrated with the `.claude/agents/`
  contract-review, scrutiny-validator, and user-testing-validator lanes.
  Renumbering or migrating it would be pure churn. The AWT `docs/specs/`
  slot fills a separate need: initiatives that span domains or evolve the
  harness itself.
- **Impact:** Agents read `specs/README.md` and `specs/global/agent-routing.md`
  to pick a domain; they read `docs/specs/` only when `PLANS.md` names a
  governing cross-cutting spec. `docs/runbooks/spec-rules.md` documents
  both surfaces.

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

## DEC-004 - `.env` is host-local and never transported by `make deploy`

- **Decision:** The `RSYNC_EXCLUDES` list in the Makefile excludes `.env`
  (along with `.git/`, `.github/`, `.agents/`, `.claude/`, `.codex/`,
  `.mcp.json`, AGENTS/README/PROCESS/NOTES, `specs/`, `__pycache__/`,
  `.rendered/`). Every VM has its own `.env` placed manually.
- **Reason:** Rsyncing a real `.env` into a VM is a leak surface and
  would silently overwrite per-VM secrets. Deploy must never touch
  credential material.
- **Impact:** New deploy flows must extend `RSYNC_EXCLUDES` to keep any
  new secret file out of the payload. Bootstrap new VMs by copying
  `.env` separately (`scp` or systemd-creds).

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
  end-to-end. VAL-SBC contracts must guard this.

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
