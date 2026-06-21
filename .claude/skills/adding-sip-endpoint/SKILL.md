---
name: adding-sip-endpoint
description: Use when the user asks to add, provision, or remove a SIP endpoint (extension number like 1003, 1004) on the Asterisk lab — covers the .env edit, redeploy, baresip mirror, and orphan cleanup.
---

# Adding (or removing) a SIP endpoint

Endpoints are driven by `SIP_EXTENSIONS` in `.env`. Adding one = two lines in `.env` + redeploy. The repo's `install.sh` loops over the list and renders `/etc/asterisk/pjsip.d/<ext>.conf` per entry; an extension removed from `.env` is pruned from `pjsip.d/` on the next run.

## Add a new endpoint

1. **Edit `.env` on the VM** (`~/asterisk-lab/.env`). Append the number to the list and add its password:

   ```bash
   SIP_EXTENSIONS="1001 1002 1003"
   SIP_EXT_1003_PASSWORD=<choose-a-strong-password>
   ```

2. **Re-run install:**

   ```bash
   cd ~/asterisk-lab && sudo ./install.sh
   ```

   Idempotent — Asterisk build is skipped (already installed), only `pjsip.d/1003.conf` is rendered, then `systemctl restart asterisk`.

3. **Verify on the VM:**

   ```bash
   sudo asterisk -rx 'pjsip show endpoints' | grep 1003
   sudo ./scripts/verify.sh                   # picks up 1003 automatically from pjsip.d/
   ```

4. **Mirror on the host** (baresip). Append to `~/.baresip/accounts`:

   ```text
   <sip:1003@<VM IP>>;auth_pass=<same-password>;transport=udp;regint=3600;answermode=auto;audio_codecs=opus,PCMU,PCMA
   ```

   Reload baresip (`/reload` in its REPL, or restart it). Confirm REGISTER landed:

   ```bash
   sudo asterisk -rx 'pjsip show contacts' | grep 1003
   ```

## Remove an endpoint

1. Delete the line from `SIP_EXTENSIONS` and remove its `SIP_EXT_<n>_PASSWORD` from `.env`.
2. `sudo ./install.sh` — the orphan-cleanup loop deletes `/etc/asterisk/pjsip.d/<n>.conf` and restarts asterisk. You'll see `pruning orphan endpoint <n>` in stdout.
3. Remove the matching `<sip:<n>@...>` line from `~/.baresip/accounts` on the host.

## Gotchas

- **Password must match exactly** between VM `.env` and host `~/.baresip/accounts`. Any mismatch produces an endless 401 loop visible in `sngrep`.
- **`SIP_EXTENSIONS` is space-separated**, not comma-separated. `"1001,1002"` will be read as one weird extension name and fail silently.
- The `_10XX` dialplan pattern in `extensions.conf.tmpl` already covers 1000–1099 for direct dial. Outside that range, add a new pattern or explicit `exten => <n>,1,...` lines.
- Don't hand-edit `/etc/asterisk/pjsip.d/*.conf` on the VM — `install.sh` re-renders them from the template on every run.
