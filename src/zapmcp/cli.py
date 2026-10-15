"""zapmcp sync | chats | export | transcribe | serve"""

import argparse
import sys
import time
from contextlib import closing
from pathlib import Path

from . import config, store, sync
from . import format as fmt
from .dates import parse_when
from .snapshot import SnapshotError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="zapmcp", description="Contexto do WhatsApp (Mac) para o Claude.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("sync", help="Atualiza o índice a partir de uma cópia do banco do WhatsApp.")
    p.add_argument("--full", action="store_true", help="Reconstrói o índice do zero.")

    p = sub.add_parser("chats", help="Lista conversas, das mais recentes para as mais antigas.")
    p.add_argument("query", nargs="?", default="", help="Parte do nome; aceita nome aproximado.")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--no-sync", action="store_true", help="Usa o índice como está, sem atualizar.")

    p = sub.add_parser("export", help="Exporta uma conversa para um arquivo .md.")
    p.add_argument("--chat", required=True, help="id ou nome aproximado da conversa.")
    p.add_argument("--since", default="7d", help="Início: 7d, 24h, 2w, hoje, ontem ou AAAA-MM-DD. Padrão: 7d.")
    p.add_argument("--until", help="Fim, no mesmo formato. Padrão: agora.")
    p.add_argument("--out", type=Path, default=Path("export"), help="Pasta de saída. Padrão: ./export")
    p.add_argument("--no-sync", action="store_true", help="Usa o índice como está, sem atualizar.")

    p = sub.add_parser("transcribe", help="Transcreve os áudios dos últimos 7 dias, dos mais novos para os mais antigos.")
    p.add_argument("--all", action="store_true", help="Inclui o histórico todo, não só os últimos 7 dias.")
    p.add_argument("--archived", action="store_true", help="Inclui os grupos arquivados.")
    p.add_argument("--limit", type=int, help="Para depois de N áudios. Padrão: todos.")
    p.add_argument("--no-sync", action="store_true", help="Usa o índice como está, sem atualizar.")
    p.add_argument("--daemon", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--parent", type=int, help=argparse.SUPPRESS)

    sub.add_parser("serve", help="Roda o servidor MCP (stdio), para o Claude Desktop ou Claude Code.")

    args = parser.parse_args(argv)
    try:
        if args.command == "serve":
            from .server import serve

            serve()
        elif args.command == "sync":
            _sync(full=args.full)
        elif args.command == "chats":
            _chats(args)
        elif args.command == "export":
            _export(args)
        elif args.command == "transcribe":
            _transcribe(args)
    except (SnapshotError, LookupError, ValueError) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 1
    return 0


def _sync(full: bool = False) -> None:
    r = sync.run(full=full)
    what = "processadas (índice completo)" if r.full else "novas ou revisadas"
    print(f"{fmt.number(r.messages)} mensagens {what}, {fmt.number(r.chats)} conversas, em {r.seconds:.1f} s.")


def _chats(args: argparse.Namespace) -> None:
    if not args.no_sync:
        _sync()
    with closing(store.connect(config.index_path())) as conn:
        found = store.chats(conn, query=args.query, limit=args.limit)
    print("\n".join(fmt.chat_row(c) for c in found) or "Nenhuma conversa encontrada.")


def _export(args: argparse.Namespace) -> None:
    if not args.no_sync:
        _sync()
    since = parse_when(args.since)
    until = parse_when(args.until, end_of_day=True) if args.until else None
    with closing(store.connect(config.index_path())) as conn:
        chat, similar = store.resolve_chat(conn, args.chat)
        rows = store.messages_in(conn, chat.id, since, until)
    first_day = fmt.when(since)[:10]
    last_day = fmt.when(until - 1 if until else int(time.time()))[:10]
    slug = "-".join(store.search_key(chat.name).split()) or f"conversa-{chat.id}"
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{slug}_{first_day}_{last_day}.md"
    path.write_text(fmt.markdown(chat, rows, since, until), encoding="utf-8")
    print(f"{path}  ({fmt.number(len(rows))} mensagens de {chat.name})")
    for c in similar:
        print(f"  outra conversa com nome parecido: {fmt.chat_label(c)}")


def _transcribe(args: argparse.Namespace) -> None:
    import logging

    from . import worker
    from .transcribe import Transcriber

    logging.basicConfig(level=logging.INFO, format="%(asctime)s zapmcp[%(process)d] %(levelname)s %(message)s")
    if args.daemon:
        worker.run_forever(Transcriber(), parent_pid=args.parent)
        return
    if not args.no_sync:
        _sync()
    archived = True if args.archived else None
    count = worker.run_once(Transcriber(), limit=args.limit, all_history=args.all, archived_groups=archived)
    print(f"{fmt.number(count)} áudios processados.")


if __name__ == "__main__":
    sys.exit(main())
