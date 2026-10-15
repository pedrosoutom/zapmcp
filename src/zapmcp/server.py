"""Servidor MCP (stdio) sobre o índice local. Só leitura."""

import atexit
import logging
import os
import time
from importlib.metadata import version
from collections.abc import Iterator
from contextlib import closing, contextmanager
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.tools import ToolResult
from mcp.types import TextContent
from pydantic import Field

from . import config, media, store, sync, transcripts, worker
from . import format as fmt
from .dates import HELP as DATE_HELP
from .dates import parse_when

log = logging.getLogger("zapmcp")

INSTRUCTIONS = """\
Acesso somente leitura às conversas do WhatsApp deste Mac, a partir de um índice local.

- Para uma conversa específica: list_chats para achar o id (aceita nome aproximado), depois get_messages com o período.
- Para um assunto sem conversa definida: search.
- Cada mensagem vem numa linha: [AAAA-MM-DD HH:MM] Autor: texto, no horário local do Mac.
- "Você" é o dono deste WhatsApp. "~ Nome" é o nome de perfil de alguém que não está na agenda.
- Menções aparecem como @Nome (agenda) ou @~Nome (nome de perfil); @ seguido de número é alguém sem nome conhecido.
- Mídias aparecem como marcadores: [imagem #123] legenda, [documento #456 · 1,2 MB] nome, [áudio 0:37].
- Anexo com número pode ser aberto: view_images para imagens (até 5 por vez) e read_document para documentos,
  em partes. Sem número, o arquivo não está neste Mac. Abra só o que a pergunta precisa: cada imagem ocupa
  bastante contexto.
- Áudios vêm transcritos no próprio Mac: [áudio 0:37] texto. A transcrição automática cobre os últimos
  7 dias e os áudios novos, exceto em grupos arquivados; os que não têm transcrição aparecem como
  [áudio #123 0:37 · ainda não transcrito], e transcribe_audio transcreve na hora, inclusive os mais
  antigos e os de grupos arquivados. A transcrição pode errar nomes próprios e termos técnicos.
"""

mcp = FastMCP("ZapMCP", instructions=INSTRUCTIONS, version=version("zapmcp"))

READ_ONLY = {"read_only_hint": True, "open_world_hint": False}

When = Annotated[str | None, Field(description=f"Data ou período relativo. {DATE_HELP}")]


@contextmanager
def _index() -> Iterator:
    with closing(store.connect(config.index_path())) as conn:
        yield conn


def _refresh() -> str:
    """Na v1, o próprio servidor atualiza o índice quando ele está velho. Devolve um aviso se falhar."""
    max_age = config.auto_sync_seconds()
    if max_age <= 0:
        return ""
    try:
        sync.refresh(max_age)
        return ""
    except Exception as e:
        log.warning("não consegui atualizar o índice: %s", e)
        with _index() as conn:
            last = store.last_sync(conn)
        if last is None:
            raise ToolError(f"O índice ainda está vazio e não consegui criá-lo: {e}") from e
        return f"Aviso: não consegui atualizar o índice agora ({e}). Dados até {fmt.when(last)}.\n\n"


def _when(value: str | None, *, end_of_day: bool = False) -> int | None:
    if not value:
        return None
    try:
        return parse_when(value, end_of_day=end_of_day)
    except ValueError as e:
        raise ToolError(str(e)) from e


def _chat(conn, ref: str) -> tuple[store.ChatInfo, list[store.ChatInfo]]:
    try:
        return store.resolve_chat(conn, ref)
    except LookupError as e:
        raise ToolError(str(e)) from e


@mcp.tool(annotations=READ_ONLY)
def list_chats(
    query: Annotated[str, Field(description="Parte do nome da conversa; aceita nome aproximado. Vazio lista as mais recentes.")] = "",
    active_since: When = None,
    limit: Annotated[int, Field(ge=1, le=200)] = 20,
) -> str:
    """Lista conversas do WhatsApp (grupos e individuais): id, nome, tipo, última mensagem e total de mensagens.

    Sem `query`, vêm as mais recentes. Com `query`, as de nome mais parecido.
    """
    note = _refresh()
    with _index() as conn:
        found = store.chats(conn, query=query, active_since=_when(active_since), limit=limit)
    if not found:
        return note + "Nenhuma conversa encontrada."
    return note + "\n".join(fmt.chat_row(c) for c in found)


