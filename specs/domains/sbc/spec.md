# SBC Domain Spec

The SBC VM runs OpenSIPS 3.6 LTS and rtpengine. It proxies SIP between host
baresip and the Asterisk VM and relays media through rtpengine.

## Supported Behavior

- `sbc/install.sh` installs OpenSIPS, rtpengine, rsyslog, renders templates,
  enables services, and is idempotent.
- OpenSIPS binds to `SBC_IP`, not `0.0.0.0`, so generated SIP headers are
  routable.
- REGISTER traffic receives `Supported: path` and `Path` handling before relay
  to Asterisk.
- Initial softphone INVITEs are record-routed, passed to rtpengine, and relayed
  to Asterisk.
- Initial INVITEs from Asterisk are not forced back to Asterisk; they follow the
  R-URI toward the registered softphone.
- RTPengine runs userspace relay on the configured port range.

## Source Files

- `sbc/install.sh`
- `sbc/opensips.cfg.tmpl`
- `sbc/rtpengine.conf.tmpl`
- `sbc/verify.sh`

Rendered `/etc/opensips` and `/etc/rtpengine` files are outputs.
