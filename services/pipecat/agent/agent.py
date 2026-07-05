"""Pipecat voicebot lane — parity twin of services/livekit/agent/agent.py.

Design axioms (change one, change both):
  * Identical OpenAI models: whisper-1 (with same domain prompt), gpt-4o-mini,
    tts-1 voice=alloy.
  * Identical SYSTEM_PROMPT and GREETING (copied verbatim from the LK lane).
  * Identical shared tool: lookup_docs → services/common/docqa.py.
  * Identical turn log format: same /var/lib/voicebot/turns.jsonl kinds,
    so services/common/tail_turns.py renders both lanes with one code path.
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
import sys
import time
from pathlib import Path

# Bind-mounted shared helpers (see docker-compose.yml).
sys.path.insert(0, "/opt/voicebot-common")
import docqa  # noqa: E402
import usage  # noqa: E402

from audiosocket import (  # noqa: E402
    AudioSocketServer,
    AudioSocketSession,
    FRAME_BYTES,
    SAMPLE_RATE,
)

# Pipecat 1.4.0 module paths (they moved from earlier releases):
#   * Services live under pipecat.services.openai.{llm,stt,tts}
#   * Context is the framework-agnostic LLMContext + ToolsSchema
#   * Aggregators come from llm_response_universal (LLMContextAggregatorPair)
from pipecat.audio.vad.silero import SileroVADAnalyzer  # noqa: E402
from pipecat.frames.frames import (  # noqa: E402
    EndFrame,
    Frame,
    InputAudioRawFrame,
    LLMRunFrame,
    OutputAudioRawFrame,
    TTSAudioRawFrame,
    TTSSpeakFrame,
    TextFrame,
    TranscriptionFrame,
    UserStoppedSpeakingFrame,
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

# ---- turn logging (parity with LK lane) --------------------------------

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

    def __init__(self, session: AudioSocketSession):
        super().__init__()
        self.session = session
        self._pump_task: asyncio.Task | None = None

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
                await self.push_frame(EndFrame())
                return
            await self.push_frame(
                InputAudioRawFrame(
                    audio=payload, sample_rate=SAMPLE_RATE, num_channels=1,
                )
            )


class AudioSocketSink(FrameProcessor):
    """Route pipecat TTS output back into the AudioSocket outbound queue."""

    def __init__(self, session: AudioSocketSession):
        super().__init__()
        self.session = session

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, (TTSAudioRawFrame, OutputAudioRawFrame)):
            # pipecat TTS outputs 24 kHz by default; downsample to 8 kHz.
            # Cheapest fix here: run TTS at 16 kHz and resample. For MVP
            # trust the OpenAI TTS service was configured with sample_rate=8000.
            try:
                self.session.outbound.put_nowait(bytes(frame.audio))
            except asyncio.QueueFull:
                pass


class LLMTrigger(FrameProcessor):
    """Force the LLM to run after each finalised user transcription.

    In principle LLMUserAggregator emits an LLMContextFrame on
    UserStoppedSpeaking+TranscriptionFrame, which the LLM service picks up.
    In practice, on Pipecat 1.4 the aggregator's default UserTurnStrategies
    can defer that emission indefinitely if no smart-turn signal fires (the
    Local Smart Turn v3 model is loaded but doesn't classify our 8 kHz
    audio confidently). Pushing an LLMRunFrame right after the aggregator
    sees the transcription is the belt-and-braces fix.
    """

    def __init__(self):
        super().__init__()

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame) and frame.text:
            await self.push_frame(LLMRunFrame(), FrameDirection.DOWNSTREAM)


class TurnLogger(FrameProcessor):
    """Mirror STT / LLM / TTS text to /var/lib/voicebot/turns.jsonl.

    Placed between the user-context-aggregator and the LLM so we see the
    fully-assembled context on the way in, and between the LLM and the TTS
    so we see the raw model text on the way out.
    """

    def __init__(self, uuid_getter):
        super().__init__()
        self.uuid_getter = uuid_getter

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        room = f"as-{self.uuid_getter()[:8]}"
        if isinstance(frame, TranscriptionFrame) and frame.text:
            logger.info("user=%r", frame.text)
            dump_turn("user_speech", room, {"text": frame.text})
        elif isinstance(frame, TextFrame) and frame.text:
            logger.info("agent=%r", frame.text)
            dump_turn("agent_speech", room, {"text": frame.text})


# ---- tool wiring (parity: same docqa, same usage.record) ---------------

async def tool_lookup_docs(params) -> str:
    """LLM tool handler. Signature per pipecat convention: dict-like `params`."""
    # Different pipecat versions surface params differently.
    if hasattr(params, "arguments"):
        args = params.arguments
    else:
        args = params or {}
    query = args.get("query") if isinstance(args, dict) else str(args)
    logger.info("tool=lookup_docs query=%r", query)
    result = docqa.search(query, top_n=3)
    logger.info("tool_result=%s", _preview(result))
    dump_turn("tool_call", "", {"tool": "lookup_docs", "query": query, "result": result})
    try:
        usage.record(provider="lab", op="tool_call", units=1,
                     unit_type="calls", ref="lookup_docs",
                     extra={"query": query})
    except Exception:  # noqa: BLE001
        pass
    return result


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

    stt = OpenAISTTService(
        model="whisper-1",
        api_key=os.environ["OPENAI_API_KEY"],
        language="tr",
        prompt=WHISPER_PROMPT,
    )
    llm = OpenAILLMService(
        model="gpt-4o-mini",
        api_key=os.environ["OPENAI_API_KEY"],
    )
    # OpenAI TTS only synthesizes at 24 kHz. Requesting 8 kHz silently produces
    # no audio (pipecat warns but doesn't error). We take 24 kHz here; the
    # audio_out_sample_rate=SAMPLE_RATE on PipelineParams tells pipecat to
    # resample the TTSAudioRawFrames down to 8 kHz before they hit the sink.
    tts = OpenAITTSService(
        model="tts-1",
        voice="alloy",
        api_key=os.environ["OPENAI_API_KEY"],
        sample_rate=24000,
    )

    # Bind the tool handler; LLMContext auto-registers it with the LLM service
    # because FunctionSchema has `handler=...` set.
    context = LLMContext(
        messages=[{"role": "system", "content": SYSTEM_PROMPT}],
        tools=_build_tools_schema(tool_lookup_docs),
    )
    context_aggregator = LLMContextAggregatorPair(context)

    pipeline = Pipeline([
        AudioSocketSource(session),
        # VAD emits UserStartedSpeaking/UserStoppedSpeaking around the audio
        # so STT knows when to run and the LLM knows when to answer. In 1.4
        # it's a stand-alone FrameProcessor, no longer a PipelineParams knob.
        VADProcessor(vad_analyzer=SileroVADAnalyzer()),
        stt,
        TurnLogger(lambda: session.uuid),
        context_aggregator.user(),
        LLMTrigger(),  # force LLM to run after each TranscriptionFrame
        llm,
        tts,
        AudioSocketSink(session),
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
        await task.queue_frames([TTSSpeakFrame(text=GREETING)])
        dump_turn("agent_speech", f"as-{session.uuid[:8]}", {"text": GREETING})

    runner = PipelineRunner()
    await asyncio.gather(runner.run(task), _greet())


async def amain() -> None:
    logger.info("pipecat agent starting")
    # Prewarm the OpenAI client cache — same rationale as the LK lane.
    try:
        import httpx
        with httpx.Client(timeout=10) as c:
            c.get("https://api.openai.com/v1/models")
        logger.info("prewarmed openai connection")
    except Exception:  # noqa: BLE001
        pass

    host = os.environ.get("AUDIOSOCKET_HOST", "0.0.0.0")
    port = int(os.environ.get("AUDIOSOCKET_PORT", "8090"))
    server = AudioSocketServer(host, port, on_session)
    await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(amain())
