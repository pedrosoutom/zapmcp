"""Cadeado: o agente só lê uma conversa depois que o dono do Mac confirma, na hora, com Touch ID.

O estado fica só na memória deste processo: cada servidor (Claude Code, Codex, Claude Desktop) pede
a sua liberação, e nenhum comando de terminal abre o cadeado. Falha sempre fechada.
"""

import logging
import subprocess
import threading
import time
from collections.abc import Callable

from . import config

log = logging.getLogger("zapmcp")

# Por que o último pedido não abriu: None, ou "sem_binario" (bin/zapmcp-unlock ausente ou sem Touch ID/senha).
ULTIMO_ERRO: str | None = None


class Cadeado:
    MENSAGEM_TRANCADO = (
        "Acesso ao WhatsApp fechado para esta conversa. "
        "Peça ao usuário para liberar no Mac (ele verá um pedido de Touch ID)."
    )
    MENSAGEM_SEM_BINARIO = (
        "Acesso ao WhatsApp fechado: o lançador de liberação não está compilado. Rode make na pasta do ZapMCP."
    )
    MENSAGEM_SEM_LIBERADAS = (
        "Nenhuma conversa liberada. Pergunte ao usuário em qual conversa buscar e chame search com chat."
    )

    def __init__(self, pedir: Callable[[str], bool], minutes: int, wait_seconds: int) -> None:
        self._pedir = pedir
        self._minutes = minutes
        self._wait = wait_seconds
        self._ate: dict[str, float] = {}  # chave → instante (monotonic) em que a janela vence
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def aberto(self, chave: str) -> bool:
        if self._minutes == 0:
            return True
        return time.monotonic() < self._ate.get(chave, 0.0)

    def liberados(self) -> set[str]:
        now = time.monotonic()
        return {k for k, ate in self._ate.items() if now < ate}

    def liberar(self, chave: str, mensagem: str) -> bool:
        """True se a chave está (ou acabou de ficar) liberada. Pede ao dono uma vez por chave por vez."""
        if self.aberto(chave):
            return True
        with self._guard:
            lock = self._locks.setdefault(chave, threading.Lock())
        with lock:
            if self.aberto(chave):  # alguém pediu enquanto esperávamos
                return True
            if self._pedir(mensagem):
                self._ate[chave] = time.monotonic() + self._minutes * 60
                return True
            return False


def pedir_no_mac(mensagem: str) -> bool:
    """Mostra o pedido de Touch ID (bin/zapmcp-unlock) e devolve True se o dono confirmou."""
    global ULTIMO_ERRO
    binary = config.unlock_binary()
    try:
        done = subprocess.run([str(binary), mensagem], capture_output=True, timeout=config.unlock_wait_seconds())
    except FileNotFoundError:
        ULTIMO_ERRO = "sem_binario"
        log.warning("pedido de liberação sem o binário %s", binary)
        return False
    except subprocess.TimeoutExpired:
        ULTIMO_ERRO = None
        log.info("pedido de liberação sem resposta em %d s", config.unlock_wait_seconds())
        return False
    ULTIMO_ERRO = "sem_binario" if done.returncode == 2 else None
    if done.returncode != 0:
        log.info("liberação negada (%d): %s", done.returncode, done.stderr.decode(errors="replace").strip())
    return done.returncode == 0
