"""LiveKit voice agent — Phase 2: STT+LLM+TTS with a `lookup_docs` tool.

Behaviour parity target: services/pipecat/agent/agent.py (lands next).
Both lanes:
  * Use identical OpenAI models (whisper-1, gpt-4o-mini, tts-1)
  * Share the same SYSTEM_PROMPT (below)
  * Bind the same `lookup_docs(query)` tool from services/common/docqa.py

The point of the parity is that any measured delta — latency, transcription
accuracy, tool-call rate, cost — is attributable to the framework, not
knobs we forgot to align.

The docqa corpus (README/PROCESS/AGENTS) is bind-mounted at /opt/voicebot-docs.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Annotated

import httpx

TURN_LOG = Path("/var/lib/voicebot/turns.jsonl")


def _preview(content, limit: int = 400) -> str:
    """Stringify + truncate for terminal-safe logging."""
    if content is None:
        return ""
    if isinstance(content, list):
        content = " ".join(str(c) for c in content)
    s = str(content)
    return s if len(s) <= limit else s[:limit] + f"...<+{len(s) - limit}>"


def _dump_turn(kind: str, room: str, payload: dict) -> None:
    """Append the full untruncated turn record for later replay."""
    try:
        TURN_LOG.parent.mkdir(parents=True, exist_ok=True)
        with TURN_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(
                {"ts": time.time(), "kind": kind, "room": room, **payload},
                ensure_ascii=False,
            ) + "\n")
    except Exception:  # noqa: BLE001
        pass
from livekit.agents import AutoSubscribe, JobContext, JobProcess, WorkerOptions, cli, llm
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import openai, silero

# services/common/ is bind-mounted at /opt/voicebot-common in the container.
sys.path.insert(0, "/opt/voicebot-common")
import docqa  # noqa: E402
import usage  # noqa: E402

logger = logging.getLogger("lk-agent")
logging.basicConfig(level=logging.INFO)

# Both lanes must load an identical prompt for the comparison to hold.
# When you change this, also change services/pipecat/agent/agent.py.
SYSTEM_PROMPT = (
    "Sen Mavi Kapı Mağazası'nın sesli müşteri hizmetleri asistanısın. "
    "Türkçe konuş. Cevapların kısa ve net olsun (en fazla iki cümle). "
    "Müşteri mağaza saatleri, ürünler, fiyatlar, kargo, iade, iletişim "
    "gibi konularda soru sorarsa — cevap vermeden ÖNCE lookup_docs "
    "aracını çağırıp mağaza bilgi tabanında arama yap. Bulduğun bilgiye "
    "göre yanıtla. Sonuç boşsa 'elimizde bu bilgi yok' de, tahmin yürütme."
)

GREETING = "Merhaba, Mavi Kapı müşteri hizmetlerine hoş geldiniz. Nasıl yardımcı olabilirim?"


class LabTools(llm.FunctionContext):
    @llm.ai_callable(
        description=(
            "Asterisk lab dokümanlarında (README, PROCESS, AGENTS) "
            "verilen sorguyla ilgili paragrafları arar ve döndürür. "
            "Lab yapısı, kullanılan servisler, kurulum, konfigürasyon "
            "gibi sorular için çağır."
        ),
    )
    async def lookup_docs(
        self,
        query: Annotated[str, llm.TypeInfo(description="Aranacak Türkçe veya İngilizce sorgu")],
    ) -> str:
        logger.info("tool=lookup_docs query=%r", query)
        result = docqa.search(query, top_n=3)
        logger.info("tool_result=%s", _preview(result))
        _dump_turn("tool_call", "", {
            "tool": "lookup_docs", "query": query, "result": result,
        })
        try:
            usage.record(provider="lab", op="tool_call", units=1,
                         unit_type="calls", ref="lookup_docs",
                         extra={"query": query})
        except Exception:  # noqa: BLE001
            pass
        return result


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
    except Exception as e:  # noqa: BLE001
        logger.warning("prewarm connection warmup failed: %s", e)
        return
    logger.info("prewarmed openai connection in %d ms", int((time.monotonic() - t0) * 1000))


async def entrypoint(ctx: JobContext) -> None:
    t_join = time.monotonic()
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    logger.info("joined room=%s join_ms=%d", ctx.room.name, int((time.monotonic() - t_join) * 1000))

    initial_ctx = llm.ChatContext().append(role="system", text=SYSTEM_PROMPT)

    async def before_llm(agent, chat_ctx: llm.ChatContext) -> None:
        """Fires just before the LLM is called.

        Dumps the full message list the model will see (system prompt, prior
        turns, tool results, latest user turn) plus the registered function
        schemas. Truncates long system prompts in the terminal but writes
        the full JSON to /var/lib/voicebot/turns.jsonl for later inspection.
        """
        msgs = [{"role": m.role, "content": _preview(m.content)} for m in chat_ctx.messages]
        fns = [f.name for f in agent.fnc_ctx.ai_functions.values()] if agent.fnc_ctx else []
        logger.info("llm_in room=%s msgs=%d fns=%s last=%r",
                    ctx.room.name, len(msgs), fns,
                    msgs[-1] if msgs else None)
        _dump_turn("llm_in", ctx.room.name, {"messages": msgs, "functions": fns})

    async def before_tts(agent, text):
        """Fires with the LLM's completed text (or stream) before TTS starts.

        `text` can be a str or an async iterator of str chunks. We buffer
        chunks so the raw completion (including any tool-call fallout) shows
        up in one log line per turn.
        """
        if isinstance(text, str):
            buf = text
        else:
            chunks: list[str] = []
            async for c in text:
                chunks.append(c)
                yield c
            buf = "".join(chunks)
            logger.info("llm_out room=%s text=%r", ctx.room.name, buf)
            _dump_turn("llm_out", ctx.room.name, {"text": buf})
            return
        logger.info("llm_out room=%s text=%r", ctx.room.name, buf)
        _dump_turn("llm_out", ctx.room.name, {"text": buf})
        yield buf

    agent = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=openai.STT(
            model="whisper-1",
            language="tr",
            # Whisper accepts a `prompt` up to 224 tokens that biases decoding
            # toward the vocabulary listed. On 8 kHz PCMU telephony audio the
            # decoder confuses Turkish consonants (ç↔l, ş↔s) and short number
            # words (bir/iki/üç) freely. Seeding domain vocab + numbers + city
            # names shifts the language-model prior enough to reduce those errors
            # without changing model or codec.
            prompt=(
                "Mavi Kapı mağazası, çift kişilik, tek kişilik, king size, "
                "nevresim takımı, havlu, halı, perde, yastık, iade, kargo, "
                "İstanbul, Ankara, İzmir, Bursa, Antalya, Adana, Trabzon, "
                "Alsancak, Kadıköy, Çankaya, "
                "bir, iki, üç, dört, beş, altı, yedi, sekiz, dokuz, on, yüz, bin, "
                "yüz otuz beş, iki yüz kırk, üç yüz doksan, altı yüz elli, "
                "sekiz yüz doksan, bin iki yüz, lira, iş günü, gün, saat."
            ),
        ),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=openai.TTS(model="tts-1", voice="alloy"),
        chat_ctx=initial_ctx,
        fnc_ctx=LabTools(),
        preemptive_synthesis=True,
        before_llm_cb=before_llm,
        before_tts_cb=before_tts,
    )

    @agent.on("user_speech_committed")
    def _log_user(msg: llm.ChatMessage) -> None:
        logger.info("user=%r", msg.content)
        _dump_turn("user_speech", ctx.room.name, {"text": msg.content})

    @agent.on("agent_speech_committed")
    def _log_agent(msg: llm.ChatMessage) -> None:
        logger.info("agent=%r", msg.content)
        _dump_turn("agent_speech", ctx.room.name, {"text": msg.content})

    @agent.on("function_calls_finished")
    def _log_fn(calls: list) -> None:
        # Sometimes the plugin emits a bare list; be defensive.
        try:
            names = [getattr(c, "name", None) or c.function_info.name for c in calls]
            logger.info("fn_calls=%s", names)
        except Exception:  # noqa: BLE001
            pass

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
