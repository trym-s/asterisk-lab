# VAL-VOICEBOT-MODEL-003: Reports reject silent mixed-profile comparisons

Surface: report artifact and API.
Needs: Benchmark artifacts from both LiveKit and Pipecat.
Behavior: Report generation includes model profile metadata for both lanes and
fails or marks comparison inconclusive when prompt, model, voice, corpus, tool
schema, pricing version, or repo revision differs without an accepted decision.
Evidence: Validator records generated report JSON/Markdown for matching and
intentionally mismatched metadata cases.
Fail: A report silently compares mismatched profiles as valid means failure.
