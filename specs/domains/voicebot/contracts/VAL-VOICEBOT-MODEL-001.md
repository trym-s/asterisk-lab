# VAL-VOICEBOT-MODEL-001: Both lanes load the same model profile

Surface: repository, Docker, and trace.
Needs: LiveKit and Pipecat deployed from the same repo revision.
Behavior: Both lanes load the same STT, LLM, TTS, voice, prompt, and pricing
profile for comparable runs, and expose the active profile in trace/report
metadata without exposing secrets.
Evidence: Validator records config/env evidence without secrets, startup logs or
profile trace events from both lanes, and a report/API response showing the same
profile values.
Fail: Silent mixed profiles, missing profile metadata, or profile values present
for only one lane means failure.
