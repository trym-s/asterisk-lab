# VAL-VOICEBOT-USAGE-001: Usage and estimated cost are attributable

Surface: artifact and API.
Needs: Passing `VAL-VOICEBOT-TRACE-001` or `VAL-VOICEBOT-TRACE-002`.
Behavior: Every provider operation that consumes billable or comparable units
records usage with lane, call ID, turn ID, stage, provider, model, units,
unit_type, estimated USD, and pricing table version. Aggregation can group cost
by lane, provider, model, stage, and time window.
Evidence: Validator records representative `usage.jsonl` rows, a usage summary
or observer API response, and the pricing version used for cost estimates.
Fail: Missing lane/call/turn/model attribution, unknown pricing version, missing
unit type, or treating missing usage as zero cost means failure.
