# VAL-VOICEBOT-DOCS-003: Shipping and return questions are grounded in docs

Surface: SIP call and trace artifact.
Needs: Passing `VAL-VOICEBOT-TRACE-001` and `VAL-VOICEBOT-TRACE-002`.
Behavior: For shipping or return questions such as "Izmir'e kargo kac gunde
geliyor?" and "Iade sureniz ne kadar?", both lanes call `lookup_docs`, retrieve
relevant content from `kargo-iade.md`, and answer in Turkish using the corpus
facts.
Evidence: Validator records LiveKit and Pipecat trace rows showing STT text,
tool query, `kargo-iade.md` tool result, LLM input after tool result, final
answer, and TTS text.
Fail: Answering without the tool, retrieving the wrong corpus source, omitting
the relevant shipping/return fact, or inventing unsupported policy means
failure.
