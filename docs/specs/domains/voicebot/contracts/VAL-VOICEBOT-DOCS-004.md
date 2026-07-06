# VAL-VOICEBOT-DOCS-004: Out-of-corpus questions do not hallucinate

Surface: SIP call and trace artifact.
Needs: Passing `VAL-VOICEBOT-TRACE-001` and `VAL-VOICEBOT-TRACE-002`.
Behavior: For a customer question outside the Mavi Kapi corpus, both lanes call
`lookup_docs` when the question asks for store facts, surface the no-hit tool
result to the LLM, and answer that the information is not available instead of
inventing a fact.
Evidence: Validator records LiveKit and Pipecat trace rows showing the no-hit
tool result, LLM input containing that result, final answer, and TTS text.
Fail: Unsupported product, price, policy, branch, or contact claims on no-hit
tool results mean failure.
