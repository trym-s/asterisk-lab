---
name: debugging-sip-registration
description: Use when a SIP endpoint fails to register — endpoint shows Unavailable indefinitely, repeated 401 Unauthorized, qualify failures, or the softphone reports register timeout. Triage flow uses Asterisk CLI + sngrep + journalctl.
---

# Debugging SIP registration

A healthy endpoint reaches state `Not in use` (or `In use` mid-call). `Unavailable` means no contact has registered. The triage below moves from "is anything happening" to "what specifically is wrong".

## Triage sequence (do in order)

1. **Is the endpoint defined at all?**

   ```bash
   sudo asterisk -rx 'pjsip show endpoints' | grep <ext>
   ```

   If empty: the extension isn't in `pjsip.d/`. Check `.env` `SIP_EXTENSIONS` includes it and `install.sh` was re-run after editing.

2. **Is there a contact (i.e. did REGISTER reach Asterisk)?**

   ```bash
   sudo asterisk -rx 'pjsip show contacts' | grep <ext>
   ```

   Empty → softphone packets aren't landing or Asterisk is rejecting REGISTER before recording a contact. Continue to step 3.

3. **Watch SIP signaling in real time** (in a second VM shell):

   ```bash
   sudo sngrep -d any port 5060
   ```

   What you should see when the softphone tries to register:

   - `REGISTER` arrives → `401 Unauthorized` (expected, Asterisk's first response always demands digest)
   - Softphone retries `REGISTER` with `Authorization:` header → `200 OK`

   What can go wrong:
   - **No REGISTER at all** → networking. Check VM firewall: `sudo iptables -L -n | grep 5060`. Check softphone is dialing the right IP/port. Check `bind=0.0.0.0:5060` in `/etc/asterisk/pjsip.conf`.
   - **REGISTER → 401 → REGISTER → 401 (loop)** → password mismatch. The host's softphone `auth_pass` and the VM's `SIP_EXT_<n>_PASSWORD` must be byte-identical.
   - **REGISTER → 403 Forbidden** → username doesn't match any endpoint or AOR. Check `pjsip show endpoints` again; extension number must match exactly.
   - **REGISTER → 408 Request Timeout** → Asterisk dropped the packet. Usually `set debug pjsip on` in the CLI reveals why.

4. **Check Asterisk logs:**

   ```bash
   sudo journalctl -u asterisk -n 100 --no-pager | grep -iE 'auth|register|401|403'
   ```

   Frequent patterns:
   - `Failed to authenticate ...` — password mismatch confirmed
   - `Endpoint: <ext> Did not match` — extension not provisioned
   - `Maximum retries exceeded` — softphone gave up; usually downstream of one of the above

5. **Confirm the softphone side.** For baresip:

   ```bash
   grep <ext> ~/.baresip/accounts
   ```

   Confirm `auth_pass=<value>` matches what's in the VM's `.env` for `SIP_EXT_<n>_PASSWORD`. After editing, restart baresip (`/quit` then re-launch, or `/reload` in REPL).

## Common root causes (by frequency)

1. **Password drift** between VM `.env` and host softphone config (most common; especially after rotating).
2. **`SIP_EXTENSIONS` and the endpoint are out of sync** — extension added to `.env` but `install.sh` not re-run, or vice versa.
3. **UDP 5060 blocked** by host firewall (less common in a libvirt lab — `virbr0` is permissive by default).
4. **RTP port range (10000–10200) blocked** — REGISTER succeeds but call has one-way or no audio. Different symptom, same root.
5. **NAT** — softphone behind double-NAT may need `direct_media=no` (already set in the template) and possibly external IP hints. Not an issue for host↔VM on the same libvirt bridge.

## Useful CLI shortcuts

```text
sudo asterisk -rvvv                       # attach with verbose logging
   pjsip set logger on                    # log every SIP message inline
   pjsip set logger off                   # turn it off when done
```

## After fixing

Re-run `make verify` (or `sudo ./scripts/verify.sh`). Expect green; expect endpoint in `Not in use` state after the softphone re-registers.
