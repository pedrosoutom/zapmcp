"""Caminhos e ajustes, com override por variável de ambiente."""

import os
from pathlib import Path

WA_DIR = "~/Library/Group Containers/group.net.whatsapp.WhatsApp.shared"
HOME = "~/Library/Application Support/zapmcp"


def wa_dir() -> Path:
    return Path(os.environ.get("ZAPMCP_WA_DIR", WA_DIR)).expanduser()


def home() -> Path:
    return Path(os.environ.get("ZAPMCP_HOME", HOME)).expanduser()


def index_path() -> Path:
    return home() / "index.db"


def snapshot_dir() -> Path:
    return home() / "snapshot"


def auto_sync_seconds() -> int:
    """De quanto em quanto tempo o servidor MCP atualiza o índice sozinho. 0 desliga."""
    return int(os.environ.get("ZAPMCP_AUTO_SYNC_SECONDS", "300"))


def _flag(name: str, default: bool) -> bool:
    # Aceita 1/0 (terminal) e true/false (como o Claude Desktop preenche os ajustes da extensão).
    # Vazio ou "${...}" (ajuste que o host não preencheu): fica o padrão.
    value = os.environ.get(name, "").strip().lower()
    return default if not value or value.startswith("${") else value in ("1", "true")


def update_check_enabled() -> bool:
    """Avisar quando sair versão nova (consulta o GitHub uma vez por dia). ZAPMCP_UPDATE_CHECK=0 desliga."""
    return _flag("ZAPMCP_UPDATE_CHECK", True)


def transcribe_enabled() -> bool:
    """O servidor transcreve áudios em segundo plano. ZAPMCP_TRANSCRIBE=0 desliga."""
    return _flag("ZAPMCP_TRANSCRIBE", True)


def transcribe_on_battery() -> bool:
    """Transcrever o histórico também com o Mac na bateria (pedidos do Claude são sempre atendidos)."""
    return _flag("ZAPMCP_TRANSCRIBE_ON_BATTERY", False)


def transcribe_wait_seconds() -> int:
    """Quanto transcribe_audio espera pelo resultado antes de responder "ainda na fila"."""
    return int(os.environ.get("ZAPMCP_TRANSCRIBE_WAIT_SECONDS", "90"))


def transcribe_days() -> int:
    """Quantos dias para trás a transcrição automática cobre. Os mais antigos, só a pedido do Claude."""
    return int(os.environ.get("ZAPMCP_TRANSCRIBE_DAYS", "7"))


def transcribe_archived_groups() -> bool:
    """Incluir grupos arquivados na transcrição automática (desligado por padrão)."""
    return _flag("ZAPMCP_TRANSCRIBE_ARCHIVED", False)


def _number(name: str, default: float) -> float:
    value = os.environ.get(name, "").strip()
    return default if not value or value.startswith("${") else float(value)


def unlock_minutes() -> float:
    """Por quantos minutos uma conversa fica liberada depois que o dono confirma no Mac. 0 desliga o cadeado."""
    return _number("ZAPMCP_UNLOCK_MINUTES", 15)


def unlock_wait_seconds() -> int:
    """Quanto uma tool espera o dono responder ao pedido de Touch ID."""
    return int(_number("ZAPMCP_UNLOCK_WAIT_SECONDS", 60))


def unlock_binary() -> Path:
    """O programa que mostra o pedido de Touch ID (bin/zapmcp-unlock, compilado pelo make)."""
    default = Path(__file__).resolve().parents[2] / "bin" / "zapmcp-unlock"
    return Path(os.environ.get("ZAPMCP_UNLOCK_BIN") or default).expanduser()
