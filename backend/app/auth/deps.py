"""Dependency de tenant (escritório). Único ponto a trocar quando o login for ativado.

MVP single-tenant: devolve sempre o escritório default. Quando o JWT próprio entrar,
esta função passa a extrair o escritorio_id do header Authorization (ver security.ler_token),
e nenhum endpoint/model precisa mudar — todos já filtram por escritorio_id.
"""
from app.config import settings


async def escritorio_atual() -> str:
    # TODO(auth): extrair de `Authorization: Bearer <jwt>` via security.ler_token quando ativar login.
    return settings.escritorio_default_id
