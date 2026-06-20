"""Sentence-boundary buffer for streaming LLM → TTS pipeline."""

import re

_SENTENCE_END = re.compile(r"[.!?]\s*$")


class SentenceStreamBuffer:
    """Accumulates LLM token deltas and yields TTS-sized chunks.

    Avoids flushing on every short sentence (e.g. "Sure." "OK.") which causes
    word-by-word audio when each fragment is synthesized and played separately.
    """

    def __init__(self, min_chunk_len: int = 100, max_chunk_len: int = 220):
        self._buffer = ""
        self._min_chunk_len = min_chunk_len
        self._max_chunk_len = max_chunk_len

    def add(self, delta: str) -> list[str]:
        if not delta:
            return []
        self._buffer += delta
        sentences: list[str] = []
        while True:
            if len(self._buffer) >= self._max_chunk_len:
                split_at = self._buffer.rfind(" ", 0, self._max_chunk_len)
                if split_at <= 0:
                    split_at = self._max_chunk_len
                chunk = self._buffer[:split_at].strip()
                self._buffer = self._buffer[split_at:].lstrip()
                if chunk:
                    sentences.append(chunk)
                continue

            if len(self._buffer.strip()) >= self._min_chunk_len and _SENTENCE_END.search(self._buffer):
                chunk = self._buffer.strip()
                self._buffer = ""
                if chunk:
                    sentences.append(chunk)
                continue

            break
        return sentences

    def flush(self) -> str | None:
        remainder = self._buffer.strip()
        self._buffer = ""
        return remainder or None
