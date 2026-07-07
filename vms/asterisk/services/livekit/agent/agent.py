"""LiveKit voice agent — Phase 2: STT+LLM+TTS with a `lookup_docs` tool.

Behaviour parity target: services/pipecat/agent/agent.py (lands next).
Both lanes:
  * Use identical OpenAI models (whisper-1, gpt-4o-mini, tts-1)
  * Share the same SYSTEM_PROMPT (below)
  * Bind the same `lookup_docs(query)` tool from services/common/docqa.py
  * Emit the same /var/lib/voicebot/events.jsonl schema

The point of the parity is that any measured delta — latency, transcription
accuracy, tool-call rate, cost — is attributable to the framework, not
knobs we forgot to align.

The docqa corpus is the shared Mavi Kapı store corpus under
services/common/docs/magaza/.
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
    """Append legacy debug turn records; acceptance uses events.jsonl."""
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
import trace_events  # noqa: E402
import usage  # noqa: E402
import voicebot_profile  # noqa: E402

logger = logging.getLogger("lk-agent")
logging.basicConfig(level=logging.INFO)

LANE = "livekit"

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

TOOL_SCHEMA = [
    {
        "name": "lookup_docs",
        "description": "Mavi Kapı mağaza bilgi tabanında verilen sorguyla ilgili paragrafları arar.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Aranacak Türkçe veya İngilizce sorgu",
                }
            },
            "required": ["query"],
        },
    }
]

MODEL_PROFILE = voicebot_profile.load_model_profile()


def _trace(**kwargs) -> None:
    try:
        trace_events.record_event(**kwargs)
    except Exception as e:  # noqa: BLE001
        logger.warning("trace event write failed: %s", e)


def _message_payload(messages) -> list[dict]:
    rows: list[dict] = []
    for message in messages:
        rows.append({
            "role": getattr(message, "role", None),
            "content": getattr(message, "content", None),
        })
    return rows


class LabTools(llm.FunctionContext):
    def __init__(self, call_ctx: trace_events.CallContext):
        super().__init__()
        self.call_ctx = call_ctx

    @llm.ai_callable(
        description=(
            "Mavi Kapı mağaza bilgi tabanında verilen sorguyla ilgili "
            "paragrafları arar ve döndürür."
        ),
    )
    async def lookup_docs(
        self,
        query: Annotated[str, llm.TypeInfo(description="Aranacak Türkçe veya İngilizce sorgu")],
    ) -> str:
        logger.info("tool=lookup_docs query=%r", query)
        turn_id = self.call_ctx.current_turn_id
        t0 = time.monotonic()
        _trace(
            lane=LANE,
            call_id=self.call_ctx.call_id,
            turn_id=turn_id,
            stage="tool",
            event="lookup_docs.request",
            provider="lab",
            model="keyword-search",
            payload={"query": query, "tool": "lookup_docs"},
        )
        result = docqa.search(query, top_n=3)
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.info("tool_result=%s", _preview(result))
        _trace(
            lane=LANE,
            call_id=self.call_ctx.call_id,
            turn_id=turn_id,
            stage="tool",
            event="lookup_docs.result",
            provider="lab",
            model="keyword-search",
            duration_ms=duration_ms,
            payload={"query": query, "result": result, "tool": "lookup_docs"},
        )
        _dump_turn("tool_call", "", {
            "tool": "lookup_docs", "query": query, "result": result,
        })
        try:
            usage.record(provider="lab", op="tool_call", units=1,
                         unit_type="calls", ref="lookup_docs",
                         lane=LANE, call_id=self.call_ctx.call_id,
                         turn_id=turn_id, stage="tool", model="keyword-search",
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
    proc.userdata["vad"] = silero.VAD.load(
        # LiveKit's defaults are tuned for clean mics. On SIP/PCMU telephony
        # they treat very quiet room noise as speech, which creates ghost turns.
        min_speech_duration=float(os.environ.get("LIVEKIT_VAD_MIN_SPEECH_DURATION", "0.25")),
        min_silence_duration=float(os.environ.get("LIVEKIT_VAD_MIN_SILENCE_DURATION", "0.55")),
        prefix_padding_duration=float(os.environ.get("LIVEKIT_VAD_PREFIX_PADDING_DURATION", "0.25")),
        activation_threshold=float(os.environ.get("LIVEKIT_VAD_ACTIVATION_THRESHOLD", "0.62")),
        sample_rate=8000,
    )

    t0 = time.monotonic()
    try:
        with httpx.Client(timeout=10.0, http2=False) as client:
            client.get(
                "https://api.openai.com/v1/models",
                headers={
                    "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                    "User-Agent": "prewarm",
                },
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("prewarm connection warmup failed: %s", e)
        return
    logger.info("prewarmed openai connection in %d ms", int((time.monotonic() - t0) * 1000))


async def entrypoint(ctx: JobContext) -> None:
    t_join = time.monotonic()
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    join_ms = int((time.monotonic() - t_join) * 1000)
    call_ctx = trace_events.CallContext(LANE, ctx.room.name)
    logger.info("joined room=%s join_ms=%d", ctx.room.name, join_ms)
    _trace(
        lane=LANE,
        call_id=call_ctx.call_id,
        stage="call",
        event="call.started",
        provider="livekit",
        duration_ms=join_ms,
        payload={"room": ctx.room.name},
    )
    _trace(
        lane=LANE,
        call_id=call_ctx.call_id,
        stage="call",
        event="profile.loaded",
        provider="livekit",
        payload=voicebot_profile.startup_metadata(
            lane=LANE,
            system_prompt=SYSTEM_PROMPT,
            tools=TOOL_SCHEMA,
            docs_root=docqa.DOCS_ROOT,
            corpus=docqa.CORPUS,
            repo_root=Path("/opt/voicebot-docs"),
        ),
    )

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
        _trace(
            lane=LANE,
            call_id=call_ctx.call_id,
            turn_id=call_ctx.current_turn_id,
            stage="llm",
            event="request",
            provider="openai",
            model=MODEL_PROFILE.llm_model,
            payload={
                "model_profile": MODEL_PROFILE.asdict(),
                "messages": _message_payload(chat_ctx.messages),
                "tools": TOOL_SCHEMA,
                "tool_policy": "auto",
            },
        )
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
            _trace(
                lane=LANE,
                call_id=call_ctx.call_id,
                turn_id=call_ctx.current_turn_id,
                stage="llm",
                event="response",
                provider="openai",
                model=MODEL_PROFILE.llm_model,
                payload={"text": buf},
            )
            _trace(
                lane=LANE,
                call_id=call_ctx.call_id,
                turn_id=call_ctx.current_turn_id,
                stage="tts",
                event="request",
                provider="openai",
                model=MODEL_PROFILE.tts_model,
                payload={"text": buf, "voice": MODEL_PROFILE.tts_voice, "characters": len(buf)},
            )
            _dump_turn("llm_out", ctx.room.name, {"text": buf})
            return
        logger.info("llm_out room=%s text=%r", ctx.room.name, buf)
        _trace(
            lane=LANE,
            call_id=call_ctx.call_id,
            turn_id=call_ctx.current_turn_id,
            stage="llm",
            event="response",
            provider="openai",
            model=MODEL_PROFILE.llm_model,
            payload={"text": buf},
        )
        _trace(
            lane=LANE,
            call_id=call_ctx.call_id,
            turn_id=call_ctx.current_turn_id,
            stage="tts",
            event="request",
            provider="openai",
            model=MODEL_PROFILE.tts_model,
            payload={"text": buf, "voice": MODEL_PROFILE.tts_voice, "characters": len(buf)},
        )
        _dump_turn("llm_out", ctx.room.name, {"text": buf})
        yield buf

    agent = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=openai.STT(
            model=MODEL_PROFILE.stt_model,
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
        llm=openai.LLM(model=MODEL_PROFILE.llm_model),
        tts=openai.TTS(model=MODEL_PROFILE.tts_model, voice=MODEL_PROFILE.tts_voice),
        chat_ctx=initial_ctx,
        fnc_ctx=LabTools(call_ctx),
        allow_interruptions=True,
        interrupt_speech_duration=float(os.environ.get("LIVEKIT_INTERRUPT_SPEECH_DURATION", "0.7")),
        interrupt_min_words=int(os.environ.get("LIVEKIT_INTERRUPT_MIN_WORDS", "1")),
        min_endpointing_delay=float(os.environ.get("LIVEKIT_MIN_ENDPOINTING_DELAY", "0.7")),
        preemptive_synthesis=True,
        before_llm_cb=before_llm,
        before_tts_cb=before_tts,
    )

    @agent.on("user_speech_committed")
    def _log_user(msg: llm.ChatMessage) -> None:
        turn_id = call_ctx.next_turn()
        logger.info("user=%r", msg.content)
        _trace(
            lane=LANE,
            call_id=call_ctx.call_id,
            turn_id=turn_id,
            stage="stt",
            event="final_transcript",
            provider="openai",
            model=MODEL_PROFILE.stt_model,
            payload={
                "text": msg.content,
                "language": "tr",
                "audio_receive_boundary": "livekit.audio_only.track",
            },
        )
        _dump_turn("user_speech", ctx.room.name, {"text": msg.content})

    @agent.on("agent_speech_committed")
    def _log_agent(msg: llm.ChatMessage) -> None:
        logger.info("agent=%r", msg.content)
        _trace(
            lane=LANE,
            call_id=call_ctx.call_id,
            turn_id=call_ctx.current_turn_id,
            stage="tts",
            event="speech_committed",
            provider="livekit",
            model=MODEL_PROFILE.tts_model,
            payload={"text": msg.content},
        )
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
                                 unit_type="seconds", ref=room,
                                 lane=LANE, call_id=call_ctx.call_id,
                                 turn_id=call_ctx.current_turn_id,
                                 stage="stt", model=MODEL_PROFILE.stt_model)
                    _trace(
                        lane=LANE,
                        call_id=call_ctx.call_id,
                        turn_id=call_ctx.current_turn_id,
                        stage="stt",
                        event="metrics",
                        provider="openai",
                        model=MODEL_PROFILE.stt_model,
                        payload={"audio_duration_seconds": float(secs)},
                    )
            elif "LLM" in cls:
                pt = getattr(m, "prompt_tokens", None)
                ct = getattr(m, "completion_tokens", None)
                if pt is not None:
                    usage.record(provider="openai", op="chat", units=float(pt),
                                 unit_type="tokens_in", ref=room,
                                 lane=LANE, call_id=call_ctx.call_id,
                                 turn_id=call_ctx.current_turn_id,
                                 stage="llm", model=MODEL_PROFILE.llm_model)
                if ct is not None:
                    usage.record(provider="openai", op="chat", units=float(ct),
                                 unit_type="tokens_out", ref=room,
                                 lane=LANE, call_id=call_ctx.call_id,
                                 turn_id=call_ctx.current_turn_id,
                                 stage="llm", model=MODEL_PROFILE.llm_model)
                _trace(
                    lane=LANE,
                    call_id=call_ctx.call_id,
                    turn_id=call_ctx.current_turn_id,
                    stage="llm",
                    event="metrics",
                    provider="openai",
                    model=MODEL_PROFILE.llm_model,
                    payload={"prompt_tokens": pt, "completion_tokens": ct},
                )
            elif "TTS" in cls:
                chars = getattr(m, "characters_count", None)
                if chars is not None:
                    usage.record(provider="openai", op="tts", units=float(chars),
                                 unit_type="chars", ref=room,
                                 lane=LANE, call_id=call_ctx.call_id,
                                 turn_id=call_ctx.current_turn_id,
                                 stage="tts", model=MODEL_PROFILE.tts_model)
                    _trace(
                        lane=LANE,
                        call_id=call_ctx.call_id,
                        turn_id=call_ctx.current_turn_id,
                        stage="tts",
                        event="output",
                        provider="openai",
                        model=MODEL_PROFILE.tts_model,
                        payload={"characters": chars, "voice": MODEL_PROFILE.tts_voice},
                    )
        except Exception as e:  # noqa: BLE001
            logger.warning("usage record failed: %s (metrics=%s)", e, cls)

    participant = await ctx.wait_for_participant()
    _trace(
        lane=LANE,
        call_id=call_ctx.call_id,
        stage="audio",
        event="participant.attached",
        provider="livekit",
        payload={"participant": getattr(participant, "identity", None)},
    )
    agent.start(ctx.room, participant)
    _trace(
        lane=LANE,
        call_id=call_ctx.call_id,
        turn_id="greeting",
        stage="tts",
        event="request",
        provider="openai",
        model=MODEL_PROFILE.tts_model,
        payload={"text": GREETING, "voice": MODEL_PROFILE.tts_voice, "characters": len(GREETING)},
    )
    await agent.say(GREETING, allow_interruptions=True)


if __name__ == "__main__":
    # No agent_name → worker auto-dispatches to every new room the SFU creates
    # (SIP GW spins one room per inbound call via the dispatch rule below).
    # Adding a name would require explicit dispatch config on the rule.
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
