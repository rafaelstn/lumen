"""Tokens JWT (auth próprio) — PREPARADO, ainda não ativo no MVP.

As funções estão prontas para quando o login for ligado; hoje ninguém as chama
(o tenant vem do escritório default em deps.py). Manter aqui evita retrabalho depois.
"""
from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings


def criar_token(escritorio_id: str) -> str:
    payload = {
        "sub": escritorio_id,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expira_min),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def ler_token(token: str) -> str | None:
    """Devolve o escritorio_id do token, ou None se inválido/expirado."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None
