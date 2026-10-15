"""O índice próprio (index.db): o contrato entre o indexador, o servidor MCP e o export."""

import re
import sqlite3
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from .whatsapp import Chat, Message

SCHEMA = """
PRAGMA journal_mode = WAL;
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY,
    jid TEXT NOT NULL,
    name TEXT NOT NULL,
    search_name TEXT NOT NULL,
    is_group INTEGER NOT NULL,
    archived INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    ts INTEGER NOT NULL,
    from_me INTEGER NOT NULL,
    author TEXT NOT NULL,
    kind TEXT NOT NULL,
    text TEXT,
    media_path TEXT,
    duration REAL,
    transcript TEXT
);
CREATE INDEX IF NOT EXISTS messages_by_chat ON messages (chat_id, ts);
CREATE INDEX IF NOT EXISTS messages_by_media ON messages (media_path);
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
    USING fts5 (body, tokenize = 'unicode61 remove_diacritics 2');
"""

# Abaixo disso, o nome não parece com o que foi pedido.
MIN_SCORE = 0.5


@dataclass(frozen=True)
class ChatInfo:
    id: int
    name: str
    is_group: bool
    last_ts: int
    message_count: int
    score: float = 0.0
    archived: bool = False

    @property
    def archived_group(self) -> bool:
        return self.is_group and self.archived


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    # Índices criados antes da transcrição de áudio não têm a coluna; ela entra antes do resto do schema.
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(messages)")}
    if columns and "transcript" not in columns:
        conn.execute("ALTER TABLE messages ADD COLUMN transcript TEXT")
    conn.executescript(SCHEMA)
    return conn


# --- escrita (indexador) ---


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))


def last_sync(conn: sqlite3.Connection) -> int | None:
    value = get_meta(conn, "last_sync")
    return int(value) if value else None


def clear(conn: sqlite3.Connection) -> None:
    for table in ("messages", "messages_fts", "chats", "meta"):
        conn.execute(f"DELETE FROM {table}")


def upsert_chats(conn: sqlite3.Connection, chats: Iterable[Chat]) -> int:
    rows = [(c.id, c.jid, c.name, search_key(c.name), int(c.is_group), int(c.archived)) for c in chats]
    conn.executemany(
        """
        INSERT INTO chats (id, jid, name, search_name, is_group, archived) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (id) DO UPDATE SET jid = excluded.jid, name = excluded.name,
            search_name = excluded.search_name, is_group = excluded.is_group, archived = excluded.archived
        """,
        rows,
    )
    return len(rows)


def upsert_messages(
    conn: sqlite3.Connection, messages: Iterable[Message], transcripts: dict[str, str] | None = None
) -> tuple[int, int]:
    """Grava (ou regrava) mensagens e o texto pesquisável. Devolve (quantidade, maior id).

    `transcripts` (media_path → texto) vem do cache, para um áudio já transcrito não perder o texto
    quando o índice é regravado.
    """
    transcripts = transcripts or {}
    count = max_id = 0
    for m in messages:
        transcript = transcripts.get(m.media_path) if m.kind == "áudio" and m.media_path else None
        conn.execute(
            """
            INSERT OR REPLACE INTO messages
                (id, chat_id, ts, from_me, author, kind, text, media_path, duration, transcript)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (m.id, m.chat_id, m.ts, int(m.from_me), m.author, m.kind, m.text, m.media_path, m.duration, transcript),
        )
        _index_text(conn, m.id, m.kind, m.text, transcript)
        count += 1
        max_id = max(max_id, m.id)
    return count, max_id


def set_transcript(conn: sqlite3.Connection, media_path: str, text: str) -> list[int]:
    """Grava a transcrição em toda mensagem com esse áudio. Devolve os ids atualizados."""
    rows = conn.execute("SELECT id, kind, text FROM messages WHERE media_path = ?", (media_path,)).fetchall()
    with conn:
        conn.execute("UPDATE messages SET transcript = ? WHERE media_path = ?", (text, media_path))
        for r in rows:
            _index_text(conn, r["id"], r["kind"], r["text"], text)
    return [r["id"] for r in rows]


def pending_audio(
    conn: sqlite3.Connection, since: int = 0, limit: int = 200, archived_groups: bool = False
) -> list[sqlite3.Row]:
    """Áudios ainda sem transcrição desde `since` (unix), dos mais novos para os mais antigos.

    Grupos arquivados ficam de fora, a menos que `archived_groups`.
    """
    return conn.execute(
        """
        SELECT m.id, m.media_path, m.duration FROM messages m JOIN chats c ON c.id = m.chat_id
        WHERE m.kind = 'áudio' AND m.transcript IS NULL AND m.media_path IS NOT NULL AND m.ts >= ?
          AND (? OR NOT (c.is_group = 1 AND c.archived = 1))
        ORDER BY m.ts DESC LIMIT ?
        """,
        (since, int(archived_groups), limit),
    ).fetchall()


def _index_text(conn: sqlite3.Connection, message_id: int, kind: str, text: str | None, transcript: str | None) -> None:
    conn.execute("DELETE FROM messages_fts WHERE rowid = ?", (message_id,))
    body = " ".join(part for part in (text, transcript) if part)
    if body and kind != "sistema":
        conn.execute("INSERT INTO messages_fts (rowid, body) VALUES (?, ?)", (message_id, body))


# --- leitura (servidor MCP e export) ---

_CHATS_SQL = """
    SELECT c.id, c.name, c.search_name, c.is_group, c.archived, s.last_ts, s.n
    FROM chats c
    JOIN (
        SELECT chat_id, MAX(ts) AS last_ts, COUNT(*) AS n
        FROM messages WHERE kind <> 'sistema' GROUP BY chat_id
    ) s ON s.chat_id = c.id
"""


def chats(
    conn: sqlite3.Connection, query: str = "", active_since: int | None = None, limit: int | None = 20
) -> list[ChatInfo]:
    """Conversas com mensagens, das mais recentes para as mais antigas; com `query`, as mais parecidas primeiro."""
    rows = conn.execute(_CHATS_SQL + " WHERE s.last_ts >= ?", (active_since or 0,)).fetchall()
    wanted = search_key(query)
    found = []
    for r in rows:
        score = _similarity(wanted, r["search_name"]) if wanted else 0.0
        if wanted and score < MIN_SCORE:
            continue
        found.append(ChatInfo(r["id"], r["name"], bool(r["is_group"]), r["last_ts"], r["n"], score, bool(r["archived"])))
    found.sort(key=lambda c: (c.score, c.last_ts), reverse=True)
    return found[:limit] if limit else found


def resolve_chat(conn: sqlite3.Connection, ref: str) -> tuple[ChatInfo, list[ChatInfo]]:
    """Acha uma conversa por id ou nome aproximado. Devolve a escolhida e outras quase tão parecidas."""
    ref = ref.strip()
    if ref.isdigit():
        row = conn.execute(_CHATS_SQL + " WHERE c.id = ?", (int(ref),)).fetchone()
        if row:
            return ChatInfo(
                row["id"], row["name"], bool(row["is_group"]), row["last_ts"], row["n"], 1.0, bool(row["archived"])
            ), []
    ranked = chats(conn, query=ref, limit=5)
    if not ranked:
        raise LookupError(f'Nenhuma conversa com nome parecido com "{ref}". Use list_chats para ver os nomes.')
    best, rest = ranked[0], ranked[1:]
    return best, [c for c in rest if c.score >= best.score - 0.05]


def messages_in(
    conn: sqlite3.Connection, chat_id: int, since: int, until: int | None = None
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM messages
        WHERE chat_id = ? AND ts >= ? AND ts < ? AND kind <> 'sistema'
        ORDER BY ts, id
        """,
        (chat_id, since, until if until is not None else 2**62),
    ).fetchall()


