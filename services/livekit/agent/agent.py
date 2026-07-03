"""LiveKit voice agent — Phase 1 smoke test.

Bare-minimum agent used to validate the SIP → SFU → agent → OpenAI path.
Confirms:
  * SIP INVITE from Asterisk reaches the LiveKit SIP gateway
  * The SFU dispatches this worker into the per-call room
  * Audio flows both ways (wideband codec negotiated via pjsip.conf.tmpl)
  * OpenAI Whisper / gpt-4o-mini / tts-1 all reachable from the container

No tools, no retrieval — those land in Phase 2 alongside services/common/docqa.
Kept intentionally symmetric with services/pipecat/agent/agent.py so the two
stacks can be compared on identical prompts and models.
"""

from __future__ import annotations

import logging
import sys
import time

import httpx
from livekit.agents import AutoSubscribe, JobContext, JobProcess, WorkerOptions, cli, llm
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import openai, silero

# services/common/ is bind-mounted at /opt/voicebot-common in the container.
sys.path.insert(0, "/opt/voicebot-common")
import usage  # noqa: E402

logger = logging.getLogger("lk-smoke")
logging.basicConfig(level=logging.INFO)

SYSTEM_PROMPT = (
    "Sen bir test asistanısın. Türkçe konuş. Cevapların çok kısa olsun "
    "(en fazla iki cümle). Amaç sesli hattın çalıştığını doğrulamak."
)

GREETING = "Merhaba, sizi duyabiliyorum. Size nasıl yardımcı olabilirim?"


def prewarm(proc: JobProcess) -> None:
    """Load VAD + warm the OpenAI connection pool in the worker process.

    On the very first call, cold DNS + TLS + HTTP/2 handshake to api.openai.com
    can push the greeting past a caller's patience (observed 5–7 s wait).
    A single GET /v1/models here primes the shared httpx client that
    livekit-plugins-openai will reuse, so the greeting TTS on the first real
    call skips the ~1–2 s handshake cost.
    """
    proc.userdata["vad"] = silero.VAD.load()

    t0 = time.monotonic()
    try:
        with httpx.Client(timeout=10.0, http2=False) as client:
            client.get("https://api.openai.com/v1/models", headers={"User-Agent": "prewarm"})
    except Exception as e:
        logger.warning("prewarm connection warmup failed: %s", e)
        return
    logger.info("prewarmed openai connection in %d ms", int((time.monotonic() - t0) * 1000))


async def entrypoint(ctx: JobContext) -> None:
    t_join = time.monotonic()
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    logger.info("joined room=%s join_ms=%d", ctx.room.name, int((time.monotonic() - t_join) * 1000))

    initial_ctx = llm.ChatContext().append(role="system", text=SYSTEM_PROMPT)

    agent = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=openai.STT(model="whisper-1", language="tr"),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=openai.TTS(model="tts-1", voice="alloy"),
        chat_ctx=initial_ctx,
        # Start TTS as LLM tokens stream in, don't wait for full response.
        # Cuts perceived latency on reply turns by ~500-800 ms.
        preemptive_synthesis=True,
    )

    @agent.on("user_speech_committed")
    def _log_user(msg: llm.ChatMessage) -> None:
        logger.info("user=%r", msg.content)

    @agent.on("agent_speech_committed")
    def _log_agent(msg: llm.ChatMessage) -> None:
        logger.info("agent=%r", msg.content)

    @agent.on("metrics_collected")
    def _log_metrics(m) -> None:
        """livekit-agents emits STT/LLM/TTS metrics after each turn.

        Payload varies by plugin but each object exposes duration/tokens/chars
        via well-known attributes. We defensively getattr so a schema drift
        in a future plugin release only loses that one signal instead of
        crashing the callback.
        """
        room = ctx.room.name
        cls = m.__class__.__name__
        try:
            if "STT" in cls:
                secs = getattr(m, "audio_duration", None)
                if secs is not None:
                    usage.record(provider="openai", op="stt", units=float(secs),
                                 unit_type="seconds", ref=room)
            elif "LLM" in cls:
                pt = getattr(m, "prompt_tokens", None)
                ct = getattr(m, "completion_tokens", None)
                if pt is not None:
                    usage.record(provider="openai", op="chat", units=float(pt),
                                 unit_type="tokens_in", ref=room)
                if ct is not None:
                    usage.record(provider="openai", op="chat", units=float(ct),
                                 unit_type="tokens_out", ref=room)
            elif "TTS" in cls:
                chars = getattr(m, "characters_count", None)
                if chars is not None:
                    usage.record(provider="openai", op="tts", units=float(chars),
                                 unit_type="chars", ref=room)
        except Exception as e:  # noqa: BLE001
            logger.warning("usage record failed: %s (metrics=%s)", e, cls)

    participant = await ctx.wait_for_participant()
    agent.start(ctx.room, participant)
    await agent.say(GREETING, allow_interruptions=True)


if __name__ == "__main__":
    # No agent_name → worker auto-dispatches to every new room the SFU creates
    # (SIP GW spins one room per inbound call via the dispatch rule below).
    # Adding a name would require explicit dispatch config on the rule.
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
