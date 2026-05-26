"""Regras de auth: signup (escritório + usuário dono), login, seed do admin.

Tudo escrito multi-tabela (Escritorio + Usuario) ocorre numa transação atômica:
ou cria os dois, ou nenhum. E-mail é o identificador único do usuário.
"""
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_senha, verificar_senha
from app.config import settings
from app.models.analise import Analise
from app.models.escritorio import Escritorio
from app.models.fornecedor import EscritorioFornecedor, EnriquecimentoTentativa
from app.models.usuario import ROLE_ADMIN, ROLE_ESCRITORIO, Usuario
from app.modules.consumo.models import ConsultaLog
from app.modules.modulo02.models import Alerta, FornecedorMonitorado, HistoricoCnd


class EmailJaCadastrado(Exception):
    """Sinaliza colisão de e-mail no signup (mapeado para 409 no router)."""


class EscritorioInexistente(Exception):
    """Escritório alvo não existe (mapeado para 404 no router)."""


class RemocaoProibida(Exception):
    """Remoção bloqueada por proteção (admin dentro / escritório default).

    Mapeada para 400 no router. `motivo` carrega a mensagem clara da proteção violada.
    """

    def __init__(self, motivo: str):
        super().__init__(motivo)
        self.motivo = motivo


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


async def criar_escritorio_admin(
    session: AsyncSession, nome_escritorio: str, email: str, senha: str
) -> Usuario:
    """Admin cria um Escritorio novo + Usuario dono (role='escritorio').

    Mesma garantia do signup: transação atômica (escritório + usuário juntos), e-mail único
    (colisão levanta EmailJaCadastrado), senha hasheada (bcrypt), texto puro nunca persiste.
    O usuário criado é sempre role='escritorio' (admin não fabrica outro admin por aqui).
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
    await session.refresh(escritorio)
    await session.refresh(usuario)
    return usuario


async def deletar_escritorio(session: AsyncSession, escritorio_id: str) -> dict:
    """Remove um escritório e TODOS os seus dados de tenant, numa transação atômica.

    Cascata (só do escritório alvo, nunca de outro tenant):
      usuarios, analises, escritorio_fornecedor (associação), enriquecimento_tentativa,
      consulta_logs, e o M02 (fornecedores_monitorados, alertas, historico_cnd).
    NÃO toca o cache global de Fornecedor/FornecedorSocio (compartilhado entre tenants):
    some só a associação EscritorioFornecedor, o cadastro do CNPJ permanece.

    Proteções (levantam exceção, nada é apagado):
      - EscritorioInexistente: alvo não existe (404).
      - RemocaoProibida: alvo é o default (settings.escritorio_default_id) OU contém
        algum usuário 'admin' (protege o próprio admin de se autodeletar).

    Devolve as contagens do que foi removido por tabela.
    """
    escritorio = await session.get(Escritorio, escritorio_id)
    if escritorio is None:
        raise EscritorioInexistente()

    if escritorio_id == settings.escritorio_default_id:
        raise RemocaoProibida("Não é permitido remover o escritório default do sistema.")

    tem_admin = await session.scalar(
        select(func.count(Usuario.id)).where(
            Usuario.escritorio_id == escritorio_id, Usuario.role == ROLE_ADMIN
        )
    )
    if tem_admin:
        raise RemocaoProibida(
            "Não é permitido remover um escritório que contém um usuário administrador."
        )

    # Apaga por escritorio_id em cada tabela do tenant. Nenhuma toca o cache global de
    # fornecedores (tabelas `fornecedores`/`fornecedor_socios` ficam intactas).
    contagens: dict[str, int] = {}
    alvos = (
        ("usuarios", Usuario, Usuario.escritorio_id),
        ("analises", Analise, Analise.escritorio_id),
        ("escritorio_fornecedor", EscritorioFornecedor, EscritorioFornecedor.escritorio_id),
        ("enriquecimento_tentativa", EnriquecimentoTentativa, EnriquecimentoTentativa.escritorio_id),
        ("consulta_logs", ConsultaLog, ConsultaLog.escritorio_id),
        ("fornecedores_monitorados", FornecedorMonitorado, FornecedorMonitorado.escritorio_id),
        ("alertas", Alerta, Alerta.escritorio_id),
        ("historico_cnd", HistoricoCnd, HistoricoCnd.escritorio_id),
    )
    for chave, model, coluna in alvos:
        res = await session.execute(delete(model).where(coluna == escritorio_id))
        contagens[chave] = int(res.rowcount or 0)

    await session.delete(escritorio)
    await session.commit()
    return contagens


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
