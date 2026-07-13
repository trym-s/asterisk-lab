# Common operations for the Asterisk lab.
# Three VMs are involved: Asterisk, the OpenSIPS SBC, and monitoring. Each has its own
# target host variable and its own install/verify/deploy/logs trio.
# Override the targets with `make VM=user@host <target>` for asterisk,
# or `make SBC_VM=user@host <target>` for the SBC.
# or `make MONITORING_VM=user@host <target>` for monitoring.
# Override the SSH command (e.g. for sshpass) with `make SSH="sshpass -e ssh" <target>`.
.PHONY: help install verify deploy logs install-sbc verify-sbc deploy-sbc logs-sbc install-monitoring verify-monitoring deploy-monitoring logs-monitoring install-zabbix-agent verify-zabbix-agent deploy-agent-asterisk deploy-agent-sbc install-voicebot-dashboard verify-voicebot-dashboard deploy-voicebot-dashboard logs-voicebot-dashboard clean

SHELL  := /bin/bash
VM     ?= deb@192.168.122.247
SBC_VM ?= deb@192.168.122.3
MONITORING_VM ?= deb@192.168.122.13
VIRSH             ?= sudo virsh
ASTERISK_DOMAIN   ?= asterisk-deb13-cloudinit
SBC_DOMAIN        ?= opensips-sbc-deb13-cloudinit
MONITORING_DOMAIN ?= monitoring-deb13-cloudinit
SSH    ?= ssh
RSYNC  ?= rsync
RSYNC_SSH ?= $(SSH)
DEPLOY_DIR ?= /opt/asterisk-lab/current
LAB_ENV ?= /etc/asterisk-lab/env
DEPLOY_REVISION ?= $(shell git rev-parse --short=12 HEAD 2>/dev/null || echo unknown)$(shell test -z "$$(git status --porcelain 2>/dev/null)" || echo -dirty)

# VMs receive role payloads under /opt. Secrets stay in /etc/asterisk-lab/env.
RSYNC_TO_VM := $(RSYNC) -e "$(RSYNC_SSH)" -avc --delete --delete-excluded --rsync-path="sudo rsync"
REMOTE_PREP = sudo install -d -m 0755 $(DEPLOY_DIR) /etc/asterisk-lab
REMOTE_ENV_MIGRATE = if [ ! -f $(LAB_ENV) ] && [ -f ~/asterisk-lab/.env ]; then sudo install -m 0600 -o root -g root ~/asterisk-lab/.env $(LAB_ENV); fi
REMOTE_STAMP = printf "%s\n" "$(DEPLOY_REVISION)" | sudo tee $(DEPLOY_DIR)/.deploy-revision >/dev/null

help: ## Show this help
	@awk 'BEGIN{FS=":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ---- Asterisk VM targets --------------------------------------------------

install: ## Run install.sh + setup-transcriber.sh on this host (Asterisk)
	sudo ./install.sh
	sudo ./infra/scripts/setup-transcriber.sh

verify: ## Smoke-check the Asterisk lab on this host
	sudo ./infra/scripts/verify.sh

deploy: ## rsync Asterisk payload to $(VM), then run install + setup-transcriber there
	$(SSH) $(VM) '$(REMOTE_PREP)'
	$(RSYNC_TO_VM) --filter='merge infra/deploy/asterisk.filter' ./ $(VM):$(DEPLOY_DIR)/
	$(SSH) $(VM) '$(REMOTE_ENV_MIGRATE)'
	$(SSH) $(VM) '$(REMOTE_STAMP)'
	$(SSH) $(VM) 'cd $(DEPLOY_DIR) && sudo ASTERISK_LAB_ENV=$(LAB_ENV) ./install.sh && sudo ASTERISK_LAB_ENV=$(LAB_ENV) ./infra/scripts/setup-transcriber.sh'

logs: ## Tail asterisk + transcriber journals on $(VM)
	$(SSH) $(VM) 'sudo journalctl -u asterisk -u transcriber -f --no-pager'

# ---- SBC VM targets -------------------------------------------------------

install-sbc: ## Run sbc/install.sh on this host (OpenSIPS + rtpengine)
	sudo ./vms/sbc/install.sh

verify-sbc: ## Smoke-check the SBC on this host
	sudo ./vms/sbc/verify.sh

