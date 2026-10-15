"""Datas que as pessoas (e o Claude) escrevem: 7d, 24h, 2w, hoje, ontem, AAAA-MM-DD."""

import re
from datetime import datetime, timedelta

_RELATIVE = re.compile(r"^(\d+)\s*([hdw])$")
_UNITS = {"h": "hours", "d": "days", "w": "weeks"}
_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M")

HELP = "Use 7d, 24h, 2w, hoje, ontem, AAAA-MM-DD ou AAAA-MM-DD HH:MM."


def parse_when(value: str, *, end_of_day: bool = False, now: datetime | None = None) -> int:
    """Converte para unix (hora local). Com `end_of_day`, uma data sem hora vale até o fim daquele dia."""
    text = value.strip().lower()
    now = now or datetime.now()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if text in ("agora", "now"):
        return int(now.timestamp())
    if text in ("hoje", "today"):
        return int((midnight + timedelta(days=1) if end_of_day else midnight).timestamp())
    if text in ("ontem", "yesterday"):
        return int((midnight if end_of_day else midnight - timedelta(days=1)).timestamp())
    if m := _RELATIVE.match(text):
        return int((now - timedelta(**{_UNITS[m[2]]: int(m[1])})).timestamp())
    for fmt in _FORMATS:
        try:
            return int(datetime.strptime(text, fmt).timestamp())
        except ValueError:
            pass
    try:
        day = datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f'Data não reconhecida: "{value}". {HELP}') from None
    return int((day + timedelta(days=1) if end_of_day else day).timestamp())
