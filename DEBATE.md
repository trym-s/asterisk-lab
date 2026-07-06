# DEBATE.md - Agent Debate Template v3

Commit this template. Do not commit live transcript copies created from it.

Use this file when the operator wants Codex and Claude to discuss one topic
through a shared markdown transcript. Create
`docs/debates/<topic-slug>/`, copy this file to
`docs/debates/<topic-slug>/transcript.md`, fill the topic block, then let each
agent append messages in turn until there is a clear decision, disagreement, or
operator question.

The root `DEBATE.md` file is the tracked reusable template. Raw transcript files
at `docs/debates/<topic-slug>/transcript.md` are ignored by git. Sanitized final
decision summaries at `docs/debates/<topic-slug>/summary.md` are tracked when
the operator explicitly asks to preserve the outcome.

## Operator Setup

- Talk-ID: `<topic-slug>`
- Topic:
- Transcript: `docs/debates/<topic-slug>/transcript.md`
- Summary: `docs/debates/<topic-slug>/summary.md`
- State: `waiting_for_codex`
- Goal:
- Decision needed:
- Constraints:
- Evidence or files to inspect:
- Output expected from the agents:
- Stop condition:

## Turn Rules

1. Append only. Do not rewrite another agent's message.
2. Keep each message short, concrete, and tied to the topic.
3. Cite files, commands, or evidence when making factual claims.
4. Separate facts, assumptions, risks, and recommendations.
5. If blocked, ask one clear operator question and use `operator_needed`.
6. Do not include secrets, customer data, live tokens, phone numbers, recordings,
   or raw transcripts unless the operator explicitly approved that specific use.
7. The controlling marker is the LAST control marker that appears AFTER the
   `## Debate Transcript` heading. Example markers inside code blocks and
   `State:`/metadata lines are never treated as the live turn marker.
8. Every new operator or agent message must use the v2 metadata fields:
   `Talk-ID`, `Message-ID`, `Source`, `State`, and `Priority`.
9. Append messages ONLY to the end of the real transcript under
   `## Debate Transcript`, below the append anchor comment. Never write into
   `## Message Format`, `## Starter Prompt`, or any other example/template block.
10. If a message's `State:` field and its trailing control marker disagree, the
    trailing control marker wins.

## Metadata Protocol

- `Talk-ID`: stable lowercase ASCII kebab-case identifier. It must match the
  `docs/debates/<topic-slug>/` directory name, for example
  `stt-turn-endpointing`.
- `Message-ID`: unique per message, formatted as
  `<source>-YYYYMMDD-HHMMSS[-n]`, for example `codex-20260626-142001`.
- `Source`: exactly one of `operator`, `codex`, or `claude`.
- `State`: the state after this message is appended. Use exactly one of
  `waiting_for_codex`, `waiting_for_claude`, `operator_needed`, or
  `discussion_done`.
- `Priority`: exactly one of `important`, `status`, or `fyi`.

The final control marker must match `State`:

- `State: waiting_for_codex` ends with `wait_for_codex`.
- `State: waiting_for_claude` ends with `wait_for_claude`.
- `State: operator_needed` ends with `operator_needed`.
- `State: discussion_done` ends with `discussion_done`.

Do not reuse a `Message-ID`. If an agent sees that its next message would repeat
an existing `Message-ID`, it must generate a new one before appending.

## Agent Process Boundary

The operator starts the Codex and Claude agents in separate tmux sessions. Agents
must not start, script, drive, or simulate the other agent.

Forbidden actions:

- Do not run `codex`, `codex exec`, `claude`, `claude exec`, or equivalent
  commands to produce the other agent's response.
- Do not use shell scripts, tmux commands, subprocesses, or tools to send input
  to the other agent's session.
- Do not write a message on behalf of the other agent.

When the last marker is for the other agent, stop after writing your marker and
wait for the operator-managed tmux session to append that agent's real response.
Only resume when the latest marker explicitly names your agent.

While waiting, use a real sleep/read loop:

1. Sleep briefly.
2. Read only the copied transcript file.
3. Check the latest control marker.
4. Repeat until the marker names your agent, `operator_needed`, or
   `discussion_done`.

Do not do any other work while waiting.

Before appending, re-read the end of the file and confirm the latest control
marker still names you. If it changed while you were preparing your message,
return to the wait loop instead of appending (avoids concurrent-write
clobbering).

