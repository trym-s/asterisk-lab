# Global Mission

Build and maintain a reproducible Debian 13 / Ubuntu 26.04 lab with:

- an Asterisk 22 LTS PBX;
- an optional OpenSIPS 3.6 LTS SBC with rtpengine;
- an optional monitoring VM running Zabbix 7.0 LTS and Grafana;
- optional voicebot lanes for LiveKit and Pipecat comparison;
- host-side baresip and test-caller workflows for repeatable validation.

The lab must be reproducible from a fresh clone, idempotent on re-run, and
validated through explicit contracts rather than unstated operator memory.

## Actors

- Operator: provisions VMs, places per-VM `.env`, runs Makefile targets.
- Softphone user: registers baresip and places SIP calls.
- Agent: edits templates/scripts/specs and follows contracts before changes.
- Validator: collects evidence from real CLI, SIP, logs, Docker, and services.

## Boundaries

- Secrets and real IPs live in target `.env` files, not git.
- Rendered files under `/etc/asterisk`, `/etc/opensips`, `/etc/rtpengine`,
  `/etc/zabbix`, and Grafana provisioning state are outputs, not sources.
- Templates, install scripts, specs, and contracts in this repo are sources.
- VMs may receive dynamic DHCP leases; specs must not hardcode last-seen IPs.

## Non-Goals

- This repo is not a production HA deployment.
- The SBC is a stateless proxy in the current design, not topology-hiding B2BUA.
- Voicebot lanes are comparison surfaces; parity must be proven before a lane is
  treated as stable.
