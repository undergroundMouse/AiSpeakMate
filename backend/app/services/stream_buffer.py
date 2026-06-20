"""Sentence-boundary buffer for streaming LLM → TTS pipeline."""

import re

_SENTENCE_END = re.compile(r"[.!?]\s*$")


class SentenceStreamBuffer:
    """Accumulates LLM token deltas and yields complete sentences."""

    def __init__(self, max_chunk_len: int = 80):
        self._buffer = ""
        self._max_chunk_len = max_chunk_len

    def add(self, delta: str) -> list[str]:
        if not delta:
            return []
        self._buffer += delta
        sentences: list[str] = []
        while True:
            match = _SENTENCE_END.search(self._buffer)
            if match:
                end = match.end()
                sentence = self._buffer[:end].strip()
                self._buffer = self._buffer[end:].lstrip()
                if sentence:
                    sentences.append(sentence)
                continue
            if len(self._buffer) >= self._max_chunk_len:
                # Flush at last space or hard split
                split_at = self._buffer.rfind(" ", 0, self._max_chunk_len)
                if split_at <= 0:
                    split_at = self._max_chunk_len
                chunk = self._buffer[:split_at].strip()
                self._buffer = self._buffer[split_at:].lstrip()
                if chunk:
                    sentences.append(chunk)
                continue
            break
        return sentences

    def flush(self) -> str | None:
        remainder = self._buffer.strip()
        self._buffer = ""
        return remainder or None