@mcp.tool(annotations=READ_ONLY)
def get_messages(
    chat: Annotated[str, Field(description="id da conversa (de list_chats) ou nome aproximado.")],
    since: Annotated[str, Field(description=f"Início do período. {DATE_HELP}")] = "7d",
    until: When = None,
    limit: Annotated[int, Field(ge=1, le=2000, description="Máximo de mensagens; se passar, vêm as mais recentes.")] = 400,
) -> str:
    """Mensagens de uma conversa num período, em ordem cronológica, uma por linha."""
    note = _refresh()
    start = _when(since) or 0
    end = _when(until, end_of_day=True)
    with _index() as conn:
        found, similar = _chat(conn, chat)
        rows = store.messages_in(conn, found.id, start, end)
    return note + fmt.conversation(found, rows, start, end, limit, similar)


@mcp.tool(annotations=READ_ONLY)
def search(
    query: Annotated[
        str,
        Field(description='Palavras a buscar (todas precisam aparecer). Aceita "frase exata", prefixo* e OR. Ignora acentos.'),
    ],
    chat: Annotated[str | None, Field(description="Restringe a uma conversa: id ou nome aproximado.")] = None,
    since: When = None,
    until: When = None,
    limit: Annotated[int, Field(ge=1, le=100)] = 20,
) -> str:
    """Busca por palavras nas mensagens, das mais relevantes para as menos, com as mensagens ao redor de cada uma.

    Encontra palavras, não significado: para "prazo", tente também "entrega", "sexta" etc.
    """
    note = _refresh()
    with _index() as conn:
        chat_id = _chat(conn, chat)[0].id if chat else None
        try:
            hits = store.search(conn, query, chat_id, _when(since), _when(until, end_of_day=True), limit)
        except ValueError as e:
            raise ToolError(str(e)) from e
        results = [(hit, *store.neighbors(conn, hit, 2)) for hit in hits]
    return note + fmt.search_results(query, results)


def _attachment(conn, message_id: int, kind: str):
    """A mensagem e o arquivo de um anexo, ou um erro que diz ao Claude o que fazer."""
    msg = store.message(conn, message_id)
    if msg is None:
        raise ToolError(f"#{message_id}: não encontrei essa mensagem.")
    if msg["kind"] != kind:
        other = {"imagem": "view_images", "documento": "read_document"}.get(msg["kind"])
        hint = f" Use {other}." if other else ""
        raise ToolError(f"#{message_id} é {msg['kind']}, não {kind}.{hint}")
    path = media.local_file(msg["media_path"])
    if path is None:
        raise ToolError(f"#{message_id}: o arquivo não está neste Mac (o WhatsApp Desktop nunca o baixou).")
    return msg, path


def _blocks(items: list) -> ToolResult:
    """Cada texto e imagem como um bloco. Uma lista só de textos o FastMCP juntaria num JSON."""
    return ToolResult(content=[TextContent(type="text", text=i) if isinstance(i, str) else i for i in items])


def _origin(msg) -> str:
    return f"{msg['chat_name']} · {msg['author']} · {fmt.when(msg['ts'])}"


@mcp.tool(annotations=READ_ONLY)
def view_images(
    ids: Annotated[
        list[int],
        Field(min_length=1, max_length=5, description="Números das imagens, como aparecem em [imagem #123]."),
    ],
) -> ToolResult:
    """Mostra imagens das conversas, com conversa, autor, data e legenda de cada uma."""
    content: list = []
    with _index() as conn:
        for message_id in ids:
            try:
                msg, path = _attachment(conn, message_id, "imagem")
                picture = media.image(path)
            except ToolError as e:
                content.append(str(e))
                continue
            except Exception as e:
                content.append(f"#{message_id}: não consegui abrir a imagem ({e}).")
                continue
            caption = f" · legenda: {msg['text']}" if msg["text"] else ""
            content += [f"#{message_id} · {_origin(msg)}{caption}", picture]
    return _blocks(content)


