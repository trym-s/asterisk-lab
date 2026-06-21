# Common operations for the Asterisk lab.
# Override the target VM with `make VM=user@host <target>`.
# Override the SSH command (e.g. for sshpass) with `make SSH="sshpass -e ssh" <target>`.
.PHONY: help install verify deploy logs clean

SHELL := /bin/bash
VM    ?= deb@192.168.122.20
SSH   ?= ssh
RSYNC ?= rsync

help: ## Show this help
	@awk 'BEGIN{FS=":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Run install.sh + setup-transcriber.sh on this host
	sudo ./install.sh
	sudo ./scripts/setup-transcriber.sh

verify: ## Smoke-check the lab on this host
	sudo ./scripts/verify.sh

deploy: ## rsync repo to $(VM), then run install + setup-transcriber there
	$(RSYNC) -av --delete \
	  --exclude='.git/' --exclude='.env' --exclude='NOTES.md' \
	  --exclude='__pycache__/' \
	  ./ $(VM):~/asterisk-lab/
	$(SSH) $(VM) 'cd ~/asterisk-lab && sudo ./install.sh && sudo ./scripts/setup-transcriber.sh'

logs: ## Tail asterisk + transcriber journals on $(VM)
	$(SSH) $(VM) 'sudo journalctl -u asterisk -u transcriber -f --no-pager'

clean: ## Remove python bytecode caches
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
