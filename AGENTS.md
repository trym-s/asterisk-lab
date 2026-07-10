# asterisk-lab - Agent Source of Truth

This file is the single source of truth for every AI agent (Claude Code, Codex,
or any other harness) working in this repository. Read it first, follow it, and
update it here instead of duplicating rules elsewhere.

## 1. Purpose

This repository is a reproducible three-VM lab for Debian 13 / Ubuntu 26.04:
an **Asterisk 22 LTS PBX**, an optional **OpenSIPS 3.6 LTS SBC** with
rtpengine, and an optional **monitoring VM** running Zabbix 7.0 LTS and
Grafana. Optional voicebot lanes (LiveKit and Pipecat) run on the Asterisk VM
so telephony/AI integrations can be compared under identical conditions. A
host softphone (baresip) drives the lab through the SBC when that layer is
present, or directly against Asterisk when it is not. Everything must be
reproducible from a fresh clone, idempotent on re-run, and validated through
explicit contracts rather than unstated operator memory.

## 2. Mandatory Read Order

Start every session in this order:

1. `AGENTS.md` (this file).
2. `PLANS.md` (live execution state).
3. The governing spec under `docs/specs/`, if `PLANS.md` points to one.
4. Relevant `docs/memory/*` files.
5. Relevant `docs/architecture/*` files.
6. Relevant `docs/runbooks/*` files.

`README.md`, `PROCESS.md`, and `NOTES.md` are not acceptance sources. They
explain onboarding, current state, or personal rationale, but the specs and
contracts define supported behavior and required evidence.

## 3. Directory Ownership

| Path | Ownership |
| --- | --- |
| `AGENTS.md` | Agent rulebook. Update here; never fork the rules. |
| `CLAUDE.md` | Claude Code entry point; delegates to `AGENTS.md`. |
| `PLANS.md` | Live execution state for the current spec or work item (governed by `docs/runbooks/plan-rules.md`). |
| `TODO.md` | Operator-controlled open/closed task index only; agent changes require operator approval. |
| `DEBATE.md` | Reusable Codex/Claude debate protocol template (live copies under `docs/debates/`). |
| `README.md` | Human onboarding, not acceptance. |
| `PROCESS.md` | Current-state index, not acceptance. |
| `Makefile` | Operator-facing entry point for install/verify/deploy/logs per VM. |
| `install.sh` | Asterisk VM installer (source build + config render + service enable). |
| `docs/specs/` | Governing specs (`specNN-topic.md`); paired with `docs/prompts/`. |
| `docs/prompts/` | Short kickoff prompts paired to `docs/specs/`. |
| `docs/memory/` | Proven product-local decisions, bugs, and reusable facts. |
| `docs/runbooks/` | Operational procedures and the plan/spec rules. |
| `docs/architecture/` | Durable architecture documentation. |
| `docs/research/` | Product-local research and tradeoff notes. |
| `docs/todo/` | One detail file per `TODO.md` entry. |
| `docs/archive/plan/` | Dated archives of completed `PLANS.md` states. |
| `docs/debates/` | Debate transcripts (ignored) and sanitized summaries (tracked). |
| `docs/templates/` | Seed templates for plans, specs, kickoff prompts, TODO topics, subagent roles. |
| `.claude/` | Claude Code harness: skills, subagent roles, per-developer settings. |
| `.codex/` | Codex harness: config, skills, subagent roles. |
| `.agents/` | Provider-neutral shared skill library (see DEC-006 on skill store layout). |
| `.githooks/` | Repo-managed git hooks (identity + ASCII + spec-boundary checks). |
| `.github/` | GitHub Actions workflows. |
| `vms/asterisk/` | Asterisk VM source of truth: `etc/asterisk/*.tmpl` config files, `lib/systemd/system/*.service` units (`asterisk.service`, `transcriber.service`, `voicebot-dashboard.service`). |
| `vms/asterisk/services/` | Voicebot lane and test harness: `pipecat/` (single lane, Soniox streaming STT/TTS), `common/` (shared model/cost/usage/trace code), `test-caller/`, `dashboard/` (read-only observability dashboard, spec02). |
| `vms/sbc/` | OpenSIPS + rtpengine source of truth: `etc/opensips/opensips.cfg.tmpl`, `etc/rtpengine/rtpengine.conf.tmpl`, `install.sh`, `verify.sh`. |
| `vms/monitoring/` | Zabbix + Grafana source of truth: `install.sh`, `verify.sh`, `setup-zabbix-agent.sh`, `verify-agent.sh`, metric collectors, dashboard provisioning. |
| `infra/scripts/` | Repo-owned host/VM scripts: `lib/env.sh` (shared lab-env loader), `setup-transcriber.sh`, `verify.sh` (Asterisk VM smoke check), `watcher.py`, `transcribe.py`, `requirements.txt`. |
| `infra/libvirt/` | Host-side VM provisioning: cloud-init domain XML, `create-cloudinit-vm.sh`, `setup-host.sh`. |
| `infra/deploy/` | rsync filters shaping each VM's deploy payload (`asterisk.filter`, `sbc.filter`, `monitoring.filter`). |
| `runtime/` | Ignored. Live evidence, recordings, logs, local state. |

