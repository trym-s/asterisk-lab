# VAL-VOICEBOT-AUDIO-002: Caller audio reaches the Asterisk VM

Surface: SIP call, recording artifact, and trace.
Needs: Passing `VAL-VOICEBOT-AUDIO-001` and deployed target lane.
Behavior: For LiveKit and Pipecat benchmark calls, Asterisk-side recording or
equivalent receive-side evidence proves that the caller utterance audio reached
the VM and was not materially truncated before STT.
Evidence: Validator records source WAV duration, matching Asterisk recording
path/metadata, detected caller speech duration, STT transcript, and a comparison
summary for each checked utterance.
Fail: No receive-side evidence, missing recording metadata, caller speech
shorter than source by more than the accepted tolerance, or transcript showing
only a tail fragment means failure or inconclusive status.
