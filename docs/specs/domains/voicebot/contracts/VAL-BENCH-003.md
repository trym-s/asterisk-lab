# VAL-BENCH-003: Report refuses invalid lane comparisons

Surface: CLI benchmark and generated artifacts.
Needs: Benchmark artifacts from both lanes.
Behavior: Report generation refuses or clearly marks inconclusive comparisons
when lanes differ by repo revision, prompt, model profile, corpus, tool schema,
pricing version, or missing trace/usage/audio evidence.
Evidence: Validator records report output for a valid run and at least one
invalid or incomplete fixture/run, showing the refusal or inconclusive status.
Fail: Silent comparison of mismatched or incomplete lane evidence means failure.
