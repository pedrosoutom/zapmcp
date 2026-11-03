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

# Uma negação (ou silêncio) responde também quem já esperava e quem chegar logo em seguida.
NEGACAO_VALE_SEGUNDOS = 5.0

Pedido = Callable[[str], tuple[bool, str | None]]  # mensagem → (confirmou, motivo da falha ou None)


class Cadeado:
    MENSAGEM_TRANCADO = (
        "Acesso ao WhatsApp fechado para esta conversa: o usuário não confirmou no Mac. "
        "Avise que a leitura foi negada e pare. Se ele quiser, peça de novo e ele confirma no pedido "
        "de Touch ID que aparece."
    )
    MENSAGEM_SEM_BINARIO = (
        "Acesso ao WhatsApp fechado: o lançador de liberação não está compilado. Rode make na pasta do ZapMCP."
    )
    MENSAGEM_SEM_LIBERADAS = (
        "Nenhuma conversa liberada. Pergunte ao usuário em qual conversa buscar e chame search com chat."
    )

    def __init__(self, pedir: Pedido, minutes: float, wait_seconds: int) -> None:
        self._pedir = pedir
        self._minutes = float(minutes)
        self._wait = wait_seconds
        self._ate: dict[str, float] = {}  # chave → instante (time.time) em que a janela vence
        self._negado_em: dict[str, float] = {}  # chave → instante da última negação
        self.erro: dict[str, str | None] = {}  # chave → motivo da última falha ("sem_binario") ou None
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    @property
    def desligado(self) -> bool:
        """ZAPMCP_UNLOCK_MINUTES=0: tudo liberado, sem pedir (modo antigo)."""
        return self._minutes <= 0

    def aberto(self, chave: str) -> bool:
        if self.desligado:
            return True
        return time.time() < self._ate.get(chave, 0.0)

    def liberados(self) -> set[str]:
        now = time.time()
        with self._guard:
            return {k for k, ate in self._ate.items() if now < ate}

    def liberar(self, chave: str, mensagem: str) -> tuple[bool, bool]:
        """(liberada, pediu). Pede ao dono uma vez por chave por vez; a negação vale para quem já esperava."""
        if self.aberto(chave):
            return True, False
        chegada = time.time()
        with self._guard:
            lock = self._locks.setdefault(chave, threading.Lock())
        with lock:
            if self.aberto(chave):  # alguém pediu enquanto esperávamos
                return True, False
            negado = self._negado_em.get(chave)
            if negado is not None and (negado >= chegada or time.time() - negado < NEGACAO_VALE_SEGUNDOS):
                return False, False
            ok, erro = self._pedir(mensagem)
            self.erro[chave] = erro
            if ok:
                self._ate[chave] = time.time() + self._minutes * 60
            else:
                self._negado_em[chave] = time.time()
            return ok, True


def pedir_no_mac(mensagem: str) -> tuple[bool, str | None]:
    """Mostra o pedido de Touch ID (bin/zapmcp-unlock). Devolve (confirmou, motivo da falha)."""
    binary = config.unlock_binary()
    try:
        done = subprocess.run(
            [str(binary), mensagem],
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=config.unlock_wait_seconds(),
        )
    except subprocess.TimeoutExpired:
        log.info("pedido de liberação sem resposta em %d s", config.unlock_wait_seconds())
        return False, None
    except OSError as e:  # não existe, sem bit de execução, arquitetura errada...
        log.warning("pedido de liberação sem o binário %s: %s", binary, e)
        return False, "sem_binario"
    if done.returncode != 0:
        log.info("liberação negada (%d): %s", done.returncode, done.stderr.decode(errors="replace").strip())
    return done.returncode == 0, ("sem_binario" if done.returncode == 2 else None)
