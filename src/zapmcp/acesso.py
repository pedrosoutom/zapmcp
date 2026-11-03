"""Log de acesso: uma linha por chamada de tool, para o dono auditar o que o agente leu.

Nunca grava conteúdo de mensagem: só ids, nomes de conversa, períodos e a query da busca.
"""

import logging
import time

from . import config

log = logging.getLogger("zapmcp")


def caminho():
    return config.home() / "logs" / "acesso.log"


def _campo(text: str) -> str:
    return text.replace("|", " ").replace("\n", " ").replace("\r", " ")


def registrar(agente: str, tool: str, resumo: str, resultado: str) -> None:
    """`resultado`: "livre", "liberado", "trancado", ou com "pedido, " na frente quando o diálogo abriu."""
    campos = [time.strftime("%Y-%m-%d %H:%M:%S"), _campo(agente), _campo(tool), " ".join(_campo(resumo).split()), _campo(resultado)]
    linha = " | ".join(campos) + "\n"
    try:
        path = caminho()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as out:
            out.write(linha)
    except OSError as e:
        log.warning("não consegui gravar o log de acesso: %s", e)
