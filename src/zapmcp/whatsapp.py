"""Leitura do banco do WhatsApp Desktop (Mac), sempre a partir de uma cópia.

O schema é o Core Data interno do app, sem documentação. Tudo que depende dele fica aqui.
"""

import re
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

# Sobe quando muda a forma de montar as linhas; o sync então refaz o índice do zero.
NORMALIZER_VERSION = 4

# ZMESSAGEDATE conta segundos desde 2001-01-01 (epoch da Apple).
APPLE_EPOCH = 978307200

# ZSESSIONTYPE: 0 individual, 1 grupo, 4 grupo de comunidade.
# Ficam de fora 2 (status) e 3 (listas de transmissão, que repetem as conversas individuais).
CHAT_SESSION_TYPES = (0, 1, 4)

# ZMESSAGETYPE confirmados ou de alta confiança. Os demais viram "tipo N" até serem mapeados.
KINDS = {
    0: "texto",
    1: "imagem",
    2: "vídeo",
    3: "áudio",
    6: "sistema",
    7: "link",
    8: "documento",
    15: "figurinha",
}


@dataclass(frozen=True)
class Chat:
    id: int
    jid: str
    name: str
    is_group: bool
    archived: bool


@dataclass(frozen=True)
class Message:
    id: int
    chat_id: int
    ts: int
    from_me: bool
    author: str
    kind: str
    text: str | None
    media_path: str | None
    duration: float | None


