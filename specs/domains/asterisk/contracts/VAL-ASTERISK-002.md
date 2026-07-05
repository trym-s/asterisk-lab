# VAL-ASTERISK-002: SIP endpoint inventory renders and prunes

Surface: CLI and generated artifact.
Needs: Asterisk VM `.env` with `SIP_EXTENSIONS` and matching passwords.
Behavior: Running `install.sh` renders one `/etc/asterisk/pjsip.d/<ext>.conf`
per listed extension from `asterisk/pjsip-endpoint.conf.tmpl`, and removes
orphan endpoint files for extensions no longer listed.
Evidence: Validator records `.env` extension list without secret values,
rendered file names, `sudo asterisk -rx 'pjsip show endpoints'`, and a prune
check using a temporary non-secret extension or source review if runtime mutation
is not allowed.
Fail: Missing endpoint file, stale orphan after re-run, or endpoint absent from
Asterisk CLI means failure.
