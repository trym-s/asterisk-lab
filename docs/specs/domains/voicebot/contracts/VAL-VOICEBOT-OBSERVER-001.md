# VAL-VOICEBOT-OBSERVER-001: Observer service starts and serves health/API

Surface: Docker, HTTP API, and service log.
Needs: Asterisk VM with `/var/lib/voicebot` present and observer deployed.
Behavior: The FastAPI observer starts on `127.0.0.1:8088`, serves `/healthz`,
and exposes JSON APIs for calls, events, usage, comparisons, and reports without
requiring provider credentials.
Evidence: Validator records container status, observer logs, listener evidence,
and `curl` responses for `/healthz` and representative `/api/*` endpoints.
Fail: Service not listening, non-2xx health response, missing API endpoints, or
secret env requirements means failure.