@mcp.tool(annotations=READ_ONLY)
def read_document(
    id: Annotated[int, Field(description="Número do documento, como aparece em [documento #456].")],
    part: Annotated[int, Field(ge=1, description="Parte a ler; documentos longos vêm em partes.")] = 1,
) -> ToolResult:
    """Lê um documento anexado: PDF, Word, Excel, PowerPoint, HTML, texto ou a lista de um ZIP.

    O texto vem em partes de até ~15 mil caracteres. Páginas escaneadas de PDF vêm como imagem.
    """
    with _index() as conn:
        msg, path = _attachment(conn, id, "documento")
    name = msg["text"] or path.name
    if path.suffix.lower() in media.IMAGE_SUFFIXES:
        return _blocks([f"# {name} · imagem\n{_origin(msg)}", media.image(path)])
    try:
        doc = media.read_document(path)
    except media.UnsupportedDocument as e:
        raise ToolError(f"#{id} ({name}): {e}") from e
    except Exception as e:
        raise ToolError(f"#{id} ({name}): não consegui ler o documento ({e}).") from e
    if part > len(doc.parts):
        raise ToolError(f"#{id} tem {len(doc.parts)} parte(s).")

    chunk = doc.parts[part - 1]
    head = [f"# {name} · {doc.kind}, {doc.extent} · parte {part} de {len(doc.parts)}", _origin(msg)]
    if part < len(doc.parts):
        head.append(f"Para continuar, chame read_document com part={part + 1}.")
    content: list = ["\n".join(head) + "\n\n" + chunk.text]
    for page in chunk.scanned_pages:
        content += [f"Página {page + 1} (escaneada):", media.pdf_page_image(path, page)]
    return _blocks(content)


_worker = None


def _ensure_worker() -> None:
    """Garante o processo de transcrição rodando (ele sai sozinho quando o servidor fecha)."""
    global _worker
    if not config.transcribe_enabled():
        return
    if _worker is None or _worker.poll() is not None:
        _worker = worker.spawn(os.getpid())
        atexit.register(_worker.terminate)


@mcp.tool(annotations=READ_ONLY)
def transcribe_audio(
    ids: Annotated[
        list[int],
        Field(min_length=1, max_length=10, description="Números dos áudios, como em [áudio #123 · ainda não transcrito]."),
    ],
) -> str:
    """Transcreve na hora áudios que ainda não foram transcritos. Espera até ~1,5 min pelo resultado."""
    problems, wanted = [], []
    with _index() as conn:
        for message_id in ids:
            msg = store.message(conn, message_id)
            if msg is None:
                problems.append(f"#{message_id}: não encontrei essa mensagem.")
            elif msg["kind"] != "áudio":
                problems.append(f"#{message_id} é {msg['kind']}, não áudio.")
            elif msg["transcript"] is None:
                if media.local_file(msg["media_path"]):
                    wanted.append(message_id)
                else:
                    problems.append(f"#{message_id}: o arquivo não está neste Mac (o WhatsApp Desktop nunca o baixou).")

    if wanted:
        with closing(transcripts.connect()) as cache:
            transcripts.prioritize(cache, wanted)
        _ensure_worker()
        deadline = time.monotonic() + config.transcribe_wait_seconds()
        while time.monotonic() < deadline:
            with _index() as conn:
                if all(store.message(conn, i)["transcript"] is not None for i in wanted):
                    break
            time.sleep(1)

    results = []
    with _index() as conn:
        for message_id in ids:
            msg = store.message(conn, message_id)
            if msg is None or msg["kind"] != "áudio" or message_id not in wanted and msg["transcript"] is None:
                continue
            if msg["transcript"] is None:
                results.append(f"#{message_id}: ainda na fila de transcrição; tente de novo em instantes.")
            else:
                spoken = msg["transcript"] or "(sem fala)"
                results.append(f"#{message_id} · {_origin(msg)} · {fmt.duration(msg['duration'] or 0)}: {spoken}")
    return "\n".join(problems + results)


def serve() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s zapmcp %(levelname)s %(message)s")
    started = time.monotonic()
    try:
        sync.refresh(config.auto_sync_seconds() or 10**9)
        log.info("índice pronto em %.1f s", time.monotonic() - started)
    except Exception as e:
        log.warning("não consegui atualizar o índice ao iniciar: %s", e)
    _ensure_worker()
    mcp.run(show_banner=False)
