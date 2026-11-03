"""Log de acesso: uma linha por chamada de tool, para o dono auditar o que o agente leu.

Nunca grava conteúdo de mensagem: só ids, nomes de conversa, períodos e a query da busca.
"""

import logging
import time

from . import config

log = logging.getLogger("zapmcp")


def caminho():
    return config.home() / "logs" / "acesso.log"


def registrar(agente: str, tool: str, resumo: str, resultado: str) -> None:
    """`resultado`: "liberado", "trancado" ou "pedido, liberado" / "pedido, trancado" (quando o diálogo abriu)."""
    limpo = " ".join(resumo.replace("|", " ").split())
    linha = f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {agente} | {tool} | {limpo} | {resultado}\n"
    try:
        path = caminho()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as out:
            out.write(linha)
    except OSError as e:
        log.warning("não consegui gravar o log de acesso: %s", e)
