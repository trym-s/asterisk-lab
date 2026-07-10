"""Pipecat voicebot lane — Soniox streaming STT/TTS with an OpenAI LLM.

Architecture (mirrors the Soniox voice-agent reference design):
  * Transport: Asterisk AudioSocket channel driver, slin16 @ 16 kHz mono,
    20 ms ptime. Asterisk connects to our TCP listener per call.
  * Ears: SonioxSTTService (WebSocket, model stt-rt-v5). Semantic endpoint
    detection is ON — Soniox emits a final "<end>"-terminated transcript
    when the caller's sentence is complete. That final TranscriptionFrame
    is the ONLY turn-end signal; VAD silence thresholds never end a turn.
  * Brain: OpenAI chat model (token streaming) + the shared lookup_docs
    tool from services/common/docqa.py.
  * Mouth: SonioxTTSService (WebSocket, streaming text in / PCM out at
    16 kHz natively — no resampling anywhere in this file).
  * Reflex: Silero VAD is kept ONLY as the barge-in trigger: caller speech
    while the bot is talking clears queued output audio immediately.

Observability contract (unchanged surfaces, richer content):
  * /var/lib/voicebot/events.jsonl — voicebot-events-v1 stages; stt/llm/tts
    events now carry measured duration_ms (endpoint latency, LLM total,
    first-audio) with latency_basis="measured".
  * /var/lib/voicebot/usage.jsonl — Soniox STT seconds + TTS chars, OpenAI
    token estimates; priced by services/common/usage_summary.py.
  * /var/lib/voicebot/turns.jsonl — legacy debug rendering only.
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

from pipecat.audio.vad.silero import SileroVADAnalyzer  # noqa: E402
from pipecat.audio.vad.vad_analyzer import VADParams  # noqa: E402
from pipecat.frames.frames import (  # noqa: E402
    EndFrame,
    Frame,
    InputAudioRawFrame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    InterimTranscriptionFrame,
    LLMTextFrame,
    OutputAudioRawFrame,
    TTSAudioRawFrame,
    TTSSpeakFrame,
    TextFrame,
    TranscriptionFrame,
    InterruptionFrame,
    UserStartedSpeakingFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
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
from pipecat.services.soniox.stt import (  # noqa: E402
    SonioxContextGeneralItem,
    SonioxContextObject,
    SonioxSTTService,
)
from pipecat.services.soniox.tts import SonioxTTSService  # noqa: E402
from pipecat.transcriptions.language import Language  # noqa: E402

logger = logging.getLogger("pc-agent")
logging.basicConfig(level=logging.INFO)

LANE = "pipecat"

ECHO_FILTER_ENABLED = os.environ.get("VOICEBOT_ECHO_FILTER", "1") not in ("0", "false", "")


def _env_int(name: str) -> int | None:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else None


def _env_float(name: str) -> float | None:
    raw = os.environ.get(name, "").strip()
    return float(raw) if raw else None


# ---- prompts + tool schema ----------------------------------------------

SYSTEM_PROMPT = (
    "Sen Mavi Kapı Mağazası'nın sesli müşteri hizmetleri asistanısın. "
    "Türkçe konuş. Cevapların kısa ve net olsun (en fazla iki cümle). "
    "Müşteri mağaza saatleri, ürünler, fiyatlar, kargo, iade, iletişim "
    "gibi konularda soru sorarsa — cevap vermeden ÖNCE lookup_docs "
    "aracını çağırıp mağaza bilgi tabanında arama yap. Bulduğun bilgiye "
    "göre yanıtla. Sonuç boşsa 'elimizde bu bilgi yok' de, tahmin yürütme."
)

GREETING = "Merhaba, Mavi Kapı müşteri hizmetlerine hoş geldiniz. Nasıl yardımcı olabilirim?"

# Domain context for Soniox STT (context_version 2). Replaces the old
# Whisper prompt-seeding hack: terms bias recognition toward the store's
# vocabulary, product names, cities and Turkish numbers.
STT_CONTEXT = SonioxContextObject(
    general=[
        SonioxContextGeneralItem(key="domain", value="ev tekstili mağazası müşteri hizmetleri"),
        SonioxContextGeneralItem(key="company", value="Mavi Kapı Mağazası"),
    ],
    terms=[
        "Mavi Kapı", "nevresim takımı", "çift kişilik", "tek kişilik",
        "king size", "havlu", "halı", "perde", "yastık", "iade", "kargo",
        "iş günü", "lira", "İstanbul", "Ankara", "İzmir", "Bursa",
        "Antalya", "Adana", "Trabzon", "Alsancak", "Kadıköy", "Çankaya",
    ],
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


# ---- Pipecat FrameProcessors that bridge AudioSocket <-> pipeline -------

class AudioSocketSource(FrameProcessor):
    """Pump 16 kHz slin PCM from the AudioSocket into pipecat as InputAudioRawFrames."""

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
                    payload={"uuid": self.session.uuid, "bytes": len(payload), "sample_rate": SAMPLE_RATE},
                )
            await self.push_frame(
                InputAudioRawFrame(
                    audio=payload, sample_rate=SAMPLE_RATE, num_channels=1,
                )
            )


class AudioSocketSink(FrameProcessor):
    """Route TTS output audio into the AudioSocket outbound queue.

    Soniox TTS synthesizes at the pipeline's 16 kHz directly, so audio passes
    through untouched. A sample-rate mismatch is a config error and is logged
    once instead of being papered over with a resampler.
    """

    def __init__(self, session: AudioSocketSession, call_ctx: trace_events.CallContext):
        super().__init__()
        self.session = session
        self.call_ctx = call_ctx
        self._seen_audio = False
        self._rate_warned = False

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, (TTSAudioRawFrame, OutputAudioRawFrame)):
            source_rate = getattr(frame, "sample_rate", None)
            if source_rate and source_rate != SAMPLE_RATE and not self._rate_warned:
                self._rate_warned = True
                logger.error(
                    "TTS produced %s Hz but AudioSocket runs at %s Hz — fix the TTS sample_rate",
                    source_rate, SAMPLE_RATE,
                )
            audio = bytes(frame.audio)
            try:
                setattr(self.session, "_voicebot_real_audio_started", True)
                setattr(self.session, "_voicebot_last_outbound_audio_ts", time.monotonic())
                self.session.outbound.put_nowait(audio)
                if not self._seen_audio or getattr(self.session, "_voicebot_turn_first_audio_pending", False):
                    turn_t0 = getattr(self.session, "_voicebot_turn_t0", None)
                    first_audio_ms = (
                        int((time.monotonic() - turn_t0) * 1000) if turn_t0 is not None else None
                    )
                    setattr(self.session, "_voicebot_turn_first_audio_pending", False)
                    self._seen_audio = True
                    _trace(
                        lane=LANE,
                        call_id=self.call_ctx.call_id,
                        turn_id=self.call_ctx.current_turn_id,
                        stage="tts",
                        event="output_audio.started",
                        provider=MODEL_PROFILE.tts_provider,
                        model=MODEL_PROFILE.tts_model,
                        duration_ms=first_audio_ms,
                        payload={
                            "bytes": len(audio),
                            "sample_rate": SAMPLE_RATE,
                            "source_sample_rate": source_rate,
                            "voice": MODEL_PROFILE.tts_voice,
                            "latency_basis": "measured" if first_audio_ms is not None else "unknown",
                            "measures": "final transcript -> first output audio",
                        },
                    )
            except asyncio.QueueFull:
                pass
        await self.push_frame(frame, direction)


class EndpointLLMTrigger(FrameProcessor):
    """Fire the LLM on Soniox's semantic endpoint.

    SonioxSTTService (with vad_force_turn_endpoint=False) pushes exactly one
    final TranscriptionFrame per caller turn — when the model's endpoint
    detection decides the sentence is complete. That frame IS the turn-end
    signal, so we append it to the shared context and run the LLM
    immediately. No VAD silence threshold is involved.
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

    In this lab the host softphone often loops speaker audio back into the
    mic. Enabled by default; set VOICEBOT_ECHO_FILTER=0 to bypass once live
    evidence shows the streaming pipeline no longer needs it.
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
    """Stop queued AudioSocket output as soon as caller speech begins.

    This is VAD's only job in this pipeline: interrupting bot playback.
    Turn-end belongs to Soniox endpoint detection (see EndpointLLMTrigger).
    Also timestamps VAD speech-stop so TurnLogger can measure how long the
    semantic endpointing takes after the caller actually falls silent.
    """

    def __init__(self, session: AudioSocketSession, call_ctx: trace_events.CallContext):
        super().__init__()
        self.session = session
        self.call_ctx = call_ctx

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, VADUserStoppedSpeakingFrame):
            setattr(self.session, "_voicebot_last_vad_stop_ts", time.monotonic())
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
    """Trace STT / LLM / TTS text plus measured stage latencies.

    Placed once between STT and the LLM trigger (sees final transcripts) and
    once between the LLM and TTS (sees the streamed model text). Measured
    timings, all monotonic:
      * stt final_transcript duration_ms: caller-silence (VAD stop) ->
        endpoint transcript arrival.
      * llm response duration_ms: final transcript -> LLM response end;
        payload carries ttft_ms (first streamed token).
    """

    def __init__(self, session: AudioSocketSession, call_ctx: trace_events.CallContext):
        super().__init__()
        self.session = session
        self.call_ctx = call_ctx
        self._llm_parts: list[str] = []
        self._in_llm_response = False
        self._llm_first_token_ts: float | None = None

    async def _record_agent_text(self, room: str, text: str) -> None:
        if not text:
            return
        logger.info("agent=%r", text)
        turn_t0 = getattr(self.session, "_voicebot_turn_t0", None)
        now = time.monotonic()
        llm_total_ms = int((now - turn_t0) * 1000) if turn_t0 is not None else None
        ttft_ms = (
            int((self._llm_first_token_ts - turn_t0) * 1000)
            if turn_t0 is not None and self._llm_first_token_ts is not None
            else None
        )
        _trace(
            lane=LANE,
            call_id=self.call_ctx.call_id,
            turn_id=self.call_ctx.current_turn_id,
            stage="llm",
            event="response",
            provider=MODEL_PROFILE.llm_provider,
            model=MODEL_PROFILE.llm_model,
            duration_ms=llm_total_ms,
            payload={
                "text": text,
                "ttft_ms": ttft_ms,
                "latency_basis": "measured" if llm_total_ms is not None else "unknown",
                "measures": "final transcript -> llm response end",
            },
        )
        _usage(
            provider=MODEL_PROFILE.llm_provider,
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
            provider=MODEL_PROFILE.tts_provider,
            model=MODEL_PROFILE.tts_model,
            payload={"text": text, "voice": MODEL_PROFILE.tts_voice, "characters": len(text)},
        )
        _usage(
            provider=MODEL_PROFILE.tts_provider,
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
            self._llm_first_token_ts = None
        elif isinstance(frame, LLMFullResponseEndFrame):
            await self._record_agent_text(room, "".join(self._llm_parts).strip())
            self._llm_parts = []
            self._in_llm_response = False
        elif isinstance(frame, LLMTextFrame) and frame.text:
            if self._llm_first_token_ts is None:
                self._llm_first_token_ts = time.monotonic()
            self._llm_parts.append(frame.text)
        elif isinstance(frame, TranscriptionFrame) and frame.text:
            turn_id = self.call_ctx.next_turn()
            now = time.monotonic()
            setattr(self.session, "_voicebot_turn_t0", now)
            setattr(self.session, "_voicebot_turn_first_audio_pending", True)
            vad_stop_ts = getattr(self.session, "_voicebot_last_vad_stop_ts", None)
            endpoint_ms = (
                int((now - vad_stop_ts) * 1000)
                if vad_stop_ts is not None and now >= vad_stop_ts
                else None
            )
            logger.info("user=%r", frame.text)
            stats = self.session.audio_stats()
            _trace(
                lane=LANE,
                call_id=self.call_ctx.call_id,
                turn_id=turn_id,
                stage="stt",
                event="final_transcript",
                provider=MODEL_PROFILE.stt_provider,
                model=MODEL_PROFILE.stt_model,
                duration_ms=endpoint_ms,
                payload={
                    "text": frame.text,
                    "language": "tr",
                    "audio_receive_boundary": "asterisk-audiosocket",
                    "latency_basis": "measured" if endpoint_ms is not None else "unknown",
                    "measures": "VAD speech stop -> endpoint transcript",
                    "audio": stats,
                },
            )
            _usage(
                provider=MODEL_PROFILE.stt_provider,
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
                provider=MODEL_PROFILE.llm_provider,
                model=MODEL_PROFILE.llm_model,
                payload={
                    "model_profile": MODEL_PROFILE.asdict(),
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": frame.text},
                    ],
                    "tools": TOOL_SCHEMA,
                    "tool_policy": "auto",
                    "note": "Shared LLMContext carries prior turns at runtime.",
                },
            )
            _usage(
                provider=MODEL_PROFILE.llm_provider,
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
        elif (
            isinstance(frame, TextFrame)
            and not isinstance(frame, (TranscriptionFrame, InterimTranscriptionFrame))
            and frame.text
        ):
            # Guard against STT interim/transcription frames: both subclass
            # TextFrame, and streaming STT (Soniox) emits interim words that
            # must NOT be logged as bot speech (that also poisons the echo
            # filter's recent-bot-text set with the caller's own words).
            await self._record_agent_text(room, frame.text)
        await self.push_frame(frame, direction)


# ---- tool wiring --------------------------------------------------------

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


# ---- per-call pipeline ---------------------------------------------------

async def on_session(session: AudioSocketSession) -> None:
    """Called by AudioSocketServer for every inbound call from Asterisk.

    Constructs a fresh pipecat pipeline per call; the Soniox STT/TTS
    WebSockets connect during StartFrame propagation.
    """
    # Wait for UUID (Asterisk sends it right after connect).
    for _ in range(20):
        if session.uuid:
            break
        await asyncio.sleep(0.05)
    call_id = session.uuid or "unknown-audiosocket-call"
    call_ctx = trace_events.CallContext(LANE, call_id)
    run_id = trace_events.current_run_id()
    _trace(
        lane=LANE,
        call_id=call_ctx.call_id,
        stage="call",
        event="call.started",
        provider="asterisk-audiosocket",
        run_id=run_id,
        payload={
            "uuid": session.uuid,
            "asterisk_audiosocket_uuid": session.uuid,
            "asterisk_uniqueid": session.uuid,
            "correlation_status": "audiosocket_uuid",
            "listener": "0.0.0.0:8090",
            "sample_rate": SAMPLE_RATE,
        },
    )
    _trace(
        lane=LANE,
        call_id=call_ctx.call_id,
        stage="call",
        event="profile.loaded",
        provider="pipecat",
        run_id=run_id,
        payload=voicebot_profile.startup_metadata(
            lane=LANE,
            system_prompt=SYSTEM_PROMPT,
            tools=TOOL_SCHEMA,
            docs_root=docqa.DOCS_ROOT,
            corpus=docqa.CORPUS,
            repo_root=Path("/opt/voicebot-docs"),
        ),
    )

    # Ears: semantic endpointing owns turn-end (vad_force_turn_endpoint=False
    # flips Soniox's enable_endpoint_detection on). endpoint_sensitivity /
    # max_endpoint_delay_ms are env-tunable without a code change.
    stt = SonioxSTTService(
        api_key=os.environ["SONIOX_API_KEY"],
        vad_force_turn_endpoint=False,
        settings=SonioxSTTService.Settings(
            model=MODEL_PROFILE.stt_model,
            language_hints=[Language.TR],
            context=STT_CONTEXT,
            endpoint_sensitivity=_env_float("VOICEBOT_STT_ENDPOINT_SENSITIVITY"),
            max_endpoint_delay_ms=_env_int("VOICEBOT_STT_MAX_ENDPOINT_DELAY_MS"),
        ),
    )
    llm = OpenAILLMService(
        model=MODEL_PROFILE.llm_model,
        api_key=os.environ["OPENAI_API_KEY"],
    )
    # Mouth: Soniox synthesizes at the pipeline rate (16 kHz) natively.
    tts = SonioxTTSService(
        api_key=os.environ["SONIOX_API_KEY"],
        sample_rate=SAMPLE_RATE,
        settings=SonioxTTSService.Settings(
            model=MODEL_PROFILE.tts_model,
            voice=MODEL_PROFILE.tts_voice,
            language=Language.TR,
        ),
    )

    # Bind the tool handler; LLMContext auto-registers it with the LLM service
    # because FunctionSchema has `handler=...` set.
    context = LLMContext(
        messages=[{"role": "system", "content": SYSTEM_PROMPT}],
        tools=_build_tools_schema(make_tool_lookup_docs(call_ctx)),
    )
    context_aggregator = LLMContextAggregatorPair(context)
    stages: list[FrameProcessor] = [
        AudioSocketSource(session, call_ctx),
        # VAD's only job is the barge-in reflex (and timestamping caller
        # silence for the endpoint-latency measurement). It does NOT end
        # turns: SonioxSTTService ignores VAD stop frames because
        # vad_force_turn_endpoint=False.
        VADProcessor(
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(confidence=0.82, start_secs=0.45, stop_secs=0.35, min_volume=0.75)
            )
        ),
        BargeInAudioStopper(session, call_ctx),
        stt,
    ]
    if ECHO_FILTER_ENABLED:
        stages.append(BotEchoFilter(session, call_ctx))
    stages += [
        TurnLogger(session, call_ctx),
        EndpointLLMTrigger(context),
        llm,
        TurnLogger(session, call_ctx),
        tts,
        AudioSocketSink(session, call_ctx),
        context_aggregator.assistant(),
    ]
    pipeline = Pipeline(stages)

    task = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=SAMPLE_RATE,
            audio_out_sample_rate=SAMPLE_RATE,
        ),
    )

    # Kick things off: greet the caller before waiting for STT.
    async def _greet() -> None:
        await asyncio.sleep(0.5)  # let StartFrame propagate through the pipeline
        _trace(
            lane=LANE,
            call_id=call_ctx.call_id,
            turn_id="greeting",
            stage="tts",
            event="request",
            provider=MODEL_PROFILE.tts_provider,
            model=MODEL_PROFILE.tts_model,
            payload={"text": GREETING, "voice": MODEL_PROFILE.tts_voice, "characters": len(GREETING)},
        )
        _usage(
            provider=MODEL_PROFILE.tts_provider,
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
    logger.info("pipecat agent starting (soniox streaming, %d Hz)", SAMPLE_RATE)
    for key in ("SONIOX_API_KEY", "OPENAI_API_KEY"):
        if not os.environ.get(key):
            logger.error("%s is not set — the agent cannot serve calls", key)
    # Prewarm the OpenAI client cache so the first LLM turn skips DNS+TLS.
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
