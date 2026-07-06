# Agent Debate Files

This directory is the only approved location for Codex/Claude debate artifacts
created from the root `DEBATE.md` template.

## Rules

1. Keep the reusable template at repo root as `DEBATE.md`.
2. For each new debate, create `docs/debates/<topic-slug>/` and copy
   `DEBATE.md` to `docs/debates/<topic-slug>/transcript.md`.
3. Use a lowercase, ASCII, kebab-case topic slug, for example
   `docs/debates/stt-turn-endpointing/transcript.md`.
4. Do not create live debate copies next to the root `DEBATE.md`.
5. Do not commit raw transcript files. They may contain draft reasoning,
   operator notes, or sensitive context. `transcript.md` is ignored by git.
6. Track only sanitized final decision summaries at
   `docs/debates/<topic-slug>/summary.md` when the operator asks to preserve the
   outcome.
7. Every copied transcript file uses the v2 metadata protocol: `Talk-ID`,
   `Message-ID`, `Source`, `State`, and `Priority`.
8. `Talk-ID` is the lowercase kebab-case directory name. `Message-ID` is unique
   and formatted as `<source>-YYYYMMDD-HHMMSS[-n]`. `Source` is `operator`,
   `codex`, or `claude`. `Priority` is `important`, `status`, or `fyi`.
9. `State` is the state after the message and must match the final marker:
   `waiting_for_codex` -> `wait_for_codex`, `waiting_for_claude` ->
   `wait_for_claude`, `operator_needed` -> `operator_needed`,
   `discussion_done` -> `discussion_done`.
10. The controlling marker is the last control marker after the
   `## Debate Transcript` heading. Ignore example markers and code blocks.
11. When an agent is started with `/goal` for a copied transcript file, keep that
   `/goal` active until the transcript ends with `discussion_done`,
   `operator_needed`, or an explicit operator close instruction.
12. Do not mark the `/goal` complete while the last marker is `wait_for_codex`
   or `wait_for_claude`; the debate is still open.
13. The operator starts Codex and Claude in separate tmux sessions. Agents must
   not run `codex`, `codex exec`, `claude`, `claude exec`, tmux send commands,
   scripts, subprocesses, or tools to start, drive, or simulate the other agent.
14. When the last marker is for the other agent, the current agent must stop and
   wait for the real operator-managed agent response.
15. Waiting must be a real sleep/read loop: sleep briefly, read only the copied
   transcript file, check the latest marker, and repeat until the marker names
   the current agent or reaches a closing marker.
16. During a debate goal, agents may read repository files and ignored evidence
   for analysis, but must not change the repository. The only allowed write is
   appending the agent's own message to the copied transcript file.
17. During a debate goal, do not edit code/config/docs/tests, run formatters,
   tests, builds, service restarts, deploy commands, git staging, git commits,
   or cleanup commands.
18. Create or edit `summary.md` only after the raw transcript reaches
   `discussion_done`, or after the operator explicitly requests a summary from
   an `operator_needed` state.
19. A tracked `summary.md` must be sanitized: no raw transcript excerpts unless
   explicitly approved, no secrets, no phone numbers, no customer data, no
   recordings, no tokens, and no credentials.
20. Commit only this README, the root `DEBATE.md` template, `.gitignore`, and
   sanitized `summary.md` files.

`docs/debates/*/transcript.md` is ignored by git. Sanitized
`docs/debates/*/summary.md` files are tracked when created.