## 4. Agent and Skill Model

Three layers; use the smallest set that covers the task:

- Constitution and execution state: `AGENTS.md`, `PLANS.md`,
  `docs/specs/`, and `docs/memory/`.
- Subagents (bounded evidence lanes and domain reviewers) live under
  `.claude/agents/*.md` and `.codex/agents/*.toml`. The current set includes
  `contract-review`, `feature-reviewer`, `flow-validator`, and
  `investigator`; add a new role only when a responsibility boundary
  deserves one.
- Repeatable workflows (skills) live under `.claude/skills/`, `.codex/skills/`,
  and the provider-neutral copy under `.agents/skills/`.

Rules:

- Treat agent roles as ownership boundaries, not personalities.
- `.agents/skills/` is the canonical shared skill library. In this project it
  is currently a symlink into an out-of-repo store (see DEC-006). When that
  changes to real copies, keep the `.claude/skills/` and `.codex/skills/`
  trees in sync in the same commit.
- Add a skill only when a workflow is repeated enough to deserve a stable
  checklist.
- Project-level skills already codify the canonical sequence and known
  gotchas for common operations: read the matching skill before adding a
  SIP endpoint, deploying to a VM, debugging registration, or rotating
  passwords.

## 5. Working Rules

- Read before acting, in the order of section 2.
- Preserve user changes. Never revert changes you did not make unless the
  operator explicitly asks for that exact action.
- Language rules:
  - All AI context and workflow content is always written in English: this
    file, `PLANS.md`, `TODO.md`, `DEBATE.md`, everything under `docs/`,
    `.claude/`, `.codex/`, and `.agents/`.
  - Source code is always written in English: identifiers, comments, log
    messages, and commit messages.
  - User-facing content (UI strings, API/user messages, templates, fixtures)
    may be in any language the product needs; write it with that language's
    proper characters (diacritics, accents, special letters). Never
    transliterate or force such text into ASCII.
- Character conventions for the English harness content above (enforced by
  the pre-commit hook on harness paths only): em and en dashes are banned
  (use `-` or `--`), emoji are banned, non-ASCII arrows are banned (use `->`
  or `=>`), typographic quotes and other non-ASCII punctuation are banned.
  Application source and user-facing content are not subject to this ASCII
  check. Harness paths that legitimately need non-ASCII content can be
  exempted in `.githooks/ascii-allowlist`.
- Keep secrets out of git. VM secrets live in `/etc/asterisk-lab/env`;
  host-local workflows may use ignored `.env` files or local secret stores.
  `.env.example` carries the shape with names or sentinel values, never real
  credentials. Runtime state and evidence belong under ignored `runtime/`.
