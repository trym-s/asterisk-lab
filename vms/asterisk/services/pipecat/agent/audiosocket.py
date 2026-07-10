"""Asterisk AudioSocket protocol I/O for the Pipecat lane.

Protocol (per res_audiosocket.c):
  Each message = 1-byte type + 2-byte big-endian length + <length> bytes payload.

  Types we handle (per include/asterisk/res_audiosocket.h, Asterisk 22):
    0x00  hangup      (Asterisk closing; payload is 0 bytes)
    0x01  uuid        (16-byte call UUID sent first on connect)
    0x03  DTMF        (1-byte digit)
    0x10..0x18  PCM audio (mono, 16-bit LE signed linear; the KIND byte
                encodes the sample rate: 0x10=8k, 0x11=12k, 0x12=16k,
                0x13=24k, 0x14=32k, 0x15=44.1k, 0x16=48k, 0x17=96k,
                0x18=192k. The c(slin16) dialplan leg sends 0x12, and we
                must frame our own outbound audio with the same kind byte
                or Asterisk misinterprets the rate.)
    0xFF  error       (server -> client, terminates call)

  Asterisk connects TO us (dialplan: Dial(AudioSocket/<host>:<port>/<uuid>/
  c(slin16))), so we're a TCP server. Ptime is 20 ms -> 640 bytes payload
  per audio frame at 16 kHz mono s16le (16000 * 0.02 * 2 = 640).

We expose an asyncio protocol handler that produces (uuid, inbound_queue,
outbound_queue) triples. The Pipecat pipeline consumes from `inbound_queue`
and writes to `outbound_queue`; this module owns the socket framing.
"""

from __future__ import annotations

import asyncio
import logging
import os
import struct
import time
from typing import Callable, Awaitable

logger = logging.getLogger("audiosocket")

TYPE_HANGUP = 0x00
TYPE_UUID = 0x01
TYPE_DTMF = 0x03
TYPE_ERROR = 0xFF

# KIND byte <-> sample rate for slin PCM audio messages.
AUDIO_KIND_BY_RATE = {
    8000: 0x10,
    12000: 0x11,
    16000: 0x12,
    24000: 0x13,
    32000: 0x14,
    44100: 0x15,
    48000: 0x16,
    96000: 0x17,
    192000: 0x18,
}
AUDIO_KINDS = set(AUDIO_KIND_BY_RATE.values())

# 16-bit LE mono PCM, 20 ms frames. Must match the codec the dialplan
# forces on the AudioSocket leg (c(slin16) -> 16000).
SAMPLE_RATE = int(os.getenv("AUDIOSOCKET_SAMPLE_RATE", "16000"))
TYPE_AUDIO = AUDIO_KIND_BY_RATE[SAMPLE_RATE]
FRAME_MS = 20
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000  # 320 @ 16 kHz
FRAME_BYTES = FRAME_SAMPLES * 2  # 640 @ 16 kHz


async def _read_msg(reader: asyncio.StreamReader) -> tuple[int, bytes] | None:
    """Read one framed message. Return (type, payload) or None on EOF."""
    try:
        hdr = await reader.readexactly(3)
    except asyncio.IncompleteReadError:
        return None
    msg_type = hdr[0]
    length = struct.unpack(">H", hdr[1:3])[0]
    payload = await reader.readexactly(length) if length else b""
    return msg_type, payload


def _pack_audio(pcm: bytes) -> bytes:
    """Frame a slin16 payload for Asterisk. Payload must be <= 65535 bytes."""
    return bytes([TYPE_AUDIO]) + struct.pack(">H", len(pcm)) + pcm


def _pack_hangup() -> bytes:
    return bytes([TYPE_HANGUP]) + b"\x00\x00"


