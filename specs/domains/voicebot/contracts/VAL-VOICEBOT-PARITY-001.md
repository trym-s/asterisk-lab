# VAL-VOICEBOT-PARITY-001: Lanes share comparable runtime configuration

Surface: repository, VM config, Docker, and trace.
Needs: LiveKit and Pipecat stacks deployed from the same repo revision.
Behavior: LiveKit and Pipecat use the same business prompt, document corpus,
model profile, tool schema, trace schema, usage schema, and benchmark corpus for
the same comparison run unless an accepted decision records the divergence.
Evidence: Validator records repo revision, relevant config/env values without
secrets, agent startup logs or trace profile events for both lanes, corpus hash
or file list, and a comparison report or API response showing the same profile
for both lanes.
Fail: Silent prompt/model/corpus/tool/schema drift, missing profile evidence, or
different repo revisions means the comparison is invalid.
