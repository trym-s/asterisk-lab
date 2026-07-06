# VAL-VOICEBOT-OBSERVER-002: Observer renders recent calls and call detail

Surface: browser and HTTP API.
Needs: Passing `VAL-VOICEBOT-OBSERVER-001` and at least one traced voicebot call.
Behavior: The observer Calls page lists recent traced calls, and a Call Detail
page groups the selected call by turn with lane, status, duration, stage
presence, usage, and raw event links.
Evidence: Validator records browser screenshots or HTML excerpts, API responses,
and the matching source `events.jsonl` rows.
Fail: Empty UI despite matching trace files, missing call detail, ungrouped turn
data, broken links, or server errors means failure.