- Agent memory is repo-tracked only (hard rule). Durable knowledge goes to
  `docs/memory/*`, never to harness-private storage.
- Spec naming boundary (hard rule): `specNN` tokens may appear only in
  `docs/`, the root workflow files, and the harness directories.
  They must never appear in application source, identifiers, config keys,
  service names, or runtime paths. The pre-commit hook enforces this.
- TODO tracking (hard rule): `TODO.md` and `docs/todo/*` are operator-owned.
  Agents may propose entries but must not add, close, or edit them without
  explicit operator approval.
- If a task conflicts with `docs/memory/decisions.md` or a governing
  contract, do not proceed silently. Report the conflict and propose an
  updated decision or contract.
- Root-cause first: prefer architectural fixes over band-aids; never hide a
  failure to make a check pass.
- Leave no repository change uncommitted at the end of a task.

## 6. Architecture Principles

- Templates are the source of truth for every rendered runtime config.
  `vms/asterisk/etc/asterisk/*.tmpl` renders into `/etc/asterisk`;
  `vms/sbc/etc/{opensips,rtpengine}/*.tmpl` into `/etc/opensips` and
  `/etc/rtpengine`; `vms/monitoring/` templates and companion scripts into
  `/etc/zabbix` and Grafana provisioning state. Never hand-edit a rendered
  file on a VM: re-running the matching installer will overwrite it.
- Installers are idempotent. Root `install.sh`, `vms/sbc/install.sh`,
  `vms/monitoring/install.sh`, `vms/asterisk/services/pipecat/install.sh`,
  and `vms/asterisk/services/dashboard/install.sh` must be safe to re-run
  on an already-configured box.
- Deploy payloads live under `/opt/asterisk-lab/current` on each VM. That
  directory is disposable rsync output, not a source repository.
- Secrets and per-host values live in `/etc/asterisk-lab/env` on VMs.
  Host-local `.env` files are only a local fallback. `.env.example` carries
  only names and non-secret defaults. `make deploy` never transports `.env`
  (see DEC-004 and DEC-007).
- Real VM IPs are DHCP-allocated and not fixed. Specs, scripts, and
  templates must not hardcode last-seen IPs. Read live values from
  `virsh net-dhcp-leases default` after boot, or from the target lab env.
- Rendered configs under `/etc/asterisk`, `/etc/opensips`,
  `/etc/rtpengine`, `/etc/zabbix`, and Grafana provisioning state are
  outputs, not sources.
- The SBC is a stateless proxy in the current design, not a
  topology-hiding B2BUA. The initial-INVITE branch must remain
  direction-aware so Asterisk-generated INVITEs (`Dial(PJSIP/<ext>)`
  B2BUA legs) fall through to their R-URI instead of being looped back
  to Asterisk (see DEC-005).
- The Pipecat voicebot lane (Soniox streaming STT/TTS, OpenAI LLM) is the
  single lane (see DEC-010; the former LiveKit lane and two-lane
  comparison mission are retired). Turn-end is owned by Soniox semantic
  endpoint detection, never by VAD silence thresholds; VAD is limited to
  the barge-in reflex. Shared model/cost policy lives under
  `vms/asterisk/services/common/`.
- The observability dashboard (`vms/asterisk/services/dashboard/`, spec02)
  is a read-only consumer of `/var/lib/voicebot/*.jsonl` and
  `/var/spool/asterisk/monitor/`. It never writes to those sinks and never
  calls a model provider. It must not import the writer-oriented default-path
  helpers in `vms/asterisk/services/common` (`trace_events.default_events_path()`,
  `usage.LOG_PATH`): those fall back based on *write* access, which is wrong
  for a reader running as `asterisk` on a root-owned directory (DEC-008).

## 7. Environment And Safety

- The lab runs across up to three VMs (Asterisk, SBC, monitoring) plus the
  host. Detect which VM you are on (by hostname or by the Makefile
  `VM` / `SBC_VM` / `MONITORING_VM` variable) before running host-scoped
  commands.