def open_copy(snapshot_dir: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(snapshot_dir / "ChatStorage.sqlite")
    conn.row_factory = sqlite3.Row
    contacts = snapshot_dir / "ContactsV2.sqlite"
    if contacts.exists():
        conn.execute("ATTACH DATABASE ? AS contacts", (str(contacts),))
    return conn


def read_chats(conn: sqlite3.Connection) -> list[Chat]:
    types = ", ".join(str(t) for t in CHAT_SESSION_TYPES)
    rows = conn.execute(
        f"""
        SELECT Z_PK, ZCONTACTJID, ZPARTNERNAME, ZARCHIVED
        FROM ZWACHATSESSION
        WHERE ZSESSIONTYPE IN ({types}) AND COALESCE(ZREMOVED, 0) = 0
        """
    )
    chats = []
    for r in rows:
        jid = r["ZCONTACTJID"] or ""
        name = _clean(r["ZPARTNERNAME"]) or jid or f"conversa {r['Z_PK']}"
        chats.append(Chat(r["Z_PK"], jid, name, jid.endswith("@g.us"), bool(r["ZARCHIVED"])))
    return chats


def address_book(conn: sqlite3.Connection) -> dict[str, str]:
    """jid (@lid ou @s.whatsapp.net) → nome na agenda."""
    attached = {r["name"] for r in conn.execute("PRAGMA database_list")}
    if "contacts" not in attached:
        return {}
    book = {}
    rows = conn.execute(
        "SELECT ZLID, ZWHATSAPPID, ZFULLNAME FROM contacts.ZWAADDRESSBOOKCONTACT WHERE ZFULLNAME <> ''"
    )
    for r in rows:
        for jid in (r["ZLID"], r["ZWHATSAPPID"]):
            if jid:
                book[jid] = r["ZFULLNAME"].strip()
    return book


def profile_names(conn: sqlite3.Connection) -> dict[str, str]:
    """jid → nome de perfil (o que a pessoa escolheu no WhatsApp)."""
    try:
        rows = conn.execute("SELECT ZJID, ZPUSHNAME FROM ZWAPROFILEPUSHNAME WHERE ZJID IS NOT NULL").fetchall()
    except sqlite3.OperationalError:  # versões do app sem essa tabela
        return {}
    return {r["ZJID"]: name for r in rows if (name := _clean(r["ZPUSHNAME"]))}


def read_messages(
    conn: sqlite3.Connection,
    chats: dict[int, Chat],
    book: dict[str, str],
    profiles: dict[str, str],
    after_id: int,
    since_ts: int,
) -> Iterator[Message]:
    """Mensagens com Z_PK depois de `after_id` ou com data depois de `since_ts` (unix)."""
    rows = conn.execute(
        """
        SELECT m.Z_PK AS id, m.ZCHATSESSION AS chat_id, m.ZMESSAGEDATE AS date,
               m.ZISFROMME AS from_me, m.ZMESSAGETYPE AS type, m.ZTEXT AS text,
               gm.ZMEMBERJID AS member_jid,
               gm.ZFIRSTNAME AS member_first_name, mi.ZTITLE AS media_title,
               mi.ZMEDIALOCALPATH AS media_path, mi.ZMOVIEDURATION AS duration
        FROM ZWAMESSAGE m
        LEFT JOIN ZWAGROUPMEMBER gm ON gm.Z_PK = m.ZGROUPMEMBER
        LEFT JOIN ZWAMEDIAITEM mi ON mi.ZMESSAGE = m.Z_PK
        WHERE m.ZMESSAGEDATE IS NOT NULL AND (m.Z_PK > ? OR m.ZMESSAGEDATE > ?)
        ORDER BY m.Z_PK
        """,
        (after_id, since_ts - APPLE_EPOCH),
    )
    for r in rows:
        chat = chats.get(r["chat_id"])
        if chat is not None:
            yield _normalize(r, chat, book, profiles)


def _normalize(r: sqlite3.Row, chat: Chat, book: dict[str, str], profiles: dict[str, str]) -> Message:
    kind = KINDS.get(r["type"], f"tipo {r['type']}")
    # Em imagem e vídeo a legenda fica no item de mídia; em documento, ZTEXT traz o nome do arquivo.
    text = r["media_title"] if kind in ("imagem", "vídeo") else r["text"] or r["media_title"]
    if text:
        text = _name_mentions(text, book, profiles)
    return Message(
        id=r["id"],
        chat_id=chat.id,
        ts=int(r["date"]) + APPLE_EPOCH,
        from_me=bool(r["from_me"]),
        author=_author(r, chat, book, profiles),
        kind=kind,
        text=_clean(text),
        media_path=r["media_path"],
        duration=r["duration"] or None,
    )


def _author(r: sqlite3.Row, chat: Chat, book: dict[str, str], profiles: dict[str, str]) -> str:
    if r["from_me"]:
        return "Você"
    if not chat.is_group:
        return chat.name
    jid = r["member_jid"]
    if jid in book:
        return book[jid]
    # Fora da agenda, o WhatsApp mostra o nome de perfil com "~" na frente; fazemos igual.
    # O ZPUSHNAME da mensagem não serve: no app de Mac ele guarda um dado codificado, não o nome.
    if jid in profiles:
        return f"~ {profiles[jid]}"
    # ZFIRSTNAME às vezes traz um dado codificado com "+" na frente (o recado do perfil, por exemplo).
    first_name = _clean(r["member_first_name"])
    if first_name and not re.fullmatch(r"\+[A-Za-z0-9+/]{6,}={0,2}", first_name):
        return first_name
    return jid.split("@")[0] if jid else "desconhecido"


# Menção no texto: "@" + o número do identificador da pessoa (@lid ou telefone), que o app troca pelo nome.
_MENTION = re.compile(r"(?<!\w)@(\d{6,})")


def _name_mentions(text: str, book: dict[str, str], profiles: dict[str, str]) -> str:
    """ "bora @4455667788990!" → "bora @Tatá!" (agenda) ou "@~Maria" (nome de perfil)."""

    def name(match: re.Match) -> str:
        jids = (match[1] + "@lid", match[1] + "@s.whatsapp.net")
        if found := next((book[j] for j in jids if j in book), None):
            return f"@{found}"
        if found := next((profiles[j] for j in jids if j in profiles), None):
            return f"@~{found}"
        return match[0]

    return _MENTION.sub(name, text)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None
