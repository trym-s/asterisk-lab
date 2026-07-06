# VAL-ASTERISK-003: Loopback call records and transcribes

Surface: SIP call and artifact.
Needs: A registered softphone endpoint and passing `VAL-ASTERISK-001`.
Behavior: A call to extension `600` is answered, recorded as WAV under
`/var/spool/asterisk/monitor/`, and transcribed to a sibling `.txt` after the
recording becomes stable.
Evidence: Validator records SIP call flow or baresip command, Asterisk logs,
new WAV path, new TXT path, and relevant `journalctl -u transcriber` lines.
Fail: No answer, no WAV, empty or missing TXT after stable recording, or
transcriber crash means failure.