deploy-sbc: ## rsync SBC payload to $(SBC_VM), then run sbc/install.sh there
	$(SSH) $(SBC_VM) '$(REMOTE_PREP)'
	$(RSYNC_TO_VM) --filter='merge infra/deploy/sbc.filter' ./ $(SBC_VM):$(DEPLOY_DIR)/
	$(SSH) $(SBC_VM) '$(REMOTE_ENV_MIGRATE)'
	$(SSH) $(SBC_VM) '$(REMOTE_STAMP)'
	$(SSH) $(SBC_VM) 'cd $(DEPLOY_DIR) && sudo ASTERISK_LAB_ENV=$(LAB_ENV) ./vms/sbc/install.sh'

logs-sbc: ## Tail /var/log/syslog on $(SBC_VM) — opensips + rtpengine live
	$(SSH) $(SBC_VM) 'sudo tail -f /var/log/syslog'

# ---- Monitoring VM targets -----------------------------------------------

install-monitoring: ## Run monitoring/install.sh on this host (Zabbix + Grafana)
	sudo ./vms/monitoring/install.sh

verify-monitoring: ## Smoke-check the monitoring stack on this host
	sudo ./vms/monitoring/verify.sh

deploy-monitoring: ## rsync monitoring payload to $(MONITORING_VM), then run monitoring/install.sh there
	$(SSH) $(MONITORING_VM) '$(REMOTE_PREP)'
	$(RSYNC_TO_VM) --filter='merge infra/deploy/monitoring.filter' ./ $(MONITORING_VM):$(DEPLOY_DIR)/
	$(SSH) $(MONITORING_VM) '$(REMOTE_ENV_MIGRATE)'
	$(SSH) $(MONITORING_VM) '$(REMOTE_STAMP)'
	$(SSH) $(MONITORING_VM) 'cd $(DEPLOY_DIR) && sudo ASTERISK_LAB_ENV=$(LAB_ENV) ./vms/monitoring/install.sh'

logs-monitoring: ## Tail monitoring service journals on $(MONITORING_VM)
	$(SSH) $(MONITORING_VM) 'sudo journalctl -u zabbix-server -u zabbix-agent2 -u grafana-server -u apache2 -u postgresql -f --no-pager'

install-zabbix-agent: ## Run monitoring/setup-zabbix-agent.sh on this host
	sudo ./vms/monitoring/setup-zabbix-agent.sh

verify-zabbix-agent: ## Smoke-check zabbix-agent2 on this host
	sudo ./vms/monitoring/verify-agent.sh

deploy-agent-asterisk: ## rsync Asterisk payload to $(VM), then install zabbix-agent2 there
	$(SSH) $(VM) '$(REMOTE_PREP)'
	$(RSYNC_TO_VM) --filter='merge infra/deploy/asterisk.filter' ./ $(VM):$(DEPLOY_DIR)/
	$(SSH) $(VM) '$(REMOTE_ENV_MIGRATE)'
	$(SSH) $(VM) '$(REMOTE_STAMP)'
	$(SSH) $(VM) 'cd $(DEPLOY_DIR) && sudo ASTERISK_LAB_ENV=$(LAB_ENV) ./vms/monitoring/setup-zabbix-agent.sh'

deploy-agent-sbc: ## rsync SBC payload to $(SBC_VM), then install zabbix-agent2 there
	$(SSH) $(SBC_VM) '$(REMOTE_PREP)'
	$(RSYNC_TO_VM) --filter='merge infra/deploy/sbc.filter' ./ $(SBC_VM):$(DEPLOY_DIR)/
	$(SSH) $(SBC_VM) '$(REMOTE_ENV_MIGRATE)'
	$(SSH) $(SBC_VM) '$(REMOTE_STAMP)'
	$(SSH) $(SBC_VM) 'cd $(DEPLOY_DIR) && sudo ASTERISK_LAB_ENV=$(LAB_ENV) ./vms/monitoring/setup-zabbix-agent.sh'

# ---- Voicebot stack (Pipecat) — runs on the Asterisk VM ------------------

install-voicebot-pipecat: ## Provision the Pipecat voicebot stack on this host
	sudo -E ./vms/asterisk/services/pipecat/install.sh

deploy-voicebot-pipecat: ## rsync Asterisk payload to $(VM), then provision Pipecat stack there
	$(SSH) $(VM) '$(REMOTE_PREP)'
	$(RSYNC_TO_VM) --filter='merge infra/deploy/asterisk.filter' ./ $(VM):$(DEPLOY_DIR)/
	$(SSH) $(VM) '$(REMOTE_ENV_MIGRATE)'
	$(SSH) $(VM) '$(REMOTE_STAMP)'
	$(SSH) $(VM) 'cd $(DEPLOY_DIR) && sudo ASTERISK_LAB_ENV=$(LAB_ENV) VOICEBOT_REPO_REVISION="$$(cat .deploy-revision 2>/dev/null || echo unknown)" ./vms/asterisk/services/pipecat/install.sh'

