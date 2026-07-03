# Common operations for the Asterisk lab.
# Three VMs are involved: Asterisk, the OpenSIPS SBC, and monitoring. Each has its own
# target host variable and its own install/verify/deploy/logs trio.
# Override the targets with `make VM=user@host <target>` for asterisk,
# or `make SBC_VM=user@host <target>` for the SBC.
# or `make MONITORING_VM=user@host <target>` for monitoring.
# Override the SSH command (e.g. for sshpass) with `make SSH="sshpass -e ssh" <target>`.
.PHONY: help install verify deploy logs install-sbc verify-sbc deploy-sbc logs-sbc install-monitoring verify-monitoring deploy-monitoring logs-monitoring install-zabbix-agent verify-zabbix-agent deploy-agent-asterisk deploy-agent-sbc clean

SHELL  := /bin/bash
VM     ?= deb@192.168.122.20
SBC_VM ?= deb@192.168.122.3
MONITORING_VM ?= deb@192.168.122.13
SSH    ?= ssh
RSYNC  ?= rsync
RSYNC_SSH ?= $(SSH)

# rsync exclusions for both deploy paths. .env is intentionally excluded so
# the lab .env on each VM (with SIP passwords / SBC_IP / ASTERISK_IP) is not
# overwritten by a host-side .env. Place .env manually on each target VM.
RSYNC_EXCLUDES := --exclude='.git/' --exclude='.env' --exclude='NOTES.md' --exclude='__pycache__/' --exclude='.rendered/'

help: ## Show this help
	@awk 'BEGIN{FS=":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ---- Asterisk VM targets --------------------------------------------------

install: ## Run install.sh + setup-transcriber.sh on this host (Asterisk)
	sudo ./install.sh
	sudo ./scripts/setup-transcriber.sh

verify: ## Smoke-check the Asterisk lab on this host
	sudo ./scripts/verify.sh

deploy: ## rsync repo to $(VM), then run install + setup-transcriber there
	$(RSYNC) -e "$(RSYNC_SSH)" -av --delete $(RSYNC_EXCLUDES) ./ $(VM):~/asterisk-lab/
	$(SSH) $(VM) 'cd ~/asterisk-lab && sudo ./install.sh && sudo ./scripts/setup-transcriber.sh'

logs: ## Tail asterisk + transcriber journals on $(VM)
	$(SSH) $(VM) 'sudo journalctl -u asterisk -u transcriber -f --no-pager'

# ---- SBC VM targets -------------------------------------------------------

install-sbc: ## Run sbc/install.sh on this host (OpenSIPS + rtpengine)
	sudo ./sbc/install.sh

verify-sbc: ## Smoke-check the SBC on this host
	sudo ./sbc/verify.sh

deploy-sbc: ## rsync repo to $(SBC_VM), then run sbc/install.sh there
	$(RSYNC) -e "$(RSYNC_SSH)" -av --delete $(RSYNC_EXCLUDES) ./ $(SBC_VM):~/asterisk-lab/
	$(SSH) $(SBC_VM) 'cd ~/asterisk-lab && sudo ./sbc/install.sh'

logs-sbc: ## Tail /var/log/syslog on $(SBC_VM) — opensips + rtpengine live
	$(SSH) $(SBC_VM) 'sudo tail -f /var/log/syslog'

# ---- Monitoring VM targets -----------------------------------------------

install-monitoring: ## Run monitoring/install.sh on this host (Zabbix + Grafana)
	sudo ./monitoring/install.sh

verify-monitoring: ## Smoke-check the monitoring stack on this host
	sudo ./monitoring/verify.sh

deploy-monitoring: ## rsync repo to $(MONITORING_VM), then run monitoring/install.sh there
	$(RSYNC) -e "$(RSYNC_SSH)" -av --delete $(RSYNC_EXCLUDES) ./ $(MONITORING_VM):~/asterisk-lab/
	$(SSH) $(MONITORING_VM) 'cd ~/asterisk-lab && sudo ./monitoring/install.sh'

logs-monitoring: ## Tail monitoring service journals on $(MONITORING_VM)
	$(SSH) $(MONITORING_VM) 'sudo journalctl -u zabbix-server -u zabbix-agent2 -u grafana-server -u apache2 -u postgresql -f --no-pager'

install-zabbix-agent: ## Run monitoring/setup-zabbix-agent.sh on this host
	sudo ./monitoring/setup-zabbix-agent.sh

verify-zabbix-agent: ## Smoke-check zabbix-agent2 on this host
	sudo ./monitoring/verify-agent.sh

deploy-agent-asterisk: ## rsync repo to $(VM), then install zabbix-agent2 there
	$(RSYNC) -e "$(RSYNC_SSH)" -av --delete $(RSYNC_EXCLUDES) ./ $(VM):~/asterisk-lab/
	$(SSH) $(VM) 'cd ~/asterisk-lab && sudo ./monitoring/setup-zabbix-agent.sh'

deploy-agent-sbc: ## rsync repo to $(SBC_VM), then install zabbix-agent2 there
	$(RSYNC) -e "$(RSYNC_SSH)" -av --delete $(RSYNC_EXCLUDES) ./ $(SBC_VM):~/asterisk-lab/
	$(SSH) $(SBC_VM) 'cd ~/asterisk-lab && sudo ./monitoring/setup-zabbix-agent.sh'

# ---- Voicebot stacks (LiveKit / Pipecat) — run on the Asterisk VM --------

install-voicebot-livekit: ## Provision the LiveKit voicebot stack on this host
	sudo -E ./services/livekit/install.sh

deploy-voicebot-livekit: ## rsync repo to $(VM), then provision LiveKit stack there
	$(RSYNC) -e "$(RSYNC_SSH)" -av --delete $(RSYNC_EXCLUDES) ./ $(VM):~/asterisk-lab/
	$(SSH) $(VM) 'cd ~/asterisk-lab && sudo -E ./services/livekit/install.sh'

logs-voicebot-livekit: ## Tail LiveKit stack container logs on $(VM)
	$(SSH) $(VM) 'sudo docker logs -f --tail=100 lk-agent lk-sip lk-server 2>&1'

gen-utterances: ## Generate test-caller WAVs via ElevenLabs (uses host .env)
	./services/test-caller/gen-utterances.sh

usage-summary: ## Print API spend summary from /var/lib/voicebot/usage.jsonl on $(VM)
	$(SSH) $(VM) 'python3 ~/asterisk-lab/services/common/usage_summary.py $(ARGS)'

# ---- shared ---------------------------------------------------------------

clean: ## Remove python bytecode caches
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
