"""Naive markdown Q&A used by both voicebot agent lanes as a `lookup_docs` tool.

Purpose: give the agent a way to answer factual questions about the lab
("which Asterisk version?", "which SBC?", "how does monitoring work?")
without shipping embeddings, a vector DB, or a full RAG stack. This is
deliberately simple — one Python module, two functions, dependency-free —
so the LiveKit lane and the Pipecat lane call the *same* code and the
comparison isolates the agent framework, not the retrieval quality.

Design:
  * Split each source doc into paragraph chunks (blank-line separated).
  * Score a chunk by the count of query tokens that appear in it (case
    and Turkish-diacritic folded). No IDF, no cosine — this is a naive
    keyword baseline. Good enough for a lab with three markdown files.
  * Return the top-N chunks concatenated, each prefixed with `[source]`
    so the agent can cite. The LLM synthesises the final answer.

Docs live at $VOICEBOT_DOCS_ROOT (defaults to /opt/voicebot-docs, which
the compose files bind-mount to the repo root on the VM).
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# DOCS_ROOT points at services/common/docs/. Compose bind-mounts the whole
# services/common tree read-only, so the container sees docs at
# /opt/voicebot-common/docs/.
DOCS_ROOT = Path(
    os.environ.get("VOICEBOT_DOCS_ROOT", "/opt/voicebot-common/docs/magaza")
)

# Hardcoded list keeps the corpus deterministic across LK and Pipecat runs.
# The corpus is a fictional Turkish home-textile store ("Mavi Kapı") — we
# deliberately picked a non-technical domain so any measured framework
# difference isn't confounded by the model's ability to reason about
# telecom jargon. Add a doc here (not autodiscover) so a stray new .md
# doesn't shift retrieval scores.
CORPUS = [
    "hakkinda.md",
    "urunler.md",
    "kargo-iade.md",
    "iletisim.md",
]


@dataclass(frozen=True)
class Chunk:
    source: str  # filename relative to DOCS_ROOT
    idx: int  # paragraph index within the source, 0-based
    text: str


def _fold(s: str) -> str:
    """Case- and diacritic-fold so 'Sürüm' matches 'surum'.

    Turkish 'ı'/'i' are handled by NFKD decomposition + ASCII drop; the
    dotless-i quirk doesn't hurt search because query and doc are folded
    identically.
    """
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(s: str) -> list[str]:
    return _TOKEN_RE.findall(_fold(s))


@lru_cache(maxsize=1)
def _load_chunks() -> list[Chunk]:
    """Parse every CORPUS file into paragraph chunks, once per process.

    Called from the tool path, so cache it — the docs are read-only.
    """
    chunks: list[Chunk] = []
    for name in CORPUS:
        path = DOCS_ROOT / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for i, para in enumerate(re.split(r"\n\s*\n", text)):
            para = para.strip()
            if len(para) < 40:  # drop navigation lines, headings, short bullets
                continue
            chunks.append(Chunk(source=name, idx=i, text=para))
    return chunks


def search(query: str, top_n: int = 3) -> str:
    """Return the top-N most-overlapping paragraphs, or a 'not found' hint.

    Format matters: the agent will read this literally and paraphrase to the
    caller, so lead each hit with `[source:line]` and separate hits with a
    blank line. When nothing scores >0, list the doc filenames so the LLM
    can honestly say "I don't have that in the docs, but I have X, Y".
    """
    qtokens = set(_tokens(query))
    if not qtokens:
        return "Boş sorgu."

    scored: list[tuple[int, Chunk]] = []
    for c in _load_chunks():
        ct = _tokens(c.text)
        # Number of *distinct* query tokens present. Prevents one repeated
        # word from swamping the score.
        overlap = sum(1 for q in qtokens if q in ct)
        if overlap > 0:
            scored.append((overlap, c))

    if not scored:
        # No hit — tell the agent honestly what's available.
        return (
            "Bu konuda mağaza bilgi tabanında kayıt bulamadım. "
            "Elimdeki başlıklar: hakkında/konum/saatler, ürünler ve fiyatlar, "
            "kargo ve iade politikası, iletişim bilgileri."
        )

    scored.sort(key=lambda t: (-t[0], t[1].source, t[1].idx))
    lines: list[str] = []
    for score, c in scored[:top_n]:
        lines.append(f"[{c.source} §{c.idx}, skor {score}]\n{c.text}")
    return "\n\n".join(lines)


if __name__ == "__main__":
    import sys

    q = " ".join(sys.argv[1:]) or "Asterisk sürümü"
    print(search(q))
