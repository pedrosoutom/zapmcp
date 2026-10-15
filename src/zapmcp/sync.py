"""O indexador: copia o banco do WhatsApp e atualiza o índice próprio."""

import threading
import time
from contextlib import closing
from dataclasses import dataclass

from . import config, snapshot, store, transcripts, whatsapp

# Além das mensagens novas, cada rodada revisita as últimas 48 h: pega edições,
# mensagens apagadas e mídias baixadas depois de a mensagem chegar.
RESCAN_SECONDS = 48 * 3600

_lock = threading.Lock()


@dataclass(frozen=True)
class SyncResult:
    messages: int
    chats: int
    seconds: float
    full: bool


def run(full: bool = False) -> SyncResult:
    with _lock:
        return _run(full)


def refresh(max_age: int) -> SyncResult | None:
    """Roda o sync só se o último tiver mais de `max_age` segundos."""
    with _lock:
        with closing(store.connect(config.index_path())) as idx:
            last = store.last_sync(idx)
        if last is not None and time.time() - last < max_age:
            return None
        return _run(full=False)


def _run(full: bool) -> SyncResult:
    started = time.monotonic()
    snap = snapshot.take(config.wa_dir(), config.snapshot_dir())
    try:
        with closing(whatsapp.open_copy(snap)) as wa, closing(store.connect(config.index_path())) as idx:
            with idx:
                last_id = int(store.get_meta(idx, "last_message_id") or 0)
                # Índice montado por uma versão anterior do normalizador: refaz tudo.
                full = full or store.get_meta(idx, "normalizer_version") != str(whatsapp.NORMALIZER_VERSION)
                if full:
                    store.clear(idx)
                    last_id = 0
                since = int(time.time()) - RESCAN_SECONDS if last_id else 0

                chats = whatsapp.read_chats(wa)
                store.upsert_chats(idx, chats)
                messages = whatsapp.read_messages(
                    wa,
                    {c.id: c for c in chats},
                    whatsapp.address_book(wa),
                    whatsapp.profile_names(wa),
                    after_id=last_id,
                    since_ts=since,
                )
                with closing(transcripts.connect()) as cache:
                    known = transcripts.by_media_path(cache)
                count, max_id = store.upsert_messages(idx, messages, known)

                store.set_meta(idx, "last_message_id", str(max(last_id, max_id)))
                store.set_meta(idx, "last_sync", str(int(time.time())))
                store.set_meta(idx, "normalizer_version", str(whatsapp.NORMALIZER_VERSION))
    finally:
        snapshot.discard(snap)
    return SyncResult(count, len(chats), time.monotonic() - started, full or last_id == 0)
