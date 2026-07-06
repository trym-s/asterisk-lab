# Monitoring Runbook

## Monitoring VM `.env`

```text
MONITORING_IP=<monitoring-vm-ip>
ZABBIX_DB_PASSWORD=<secret>
ZABBIX_VERSION=7.0
```

## Deploy Monitoring VM

```bash
make MONITORING_VM=deb@<monitoring-ip> deploy-monitoring
ssh deb@<monitoring-ip> 'cd ~/asterisk-lab && sudo ./monitoring/verify.sh'
```

## Deploy Agents

Each monitored node needs `MONITORING_IP` in its own `.env`.

```bash
make VM=deb@<asterisk-ip> deploy-agent-asterisk
make SBC_VM=deb@<sbc-ip> deploy-agent-sbc
```

Then on each node:

```bash
cd ~/asterisk-lab
sudo ./monitoring/verify-agent.sh
```
