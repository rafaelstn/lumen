"""Regras de auth: signup (escritório + usuário dono), login, seed do admin.

Tudo escrito multi-tabela (Escritorio + Usuario) ocorre numa transação atômica:
ou cria os dois, ou nenhum. E-mail é o identificador único do usuário.
"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_senha, verificar_senha
from app.models.escritorio import Escritorio
from app.models.usuario import ROLE_ADMIN, ROLE_ESCRITORIO, Usuario


class EmailJaCadastrado(Exception):
    """Sinaliza colisão de e-mail no signup (mapeado para 409 no router)."""


def _novo_id() -> str:
    return str(uuid.uuid4())


async def _usuario_por_email(session: AsyncSession, email: str) -> Usuario | None:
    email = (email or "").strip().lower()
    res = await session.execute(select(Usuario).where(Usuario.email == email))
    return res.scalar_one_or_none()


async def signup(
    session: AsyncSession, nome_escritorio: str, email: str, senha: str
) -> Usuario:
    """Auto-cadastro: cria um Escritorio novo + um Usuario role='escritorio' dono dele.

    Transação atômica (escritório + usuário juntos). E-mail único: colisão levanta
    EmailJaCadastrado. A senha é hasheada (bcrypt); o texto puro nunca é persistido.
    """
    email = (email or "").strip().lower()
    if await _usuario_por_email(session, email) is not None:
        raise EmailJaCadastrado()

    escritorio = Escritorio(id=_novo_id(), nome=nome_escritorio.strip())
    usuario = Usuario(
        id=_novo_id(),
        email=email,
        senha_hash=hash_senha(senha),
        escritorio_id=escritorio.id,
        role=ROLE_ESCRITORIO,
        ativo=True,
    )
    session.add(escritorio)
    session.add(usuario)
    await session.commit()
    await session.refresh(usuario)
    return usuario


async def autenticar(session: AsyncSession, email: str, senha: str) -> Usuario | None:
    """Valida credenciais. Devolve o Usuario se ok, senão None (erro genérico no router).

    Não revela se o e-mail existe: verifica a senha mesmo quando o usuário não existe
    seria ideal contra timing, mas aqui o controle é o erro genérico no endpoint.
    """
    usuario = await _usuario_por_email(session, email)
    if usuario is None or not usuario.ativo:
        return None
    if not verificar_senha(senha, usuario.senha_hash):
        return None
    return usuario


async def seed_admin(session: AsyncSession, email: str, senha: str) -> bool:
    """Cria o admin a partir do env, se ainda não existir. Idempotente.

    Cria um Escritorio "Administração" + Usuario role='admin'. Retorna True se criou,
    False se já existia (ou se faltou email/senha). Tolerante a chamada repetida no startup.
    """
    email = (email or "").strip().lower()
    if not email or not senha:
        return False
    if await _usuario_por_email(session, email) is not None:
        return False

    escritorio = Escritorio(id=_novo_id(), nome="Administração")
    admin = Usuario(
        id=_novo_id(),
        email=email,
        senha_hash=hash_senha(senha),
        escritorio_id=escritorio.id,
        role=ROLE_ADMIN,
        ativo=True,
    )
    session.add(escritorio)
    session.add(admin)
    await session.commit()
    return True


async def listar_escritorios(session: AsyncSession) -> list[dict]:
    """Lista escritórios com a contagem de usuários (endpoint admin)."""
    res = await session.execute(
        select(
            Escritorio.id,
            Escritorio.nome,
            Escritorio.criado_em,
            func.count(Usuario.id),
        )
        .outerjoin(Usuario, Usuario.escritorio_id == Escritorio.id)
        .group_by(Escritorio.id, Escritorio.nome, Escritorio.criado_em)
        .order_by(Escritorio.criado_em.asc())
    )
    return [
        {
            "id": row[0],
            "nome": row[1],
            "criado_em": row[2].isoformat() if row[2] else None,
            "total_usuarios": int(row[3]),
        }
        for row in res.all()
    ]
