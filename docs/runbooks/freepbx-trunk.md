# Runbook: FreePBX DID -> voicebot (outbound-registration trunk)

Connect a real phone number (DID) terminating on a remote FreePBX to the
lab's voicebot. The Asterisk VM registers OUTBOUND to FreePBX as an ordinary
extension; FreePBX routes the DID to that extension and the call arrives down
the registered line.

## Why outbound registration, not a peer trunk

The Asterisk VM is behind libvirt NAT behind WSL2 NAT behind the ISP router
(three NAT layers, no inbound reachability, no stable public address).
FreePBX cannot reach it, so a classic PBX-to-PBX trunk is impossible. Instead
the VM registers to FreePBX like a softphone would; the NAT pinhole opened by
that registration is what inbound calls travel back through.

## Two Asterisks

- **FreePBX side**: the Asterisk that FreePBX (the web UI) manages. Terminates
  the operator trunk and owns the DID.
- **Lab side / voicebot VM**: the Asterisk in `vms/asterisk/`, hosting the
  Pipecat voicebot.

This runbook configures both. The lab side is templated in the repo; the
FreePBX side is GUI work recorded here for reproducibility.

## FreePBX side (GUI, one-time)

1. `Applications -> Extensions -> Add SIP [chan_pjsip] Extension`.
   - User Extension: the lab's number (e.g. `1003`).
   - Display Name: e.g. `voice-lab`.
   - Secret: keep the generated value; copy it into the lab env (below).
2. Voicemail tab: **Enabled = No**. With voicemail off, a dead registration
   makes inbound calls fail with congestion instead of silently collecting
   voicemail nobody reads.
3. Advanced tab: **Direct Media = No**. NAT settings (`rtp_symmetric`,
   `rewrite_contact`, `force_rport`) are already on in FreePBX's default
   template; leave Call Waiting enabled, Max Contacts 1.
4. Submit, then the red **Apply Config** (nothing takes effect without it).
5. `Connectivity -> Inbound Routes -> <DID>`: set Destination to the new
   extension. Do this last, after the registration is proven up, so a broken
   registration does not black-hole live DID calls.

Gotchas seen in practice:
- FreePBX may listen on a non-standard SIP port (e.g. `7201`), not 5060.
  Confirm with `asterisk -rx 'pjsip show transports'` on the FreePBX box and
  set `FREEPBX_PORT` to match.
- If `Apply Config` does not update `pjsip.auth.conf` (its mtime stays old
  and `pjsip show auths` lacks the new `<ext>-auth`), a config file is
  root-owned and the web user cannot rewrite it. Fix with `fwconsole chown`
  then `fwconsole reload`. The freepbx.log shows `Permission denied` /
  `chown(): Operation not permitted` when this happens.
- FreePBX runs fail2ban (`asterisk-iptables`, maxretry 5, all-ports ban). A
  wrong password retried in a storm bans the VM's public IP -- including SSH.
  The trunk template's back-off settings prevent this, but get the password
  right the first time.

## Lab side (repo + env)

1. On the Asterisk VM, in `/etc/asterisk-lab/env`:
   ```
   FREEPBX_HOST=<freepbx public ip>
   FREEPBX_PORT=<freepbx sip port>
   FREEPBX_EXT=<the extension>
   FREEPBX_EXT_PASSWORD=<the secret from step 1>
   FREEPBX_CONTEXT=from-freepbx
   ```
   These are the trunk direction. Do NOT use `SIP_EXT_<n>_PASSWORD` or add
   the number to `SIP_EXTENSIONS`: that provisions a LOCAL endpoint (a
   softphone registering to the lab), the opposite direction.
2. Deploy and run the Asterisk installer (renders
   `/etc/asterisk/pjsip.trunks.d/freepbx.conf` from
   `vms/asterisk/etc/asterisk/pjsip-trunk.conf.tmpl` and reloads Asterisk).

Unsetting `FREEPBX_HOST` and re-running the installer removes the trunk.

## Verify (staged)

**1. Registration up (lab side):**
```bash
sudo asterisk -rx 'pjsip show registrations'   # freepbx-reg ... Registered
sudo asterisk -rx 'pjsip show aors'            # freepbx-aor Avail + RTT
```

**2. NAT proven (FreePBX side) -- the highest-value single check:**
```bash
asterisk -rx 'pjsip show contacts' | grep <ext>
# want: <ext>/sip:<ext>@<PUBLIC-IP>:<mapped-port>;line=xxxxxxx  Avail  <rtt>
```
Proves three things at once: the address is the VM's public IP not
192.168.122.x (FreePBX's rewrite_contact works), `;line=` survived (inbound
matching will fire), and `Avail` means qualify OPTIONS traverse the pinhole.

**3. Inbound call arrives (lab side):**
```bash
sudo asterisk -rx 'dialplan show s@voicebot'
sudo asterisk -rx 'pjsip set logger on'; sudo journalctl -u asterisk -f
# call the DID; want: INVITE sip:<ext>@192.168.122.x;line=xxxxxxx
```
INVITE arrives but 404 / "No matching endpoint" -> line matching failed;
check `line=yes`/`endpoint=` in the registration.

**4. Two-way audio:**
```bash
sudo asterisk -rx 'pjsip show channelstats'   # during the call
```
`RxCount` climbing -> FreePBX->us RTP arriving (symmetric latching worked).
`TxCount` climbing + caller hears the bot -> us->FreePBX. Durable evidence:
the MixMonitor WAV under `/var/spool/asterisk/monitor/` carries both legs.

## Audio quality note

The DID leg is narrowband (ulaw, 8 kHz) -- this is the phone network, not a
lab limitation, and is true of production voicebots on real numbers too. The
voicebot still receives slin16 but upsampled from 8 kHz, so STT quality on
the DID lane is measurably lower than the wideband softphone lane (g722/opus).
Measure the actual negotiated codec with `pjsip show channelstats` rather than
assuming. Do not compare DID-lane and softphone-lane metrics as equals.
