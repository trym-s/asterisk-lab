# VAL-VOICEBOT-DOCS-002: Product-price questions are grounded in docs

Surface: SIP call and trace artifact.
Needs: Passing `VAL-VOICEBOT-TRACE-001` and `VAL-VOICEBOT-TRACE-002`.
Behavior: For the question "Banyo havlusu ne kadar?", both lanes call
`lookup_docs`, retrieve relevant content from `urunler.md`, and answer in
Turkish with the banyo havlusu price from the corpus.
Evidence: Validator records LiveKit and Pipecat trace rows showing STT text,
tool query, `urunler.md` tool result, LLM input after tool result, final answer,
and TTS text.
Fail: Answering without the tool, retrieving the wrong corpus source, omitting
the price, or inventing a different price means failure.
