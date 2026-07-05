# Voicebot Decisions

## Parity First

LiveKit and Pipecat lanes should differ by framework and media transport, not
by prompt, model, tool behavior, or log schema.

## Narrowband Baseline

The current comparison baseline is 8 kHz telephony audio. Wideband experiments
belong in explicit benchmark changes so codec and framework effects do not mix.

## Shared Logs

Both lanes write usage and turn events to `/var/lib/voicebot` so summaries can
compare cost and behavior across lanes.
