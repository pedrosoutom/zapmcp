"""Fila de transcrição: roda num processo próprio, para não travar o servidor MCP.

Ordem: primeiro os áudios que o Claude pediu (transcribe_audio), depois os dos últimos 7 dias
(ZAPMCP_TRANSCRIBE_DAYS), dos mais novos para os mais antigos, e cada áudio novo que chegar. Os mais
antigos e os de grupos arquivados só a pedido, ou com `zapmcp transcribe --all` / `--archived`. Com o Mac na bateria, só atende os pedidos, a
menos que ZAPMCP_TRANSCRIBE_ON_BATTERY=1.
"""

import logging
import os
import subprocess
import sys
import threading
import time
from contextlib import closing

from . import config, media, store, transcripts

log = logging.getLogger("zapmcp")

IDLE_SLEEP = 60
BATTERY_SLEEP = 300


def run_once(
    transcriber,
    limit: int | None = None,
    requested_only: bool = False,
    all_history: bool = False,
    archived_groups: bool | None = None,
) -> int:
    """Transcreve até `limit` áudios da fila e para. Devolve quantos processou."""
    done = 0
    while limit is None or done < limit:
        job = _next_job(requested_only, all_history, archived_groups)
        if job is None:
            break
        _process(transcriber, *job)
        done += 1
    return done


def run_forever(transcriber, parent_pid: int | None = None) -> None:
    """Modo segundo plano: segue a fila enquanto o servidor que o iniciou estiver vivo."""
    try:
        os.nice(10)
    except OSError:
        pass
    if parent_pid is not None:
        threading.Thread(target=_exit_when_parent_closes, daemon=True).start()
    # Com o ZapMCP aberto em dois lugares (Claude Desktop e Claude Code), só um trabalhador transcreve;
    # o outro espera a vez. Os pedidos de qualquer servidor ficam no mesmo transcripts.db.
    lock = (config.home() / "transcricao.lock").open("w")
    while not _try_lock(lock):
        _sleep(30, parent_pid)
    while parent_pid is None or os.getppid() == parent_pid:
        battery = _on_battery() and not config.transcribe_on_battery()
        if not run_once(transcriber, limit=10, requested_only=battery):
            _sleep(BATTERY_SLEEP if battery else IDLE_SLEEP, parent_pid)


def spawn(parent_pid: int) -> subprocess.Popen:
    """Inicia o trabalhador em outro processo. A saída dele nunca pode cair no stdio do MCP."""
    logs = config.home() / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        [sys.executable, "-m", "zapmcp.cli", "transcribe", "--daemon", "--parent", str(parent_pid)],
        # O stdin fica aberto só para o trabalhador saber que o servidor está vivo (ver _exit_when_parent_closes).
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=(logs / "transcricao.log").open("a"),
    )


def _try_lock(handle) -> bool:
    try:
        import fcntl
    except ImportError:  # Windows: sem trava por enquanto
        return True
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _exit_when_parent_closes() -> None:
    """O servidor segura a outra ponta do stdin. Quando ele morre, de qualquer jeito, o sistema fecha
    o canal, a leitura volta vazia e o trabalhador sai na hora, mesmo no meio de uma transcrição."""
    sys.stdin.buffer.read()
    os._exit(0)


def _next_job(
    requested_only: bool = False, all_history: bool = False, archived_groups: bool | None = None
) -> tuple[int, str] | None:
    with closing(transcripts.connect()) as cache, closing(store.connect(config.index_path())) as idx:
        skip = transcripts.recently_failed(cache)
        for message_id in transcripts.priority_ids(cache):
            row = store.message(idx, message_id)
            if row is None or row["transcript"] is not None or not row["media_path"] or row["media_path"] in skip:
                transcripts.done(cache, message_id)
                continue
            return message_id, row["media_path"]
        if requested_only:
            return None
        since = 0 if all_history else int(time.time()) - config.transcribe_days() * 86400
        if archived_groups is None:
            archived_groups = config.transcribe_archived_groups()
        for row in store.pending_audio(idx, since, archived_groups=archived_groups):
            if row["media_path"] not in skip:
                return row["id"], row["media_path"]
    return None


def _process(transcriber, message_id: int, media_path: str) -> None:
    with closing(transcripts.connect()) as cache, closing(store.connect(config.index_path())) as idx:
        path = media.local_file(media_path)
        if path is None:
            transcripts.fail(cache, media_path, "arquivo não está neste Mac")
            transcripts.done(cache, message_id)
            return
        try:
            digest = transcripts.file_hash(cache, media_path, path)
            text = transcripts.get(cache, digest)
            if text is None:
                started = time.monotonic()
                text = transcriber.transcribe(path)
                transcripts.put(cache, digest, text, transcriber.name)
                log.info("#%d transcrito em %.1f s", message_id, time.monotonic() - started)
        except Exception as e:
            log.warning("#%d: falhou (%s)", message_id, e)
            transcripts.fail(cache, media_path, str(e)[:200])
            transcripts.done(cache, message_id)
            return
        store.set_transcript(idx, media_path, text)
        transcripts.done(cache, message_id)


def _on_battery() -> bool:
    if sys.platform != "darwin":
        return False
    try:
        out = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "Battery Power" in out.splitlines()[0] if out else False


def _sleep(seconds: int, parent_pid: int | None) -> None:
    """Dorme em passos curtos: acorda se o Claude pedir um áudio, sai se o servidor fechar."""
    for tick in range(seconds):
        if parent_pid is not None and os.getppid() != parent_pid:
            return
        if tick % 2 == 0:
            with closing(transcripts.connect()) as cache:
                if transcripts.priority_ids(cache):
                    return
        time.sleep(1)
