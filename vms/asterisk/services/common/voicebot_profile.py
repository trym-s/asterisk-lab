"""Shared voicebot profile and comparison metadata helpers."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PROFILE_SCHEMA_VERSION = "voicebot-profile-v1"
PRICING_VERSION = os.environ.get("VOICEBOT_PRICING_VERSION", "soniox-openai-2026-07-10")


@dataclass(frozen=True)
class ModelProfile:
    name: str
    stt_provider: str
    stt_model: str
    llm_provider: str
    llm_model: str
    tts_provider: str
    tts_model: str
    tts_voice: str
    pricing_version: str

    def asdict(self) -> dict[str, str]:
        return asdict(self)


def load_model_profile() -> ModelProfile:
    return ModelProfile(
        name=os.environ.get("VOICEBOT_MODEL_PROFILE", "soniox-streaming-telephony"),
        stt_provider=os.environ.get("VOICEBOT_STT_PROVIDER", "soniox"),
        stt_model=os.environ.get("VOICEBOT_STT_MODEL", "stt-rt-v5"),
        llm_provider=os.environ.get("VOICEBOT_LLM_PROVIDER", "openai"),
        llm_model=os.environ.get("VOICEBOT_LLM_MODEL", "gpt-4o-mini"),
        tts_provider=os.environ.get("VOICEBOT_TTS_PROVIDER", "soniox"),
        tts_model=os.environ.get("VOICEBOT_TTS_MODEL", "tts-rt-v1"),
        tts_voice=os.environ.get("VOICEBOT_TTS_VOICE", "Adrian"),
        pricing_version=PRICING_VERSION,
    )


def stable_json_hash(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def corpus_metadata(docs_root: Path, corpus: list[str]) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    digest = hashlib.sha256()
    for name in corpus:
        path = docs_root / name
        entry: dict[str, Any] = {"name": name, "exists": path.exists()}
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        if path.exists():
            content = path.read_bytes()
            entry["sha256"] = hashlib.sha256(content).hexdigest()
            entry["bytes"] = len(content)
            digest.update(content)
        files.append(entry)
    return {
        "schema_version": "voicebot-corpus-v1",
        "root": str(docs_root),
        "files": files,
        "hash": digest.hexdigest(),
    }


def repo_revision(root: Path | None = None) -> str:
    override = os.environ.get("VOICEBOT_REPO_REVISION")
    if override:
        return override
    candidates = [root] if root else []
    candidates.extend([Path("/opt/voicebot-docs"), Path.cwd()])
    for candidate in candidates:
        if not candidate:
            continue
        try:
            proc = subprocess.run(
                ["git", "-C", str(candidate), "rev-parse", "--short=12", "HEAD"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=2,
            )
        except Exception:  # noqa: BLE001
            continue
        revision = proc.stdout.strip()
        if revision:
            return revision
    return "unknown"


def startup_metadata(
    *,
    lane: str,
    system_prompt: str,
    tools: Any,
    docs_root: Path,
    corpus: list[str],
    repo_root: Path | None = None,
) -> dict[str, Any]:
    profile = load_model_profile()
    tool_hash = stable_json_hash(tools)
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "lane": lane,
        "model_profile": profile.asdict(),
        "prompt_hash": hash_text(system_prompt),
        "tool_schema_hash": tool_hash,
        "tool_schema": tools,
        "corpus": corpus_metadata(docs_root, corpus),
        "repo_revision": repo_revision(repo_root),
    }
