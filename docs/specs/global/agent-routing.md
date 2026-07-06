# Agent Routing

Use this table before changing files or running operational commands.

| User request | Domain spec | Also read |
| --- | --- | --- |
| Add/remove SIP endpoint | `docs/specs/domains/asterisk/` | `.claude/skills/adding-sip-endpoint/SKILL.md` |
| Asterisk install, dialplan, recordings, transcriber | `docs/specs/domains/asterisk/` | `docs/specs/global/env.md` |
| SIP registration failure | `docs/specs/domains/asterisk/`, `docs/specs/domains/sbc/` | `.claude/skills/debugging-sip-registration/SKILL.md` |
| Deploy Asterisk VM | `docs/specs/domains/asterisk/` | `.claude/skills/deploying-to-vm/SKILL.md` |
| OpenSIPS, rtpengine, media relay | `docs/specs/domains/sbc/` | `docs/specs/global/env.md` |
| Rotate SIP password | `docs/specs/domains/asterisk/` | `.claude/skills/rotating-passwords/SKILL.md` |
| Zabbix, Grafana, metrics, dashboards | `docs/specs/domains/monitoring/` | `docs/specs/global/env.md` |
| LiveKit, Pipecat, voicebot agents | `docs/specs/domains/voicebot/` | `docs/specs/domains/voicebot/benchmark.md` |
| Voicebot trace, observer UI, reports, model/cost policy | `docs/specs/domains/voicebot/` | `docs/specs/domains/voicebot/contracts/VAL-VOICEBOT-*.md` |
| Benchmark, utterance suite, or audio integrity | `docs/specs/domains/voicebot/` | `docs/specs/domains/voicebot/benchmark.md` |
| Spec architecture or contracts | `docs/specs/global/` and affected domain | `docs/specs/global/validation.md` |

If a request spans domains, read every affected domain and create or update a
cross-domain contract instead of hiding the behavior in one runbook.
