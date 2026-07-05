# VAL-BENCH-001: Test caller compares LiveKit and Pipecat fairly

Surface: CLI benchmark and artifacts.
Needs: Passing `VAL-VOICEBOT-001` and `VAL-VOICEBOT-002`, host baresip with
`ctrl_tcp` and `aufile`, and generated utterance WAVs.
Behavior: The test-caller suite can send the same utterance corpus to `1099`
and `1098`, wait for responses, and produce comparable turn and usage evidence.
Evidence: Validator records both suite commands, per-target run directories,
remote usage summaries, and turn log excerpts showing each utterance reached the
intended lane.
Fail: Different corpora, missing lane logs, failed calls, or incomparable repo
revisions means the benchmark does not pass.
