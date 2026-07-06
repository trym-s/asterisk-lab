# VAL-VOICEBOT-AUDIO-001: Test caller records send timing for every utterance

Surface: CLI benchmark and artifact.
Needs: Host baresip with `ctrl_tcp` and `aufile`, generated utterance WAVs, and
target lane deployed.
Behavior: Each test-caller run writes a manifest with run ID, target extension,
lane, repo revision, utterance ID, expected text, WAV path, WAV duration, dial
timestamp, source-switch timestamp, hangup timestamp, and VM target.
Evidence: Validator records the suite command, run directory, manifest file, and
manifest entries matching every utterance in `utterances.tsv`.
Fail: Missing manifest, missing utterance rows, missing timestamps, hardcoded VM
target drift, or WAV duration mismatch means failure.
