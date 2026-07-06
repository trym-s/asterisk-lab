# Monitoring Decisions

## Zabbix 7.0 LTS

The monitoring stack targets Zabbix 7.0 LTS for stability and predictable
package behavior.

## Agent Helpers Own Privileged Metrics

Asterisk metrics use a sudoers rule for `asterisk -rx`. OpenSIPS metrics use
MI FIFO JSON-RPC. RTPengine metrics use the CLI listener on `127.0.0.1:9900`.

## Grafana Is Provisioned From Files

Grafana datasource and dashboards are provisioned by repo files so a fresh VM
can reproduce the operator view.
