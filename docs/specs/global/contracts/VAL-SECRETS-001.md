# VAL-SECRETS-001: Secrets and per-VM IPs stay out of git deploy payloads

Surface: repository, deploy command, and generated artifact.
Needs: none.
Behavior: Real `.env` files, SIP passwords, API keys, database passwords,
dynamic VM IP assignments, specs, agent guidance, CI metadata, and repo
documentation are not sent as VM deploy payload. Each VM keeps only runtime
files plus its own manually placed `.env`.
Evidence: Validator records `.gitignore`/deploy exclusion evidence, `git status`
showing no real `.env`, and Makefile rsync excludes for `.env`, `specs/`,
agent metadata, and repo docs.
Fail: A real secret or environment-specific IP committed to source, deploy
overwriting a target `.env`, or specs/agent docs being sent by deploy means
failure.
