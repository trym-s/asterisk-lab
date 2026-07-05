# VAL-SBC-001: SBC relays registration, calls, and media

Surface: SIP, CLI, and packet observation.
Needs: Running Asterisk VM, running SBC VM with correct `SBC_IP` and
`ASTERISK_IP`, and a baresip endpoint pointed at the SBC.
Behavior: REGISTER and calls from baresip traverse host -> SBC -> Asterisk,
OpenSIPS inserts Path/Record-Route as appropriate, and RTP flows through the
rtpengine port range during a call.
Evidence: Validator records `sudo ./sbc/verify.sh`, Asterisk `pjsip show
contacts` path evidence, sngrep observations on SBC/Asterisk, and tcpdump or
rtpengine evidence showing media through `30000-40000`.
Fail: Direct media bypass when SBC is expected, missing Path, failed verify, or
missing call relay means failure.
