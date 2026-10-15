"""Cache de transcrições (transcripts.db), separado do índice para sobreviver quando ele é refeito.

A chave é o hash do arquivo de áudio: o mesmo áudio encaminhado em várias conversas é transcrito
uma vez só. Também guarda a fila de prioridade (pedidos do Claude) e as falhas recentes.
"""

import hashlib
import sqlite3
import time
from pathlib import Path

from . import config

SCHEMA = """
PRAGMA journal_mode = WAL;
CREATE TABLE IF NOT EXISTS files (media_path TEXT PRIMARY KEY, size INTEGER, mtime_ns INTEGER, sha256 TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS transcripts (
    sha256 TEXT PRIMARY KEY, text TEXT NOT NULL, model TEXT NOT NULL, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS priority (message_id INTEGER PRIMARY KEY, requested_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS failures (media_path TEXT PRIMARY KEY, reason TEXT, failed_at INTEGER NOT NULL);
"""

# Um áudio que falhou (arquivo sumiu, decodificação quebrou) só é tentado de novo depois disso.
RETRY_FAILED_AFTER = 24 * 3600


def connect() -> sqlite3.Connection:
    path = config.home() / "transcripts.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def file_hash(conn: sqlite3.Connection, media_path: str, path: Path) -> str:
    """sha256 do arquivo, reaproveitando o cálculo enquanto tamanho e data não mudam."""
    st = path.stat()
    row = conn.execute("SELECT size, mtime_ns, sha256 FROM files WHERE media_path = ?", (media_path,)).fetchone()
    if row and row["size"] == st.st_size and row["mtime_ns"] == st.st_mtime_ns:
        return row["sha256"]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO files (media_path, size, mtime_ns, sha256) VALUES (?, ?, ?, ?)",
            (media_path, st.st_size, st.st_mtime_ns, digest),
        )
    return digest


def get(conn: sqlite3.Connection, sha256: str) -> str | None:
    row = conn.execute("SELECT text FROM transcripts WHERE sha256 = ?", (sha256,)).fetchone()
    return row["text"] if row else None


def put(conn: sqlite3.Connection, sha256: str, text: str, model: str) -> None:
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO transcripts (sha256, text, model, created_at) VALUES (?, ?, ?, ?)",
            (sha256, text, model, int(time.time())),
        )


def by_media_path(conn: sqlite3.Connection) -> dict[str, str]:
    """media_path → transcrição, para o sync reaplicar no índice sem abrir nenhum arquivo."""
    rows = conn.execute("SELECT f.media_path, t.text FROM files f JOIN transcripts t ON t.sha256 = f.sha256")
    return {r["media_path"]: r["text"] for r in rows}


def prioritize(conn: sqlite3.Connection, message_ids: list[int]) -> None:
    now = int(time.time())
    with conn:
        conn.executemany("INSERT OR IGNORE INTO priority VALUES (?, ?)", [(i, now) for i in message_ids])


def priority_ids(conn: sqlite3.Connection) -> list[int]:
    return [r["message_id"] for r in conn.execute("SELECT message_id FROM priority ORDER BY requested_at")]


def done(conn: sqlite3.Connection, message_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM priority WHERE message_id = ?", (message_id,))


def fail(conn: sqlite3.Connection, media_path: str, reason: str) -> None:
    with conn:
        conn.execute("INSERT OR REPLACE INTO failures VALUES (?, ?, ?)", (media_path, reason, int(time.time())))


def recently_failed(conn: sqlite3.Connection) -> set[str]:
    since = int(time.time()) - RETRY_FAILED_AFTER
    return {r["media_path"] for r in conn.execute("SELECT media_path FROM failures WHERE failed_at > ?", (since,))}