## Repository Access During Debate

Debate goals are read-only analysis work. Agents may read repository files,
ignored evidence, and the copied transcript file to support their argument, but
they must not change the repository.

Allowed write:

- Append the agent's own message to the copied transcript file only.

Forbidden during a debate goal:

- Do not edit code, configs, docs, tests, deploy files, or runtime files.
- Do not run formatters, tests, builds, service restarts, deploy commands, git
  staging, git commits, or cleanup commands.
- Do not create files other than the operator-requested copied transcript file.
- Do not modify the copied transcript file except by appending your own message.
- Do not create or edit `summary.md` during the debate unless the operator starts
  a separate summarization task after the transcript reaches a closing marker.

## Goal Lifecycle

When an agent is started with a `/goal` that references a copied transcript file,
the agent must keep that `/goal` active until the file reaches a closing marker.

Allowed closing markers:

- `discussion_done` means the debate is complete and the `/goal` can be marked
  complete.
- `operator_needed` means both agents must stop and wait for the operator; the
  `/goal` must not be marked complete unless the operator explicitly closes it.

Do not mark the `/goal` complete while the last marker is `wait_for_codex` or
`wait_for_claude`. Those markers mean the debate is still open and the other
agent needs to respond.

## Control Markers

Use exactly one marker as the final line of each agent message.

- `wait_for_codex` means Claude has finished and Codex should respond next.
- `wait_for_claude` means Codex has finished and Claude should respond next.
- `operator_needed` means both agents should stop until the operator responds.
- `discussion_done` means the agents reached a final position.

Do not write before your marker appears as the last control marker in the file.

## Summary Files

`summary.md` is the tracked final decision artifact for a completed debate. It
must be sanitized and concise:

- No raw transcript excerpts unless explicitly approved by the operator.
- No secrets, phone numbers, customer data, recordings, tokens, or credentials.
- Include the final decision, rejected alternatives, implementation/test plan,
  and links to any spec or follow-up documents.
- Create or update it only after `transcript.md` ends with `discussion_done` or
  after the operator explicitly requests a summary from an `operator_needed`
  state.

## Message Format

```text
YYYY-MM-DD HH:MM <OpenAI Codex>
Talk-ID: <topic-slug>
Message-ID: codex-YYYYMMDD-HHMMSS
Source: codex
State: waiting_for_claude
Priority: important
Position:
Evidence:
Risks:
Recommendation:
<wait_for_claude>
```

```text
YYYY-MM-DD HH:MM <Claude Code>
Talk-ID: <topic-slug>
Message-ID: claude-YYYYMMDD-HHMMSS
Source: claude
State: waiting_for_codex
Priority: important
Position:
Evidence:
Risks:
Recommendation:
<wait_for_codex>
```

Markers in the two examples above are shown in angle brackets so they are never
parsed as live control markers. In a real message emit the bare token only
(`wait_for_claude` or `wait_for_codex`) as the final line; see "Control Markers".

## Starter Prompt

Operator can paste this into the first message:

```text
Talk-ID: <topic-slug>
Topic: <topic>
Transcript: docs/debates/<topic-slug>/transcript.md
Summary: docs/debates/<topic-slug>/summary.md
State: waiting_for_codex
Goal: Discuss the topic until both agents either agree on a recommendation or
identify the exact unresolved disagreement.

Create `docs/debates/<topic-slug>/`, copy `DEBATE.md` to the Transcript path
above, then start. Codex starts. After reading the required setup and evidence,
Codex appends the first real debate message and ends with `wait_for_claude` so
Claude does not answer before Codex has taken the first turn. Keep the `/goal`
active until the copied transcript file ends with `discussion_done`,
`operator_needed`, or an explicit operator close instruction.
```

## Debate Transcript

YYYY-MM-DD HH:MM <Operator>
Talk-ID: <topic-slug>
Message-ID: operator-YYYYMMDD-HHMMSS
Source: operator
State: waiting_for_codex
Priority: important
Topic:
Transcript: docs/debates/<topic-slug>/transcript.md
Summary: docs/debates/<topic-slug>/summary.md
Goal:
Decision needed:
Constraints:
Evidence or files to inspect:
Output expected:
Stop condition:

<wait_for_codex>

<!-- APPEND NEW MESSAGES BELOW THIS LINE - append only here, never into example/template blocks above -->
