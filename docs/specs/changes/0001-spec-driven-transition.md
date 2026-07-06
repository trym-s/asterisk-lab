# 0001: Spec-Driven Transition

## Intent

Move the repo from scattered operational memory to contract-first specs that
agents and humans can read before editing.

## Migration

1. Add spec index, global mission, environment, validation, and routing files.
2. Add domain specs for Asterisk, SBC, monitoring, and voicebot.
3. Add initial `VAL-*` contracts that describe current expected behavior.
4. Add `.claude` and `.codex` pointers so agents can route through specs.
5. Update `AGENTS.md` to make specs the acceptance source.

## Deferred Work

- Trim duplicate acceptance language from README and PROCESS.
- Add automated lint for contract file shape.
- Collect fresh runtime evidence once VMs are booted and `.env` files are
  present on their target hosts.
