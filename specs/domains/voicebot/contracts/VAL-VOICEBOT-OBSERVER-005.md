# VAL-VOICEBOT-OBSERVER-005: Observer exposes no runtime secrets

Surface: Docker, browser, and HTTP API.
Needs: Passing `VAL-VOICEBOT-OBSERVER-001`.
Behavior: The observer container does not receive provider/SIP secrets and its
HTML/API responses do not expose `.env`, OpenAI, LiveKit, ElevenLabs, SIP, or
bearer-token secret values.
Evidence: Validator records compose/container environment evidence without
secret values and targeted scans of observer pages and API responses.
Fail: Any runtime credential in observer environment, HTML, or API output means
failure.
