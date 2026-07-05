# Monitoring Domain Spec

The monitoring VM runs Zabbix 7.0 LTS, PostgreSQL, Apache-hosted Zabbix
frontend, Grafana, and the Grafana Zabbix plugin. Monitored nodes run
zabbix-agent2 with lab-specific UserParameters.

## Supported Behavior

- `monitoring/install.sh` provisions the monitoring VM idempotently.
- `monitoring/setup-zabbix-agent.sh` provisions Asterisk and SBC agents.
- Monitoring collects service status, Asterisk call/contact/recording metrics,
  OpenSIPS MI statistics, and rtpengine counters.
- Grafana is provisioned with Zabbix datasource and lab dashboards.

## Source Files

- `monitoring/install.sh`
- `monitoring/setup-zabbix-agent.sh`
- `monitoring/verify.sh`
- `monitoring/verify-agent.sh`
- `monitoring/*.tmpl`
- `monitoring/*metrics*`
- Grafana provisioning YAML/JSON files.
