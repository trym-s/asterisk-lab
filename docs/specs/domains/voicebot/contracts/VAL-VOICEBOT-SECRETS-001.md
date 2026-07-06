# VAL-VOICEBOT-SECRETS-001: Voicebot traces and observer do not expose secrets

Surface: artifacts, API, and browser.
Needs: Voicebot traces or observer output generated from at least one real call.
Behavior: Trace artifacts, usage artifacts, report artifacts, observer pages, and
observer JSON APIs may expose lab call content but never expose `.env` content,
API keys, SIP passwords, LiveKit credentials, bearer tokens, or provider secret
headers.
Evidence: Validator records targeted scans of `/var/lib/voicebot` artifacts,
observer HTML/API responses, and repository config showing observer does not
receive secret environment variables.
Fail: Any runtime credential or `.env` content in trace, usage, report, HTML, or
API output means failure.
