# VAL-VOICEBOT-DOCS-001: Store-hours questions are grounded in docs

Surface: SIP call and trace artifact.
Needs: Passing `VAL-VOICEBOT-TRACE-001` and `VAL-VOICEBOT-TRACE-002`.
Behavior: For the question "Magazaniz Pazar gunu kacta aciliyor?", both lanes
call `lookup_docs`, retrieve relevant content from `hakkinda.md`, and answer in
Turkish with the Sunday opening-hours fact from the corpus.
Evidence: Validator records LiveKit and Pipecat trace rows showing STT text,
tool query, `hakkinda.md` tool result, LLM input after tool result, final answer,
and TTS text.
Fail: Answering without the tool, retrieving the wrong corpus source, omitting
the Sunday-hours fact, or inventing unsupported hours means failure.
