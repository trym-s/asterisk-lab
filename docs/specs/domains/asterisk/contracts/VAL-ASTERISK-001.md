# VAL-ASTERISK-001: Fresh PBX install verifies

Surface: CLI.
Needs: Fresh or already provisioned Debian 13 / Ubuntu 26.04 Asterisk VM with
target `.env` containing SIP endpoint passwords.
Behavior: From a clone, `make install` provisions Asterisk and the transcriber
idempotently, and `make verify` reports all Asterisk smoke checks passing.
Evidence: Validator records the install command outcome, `sudo ./scripts/verify.sh`
stdout with pass count, and `systemctl is-active asterisk transcriber`.
Fail: Missing `.env`, failed service start, failed verifier check, or non-zero
command exit means the contract is not passed.
