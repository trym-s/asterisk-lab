"""Pipecat voicebot lane — parity twin of services/livekit/agent/agent.py.

Design axioms (change one, change both):
  * Identical OpenAI models: whisper-1 (with same domain prompt), gpt-4o-mini,
    tts-1 voice=alloy.
  * Identical SYSTEM_PROMPT and GREETING (copied verbatim from the LK lane).
  * Identical shared tool: lookup_docs → services/common/docqa.py.
  * Identical trace schema: same /var/lib/voicebot/events.jsonl stages.
  * Legacy /var/lib/voicebot/turns.jsonl remains as a debug rendering only.
  * Identical usage log: same /var/lib/voicebot/usage.jsonl entries so
    services/common/usage_summary.py sums both lanes together.

Framework differences (what we're measuring):
  * Pipeline architecture: pipecat's linear FrameProcessor chain vs. LK's
    VoicePipelineAgent orchestrator.
  * Media transport: Asterisk AudioSocket TCP (this lane) vs. LK's SIP GW +
    SFU (that lane).
  * Interruption/turn-taking: pipecat's UserStartedSpeaking/StoppedSpeaking
    frames + interruption strategy vs. LK's built-in VAD interruptions.

Audio is 8 kHz slin16 mono over AudioSocket to match the effective codec on
the LK side (PCMU 8 kHz). Wideband can come later; for the MVP we hold this
constant so the comparison isolates the framework.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

# Bind-mounted shared helpers (see docker-compose.yml).
sys.path.insert(0, "/opt/voicebot-common")
import docqa  # noqa: E402
import trace_events  # noqa: E402
import usage  # noqa: E402
import voicebot_profile  # noqa: E402

from audiosocket import (  # noqa: E402
    AudioSocketServer,
    AudioSocketSession,
    SAMPLE_RATE,
)

# Pipecat 1.4.0 module paths (they moved from earlier releases):
#   * Services live under pipecat.services.openai.{llm,stt,tts}
#   * Context is the framework-agnostic LLMContext + ToolsSchema
#   * Aggregators come from llm_response_universal (LLMContextAggregatorPair)
from pipecat.audio.vad.silero import SileroVADAnalyzer  # noqa: E402
from pipecat.audio.vad.vad_analyzer import VADParams  # noqa: E402
from pipecat.frames.frames import (  # noqa: E402
    EndFrame,
    Frame,
    InputAudioRawFrame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    OutputAudioRawFrame,
    TTSAudioRawFrame,
    TTSSpeakFrame,
    TextFrame,
    TranscriptionFrame,
    InterruptionFrame,
    UserStartedSpeakingFrame,
    VADUserStartedSpeakingFrame,
)
from pipecat.pipeline.pipeline import Pipeline  # noqa: E402
from pipecat.pipeline.runner import PipelineRunner  # noqa: E402
from pipecat.pipeline.task import PipelineParams, PipelineWorker  # noqa: E402
from pipecat.processors.audio.vad_processor import VADProcessor  # noqa: E402
from pipecat.processors.aggregators.llm_context import (  # noqa: E402
    FunctionSchema,
    LLMContext,
    ToolsSchema,
)
from pipecat.processors.aggregators.llm_response_universal import (  # noqa: E402
    LLMContextAggregatorPair,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor  # noqa: E402
from pipecat.services.openai.llm import OpenAILLMService  # noqa: E402
from pipecat.services.openai.stt import OpenAISTTService  # noqa: E402
from pipecat.services.openai.tts import OpenAITTSService  # noqa: E402

logger = logging.getLogger("pc-agent")
logging.basicConfig(level=logging.INFO)

LANE = "pipecat"

# ---- prompts + tool schema (parity with LK lane) ------------------------

SYSTEM_PROMPT = (
    "Sen Mavi Kapı Mağazası'nın sesli müşteri hizmetleri asistanısın. "
    "Türkçe konuş. Cevapların kısa ve net olsun (en fazla iki cümle). "
    "Müşteri mağaza saatleri, ürünler, fiyatlar, kargo, iade, iletişim "
    "gibi konularda soru sorarsa — cevap vermeden ÖNCE lookup_docs "
    "aracını çağırıp mağaza bilgi tabanında arama yap. Bulduğun bilgiye "
    "göre yanıtla. Sonuç boşsa 'elimizde bu bilgi yok' de, tahmin yürütme."
)

GREETING = "Merhaba, Mavi Kapı müşteri hizmetlerine hoş geldiniz. Nasıl yardımcı olabilirim?"

WHISPER_PROMPT = (
    "Mavi Kapı mağazası, çift kişilik, tek kişilik, king size, "
    "nevresim takımı, havlu, halı, perde, yastık, iade, kargo, "
    "İstanbul, Ankara, İzmir, Bursa, Antalya, Adana, Trabzon, "
    "Alsancak, Kadıköy, Çankaya, "
    "bir, iki, üç, dört, beş, altı, yedi, sekiz, dokuz, on, yüz, bin, "
    "yüz otuz beş, iki yüz kırk, üç yüz doksan, altı yüz elli, "
    "sekiz yüz doksan, bin iki yüz, lira, iş günü, gün, saat."
)

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


def _usage(**kwargs) -> None:
    try:
        usage.record(**kwargs)
    except Exception as e:  # noqa: BLE001
        logger.warning("usage event write failed: %s", e)


def _record_audiosocket_closed(session: AudioSocketSession, call_ctx: trace_events.CallContext) -> None:
    if getattr(session, "_trace_closed_recorded", False):
        return
    setattr(session, "_trace_closed_recorded", True)
    stats = session.audio_stats()
    _trace(
        lane=LANE,
        call_id=call_ctx.call_id,
        turn_id=call_ctx.current_turn_id,
        stage="audio",
        event="audiosocket.counters",
        provider="asterisk-audiosocket",
        payload=stats,
    )
    _trace(
        lane=LANE,
        call_id=call_ctx.call_id,
        stage="call",
        event="call.ended",
        provider="asterisk-audiosocket",
        payload={
            "uuid": session.uuid,
            "asterisk_audiosocket_uuid": session.uuid,
            "asterisk_uniqueid": session.uuid,
            "correlation_status": "audiosocket_uuid",
            "audio": stats,
        },
    )


def _pcm_s16le_mono_resample_nearest(audio: bytes, source_rate: int | None, target_rate: int) -> bytes:
    """Dependency-free mono s16le resampler for AudioSocket telephony output."""
    if not source_rate or source_rate == target_rate or len(audio) < 2:
        return audio
    samples = memoryview(audio).cast("h")
    target_len = max(1, int(len(samples) * target_rate / source_rate))
    out = bytearray(target_len * 2)
    for idx in range(target_len):
        src_idx = min(len(samples) - 1, int(idx * source_rate / target_rate))
        value = int(samples[src_idx])
        out[idx * 2:idx * 2 + 2] = value.to_bytes(2, "little", signed=True)
    return bytes(out)


def _norm_text(text: str) -> str:
    text = text.lower()
    text = text.replace("ı", "i").replace("ğ", "g").replace("ü", "u")
    text = text.replace("ş", "s").replace("ö", "o").replace("ç", "c")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _remember_bot_text(session: AudioSocketSession, text: str) -> None:
    recent = getattr(session, "_voicebot_recent_bot_texts", [])
    recent.append(_norm_text(text))
    setattr(session, "_voicebot_recent_bot_texts", recent[-12:])


def _token_overlap(a: str, b: str) -> float:
    left = set(_norm_text(a).split())
    right = set(_norm_text(b).split())
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


# Built lazily inside on_session so we can pass the per-call `tool_lookup_docs`
# with the right binding. LLMContext auto-registers handlers set on the schema.
def _build_tools_schema(handler) -> ToolsSchema:
    return ToolsSchema([
        FunctionSchema(
            name="lookup_docs",
            description=(
                "Mavi Kapı mağaza bilgi tabanında verilen sorguyla ilgili "
                "paragrafları arar ve döndürür."
            ),
            properties={
                "query": {
                    "type": "string",
                    "description": "Aranacak Türkçe veya İngilizce sorgu",
                }
            },
            required=["query"],
            handler=handler,
        )
    ])

# ---- legacy turn logging (debug only; acceptance uses events.jsonl) -----

TURN_LOG = Path("/var/lib/voicebot/turns.jsonl")


def _preview(content, limit: int = 400) -> str:
    if content is None:
        return ""
    if isinstance(content, list):
        content = " ".join(str(c) for c in content)
    s = str(content)
    return s if len(s) <= limit else s[:limit] + f"...<+{len(s) - limit}>"


def dump_turn(kind: str, room: str, payload: dict) -> None:
    try:
        TURN_LOG.parent.mkdir(parents=True, exist_ok=True)
        with TURN_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(
                {"ts": time.time(), "kind": kind, "room": room, **payload},
                ensure_ascii=False,
            ) + "\n")
    except Exception:  # noqa: BLE001
        pass


# ---- Pipecat FrameProcessors that bridge AudioSocket ↔ pipeline --------

class AudioSocketSource(FrameProcessor):
    """Pump slin16 8 kHz PCM from the AudioSocket into pipecat as InputAudioRawFrames.

    Pipecat 1.4 uses InputAudioRawFrame (not the generic AudioRawFrame) on the
    input side so that downstream processors — SileroVAD, STT — can distinguish
    caller audio from bot audio.
    """

    def __init__(self, session: AudioSocketSession, call_ctx: trace_events.CallContext):
        super().__init__()
        self.session = session
        self.call_ctx = call_ctx
        self._pump_task: asyncio.Task | None = None
        self._seen_audio = False

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        # Start the pump lazily on the first frame we see, so the pipeline is
        # fully wired before we start emitting audio.
        if self._pump_task is None:
            self._pump_task = asyncio.create_task(self._pump(), name="audiosocket-src")
        await self.push_frame(frame, direction)

    async def _pump(self) -> None:
        while True:
            payload = await self.session.inbound.get()
            if not payload:
                _record_audiosocket_closed(self.session, self.call_ctx)
                await self.push_frame(EndFrame())
                return
            if not self._seen_audio:
                self._seen_audio = True
                _trace(
                    lane=LANE,
                    call_id=self.call_ctx.call_id,
                    stage="audio",
                    event="audiosocket.inbound.started",
                    provider="asterisk-audiosocket",
                    payload={"uuid": self.session.uuid, "bytes": len(payload)},
                )
            await self.push_frame(
                InputAudioRawFrame(
                    audio=payload, sample_rate=SAMPLE_RATE, num_channels=1,
                )
            )


class AudioSocketSink(FrameProcessor):
    """Route pipecat TTS output back into the AudioSocket outbound queue."""

    def __init__(self, session: AudioSocketSession, call_ctx: trace_events.CallContext):
        super().__init__()
        self.session = session
        self.call_ctx = call_ctx
        self._seen_audio = False

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, (TTSAudioRawFrame, OutputAudioRawFrame)):
            source_rate = getattr(frame, "sample_rate", None)
            audio = _pcm_s16le_mono_resample_nearest(bytes(frame.audio), source_rate, SAMPLE_RATE)
            try:
                setattr(self.session, "_voicebot_real_audio_started", True)
                setattr(self.session, "_voicebot_last_outbound_audio_ts", time.monotonic())
                self.session.outbound.put_nowait(audio)
                if not self._seen_audio:
                    self._seen_audio = True
                    _trace(
                        lane=LANE,
                        call_id=self.call_ctx.call_id,
                        turn_id=self.call_ctx.current_turn_id,
                        stage="tts",
                        event="output_audio.started",
                        provider="openai",
                        model=MODEL_PROFILE.tts_model,
                        payload={
                            "bytes": len(audio),
                            "source_bytes": len(frame.audio),
                            "sample_rate": SAMPLE_RATE,
                            "source_sample_rate": source_rate,
                            "voice": MODEL_PROFILE.tts_voice,
                        },
                    )
            except asyncio.QueueFull:
                pass
        await self.push_frame(frame, direction)


class DirectLLMContextTrigger(FrameProcessor):
    """Push an LLMContextFrame immediately after a final STT transcript.

    Pipecat's LLMUserAggregator can wait for turn-strategy frames before it
    emits context. In the AudioSocket lane we already have an explicit final
    TranscriptionFrame from STT, so we write it to the shared context and run
    the LLM directly. This keeps the lane responsive on 8 kHz telephony audio.
    """

    def __init__(self, context: LLMContext):
        super().__init__()
        self.context = context

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame) and frame.text:
            self.context.add_message({"role": "user", "content": frame.text})
            await self.push_frame(LLMContextFrame(self.context), FrameDirection.DOWNSTREAM)
            return
        await self.push_frame(frame, direction)


class BotEchoFilter(FrameProcessor):
    """Drop STT transcripts that are clearly the bot's own audio.

    In this lab the host softphone often loops speaker audio back into the mic.
    Without this guard, phrases from the greeting or assistant reply become new
    user turns and the conversation drifts into self-talk.
    """

    STATIC_ECHOES = {
        "merhaba mavi kapi musteri hizmetlerine hos geldiniz nasil yardimci olabilirim",
        "nasil yardimci olabilirim",
        "size nasil yardimci olabilirim",
        "mavi kapi magazasi",
        "altyazi m k",
    }

    def __init__(self, session: AudioSocketSession, call_ctx: trace_events.CallContext):
        super().__init__()
        self.session = session
        self.call_ctx = call_ctx

    def _is_echo(self, text: str) -> bool:
        norm = _norm_text(text)
        if not norm:
            return True
        last_audio = getattr(self.session, "_voicebot_last_outbound_audio_ts", 0)
        since_bot_audio = time.monotonic() - last_audio
        if norm in self.STATIC_ECHOES:
            return True
        if "hos geldiniz" in norm and ("mavi kapi" in norm or "musteri" in norm):
            return True
        for bot_text in getattr(self.session, "_voicebot_recent_bot_texts", []):
            if not bot_text:
                continue
            if norm == bot_text:
                return True
            if len(norm) >= 10 and (norm in bot_text or bot_text in norm):
                return True
            if since_bot_audio < 4.0 and len(norm.split()) >= 4 and _token_overlap(norm, bot_text) >= 0.7:
                return True
        return False

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame) and frame.text and self._is_echo(frame.text):
            logger.info("drop_bot_echo=%r", frame.text)
            _trace(
                lane=LANE,
                call_id=self.call_ctx.call_id,
                turn_id=self.call_ctx.current_turn_id,
                stage="stt",
                event="echo_filtered",
                provider="pipecat",
                model=MODEL_PROFILE.stt_model,
                payload={"text": frame.text},
            )
            return
        await self.push_frame(frame, direction)


class BargeInAudioStopper(FrameProcessor):
    """Stop queued AudioSocket output as soon as caller speech begins."""

    def __init__(self, session: AudioSocketSession, call_ctx: trace_events.CallContext):
        super().__init__()
        self.session = session
        self.call_ctx = call_ctx

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, (VADUserStartedSpeakingFrame, UserStartedSpeakingFrame)):
            last_real_audio = getattr(self.session, "_voicebot_last_outbound_audio_ts", 0)
            if time.monotonic() - last_real_audio > 4.0:
                await self.push_frame(frame, direction)
                return
            dropped = self.session.clear_outbound()
            setattr(self.session, "_voicebot_last_barge_in_ts", time.monotonic())
            _trace(
                lane=LANE,
                call_id=self.call_ctx.call_id,
                turn_id=self.call_ctx.current_turn_id,
                stage="audio",
                event="barge_in.stop_bot_audio",
                provider="pipecat",
                payload={"dropped_outbound_frames": dropped},
            )
            await self.push_frame(InterruptionFrame(), FrameDirection.DOWNSTREAM)
        await self.push_frame(frame, direction)


class TurnLogger(FrameProcessor):
    """Mirror STT / LLM / TTS text to /var/lib/voicebot/turns.jsonl.

    Placed between the user-context-aggregator and the LLM so we see the
    fully-assembled context on the way in, and between the LLM and the TTS
    so we see the raw model text on the way out.
    """

    def __init__(self, session: AudioSocketSession, call_ctx: trace_events.CallContext):
        super().__init__()
        self.session = session
        self.call_ctx = call_ctx
        self._llm_parts: list[str] = []
        self._in_llm_response = False

    async def _record_agent_text(self, room: str, text: str) -> None:
        if not text:
            return
        logger.info("agent=%r", text)
        _trace(
            lane=LANE,
            call_id=self.call_ctx.call_id,
            turn_id=self.call_ctx.current_turn_id,
            stage="llm",
            event="response",
            provider="openai",
            model=MODEL_PROFILE.llm_model,
            payload={"text": text},
        )
        _usage(
            provider="openai",
            op="chat",
            units=max(len(text.split()), 1),
            unit_type="tokens_estimated",
            ref=self.call_ctx.call_id,
            lane=LANE,
            call_id=self.call_ctx.call_id,
            turn_id=self.call_ctx.current_turn_id,
            stage="llm",
            model=MODEL_PROFILE.llm_model,
            extra={"direction": "output", "estimated": True},
        )
        _trace(
            lane=LANE,
            call_id=self.call_ctx.call_id,
            turn_id=self.call_ctx.current_turn_id,
            stage="tts",
            event="request",
            provider="openai",
            model=MODEL_PROFILE.tts_model,
            payload={"text": text, "voice": MODEL_PROFILE.tts_voice, "characters": len(text)},
        )
        _usage(
            provider="openai",
            op="tts",
            units=len(text),
            unit_type="chars",
            ref=self.call_ctx.call_id,
            lane=LANE,
            call_id=self.call_ctx.call_id,
            turn_id=self.call_ctx.current_turn_id,
            stage="tts",
            model=MODEL_PROFILE.tts_model,
        )
        _remember_bot_text(self.session, text)
        dump_turn("agent_speech", room, {"text": text})

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        room = f"as-{self.call_ctx.call_id[:8]}"
        if isinstance(frame, LLMFullResponseStartFrame):
            self._llm_parts = []
            self._in_llm_response = True
        elif isinstance(frame, LLMFullResponseEndFrame):
            await self._record_agent_text(room, "".join(self._llm_parts).strip())
            self._llm_parts = []
            self._in_llm_response = False
        elif isinstance(frame, LLMTextFrame) and frame.text:
            self._llm_parts.append(frame.text)
        elif isinstance(frame, TranscriptionFrame) and frame.text:
            turn_id = self.call_ctx.next_turn()
            logger.info("user=%r", frame.text)
            stats = self.session.audio_stats()
            _trace(
                lane=LANE,
                call_id=self.call_ctx.call_id,
                turn_id=turn_id,
                stage="stt",
                event="final_transcript",
                provider="openai",
                model=MODEL_PROFILE.stt_model,
                payload={
                    "text": frame.text,
                    "language": "tr",
                    "audio_receive_boundary": "asterisk-audiosocket",
                    "audio": stats,
                },
            )
            _usage(
                provider="openai",
                op="stt",
                units=max(stats["inbound_duration_ms"] / 1000, 0),
                unit_type="seconds",
                ref=self.call_ctx.call_id,
                lane=LANE,
                call_id=self.call_ctx.call_id,
                turn_id=turn_id,
                stage="stt",
                model=MODEL_PROFILE.stt_model,
                extra={"source": "audiosocket_inbound_cumulative"},
            )
            _trace(
                lane=LANE,
                call_id=self.call_ctx.call_id,
                turn_id=turn_id,
                stage="llm",
                event="request",
                provider="openai",
                model=MODEL_PROFILE.llm_model,
                payload={
                    "model_profile": MODEL_PROFILE.asdict(),
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": frame.text},
                    ],
                    "tools": TOOL_SCHEMA,
                    "tool_policy": "auto",
                    "note": "Pipecat context aggregator may include prior turns at runtime.",
                },
            )
            _usage(
                provider="openai",
                op="chat",
                units=max(len((SYSTEM_PROMPT + " " + frame.text).split()), 1),
                unit_type="tokens_estimated",
                ref=self.call_ctx.call_id,
                lane=LANE,
                call_id=self.call_ctx.call_id,
                turn_id=turn_id,
                stage="llm",
                model=MODEL_PROFILE.llm_model,
                extra={"direction": "input", "estimated": True},
            )
            dump_turn("user_speech", room, {"text": frame.text})
        elif isinstance(frame, TextFrame) and frame.text:
            await self._record_agent_text(room, frame.text)
        await self.push_frame(frame, direction)


# ---- tool wiring (parity: same docqa, same usage.record) ---------------

def make_tool_lookup_docs(call_ctx: trace_events.CallContext):
    async def tool_lookup_docs(params) -> str:
        """LLM tool handler.

        Pipecat 1.4 delivers function results through params.result_callback();
        returning the string alone does not resume the LLM after a tool call.
        """
        # Different pipecat versions surface params differently.
        if hasattr(params, "arguments"):
            args = params.arguments
        else:
            args = params or {}
        query = args.get("query") if isinstance(args, dict) else str(args)
        logger.info("tool=lookup_docs query=%r", query)
        t0 = time.monotonic()
        _trace(
            lane=LANE,
            call_id=call_ctx.call_id,
            turn_id=call_ctx.current_turn_id,
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
            call_id=call_ctx.call_id,
            turn_id=call_ctx.current_turn_id,
            stage="tool",
            event="lookup_docs.result",
            provider="lab",
            model="keyword-search",
            duration_ms=duration_ms,
            payload={"query": query, "result": result, "tool": "lookup_docs"},
        )
        dump_turn("tool_call", "", {"tool": "lookup_docs", "query": query, "result": result})
        try:
            _usage(
                provider="lab",
                op="tool_call",
                units=1,
                unit_type="calls",
                ref="lookup_docs",
                lane=LANE,
                call_id=call_ctx.call_id,
                turn_id=call_ctx.current_turn_id,
                stage="tool",
                model="keyword-search",
                extra={"query": query},
            )
        except Exception:  # noqa: BLE001
            pass
        if hasattr(params, "result_callback"):
            await params.result_callback(result)
        return result

    return tool_lookup_docs


# ---- per-call pipeline ------------------------------------------------

async def on_session(session: AudioSocketSession) -> None:
    """Called by AudioSocketServer for every inbound call from Asterisk.

    Constructs a fresh pipecat pipeline per call. STT/LLM/TTS instances are
    per-call today; if per-call cost becomes an issue we can move to shared
    instances behind a semaphore, mirroring the LK JobProcess model.
    """
    # Wait for UUID (Asterisk sends it right after connect).
    for _ in range(20):
        if session.uuid:
            break
        await asyncio.sleep(0.05)
    call_id = session.uuid or "unknown-audiosocket-call"
    call_ctx = trace_events.CallContext(LANE, call_id)
    _trace(
        lane=LANE,
        call_id=call_ctx.call_id,
        stage="call",
        event="call.started",
        provider="asterisk-audiosocket",
        payload={
            "uuid": session.uuid,
            "asterisk_audiosocket_uuid": session.uuid,
            "asterisk_uniqueid": session.uuid,
            "correlation_status": "audiosocket_uuid",
            "listener": "0.0.0.0:8090",
        },
    )
    _trace(
        lane=LANE,
        call_id=call_ctx.call_id,
        stage="call",
        event="profile.loaded",
        provider="pipecat",
        payload=voicebot_profile.startup_metadata(
            lane=LANE,
            system_prompt=SYSTEM_PROMPT,
            tools=TOOL_SCHEMA,
            docs_root=docqa.DOCS_ROOT,
            corpus=docqa.CORPUS,
            repo_root=Path("/opt/voicebot-docs"),
        ),
    )

    stt = OpenAISTTService(
        model=MODEL_PROFILE.stt_model,
        api_key=os.environ["OPENAI_API_KEY"],
        language="tr",
        prompt=WHISPER_PROMPT,
    )
    llm = OpenAILLMService(
        model=MODEL_PROFILE.llm_model,
        api_key=os.environ["OPENAI_API_KEY"],
    )
    # OpenAI TTS only synthesizes at 24 kHz. Requesting 8 kHz silently produces
    # no audio (pipecat warns but doesn't error). We take 24 kHz here; the
    # audio_out_sample_rate=SAMPLE_RATE on PipelineParams tells pipecat to
    # resample the TTSAudioRawFrames down to 8 kHz before they hit the sink.
    tts = OpenAITTSService(
        model=MODEL_PROFILE.tts_model,
        voice=MODEL_PROFILE.tts_voice,
        api_key=os.environ["OPENAI_API_KEY"],
        sample_rate=24000,
    )

    # Bind the tool handler; LLMContext auto-registers it with the LLM service
    # because FunctionSchema has `handler=...` set.
    context = LLMContext(
        messages=[{"role": "system", "content": SYSTEM_PROMPT}],
        tools=_build_tools_schema(make_tool_lookup_docs(call_ctx)),
    )
    context_aggregator = LLMContextAggregatorPair(context)
    pipeline = Pipeline([
        AudioSocketSource(session, call_ctx),
        # VAD emits UserStartedSpeaking/UserStoppedSpeaking around the audio
        # so STT knows when to run and the LLM knows when to answer. In 1.4
        # it's a stand-alone FrameProcessor, no longer a PipelineParams knob.
        VADProcessor(
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(confidence=0.82, start_secs=0.45, stop_secs=0.35, min_volume=0.75)
            )
        ),
        BargeInAudioStopper(session, call_ctx),
        stt,
        BotEchoFilter(session, call_ctx),
        TurnLogger(session, call_ctx),
        DirectLLMContextTrigger(context),
        llm,
        TurnLogger(session, call_ctx),
        tts,
        AudioSocketSink(session, call_ctx),
        context_aggregator.assistant(),
    ])

    task = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=SAMPLE_RATE,
            audio_out_sample_rate=SAMPLE_RATE,
        ),
    )

    # Kick things off: greet the caller before waiting for STT.
    # TTSSpeakFrame instructs the TTS service to synthesize the given text
    # immediately, bypassing the LLM — mirrors LK's `agent.say(GREETING)`.
    async def _greet() -> None:
        await asyncio.sleep(0.5)  # let StartFrame propagate through the pipeline
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
        _usage(
            provider="openai",
            op="tts",
            units=len(GREETING),
            unit_type="chars",
            ref=call_ctx.call_id,
            lane=LANE,
            call_id=call_ctx.call_id,
            turn_id="greeting",
            stage="tts",
            model=MODEL_PROFILE.tts_model,
        )
        _remember_bot_text(session, GREETING)
        await task.queue_frames([TTSSpeakFrame(text=GREETING)])
        dump_turn("agent_speech", f"as-{session.uuid[:8]}", {"text": GREETING})

    runner = PipelineRunner()
    try:
        await asyncio.gather(runner.run(task), _greet())
    except Exception as e:  # noqa: BLE001
        _trace(
            lane=LANE,
            call_id=call_ctx.call_id,
            turn_id=call_ctx.current_turn_id,
            stage="error",
            event="pipeline.error",
            provider="pipecat",
            payload={"type": e.__class__.__name__, "message": str(e)},
        )
        raise
    finally:
        _record_audiosocket_closed(session, call_ctx)


async def amain() -> None:
    logger.info("pipecat agent starting")
    # Prewarm the OpenAI client cache — same rationale as the LK lane.
    try:
        import httpx
        with httpx.Client(timeout=10) as c:
            c.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
            )
        logger.info("prewarmed openai connection")
    except Exception:  # noqa: BLE001
        pass

    host = os.environ.get("AUDIOSOCKET_HOST", "0.0.0.0")
    port = int(os.environ.get("AUDIOSOCKET_PORT", "8090"))
    server = AudioSocketServer(host, port, on_session)
    await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(amain())
