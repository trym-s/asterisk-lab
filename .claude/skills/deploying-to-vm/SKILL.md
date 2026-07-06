---
name: deploying-to-vm
description: Use when shipping repo changes to the Asterisk lab VM - covers initial bootstrap (/etc/asterisk-lab/env on target), the make deploy / rsync flow, and post-deploy verification.
---

# Deploying to the lab VM

The deploy model: code follows the rsync; secrets stay on the target.
`make deploy` rsyncs a role payload to `/opt/asterisk-lab/current` and
excludes `.env` / `.env.*`. The VM keeps its env at
`/etc/asterisk-lab/env`, written manually once and never touched by the
pipeline.

## First-time bootstrap (per VM)

1. **Confirm the VM has SSH and a `deb` (or equivalent) user with sudo.** Note the IP (`192.168.122.20` if using the libvirt setup).

2. **Create `/etc/asterisk-lab/env` on the VM, manually:**

   ```bash
   ssh deb@192.168.122.20
   sudo install -d -m 0755 /etc/asterisk-lab
   sudo tee /etc/asterisk-lab/env >/dev/null <<'EOF'
   SIP_EXTENSIONS="1001 1002"
   SIP_EXT_1001_PASSWORD=<value>
   SIP_EXT_1002_PASSWORD=<value>
   ASTERISK_VERSION=22.9.0
   EOF
   sudo chmod 600 /etc/asterisk-lab/env
   exit
   ```

3. **Rsync the repo from the workstation:**

   ```bash
   make deploy VM=deb@192.168.122.20
   ```

   First run takes about 10 to 15 minutes (Asterisk built from source in
   step 2 of `install.sh`). Re-runs are seconds when the version pin matches.

## Routine deploy (after the first time)

```bash
make deploy VM=deb@192.168.122.20    # rsync + install.sh + setup-transcriber.sh
ssh deb@192.168.122.20 'cd /opt/asterisk-lab/current && sudo ./scripts/verify.sh'
make logs   VM=deb@192.168.122.20    # tail asterisk + transcriber journals
```

Override SSH for password-only hosts (default assumes keys):

```bash
make deploy SSH="sshpass -e ssh"     # SSHPASS env must be set
```

## Verifying it landed

```bash
ssh $VM 'sudo asterisk -rx "pjsip show endpoints"'  # each SIP_EXTENSIONS entry present
ssh $VM 'sudo systemctl is-active asterisk transcriber'
ssh $VM 'cd /opt/asterisk-lab/current && sudo ./scripts/verify.sh'
```

## Gotchas

- **Env missing on the VM** -> `install.sh` exits with
  `SIP_EXTENSIONS not set`. Create `/etc/asterisk-lab/env` before first
  deploy. Current Makefile targets migrate an old `~/asterisk-lab/.env` once
  when `/etc/asterisk-lab/env` does not exist.
- **Local `rsync` not installed** -> `make deploy` errors out. Install
  `rsync` locally.
- **First-run build can hit OOM on small VMs** -> Asterisk's source build
  defaults to `MAKE_JOBS=$(nproc)`, and a 2 GB VM can OOM-kill `cc1`. Either
  give the VM at least 4 GB or run `sudo MAKE_JOBS=2 ./install.sh`.
- **Re-running after a config edit is the right path** -> the script is
  idempotent. Do not hand-edit `/etc/asterisk/*.conf` on the VM expecting it
  to stick.