logs-voicebot-pipecat: ## Tail Pipecat agent logs on $(VM)
	$(SSH) $(VM) 'sudo docker logs -f --tail=100 pc-agent 2>&1'

install-voicebot-dashboard: ## Provision the read-only observability dashboard on this host
	sudo -E ./vms/asterisk/services/dashboard/install.sh

verify-voicebot-dashboard: ## Smoke-check the observability dashboard on this host
	sudo ./vms/asterisk/services/dashboard/verify.sh

deploy-voicebot-dashboard: ## rsync Asterisk payload to $(VM), then provision the dashboard there
	$(SSH) $(VM) '$(REMOTE_PREP)'
	$(RSYNC_TO_VM) --filter='merge infra/deploy/asterisk.filter' ./ $(VM):$(DEPLOY_DIR)/
	$(SSH) $(VM) '$(REMOTE_ENV_MIGRATE)'
	$(SSH) $(VM) '$(REMOTE_STAMP)'
	$(SSH) $(VM) 'cd $(DEPLOY_DIR) && sudo ASTERISK_LAB_ENV=$(LAB_ENV) ./vms/asterisk/services/dashboard/install.sh'

logs-voicebot-dashboard: ## Tail dashboard service logs on $(VM)
	$(SSH) $(VM) 'sudo journalctl -u voicebot-dashboard -f --no-pager'

gen-utterances: ## Generate test-caller WAVs via ElevenLabs (uses host .env)
	./vms/asterisk/services/test-caller/gen-utterances.sh

usage-summary: ## Print API spend summary from /var/lib/voicebot/usage.jsonl on $(VM)
	$(SSH) $(VM) 'python3 $(DEPLOY_DIR)/vms/asterisk/services/common/usage_summary.py $(ARGS)'

# ---- VM Management (virsh) targets ----------------------------------------

.PHONY: vms ips up-ast down-ast up-sbc down-sbc up-mon down-mon vms-up vms_up vms-down vms_down lab-provision

lab-provision: ## Create (or start) and SSH-check all three lab VMs from scratch (idempotent)
	sudo ./infra/libvirt/create-lab-vms.sh

vms: ## List all local libvirt VMs with state and DHCP-lease IP
	@$(VIRSH) list --all --name | while read -r dom; do \
		[ -n "$$dom" ] || continue; \
		state=$$($(VIRSH) domstate "$$dom" 2>/dev/null); \
		ip=$$($(VIRSH) domifaddr "$$dom" --source lease 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | head -1); \
		printf '%-32s %-12s %s\n' "$$dom" "$$state" "$${ip:-<no lease>}"; \
	done

ips: ## Show DHCP leases (active VM IPs)
	$(VIRSH) net-dhcp-leases default

up-ast: ## Start the Asterisk VM
	$(VIRSH) start $(ASTERISK_DOMAIN)

down-ast: ## Gracefully shutdown the Asterisk VM
	$(VIRSH) shutdown $(ASTERISK_DOMAIN)

up-sbc: ## Start the SBC VM
	$(VIRSH) start $(SBC_DOMAIN)

down-sbc: ## Gracefully shutdown the SBC VM
	$(VIRSH) shutdown $(SBC_DOMAIN)

up-mon: ## Start the Monitoring VM
	$(VIRSH) start $(MONITORING_DOMAIN)

down-mon: ## Gracefully shutdown the Monitoring VM
	$(VIRSH) shutdown $(MONITORING_DOMAIN)

vms-up: ## Start all three VMs (Asterisk, SBC, Monitoring)
	@running_vms=$$($(VIRSH) list --name --state-running); \
	for dom in $(ASTERISK_DOMAIN) $(SBC_DOMAIN) $(MONITORING_DOMAIN); do \
		if echo "$$running_vms" | grep -q "^$$dom$$"; then \
			echo "VM $$dom is already running"; \
		else \
			echo "Starting VM: $$dom"; \
			$(VIRSH) start $$dom; \
		fi; \
	done

vms_up: vms-up

vms-down: ## Gracefully shutdown all three VMs
	@running_vms=$$($(VIRSH) list --name --state-running); \
	for dom in $(ASTERISK_DOMAIN) $(SBC_DOMAIN) $(MONITORING_DOMAIN); do \
		if echo "$$running_vms" | grep -q "^$$dom$$"; then \
			echo "Stopping VM: $$dom"; \
			$(VIRSH) shutdown $$dom; \
		else \
			echo "VM $$dom is not running"; \
		fi; \
	done

vms_down: vms-down

# ---- shared ---------------------------------------------------------------

clean: ## Remove python bytecode caches
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
