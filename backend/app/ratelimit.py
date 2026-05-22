"""Rate limiter compartilhado (slowapi). Usa o IP real por trás do proxy do Railway."""
from slowapi import Limiter
from starlette.requests import Request


def _client_ip(request: Request) -> str:
    # Atrás do proxy do Railway o IP real vem no X-Forwarded-For (primeiro da lista).
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "anonimo"


limiter = Limiter(key_func=_client_ip)
