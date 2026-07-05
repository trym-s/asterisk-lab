# VAL-SECRETS-001: Secrets and per-VM IPs stay out of git deploy payloads

Surface: repository, deploy command, and generated artifact.
Needs: none.
Behavior: Real `.env` files, SIP passwords, API keys, database passwords, and
dynamic VM IP assignments are not committed and are excluded from rsync deploy
payloads. Each VM keeps its own `.env`.
Evidence: Validator records `.gitignore`/deploy exclusion evidence, `git status`
showing no real `.env`, and Makefile rsync excludes.
Fail: A real secret or environment-specific IP committed to source, or deploy
overwriting a target `.env`, means failure.
