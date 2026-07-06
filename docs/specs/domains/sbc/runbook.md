# SBC Runbook

## Required `.env`

On the SBC VM:

```text
SBC_IP=<sbc-vm-ip>
ASTERISK_IP=<asterisk-vm-ip>
```

Read both from:

```bash
virsh -c qemu:///system net-dhcp-leases default
```

## Deploy

```bash
make SBC_VM=deb@<sbc-ip> deploy-sbc
```

## Verify

On the SBC VM:

```bash
cd ~/asterisk-lab
sudo ./sbc/verify.sh
sudo tail -f /var/log/syslog
sudo sngrep -d any port 5060
sudo tcpdump -i any -n udp portrange 30000-40000
```

## After DHCP Drift

Update `SBC_IP` and `ASTERISK_IP` in the SBC VM `.env`, then rerun
`make deploy-sbc`.
