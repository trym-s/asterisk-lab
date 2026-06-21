---
name: rotating-passwords
description: Use when rotating a SIP endpoint password (security incident, scheduled rotation, suspected leak). Covers the VM-side .env edit, redeploy, host softphone update, and confirming old credentials no longer authenticate.
---

# Rotating a SIP endpoint password

Two places hold the password and they must agree: the VM's `~/asterisk-lab/.env` (`SIP_EXT_<n>_PASSWORD`) and the host softphone (`auth_pass=` in `~/.baresip/accounts`, or equivalent). Rotation = update both, redeploy Asterisk, confirm the old value is dead.

## Steps

1. **Pick the new password.** Strong, random, no shell metacharacters that would break unquoted `.env` reads (avoid `$`, backticks, `;`, `#`, unbalanced quotes). Generate with:

   ```bash
   openssl rand -base64 24 | tr -d '/+=' | head -c 24
   ```

2. **Update the VM's `.env`:**

   ```bash
   ssh deb@<VM IP>
   $EDITOR ~/asterisk-lab/.env
   # change SIP_EXT_<n>_PASSWORD=<old> to SIP_EXT_<n>_PASSWORD=<new>
   ```

3. **Re-render and restart Asterisk** (idempotent install):

   ```bash
   cd ~/asterisk-lab && sudo ./install.sh
   ```

   The build is skipped (version unchanged); only `pjsip.d/<n>.conf` gets re-rendered with the new password, then `systemctl restart asterisk`. Existing registered contacts are dropped during the restart and will fail to re-register with the old password.

4. **Update the host softphone.** Edit `~/.baresip/accounts`:

   ```text
   <sip:<n>@<VM IP>>;auth_pass=<new>;transport=udp;...
   ```

   Restart baresip or `/reload`.

5. **Confirm rotation took effect** (from the VM):

   ```bash
   sudo asterisk -rx 'pjsip show contacts' | grep <n>     # new contact registered with new password
   sudo journalctl -u asterisk -n 50 | grep -i 'auth'     # should show successful auth, no 'Failed to authenticate'
   ```

   If anyone is still using the old credentials they'll show up as repeated `Failed to authenticate` lines — investigate which client.

## Rotating all endpoints at once

Edit every `SIP_EXT_<n>_PASSWORD=` in `.env`, run `sudo ./install.sh` once, then update every softphone. The Asterisk restart is one event regardless of how many endpoints change.

## Gotchas

- **Don't quote the value in `.env` unless you have to.** `SIP_EXT_1001_PASSWORD=abc!def` works; `SIP_EXT_1001_PASSWORD="abc!def"` works; `SIP_EXT_1001_PASSWORD=abc"def` breaks. If the value has spaces or shell metas, use double-quotes and escape carefully.
- **Asterisk requires a restart, not a reload**, for PJSIP password changes to take effect on existing endpoints. `install.sh` does the restart for you; if you skip it, the new password file is on disk but Asterisk is still serving the old one.
- **No "grace window" for the old password.** Once the restart completes, the old value is dead. If the softphone update is delayed, registration fails until both sides match. Plan the order: VM first, then host, within a few seconds.
- **Don't commit `.env` to git.** It's in `.gitignore`; `make deploy` excludes it. If you ever accidentally stage it, `git rm --cached .env` and rotate the leaked password immediately.
