# Asterisk Runbook

## Deploy

```bash
make VM=deb@<asterisk-ip> deploy
```

The target VM must already have `~/asterisk-lab/.env`.

## Verify

On the Asterisk VM:

```bash
cd ~/asterisk-lab
sudo ./scripts/verify.sh
sudo asterisk -rx 'pjsip show endpoints'
sudo asterisk -rx 'pjsip show contacts'
sudo asterisk -rx 'dialplan show from-softphones'
```

## Observe Calls

```bash
sudo sngrep -d any port 5060
sudo journalctl -u asterisk -u transcriber -f --no-pager
ls -l /var/spool/asterisk/monitor/
```

## Endpoint Changes

Use `.env`:

```text
SIP_EXTENSIONS="1001 1002"
SIP_EXT_1001_PASSWORD=...
SIP_EXT_1002_PASSWORD=...
```

Then re-run deploy or `sudo ./install.sh`.