- Never delete production data. This rule cannot be overridden by any
  other instruction in this repository.
- Live production-scale deployment is not in scope; the lab is a
  reproducible development target. Treat any operator-designated
  production host as handoff-only unless the operator grants explicit,
  scoped approval.
- Verification commands (`make verify`, `make verify-sbc`,
  `make verify-monitoring`, `sudo asterisk -rx ...`, `sudo opensipsctl fifo ...`,
  `sudo sngrep -d any port 5060`, `journalctl -u <service>`) are always
  allowed. State-changing commands on live VMs require operator approval.
- The initial-INVITE routing rule in `vms/sbc/etc/opensips/opensips.cfg.tmpl` (DEC-005)
  is safety-critical for B2BUA scenarios; any change to that branch must
  be verified end-to-end before being merged.
- Live observation: on the SBC VM, `tail -f /var/log/syslog` shows OpenSIPS
  (`local0`) and rtpengine (`local1`) side-by-side; `journalctl -u opensips
  -u rtpengine-daemon` is the systemd-side equivalent. SIP capture:
  `sudo sngrep -d any port 5060` on any of host / SBC / Asterisk VM.
- SSH into a VM from the host: VM IPs are DHCP-allocated (see section 6),
  so look them up first with `sudo virsh net-dhcp-leases default` (the
  host sudo password is `SUDO_PASS` in the host-local `.env`, gitignored).
  SSH user on every VM is `deb`; its password is `SSH_PASS`, also read
  from `.env`. No secret value is written here or in any tracked file.

## 8. Done Criteria

Work is done only when all of these hold:

- The relevant `make verify` target passes on the affected VM, or the
  failure is explicitly reported. Targets are `make verify` (Asterisk),
  `make verify-sbc` (SBC), `make verify-monitoring` (monitoring),
  and `make verify-zabbix-agent` on monitored nodes.
- The governing spec's acceptance criteria are satisfied with real evidence.
- No secrets, customer data, or runtime artifacts (recordings,
  transcripts, `.rendered/`) are tracked by git.
- `PLANS.md` reflects the final state.
- `git status` is clean: every agent-made change is committed.
- If shell scripts changed, `shellcheck` passes (see `.github/workflows/`).
- If Python changed, `ruff check` passes on `infra/scripts/` and
  `vms/asterisk/services/`.

## 9. Commit Conventions

- English Conventional Commit style: `type(scope): summary` with types
  `feat`, `fix`, `docs`, `test`, `refactor`, `chore`.
- Set the agent identity before committing:
  - Codex: `git config user.name "Codex" && git config user.email "codex@asterisk-lab.local"`
  - Claude: `git config user.name "Claude" && git config user.email "claude@asterisk-lab.local"`
- Enable the repo hooks once per clone: `git config core.hooksPath .githooks`.
- Commit every agent-made repository change before finishing a task.

## 10. Spec and Plan Workflow

- Exactly one short root `PLANS.md` carries live state; rules live in
  `docs/runbooks/plan-rules.md`.
- Specs live under `docs/specs/specNN-topic.md`, created from
  `docs/templates/spec-template.md` and paired with a kickoff prompt under
  `docs/prompts/` from `docs/templates/spec-kickoff-prompt-template.md`.
- Small tasks skip specs entirely: track them through commits and
  `PLANS.md` updates.
- When a governing spec is complete, archive the current `PLANS.md`
  under `docs/archive/plan/YYYY-MM-DD-topic.md` and start a fresh
  `PLANS.md` from `docs/templates/PLANS.md`.
- Spec numbers are never reused. Completed specs are never deleted;
  superseded specs point to their replacement.
- Promote only proven, reusable findings into `docs/memory/*`. Decisions
  get `DEC-NNN` entries in `docs/memory/decisions.md` (Decision / Reason
  / Impact); numbers are never reused or renumbered.