def search(
    conn: sqlite3.Connection,
    query: str,
    chat_id: int | None = None,
    since: int | None = None,
    until: int | None = None,
    limit: int = 20,
) -> list[sqlite3.Row]:
    """Busca por palavras (FTS5), das mais relevantes para as menos."""
    sql = """
        SELECT m.*, c.name AS chat_name, c.is_group AS chat_is_group
        FROM messages_fts
        JOIN messages m ON m.id = messages_fts.rowid
        JOIN chats c ON c.id = m.chat_id
        WHERE messages_fts MATCH ?
    """
    params: list = []
    if chat_id is not None:
        sql += " AND m.chat_id = ?"
        params.append(chat_id)
    if since is not None:
        sql += " AND m.ts >= ?"
        params.append(since)
    if until is not None:
        sql += " AND m.ts < ?"
        params.append(until)
    sql += " ORDER BY messages_fts.rank LIMIT ?"
    params.append(limit)
    try:
        return conn.execute(sql, [query, *params]).fetchall()
    except sqlite3.OperationalError:
        # A sintaxe do FTS5 não aceita alguns caracteres soltos (R$, -, :); busca as palavras literalmente.
        words = re.findall(r"\w+", query)
        if not words:
            raise ValueError(f'Nada pesquisável em "{query}".') from None
        literal = " ".join(f'"{w}"' for w in words)
        return conn.execute(sql, [literal, *params]).fetchall()


def message(conn: sqlite3.Connection, message_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT m.*, c.name AS chat_name, c.is_group AS chat_is_group
        FROM messages m JOIN chats c ON c.id = m.chat_id WHERE m.id = ?
        """,
        (message_id,),
    ).fetchone()


def neighbors(conn: sqlite3.Connection, msg: sqlite3.Row, n: int) -> tuple[list[sqlite3.Row], list[sqlite3.Row]]:
    """As `n` mensagens antes e depois de `msg` na mesma conversa."""
    key = (msg["chat_id"], msg["ts"], msg["ts"], msg["id"])
    before = conn.execute(
        """
        SELECT * FROM messages WHERE chat_id = ? AND kind <> 'sistema' AND (ts < ? OR (ts = ? AND id < ?))
        ORDER BY ts DESC, id DESC LIMIT ?
        """,
        (*key, n),
    ).fetchall()
    after = conn.execute(
        """
        SELECT * FROM messages WHERE chat_id = ? AND kind <> 'sistema' AND (ts > ? OR (ts = ? AND id > ?))
        ORDER BY ts, id LIMIT ?
        """,
        (*key, n),
    ).fetchall()
    return list(reversed(before)), after


def search_key(text: str) -> str:
    """Minúsculas, sem acentos, emojis nem pontuação: "Família 🏡 Souza" → "familia souza"."""
    decomposed = unicodedata.normalize("NFKD", text)
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()
    return " ".join(re.findall(r"[a-z0-9]+", plain))


def _similarity(wanted: str, name: str) -> float:
    if name == wanted:
        return 1.0
    if name.startswith(wanted):
        return 0.95
    if wanted in name:
        return 0.9
    words = wanted.split()
    if words and all(w in name for w in words):
        return 0.85
    return SequenceMatcher(None, wanted, name).ratio() * 0.8
