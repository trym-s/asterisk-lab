# VAL-BENCH-001: Test caller compares LiveKit and Pipecat fairly

Surface: CLI benchmark and artifacts.
Needs: Passing `VAL-VOICEBOT-001` and `VAL-VOICEBOT-002`, host baresip with
`ctrl_tcp` and `aufile`, and generated utterance WAVs.
Behavior: The test-caller suite can send the same utterance corpus to `1099`
and `1098`, record per-run timing manifests, wait for responses, and produce
comparable trace, usage, and audio-evidence anchors for both lanes.
Evidence: Validator records both suite commands, per-target run directories,
run manifests, remote trace/usage excerpts, and evidence that each utterance
reached the intended lane.
Fail: Different corpora, missing manifests, missing lane traces, missing usage
rows, missing audio evidence, failed calls, or incomparable repo revisions means
the benchmark does not pass.
