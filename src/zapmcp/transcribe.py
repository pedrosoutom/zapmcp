"""Transcrição local com whisper.cpp e o modelo large-v3-turbo comprimido (q5, 0,6 GB).

Nada sai do Mac: o único acesso à rede é baixar o modelo, uma vez.
"""

import hashlib
import logging
import os
import re
import subprocess
import tempfile
import unicodedata
import urllib.request
import wave
from pathlib import Path

from . import config

log = logging.getLogger("zapmcp")

MODEL_FILE = "ggml-large-v3-turbo-q5_0.bin"
MODEL_URL = f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/{MODEL_FILE}"
MODEL_SHA256 = "394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2"
MODEL_BYTES = 574_041_195
MODEL_NAME = "whisper.cpp large-v3-turbo q5_0"

# Trechos que o Whisper inventa quando o áudio é silêncio ou ruído (vêm das legendas com que foi treinado).
SILENCE_HALLUCINATIONS = re.compile(r"^\W*(legendas? (pela comunidade|por)|amara\.org|inscreva-se)", re.IGNORECASE)


def model_path() -> Path:
    return config.home() / "models" / MODEL_FILE


def ensure_model() -> Path:
    """Baixa o modelo na primeira vez e confere o hash oficial."""
    path = model_path()
    if path.exists() and path.stat().st_size == MODEL_BYTES:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    log.info("baixando o modelo de transcrição (%d MB)", MODEL_BYTES // 1_000_000)
    digest = hashlib.sha256()
    with urllib.request.urlopen(MODEL_URL, timeout=60) as response, partial.open("wb") as out:
        while chunk := response.read(1 << 20):
            out.write(chunk)
            digest.update(chunk)
    if digest.hexdigest() != MODEL_SHA256:
        partial.unlink(missing_ok=True)
        raise RuntimeError("O modelo baixado não confere com o hash oficial; tente de novo.")
    partial.replace(path)
    return path


def decode(audio: Path):
    """.opus do WhatsApp → amostras float32 a 16 kHz, mono (o formato do Whisper)."""
    import numpy as np

    with tempfile.TemporaryDirectory(prefix="zapmcp-") as tmp:
        wav = Path(tmp) / "audio.wav"
        # afconvert vem com o macOS e decodifica Ogg Opus; no Windows vai precisar de outro caminho.
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(audio), str(wav)],
                       check=True, capture_output=True)
        with wave.open(str(wav)) as w:
            frames = w.readframes(w.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


class Transcriber:
    """Carrega o modelo uma vez e transcreve áudio por áudio."""

    name = MODEL_NAME

    def __init__(self) -> None:
        self._model = None

    def transcribe(self, audio: Path) -> str:
        if self._model is None:
            from pywhispercpp.model import Model

            self._model = Model(str(ensure_model()), language="pt", print_progress=False, print_realtime=False,
                                redirect_whispercpp_logs_to=os.devnull)
        segments = [s.text for s in self._model.transcribe(decode(audio))]
        return clean(segments)


def clean(segments: list[str]) -> str:
    """Junta os trechos e remove as falhas conhecidas do Whisper."""
    kept: list[str] = []
    for segment in (s.strip() for s in segments):
        if segment and (not kept or _words(segment) != _words(kept[-1])):  # trecho repetido em seguida
            kept.append(segment)
    text = _drop_repeats(" ".join(kept))
    text = _cut_foreign(text)
    return "" if SILENCE_HALLUCINATIONS.match(text) else text


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def _drop_repeats(text: str, min_words: int = 5) -> str:
    """Remove uma sequência de 5+ palavras que aparece duas vezes seguidas ("… também? … também?")."""
    tokens = text.split()
    norm = [re.sub(r"\W+", "", t.lower()) for t in tokens]
    changed = True
    while changed:
        changed = False
        for n in range(len(tokens) // 2, min_words - 1, -1):
            for i in range(len(tokens) - 2 * n + 1):
                if norm[i:i + n] == norm[i + n:i + 2 * n]:
                    del tokens[i + n:i + 2 * n], norm[i + n:i + 2 * n]
                    changed = True
                    break
            if changed:
                break
    return " ".join(tokens)


def _cut_foreign(text: str) -> str:
    """Num áudio em português, letra de outro alfabeto indica alucinação: corta dali em diante."""
    for i, ch in enumerate(text):
        if ch.isalpha() and "LATIN" not in unicodedata.name(ch, ""):
            return text[:i].rstrip() + " […]"
    return text
