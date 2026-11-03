"""Acesso Total ao Disco: conferir sem disparar pedido do macOS e explicar como liberar.

Abrir o TCC.db do usuário só funciona com Acesso Total ao Disco, e a recusa é silenciosa: o macOS não
pergunta nada. O arquivo é só aberto e fechado, nunca lido.
"""

from pathlib import Path

from . import config

PROBE = "~/Library/Application Support/com.apple.TCC/TCC.db"

_shown = False


def granted() -> bool | None:
    """True com Acesso Total ao Disco, False sem, None quando não dá para saber."""
    try:
        Path(PROBE).expanduser().open("rb").close()
        return True
    except PermissionError:
        return False
    except OSError:
        return None


def notice() -> str:
    """Na extensão do Claude Desktop, sem Acesso Total ao Disco: como liberar. Uma vez por execução."""
    global _shown
    launcher = config.launcher_path()
    if _shown or not launcher or granted() is not False:
        return ""
    _shown = True
    return (
        "Aviso para o usuário: falta liberar o acesso do ZapMCP, um passo único da instalação. Sem ele, "
        "o macOS continua perguntando se o ZapMCP pode acessar dados de outros apps. Como liberar: em "
        "Ajustes do Sistema > Privacidade e Segurança > Acesso Total ao Disco, clique em +, aperte "
        f"Cmd+Shift+G, cole {launcher} e ligue a chave do zapmcp. Outro jeito: rodar no Terminal "
        f"open -R \"{launcher}\" e arrastar o arquivo que aparece no Finder para essa lista.\n\n"
    )