class AudioSocketSession:
    """One inbound Asterisk call. Owned by AudioSocketServer.handle_conn."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer
        self.uuid: str = ""
        self.inbound: asyncio.Queue[bytes] = asyncio.Queue(maxsize=200)
        self.outbound: asyncio.Queue[bytes] = asyncio.Queue(maxsize=200)
        self._closed = asyncio.Event()
        self.inbound_bytes = 0
        self.inbound_frames = 0
        self.outbound_bytes = 0
        self.outbound_frames = 0
        self.idle_silence_bytes = 0
        self.idle_silence_frames = 0
        self.first_inbound_ts: float | None = None
        self.last_inbound_ts: float | None = None
        self.first_outbound_ts: float | None = None
        self.last_outbound_ts: float | None = None
        self._outbound_generation = 0

    def clear_outbound(self) -> int:
        """Drop pending bot audio and invalidate the chunk currently being written."""
        self._outbound_generation += 1
        dropped = 0
        while True:
            try:
                self.outbound.get_nowait()
                dropped += 1
            except asyncio.QueueEmpty:
                break
        return dropped

    def audio_stats(self) -> dict:
        bytes_per_second = SAMPLE_RATE * 2
        return {
            "sample_rate": SAMPLE_RATE,
            "frame_ms": FRAME_MS,
            "frame_bytes": FRAME_BYTES,
            "inbound_bytes": self.inbound_bytes,
            "inbound_frames": self.inbound_frames,
            "inbound_duration_ms": int((self.inbound_bytes / bytes_per_second) * 1000),
            "first_inbound_ts": self.first_inbound_ts,
            "last_inbound_ts": self.last_inbound_ts,
            "outbound_bytes": self.outbound_bytes,
            "outbound_frames": self.outbound_frames,
            "outbound_duration_ms": int((self.outbound_bytes / bytes_per_second) * 1000),
            "idle_silence_bytes": self.idle_silence_bytes,
            "idle_silence_frames": self.idle_silence_frames,
            "idle_silence_duration_ms": int((self.idle_silence_bytes / bytes_per_second) * 1000),
            "first_outbound_ts": self.first_outbound_ts,
            "last_outbound_ts": self.last_outbound_ts,
            "uuid": self.uuid,
        }

    async def _reader_loop(self) -> None:
        """Pull frames from Asterisk, drop into inbound queue."""
        try:
            while not self._closed.is_set():
                msg = await _read_msg(self.reader)
                if msg is None:
                    logger.info("audiosocket: peer EOF uuid=%s", self.uuid)
                    break
                msg_type, payload = msg
                if msg_type == TYPE_UUID:
                    self.uuid = payload.hex()
                    logger.info("audiosocket: uuid=%s", self.uuid)
                elif msg_type in AUDIO_KINDS:
                    if msg_type != TYPE_AUDIO and not getattr(self, "_rate_kind_warned", False):
                        self._rate_kind_warned = True
                        logger.warning(
                            "audiosocket: inbound audio kind %#x != expected %#x "
                            "(dialplan codec and AUDIOSOCKET_SAMPLE_RATE disagree) uuid=%s",
                            msg_type, TYPE_AUDIO, self.uuid,
                        )
                    now = time.time()
                    if self.first_inbound_ts is None:
                        self.first_inbound_ts = now
                    self.last_inbound_ts = now
                    self.inbound_bytes += len(payload)
                    self.inbound_frames += 1
                    try:
                        self.inbound.put_nowait(payload)
                    except asyncio.QueueFull:
                        # Drop-oldest to keep RT: pop then push.
                        _ = self.inbound.get_nowait()
                        self.inbound.put_nowait(payload)
                elif msg_type == TYPE_HANGUP:
                    logger.info("audiosocket: hangup uuid=%s", self.uuid)
                    break
                elif msg_type == TYPE_DTMF:
                    logger.info("audiosocket: dtmf=%r uuid=%s", payload, self.uuid)
                else:
                    logger.debug("audiosocket: unknown type=%#x uuid=%s", msg_type, self.uuid)
        except Exception:  # noqa: BLE001
            logger.exception("audiosocket reader crashed uuid=%s", self.uuid)
        finally:
            self._closed.set()
            # Signal EOF to pipeline consumers.
            try:
                self.inbound.put_nowait(b"")
            except asyncio.QueueFull:
                pass

    async def _writer_loop(self) -> None:
        """Pull PCM frames from outbound queue, frame + send to Asterisk."""
        try:
            while not self._closed.is_set():
                is_idle_silence = False
                try:
                    pcm = await asyncio.wait_for(
                        self.outbound.get(),
                        timeout=FRAME_MS / 1000,
                    )
                except asyncio.TimeoutError:
                    if not self.uuid:
                        continue
                    pcm = b"\x00" * FRAME_BYTES
                    is_idle_silence = True
                if not pcm:
                    break
                # Frame in ptime-sized chunks so we honor 20 ms cadence.
                generation = self._outbound_generation
                for i in range(0, len(pcm), FRAME_BYTES):
                    if generation != self._outbound_generation:
                        logger.info("audiosocket: interrupted outbound audio uuid=%s", self.uuid)
                        break
                    chunk = pcm[i:i + FRAME_BYTES]
                    if len(chunk) < FRAME_BYTES:
                        chunk += b"\x00" * (FRAME_BYTES - len(chunk))
                    now = time.time()
                    if self.first_outbound_ts is None:
                        self.first_outbound_ts = now
                    self.last_outbound_ts = now
                    self.outbound_bytes += len(chunk)
                    self.outbound_frames += 1
                    if is_idle_silence:
                        self.idle_silence_bytes += len(chunk)
                        self.idle_silence_frames += 1
                    self.writer.write(_pack_audio(chunk))
                    await self.writer.drain()
                    if not is_idle_silence:
                        await asyncio.sleep(FRAME_MS / 1000)
        except (ConnectionResetError, BrokenPipeError):
            logger.info("audiosocket: peer closed during write uuid=%s", self.uuid)
        except Exception:  # noqa: BLE001
            logger.exception("audiosocket writer crashed uuid=%s", self.uuid)
        finally:
            self._closed.set()

    async def close(self) -> None:
        self._closed.set()
        try:
            self.writer.write(_pack_hangup())
            await self.writer.drain()
        except Exception:  # noqa: BLE001
            pass
        self.writer.close()
        try:
            await self.writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass


class AudioSocketServer:
    """TCP server that accepts Asterisk AudioSocket connections."""

    def __init__(
        self,
        host: str,
        port: int,
        on_session: Callable[[AudioSocketSession], Awaitable[None]],
    ):
        self.host = host
        self.port = port
        self.on_session = on_session

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        session = AudioSocketSession(reader, writer)
        r_task = asyncio.create_task(session._reader_loop(), name="as-reader")
        w_task = asyncio.create_task(session._writer_loop(), name="as-writer")
        try:
            await self.on_session(session)
        except Exception:  # noqa: BLE001
            logger.exception("session handler crashed uuid=%s", session.uuid)
        finally:
            await session.close()
            for t in (r_task, w_task):
                if not t.done():
                    t.cancel()

    async def serve_forever(self) -> None:
        server = await asyncio.start_server(self._handle, self.host, self.port)
        logger.info("audiosocket: listening on %s:%d", self.host, self.port)
        async with server:
            await server.serve_forever()
