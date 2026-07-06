# VAL-VOICEBOT-AUDIO-003: Bot audio returns toward the caller before hangup

Surface: SIP call, recording artifact, and trace.
Needs: Passing `VAL-VOICEBOT-AUDIO-001` and a completed TTS response.
Behavior: For LiveKit and Pipecat benchmark calls, Asterisk-side recording or
equivalent transmit-side evidence proves that TTS response audio returned toward
the caller and that hangup did not cut the response mid-speech.
Evidence: Validator records TTS trace text, TTS/audio output timing, matching
Asterisk transmit-side recording path/metadata, detected bot speech duration,
hangup timestamp, and truncation verdict.
Fail: No returned bot audio, hangup before response audio end, missing TTS trace,
or missing recording evidence means failure or inconclusive status.
