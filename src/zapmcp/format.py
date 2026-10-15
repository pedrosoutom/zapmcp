"""Como as mensagens aparecem para o Claude e no .md: uma por linha, [data] Autor: texto."""

import sqlite3
from collections.abc import Sequence
from datetime import datetime

from . import config, media
from .store import ChatInfo


def when(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def when_exact(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def duration(seconds: float) -> str:
    minutes, secs = divmod(int(round(seconds)), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def number(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def body(msg: sqlite3.Row) -> str:
    kind, text = msg["kind"], msg["text"]
    if kind in ("texto", "link"):
        return text or ""
    tag = kind
    if msg["duration"] and kind in ("áudio", "vídeo"):
        tag += " " + duration(msg["duration"])
    if kind == "áudio":
        return _audio(msg, tag)
    if kind in media.OPENABLE:
        # Com número, o Claude pode abrir o anexo; sem arquivo no disco, avisamos para ele nem tentar.
        if path := media.local_file(msg["media_path"]):
            tag += f" #{msg['id']}"
            if kind == "documento":
                tag += f" · {media.human_size(path.stat().st_size)}"
        else:
            tag += " · sem arquivo neste Mac"
    return f"[{tag}] {text}" if text else f"[{tag}]"


def _audio(msg: sqlite3.Row, tag: str) -> str:
    transcript = msg["transcript"]
    if transcript:
        return f"[{tag}] {transcript}"
    if transcript == "":
        return f"[{tag} · sem fala]"
    if media.local_file(msg["media_path"]):
        return f"[{tag.replace('áudio', f'áudio #{msg['id']}', 1)} · ainda não transcrito]"
    return f"[{tag} · sem arquivo neste Mac]"


def pending_audio(rows: Sequence[sqlite3.Row]) -> int:
    return sum(1 for m in rows if m["kind"] == "áudio" and m["transcript"] is None and media.local_file(m["media_path"]))


def line(msg: sqlite3.Row) -> str:
    # Mensagens com várias linhas ficam recuadas, para nenhuma continuação parecer uma mensagem nova.
    return f"[{when(msg['ts'])}] {msg['author']}: {body(msg)}".replace("\n", "\n    ")


def chat_label(chat: ChatInfo) -> str:
    return f"{chat.name} ({'grupo' if chat.is_group else 'individual'} · id {chat.id})"


def chat_row(chat: ChatInfo) -> str:
    kind = "grupo arquivado" if chat.archived_group else "grupo" if chat.is_group else "individual"
    return f"{chat.id} · {chat.name} · {kind} · última {when(chat.last_ts)} · {number(chat.message_count)} msgs"


def period(since: int, until: int | None) -> str:
    return f"{when(since) if since else 'início'} → {when(until) if until else 'agora'}"


def conversation(
    chat: ChatInfo, rows: Sequence[sqlite3.Row], since: int, until: int | None, limit: int, similar: Sequence[ChatInfo]
) -> str:
    """Resposta do get_messages: cabeçalho e linhas; se passar do limite, as mais recentes."""
    shown = rows[-limit:]
    head = [f"# {chat_label(chat)}", f"{period(since, until)} · {number(len(rows))} mensagens"]
    if similar:
        head.append("Outras conversas com nome parecido: " + "; ".join(chat_label(c) for c in similar))
    if len(shown) < len(rows):
        head.append(
            f'Mostrando as {number(len(shown))} mais recentes. Para as anteriores, chame de novo com '
            f'until="{when_exact(shown[0]["ts"])}".'
        )
    if pending := pending_audio(shown):
        if chat.archived_group and not config.transcribe_archived_groups():
            why = ("Este grupo está arquivado, e áudios de grupos arquivados não são transcritos automaticamente; "
                   "para ter na hora, use transcribe_audio.")
        else:
            why = (f"Os dos últimos {config.transcribe_days()} dias são transcritos em segundo plano; para ter na "
                   "hora, ou para os mais antigos, use transcribe_audio.")
        head.append(f"{number(pending)} áudio(s) sem transcrição, marcados com #. {why}")
    if not rows:
        head.append("Nenhuma mensagem nesse período.")
    return "\n".join(head) + "\n\n" + "\n".join(line(m) for m in shown)


def search_results(query: str, hits: Sequence[tuple[sqlite3.Row, list, list]]) -> str:
    if not hits:
        return f'Nada encontrado para "{query}".'
    out = [f'{len(hits)} resultados para "{query}", dos mais relevantes aos menos. » marca a mensagem encontrada.']
    for hit, before, after in hits:
        kind = "grupo" if hit["chat_is_group"] else "individual"
        out.append(f"\n## {hit['chat_name']} ({kind} · id {hit['chat_id']})")
        out += ["  " + line(m) for m in before]
        out.append("» " + line(hit))
        out += ["  " + line(m) for m in after]
    return "\n".join(out)


def markdown(chat: ChatInfo, rows: Sequence[sqlite3.Row], since: int, until: int | None) -> str:
    audios = sum(1 for m in rows if m["kind"] == "áudio")
    kind = "Grupo" if chat.is_group else "Conversa individual"
    head = [
        f"# {chat.name}",
        "",
        f"{kind} · {period(since, until)} · {number(len(rows))} mensagens · {number(audios)} áudios",
        f"Exportado do WhatsApp pelo ZapMCP em {when(int(datetime.now().timestamp()))}.",
        "",
    ]
    return "\n".join(head + [line(m) for m in rows]) + "\n"
