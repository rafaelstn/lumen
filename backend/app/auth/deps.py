"""Dependency de CONTEXTO (tenant) — o coração do multi-tenant.

Centraliza "quem é o requisitante e o que ele pode ver" num único ponto.

- auth_enabled=False (estado atual): devolve o contexto default (escritório default,
  role 'escritorio'), SEM exigir Authorization. O sistema roda anônimo, como hoje.
- auth_enabled=True: valida o JWT do header Authorization e devolve o contexto real
  (usuario_id, escritorio_id, role). 401 se o token estiver ausente/inválido/expirado.

Todo endpoint que lê/escreve dado por escritório depende de `contexto_atual` e filtra
por `ctx.escritorio_id`. Quando `ctx.is_admin`, o filtro por escritório é dispensado
(o admin vê tudo) — cada repo aceita escritorio_id=None para "sem filtro".

`escritorio_atual` é mantido como shim de compatibilidade (devolve só o escritorio_id)
para os endpoints que ainda não migraram, mas o caminho canônico é `contexto_atual`.
"""
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException

from app.auth.security import ler_token
from app.config import settings
from app.models.usuario import ROLE_ADMIN, ROLE_ESCRITORIO


@dataclass(frozen=True)
class Contexto:
    escritorio_id: str
    role: str
    usuario_id: str | None = None
    # Contexto "anônimo" gerado com auth_enabled=False (sem login). Nesse modo NÃO há
    # isolamento por escritório: tudo é visível (comportamento atual), então filtro=None.
    anonimo: bool = False

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def filtro_escritorio(self) -> str | None:
        """escritorio_id para filtrar as queries leitura, ou None para "ver tudo".

        None quando: contexto anônimo (auth desligada, comportamento atual = vê tudo) OU
        admin (vê tudo de todos os escritórios). Caso contrário, restringe ao escritório.
        """
        if self.anonimo or self.is_admin:
            return None
        return self.escritorio_id


def _contexto_default() -> Contexto:
    # Comportamento de hoje: anônimo, escritório default, sem isolamento (filtro=None).
    return Contexto(
        escritorio_id=settings.escritorio_default_id, role=ROLE_ESCRITORIO, anonimo=True
    )


async def contexto_atual(authorization: str | None = Header(default=None)) -> Contexto:
    if not settings.auth_enabled:
        # Flag desligada: NÃO exige token. Preserva o comportamento anônimo atual.
        return _contexto_default()

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Não autenticado.")
    token = authorization[7:].strip()
    payload = ler_token(token)
    if not payload or not payload.get("sub") or not payload.get("escritorio_id"):
        raise HTTPException(status_code=401, detail="Token inválido ou expirado.")
    return Contexto(
        escritorio_id=payload["escritorio_id"],
        role=payload.get("role", ROLE_ESCRITORIO),
        usuario_id=payload["sub"],
    )


async def somente_admin(ctx: Contexto = Depends(contexto_atual)) -> Contexto:
    """Guard de endpoint administrativo: 403 se não for admin.

    Com auth_enabled=False o contexto default é role 'escritorio', então o endpoint
    admin fica naturalmente inacessível (403) enquanto o login não estiver ligado.
    """
    if not ctx.is_admin:
        raise HTTPException(status_code=403, detail="Acesso restrito ao administrador.")
    return ctx


async def escritorio_atual(ctx: Contexto = Depends(contexto_atual)) -> str:
    """Shim de compatibilidade: devolve só o escritorio_id do contexto."""
    return ctx.escritorio_id
