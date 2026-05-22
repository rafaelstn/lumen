"""Teto global diário de consultas pagas (Infosimples/CNPJá).

Blindagem de fatura independente de IP: mesmo que o rate limit por IP seja burlado,
o gasto agregado do dia não passa do teto configurado. Em memória (réplica única);
quando entrar Postgres, migrar o contador para lá.
"""
import threading
from datetime import date

from app.config import settings

_lock = threading.Lock()
_contadores: dict[tuple[str, str], int] = {}  # (servico, "YYYY-MM-DD") -> qtd

_TETOS = {
    "cnd": lambda: settings.cnd_max_diario,
    "cnpj": lambda: settings.cnpj_max_diario,
}


def restante(servico: str) -> int:
    """Quantas consultas pagas ainda cabem hoje para o serviço."""
    teto = _TETOS.get(servico, lambda: 0)()
    chave = (servico, date.today().isoformat())
    with _lock:
        return max(0, teto - _contadores.get(chave, 0))


def consumir(servico: str, n: int = 1) -> bool:
    """Reserva n consultas se houver saldo no dia. Devolve False se estourar o teto."""
    teto = _TETOS.get(servico, lambda: 0)()
    chave = (servico, date.today().isoformat())
    with _lock:
        atual = _contadores.get(chave, 0)
        if atual + n > teto:
            return False
        _contadores[chave] = atual + n
        return True
