"""Aviso de versão nova: confere a última release no GitHub, no máximo uma vez por dia.

Do GitHub só se usa o número da versão, conferido pelo formato. O texto do aviso é montado aqui, para
que nada escrito numa release chegue ao Claude como instrução.
"""

import json
import re
import threading
import time
import urllib.request
from datetime import date
from importlib.metadata import version

from . import config

RELEASES = "https://github.com/pedrosoutom/zapmcp/releases"
LATEST_API = "https://api.github.com/repos/pedrosoutom/zapmcp/releases/latest"
CHECK_EVERY = 24 * 3600
TIMEOUT = 5

_TAG = re.compile(r"v?(\d{1,4})\.(\d{1,4})\.(\d{1,4})")
_lock = threading.Lock()


def parse(tag: object) -> tuple[int, int, int] | None:
    """`v0.3.6` ou `0.3.6` → (0, 3, 6). Qualquer outro formato → None."""
    m = _TAG.fullmatch(tag.strip()) if isinstance(tag, str) else None
    return tuple(int(x) for x in m.groups()) if m else None


def current() -> str:
    return version("zapmcp")


def _state_path():
    return config.home() / "atualizacao.json"


def _load() -> dict:
    try:
        state = json.loads(_state_path().read_text())
    except (OSError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


def _save(state: dict) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))


def fetch_latest() -> str | None:
    """Versão da última release no GitHub, ou None (sem rede, sem release, formato inesperado)."""
    request = urllib.request.Request(
        LATEST_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": f"zapmcp/{current()}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            tag = json.load(response).get("tag_name")
    except Exception:
        return None
    found = parse(tag)
    return ".".join(map(str, found)) if found else None


def check(now: float | None = None) -> None:
    """Consulta o GitHub se a última consulta tem mais de um dia. Roda numa thread ao iniciar o servidor."""
    if not config.update_check_enabled():
        return
    now = time.time() if now is None else now
    with _lock:
        if now - _load().get("checked_at", 0) < CHECK_EVERY:
            return
    latest = fetch_latest()
    with _lock:
        state = _load()
        state["checked_at"] = now
        if latest:
            state["latest"] = latest
        _save(state)


def start() -> None:
    threading.Thread(target=check, name="zapmcp-atualizacao", daemon=True).start()


def notice(today: date | None = None) -> str:
    """Aviso de versão nova para o começo de uma resposta, no máximo uma vez por dia."""
    if not config.update_check_enabled():
        return ""
    day = (today or date.today()).isoformat()
    with _lock:
        state = _load()
        latest, mine = parse(state.get("latest")), parse(current())
        if not latest or not mine or latest <= mine or state.get("shown_on") == day:
            return ""
        state["shown_on"] = day
        _save(state)
    return (
        f"Aviso para o usuário: há uma versão nova do ZapMCP ({state['latest']}; esta é a {current()}). "
        f"Novidades em {RELEASES}. Para atualizar: git pull, make e reinstalar a extensão no Claude Desktop.\n\n"
    )
