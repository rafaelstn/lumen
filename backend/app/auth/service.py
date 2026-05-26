"""Regras de auth: signup (escritório + usuário dono), login, seed do admin.

Tudo escrito multi-tabela (Escritorio + Usuario) ocorre numa transação atômica:
ou cria os dois, ou nenhum. E-mail é o identificador único do usuário.
"""
import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_senha, verificar_senha
from app.config import settings
from app.models.analise import Analise
from app.models.escritorio import Escritorio
from app.models.fornecedor import (
    EnriquecimentoTentativa,
    EscritorioFornecedor,
    Fornecedor,
    FornecedorSocio,
)
from app.modules.modulo01.jobs import store as job_store
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


class TransferenciaInvalida(Exception):
    """Transferência com origem == destino (mapeada para 400 no router)."""

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


async def transferir_escritorio(
    session: AsyncSession, origem_id: str, destino_id: str
) -> dict:
    """Reatribui TODOS os dados de tenant de `origem_id` para `destino_id`, atomicamente.

    Caso de uso: o admin gerou dados no escritório default (modo anônimo, antes do login)
    e quer consolidá-los no escritório dele. Os dois escritórios continuam existindo; só
    os dados de tenant migram. NÃO toca o cache global de Fornecedor/FornecedorSocio.

    Conflitos de UNIQUE (o destino já tem a mesma chave de negócio): o registro da ORIGEM
    é DESCARTADO em vez de reatribuído, para não violar a constraint. Tratado em três tabelas:
      - escritorio_fornecedor: unique (escritorio_id, cnpj).
      - enriquecimento_tentativa: unique (escritorio_id, nome_normalizado).
      - fornecedores_monitorados: unique (escritorio_id, cnpj). Aqui há detalhe extra:
        historico_cnd e alertas referenciam o monitorado por fornecedor_id; quando o
        monitorado da origem é descartado, seus históricos/alertas são REAPONTADOS para o
        monitorado equivalente do destino (mesmo CNPJ), preservando o vínculo.
    Tabelas sem unique (analises, consulta_logs, e o restante de historico_cnd/alertas):
    reatribuição direta de escritorio_id.

    Erros (nada é gravado):
      - TransferenciaInvalida: origem == destino (400).
      - EscritorioInexistente: origem OU destino não existe (404).

    Devolve as contagens do que foi movido por tabela + total de conflitos descartados.
    """
    if origem_id == destino_id:
        raise TransferenciaInvalida("Origem e destino não podem ser o mesmo escritório.")

    origem = await session.get(Escritorio, origem_id)
    destino = await session.get(Escritorio, destino_id)
    if origem is None or destino is None:
        raise EscritorioInexistente()

    contagens: dict[str, int] = {}
    conflitos_descartados = 0

    # --- 1) Tabelas sem unique por tenant: reatribuição direta de escritorio_id. ---
    simples = (
        ("usuarios", Usuario),
        ("analises", Analise),
        ("consulta_logs", ConsultaLog),
    )
    for chave, model in simples:
        res = await session.execute(
            update(model)
            .where(model.escritorio_id == origem_id)
            .values(escritorio_id=destino_id)
        )
        contagens[chave] = int(res.rowcount or 0)

    # --- 2) escritorio_fornecedor: unique (escritorio_id, cnpj). ---
    cnpjs_destino = set(
        (
            await session.execute(
                select(EscritorioFornecedor.cnpj).where(
                    EscritorioFornecedor.escritorio_id == destino_id
                )
            )
        ).scalars()
    )
    origem_assoc = (
        (
            await session.execute(
                select(EscritorioFornecedor).where(
                    EscritorioFornecedor.escritorio_id == origem_id
                )
            )
        )
        .scalars()
        .all()
    )
    movidos_assoc = 0
    for assoc in origem_assoc:
        if assoc.cnpj in cnpjs_destino:
            await session.delete(assoc)  # destino já vê este CNPJ: descarta o da origem.
            conflitos_descartados += 1
        else:
            assoc.escritorio_id = destino_id
            cnpjs_destino.add(assoc.cnpj)
            movidos_assoc += 1
    contagens["escritorio_fornecedor"] = movidos_assoc

    # --- 3) enriquecimento_tentativa: unique (escritorio_id, nome_normalizado). ---
    nomes_destino = set(
        (
            await session.execute(
                select(EnriquecimentoTentativa.nome_normalizado).where(
                    EnriquecimentoTentativa.escritorio_id == destino_id
                )
            )
        ).scalars()
    )
    origem_tent = (
        (
            await session.execute(
                select(EnriquecimentoTentativa).where(
                    EnriquecimentoTentativa.escritorio_id == origem_id
                )
            )
        )
        .scalars()
        .all()
    )
    movidos_tent = 0
    for tent in origem_tent:
        if tent.nome_normalizado in nomes_destino:
            await session.delete(tent)  # destino já tentou este nome: descarta o da origem.
            conflitos_descartados += 1
        else:
            tent.escritorio_id = destino_id
            nomes_destino.add(tent.nome_normalizado)
            movidos_tent += 1
    contagens["enriquecimento_tentativa"] = movidos_tent

    # --- 4) fornecedores_monitorados: unique (escritorio_id, cnpj). ---
    # Mapa cnpj -> id do monitorado JÁ existente no destino (para reapontar filhos).
    monitorados_destino = {
        row.cnpj: row.id
        for row in (
            await session.execute(
                select(FornecedorMonitorado).where(
                    FornecedorMonitorado.escritorio_id == destino_id
                )
            )
        ).scalars()
    }
    origem_mon = (
        (
            await session.execute(
                select(FornecedorMonitorado).where(
                    FornecedorMonitorado.escritorio_id == origem_id
                )
            )
        )
        .scalars()
        .all()
    )
    movidos_mon = 0
    for mon in origem_mon:
        destino_mon_id = monitorados_destino.get(mon.cnpj)
        if destino_mon_id is not None:
            # Conflito: destino já monitora o CNPJ. Reaponta históricos/alertas do
            # monitorado da origem para o do destino, depois descarta o monitorado da origem.
            await session.execute(
                update(HistoricoCnd)
                .where(HistoricoCnd.fornecedor_id == mon.id)
                .values(fornecedor_id=destino_mon_id)
            )
            await session.execute(
                update(Alerta)
                .where(Alerta.fornecedor_id == mon.id)
                .values(fornecedor_id=destino_mon_id)
            )
            await session.delete(mon)
            conflitos_descartados += 1
        else:
            mon.escritorio_id = destino_id
            monitorados_destino[mon.cnpj] = mon.id
            movidos_mon += 1
    contagens["fornecedores_monitorados"] = movidos_mon

    # --- 5) historico_cnd e alertas: sem unique. Reatribui o restante por escritorio_id.
    # (fornecedor_id dos filhos de monitorados conflitantes já foi reapontado no passo 4;
    # aqui só falta migrar o escritorio_id de todos os filhos da origem.)
    for chave, model in (("historico_cnd", HistoricoCnd), ("alertas", Alerta)):
        res = await session.execute(
            update(model)
            .where(model.escritorio_id == origem_id)
            .values(escritorio_id=destino_id)
        )
        contagens[chave] = int(res.rowcount or 0)

    contagens["conflitos_descartados"] = conflitos_descartados
    await session.commit()
    return contagens


