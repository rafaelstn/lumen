"""Rate limiter compartilhado (slowapi).

Atrás do proxy do Railway, o IP real é o ÚLTIMO da cadeia X-Forwarded-For (anexado
pelo proxy confiável). O primeiro item é controlado pelo cliente e pode ser forjado
para burlar o limite — por isso NÃO o usamos como chave.
"""
from slowapi import Limiter
from starlette.requests import Request


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        partes = [p.strip() for p in forwarded.split(",") if p.strip()]
        if partes:
            return partes[-1]  # IP anexado pelo proxy (não forjável pelo cliente)
    return request.client.host if request.client else "anonimo"


limiter = Limiter(key_func=_client_ip)
