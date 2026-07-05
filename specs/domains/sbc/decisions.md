# SBC Decisions

## Stateless Proxy

The SBC is intentionally a stateless SIP proxy plus rtpengine, not a
topology-hiding B2BUA.

## Bind To Real SBC IP

Binding OpenSIPS to `0.0.0.0` can leak `0.0.0.0` into Via, Record-Route, or
Path headers. The config must render `socket=udp:${SBC_IP}:5060`.

## Inject Supported Path

Baresip does not advertise `Supported: path`; OpenSIPS injects it before
`add_path_received()` so Asterisk accepts the Path header.

## Direction-Aware Initial INVITE

The initial INVITE branch must not force Asterisk-originated INVITEs back to
Asterisk. Use a source-IP direction check or equivalent.
