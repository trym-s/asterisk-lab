# Agent Routing

Use this table before changing files or running operational commands.

| User request | Domain spec | Also read |
| --- | --- | --- |
| Add/remove SIP endpoint | `domains/asterisk/` | `.claude/skills/adding-sip-endpoint/SKILL.md` |
| Asterisk install, dialplan, recordings, transcriber | `domains/asterisk/` | `global/env.md` |
| SIP registration failure | `domains/asterisk/`, `domains/sbc/` | `.claude/skills/debugging-sip-registration/SKILL.md` |
| Deploy Asterisk VM | `domains/asterisk/` | `.claude/skills/deploying-to-vm/SKILL.md` |
| OpenSIPS, rtpengine, media relay | `domains/sbc/` | `global/env.md` |
| Rotate SIP password | `domains/asterisk/` | `.claude/skills/rotating-passwords/SKILL.md` |
| Zabbix, Grafana, metrics, dashboards | `domains/monitoring/` | `global/env.md` |
| LiveKit, Pipecat, voicebot agents | `domains/voicebot/` | `domains/voicebot/benchmark.md` |
| Voicebot trace, observer UI, reports, model/cost policy | `domains/voicebot/` | `domains/voicebot/contracts/VAL-VOICEBOT-*.md` |
| Benchmark, utterance suite, or audio integrity | `domains/voicebot/` | `domains/voicebot/benchmark.md` |
| Spec architecture or contracts | `global/` and affected domain | `global/validation.md` |

If a request spans domains, read every affected domain and create or update a
cross-domain contract instead of hiding the behavior in one runbook.
