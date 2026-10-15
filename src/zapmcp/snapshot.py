"""Cópia de trabalho do banco do WhatsApp. Nunca abrimos nem alteramos o original."""

import shutil
import time
from pathlib import Path

DATABASES = ("ChatStorage.sqlite", "ContactsV2.sqlite")
# As mensagens mais recentes ficam no -wal até o SQLite passá-las para o .sqlite,
# então os arquivos de cada banco são copiados juntos.
SUFFIXES = ("", "-wal", "-shm")


class SnapshotError(RuntimeError):
    pass


def take(source: Path, dest: Path, attempts: int = 5) -> Path:
    main = source / DATABASES[0]
    try:
        if not main.exists():
            raise SnapshotError(f"Não encontrei {main}. O WhatsApp Desktop está instalado neste Mac?")
        dest.mkdir(parents=True, exist_ok=True)
        for _ in range(attempts):
            before = _fingerprint(source)
            _copy_all(source, dest)
            if _fingerprint(source) == before:
                return dest
            time.sleep(0.5)
    except PermissionError as e:
        raise SnapshotError(
            "Sem permissão para ler a pasta do WhatsApp. Dê Full Disk Access ao app que roda o ZapMCP "
            "(Ajustes do Sistema > Privacidade e Segurança > Acesso Total ao Disco)."
        ) from e
    raise SnapshotError("O WhatsApp gravou durante todas as tentativas de cópia. Tente de novo em instantes.")


def discard(dest: Path) -> None:
    shutil.rmtree(dest, ignore_errors=True)


def _fingerprint(source: Path) -> list[tuple]:
    # O -shm fica de fora: é só um índice do -wal, e o SQLite o reconstrói ao abrir a cópia.
    marks = []
    for name in DATABASES:
        for suffix in ("", "-wal"):
            path = source / (name + suffix)
            try:
                st = path.stat()
                marks.append((path.name, st.st_size, st.st_mtime_ns))
            except FileNotFoundError:
                marks.append((path.name, None, None))
    return marks


def _copy_all(source: Path, dest: Path) -> None:
    for name in DATABASES:
        for suffix in SUFFIXES:
            src, dst = source / (name + suffix), dest / (name + suffix)
            if src.exists():
                shutil.copyfile(src, dst)
            else:
                dst.unlink(missing_ok=True)
