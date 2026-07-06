# VAL-BENCH-004: Report provides per-utterance and aggregate verdicts

Surface: report artifact and observer/API.
Needs: Passing `VAL-BENCH-002`.
Behavior: Reports provide per-utterance verdicts and aggregate LiveKit/Pipecat
summary for STT intent match, required tool use, grounding, response presence,
audio integrity, latency, usage, cost, and failure/inconclusive counts.
Evidence: Validator records report JSON/Markdown and observer/API report view
showing per-utterance rows and aggregate summaries.
Fail: Only aggregate totals, only prose, missing per-utterance verdicts, or
missing failed/inconclusive counts means failure.
