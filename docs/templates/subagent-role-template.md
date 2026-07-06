# Subagent Role Template

Domain subagent roles are defined per provider as a pair: one Markdown file
for Claude Code and one TOML file for Codex, carrying the same body. Add a
role only when a responsibility boundary deserves one. Keep the body focused
on ownership, required reading, rules, and the expected final output.

## Claude Code: `.claude/agents/<role-name>.md` (kebab-case name)

```markdown
---
name: role-name
description: One sentence saying when to use this role.
model: inherit
---
You are the <role> for this repository.
Own:
- <what this role is responsible for>
Read first:
- AGENTS.md, PLANS.md, and the relevant docs/memory/* files.
Rules:
- <boundaries: what this role must and must not do>
Return: changed files, decisions made, validation performed, and unresolved
assumptions.
```

## Codex: `.codex/agents/<role_name>.toml` (snake_case name)

```toml
name = "role_name"
description = "One sentence saying when to use this role."
model_reasoning_effort = "medium"
developer_instructions = """
<same body as the Claude version>
"""
```

Keep the two files in sync when the role changes.
