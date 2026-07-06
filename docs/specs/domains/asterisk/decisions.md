# Asterisk Decisions

## Endpoint Config Is Rendered Per Extension

`SIP_EXTENSIONS` is the operator-facing inventory. Rendering one file per
extension keeps additions and removals explicit and allows orphan pruning.

## Templates Are Source Of Truth

Rendered Asterisk config under `/etc/asterisk` is overwritten by install.
Agents must edit repo templates and redeploy.

## Transcriber Waits For Stable WAVs

The watcher must not transcribe header-only or still-growing WAV files. A
stable-size gate prevents empty transcripts while `MixMonitor` is still writing.

## Baresip Is The Linux Softphone

MicroSIP is Windows-only. Linux validation uses baresip while preserving the
same SIP behavior on the Asterisk side.
