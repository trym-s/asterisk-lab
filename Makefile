# Common operations for the Asterisk lab.
# Two VMs are involved: Asterisk and the OpenSIPS SBC. Each has its own
# target host variable and its own install/verify/deploy/logs trio.
# Override the targets with `make VM=user@host <target>` for asterisk,
# or `make SBC_VM=user@host <target>` for the SBC.
# Override the SSH command (e.g. for sshpass) with `make SSH="sshpass -e ssh" <target>`.
.PHONY: help install verify deploy logs install-sbc verify-sbc deploy-sbc logs-sbc clean

SHELL  := /bin/bash
VM     ?= deb@192.168.122.20
SBC_VM ?= deb@192.168.122.3
SSH    ?= ssh
RSYNC  ?= rsync

# rsync exclusions for both deploy paths. .env is intentionally excluded so
# the lab .env on each VM (with SIP passwords / SBC_IP / ASTERISK_IP) is not
# overwritten by a host-side .env. Place .env manually on each target VM.
RSYNC_EXCLUDES := --exclude='.git/' --exclude='.env' --exclude='NOTES.md' --exclude='__pycache__/'

help: ## Show this help
	@awk 'BEGIN{FS=":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ---- Asterisk VM targets --------------------------------------------------

install: ## Run install.sh + setup-transcriber.sh on this host (Asterisk)
	sudo ./install.sh
	sudo ./scripts/setup-transcriber.sh

verify: ## Smoke-check the Asterisk lab on this host
	sudo ./scripts/verify.sh

deploy: ## rsync repo to $(VM), then run install + setup-transcriber there
	$(RSYNC) -av --delete $(RSYNC_EXCLUDES) ./ $(VM):~/asterisk-lab/
	$(SSH) $(VM) 'cd ~/asterisk-lab && sudo ./install.sh && sudo ./scripts/setup-transcriber.sh'

logs: ## Tail asterisk + transcriber journals on $(VM)
	$(SSH) $(VM) 'sudo journalctl -u asterisk -u transcriber -f --no-pager'

# ---- SBC VM targets -------------------------------------------------------

install-sbc: ## Run sbc/install.sh on this host (OpenSIPS + rtpengine)
	sudo ./sbc/install.sh

verify-sbc: ## Smoke-check the SBC on this host
	sudo ./sbc/verify.sh

deploy-sbc: ## rsync repo to $(SBC_VM), then run sbc/install.sh there
	$(RSYNC) -av --delete $(RSYNC_EXCLUDES) ./ $(SBC_VM):~/asterisk-lab/
	$(SSH) $(SBC_VM) 'cd ~/asterisk-lab && sudo ./sbc/install.sh'

logs-sbc: ## Tail /var/log/syslog on $(SBC_VM) — opensips + rtpengine live
	$(SSH) $(SBC_VM) 'sudo tail -f /var/log/syslog'

# ---- shared ---------------------------------------------------------------

clean: ## Remove python bytecode caches
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
