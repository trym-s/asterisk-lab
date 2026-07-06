# VAL-MONITORING-001: Monitoring stack and agents verify

Surface: CLI, service, and monitoring API.
Needs: Monitoring VM `.env`, running monitored nodes, and `MONITORING_IP` set on
each monitored node.
Behavior: Monitoring install verifies locally, zabbix-agent2 verifies on each
monitored node, and Zabbix/Grafana expose the expected lab metrics and
dashboards.
Evidence: Validator records `monitoring/verify.sh`, `verify-agent.sh` on
Asterisk and SBC, representative `zabbix_get` values, and Zabbix/Grafana HTTP
reachability.
Fail: Failed verifier, missing agent metric, missing plugin/datasource, or
unreachable UI means failure.