async def resetar_ambiente(session: AsyncSession) -> dict:
    """Zera TODOS os dados de análise/consulta/cache do sistema, numa transação atômica.

    Reset GLOBAL (apaga todas as linhas, não só de um tenant): é ambiente de teste/piloto e o
    admin quer refazer um teste do zero (resubir planilha, reenriquecer, reconsultar CND). Mantém
    intactos Usuario e Escritorio (as contas e o login, inclusive o admin), por isso o login segue
    funcionando após o reset.

    Apaga: analises, fornecedores + fornecedor_socios (cache global de CNPJ + sócios),
    escritorio_fornecedor (associações), enriquecimento_tentativa, consulta_logs e o M02
    (fornecedores_monitorados, alertas, historico_cnd).

    Ordem de deleção respeita dependências: os filhos do M02 (historico_cnd e alertas, que
    referenciam o monitorado por fornecedor_id) são apagados ANTES de fornecedores_monitorados;
    fornecedor_socios (FK lógica por CNPJ) antes de fornecedores.

    Também limpa os jobs em memória do M01 (estado volátil de análises abertas), para não reabrir
    uma análise órfã cujo registro no banco já foi apagado.

    Devolve as contagens do que foi apagado por tabela.
    """
    # Filhos antes de pais. Cada par é (chave_resposta, model).
    alvos = (
        ("analises", Analise),
        ("historico_cnd", HistoricoCnd),
        ("alertas", Alerta),
        ("monitorados", FornecedorMonitorado),
        ("escritorio_fornecedor", EscritorioFornecedor),
        ("enriquecimento_tentativa", EnriquecimentoTentativa),
        ("consulta_logs", ConsultaLog),
        ("fornecedor_socios", FornecedorSocio),
        ("fornecedores", Fornecedor),
    )
    contagens: dict[str, int] = {}
    for chave, model in alvos:
        res = await session.execute(delete(model))
        contagens[chave] = int(res.rowcount or 0)

    await session.commit()

    # Jobs em memória são voláteis (TTL), mas limpamos explicitamente para não restar
    # análise viva apontando para registro já apagado. Fora da transação do banco.
    job_store.limpar_tudo()

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
