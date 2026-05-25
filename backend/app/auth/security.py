"""Hashing de senha (bcrypt) e tokens JWT do auth próprio.

Senha: bcrypt direto (lib `bcrypt`), sem passlib. passlib 1.7.4 quebra com bcrypt 5.x no
probe de backend, então usamos a API estável do bcrypt. NUNCA armazenamos texto puro; só o
hash. bcrypt opera sobre no máximo 72 bytes; truncamos no MESMO ponto no hash e na verificação
para manter consistência e evitar o ValueError do algoritmo.

JWT: payload com sub=usuario_id + escritorio_id + role + exp. O escritorio_id e o role
vão no token para o tenancy não precisar de um SELECT a cada request (o token é a fonte).
"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings

# bcrypt opera sobre no máximo 72 bytes. Truncamos no mesmo ponto no hash e na verificação.
_BCRYPT_MAX_BYTES = 72


def _truncar(senha: str) -> bytes:
    return (senha or "").encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_senha(senha: str) -> str:
    return bcrypt.hashpw(_truncar(senha), bcrypt.gensalt()).decode("utf-8")


def verificar_senha(senha: str, senha_hash: str) -> bool:
    """Compara a senha com o hash. Tolerante: hash malformado retorna False (não estoura)."""
    try:
        return bcrypt.checkpw(_truncar(senha), (senha_hash or "").encode("utf-8"))
    except (ValueError, TypeError):
        return False


def criar_token(usuario_id: str, escritorio_id: str, role: str) -> str:
    payload = {
        "sub": usuario_id,
        "escritorio_id": escritorio_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expira_min),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def ler_token(token: str) -> dict | None:
    """Decodifica e valida o JWT. Devolve o payload (sub/escritorio_id/role) ou None se inválido."""
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
