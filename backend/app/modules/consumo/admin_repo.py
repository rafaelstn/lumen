"""Agregações do DASHBOARD ADMIN (visão global do sistema, só admin).

Diferente do repo por escritório (consumo/repo.py), aqui o recorte é SISTÊMICO: o admin
vê todos os escritórios. As agregações de dinheiro somam `custo_centavos` (a FONTE DE
VERDADE imutável do ConsultaLog), sempre inteiro em centavos, nunca float, nunca recalcula
preço (que tem fração de centavo). Créditos somam `creditos_consumidos`.

Cada função abre sobre uma AsyncSession passada pelo router (sessão única por request).
As datas (inicio/fim) são opcionais e filtram pelo `criado_em` do ConsultaLog quando o
recorte é de consumo.
"""
from datetime import datetime

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.analise import Analise
from app.models.escritorio import Escritorio
from app.models.fornecedor import EscritorioFornecedor, Fornecedor
from app.models.usuario import Usuario
from app.modules.consumo.models import ConsultaLog


async def _scalar(session: AsyncSession, stmt) -> int:
    res = await session.execute(stmt)
    return int(res.scalar_one())


async def resumo_geral(
    session: AsyncSession, inicio: datetime | None, fim: datetime | None
) -> dict:
    """Métricas sistêmicas: contagens globais + consumo total e do período informado.

    'fornecedores_cache_global' = linhas da tabela global de cadastro (CNPJs já vistos por
    qualquer escritório). 'fornecedores_cadastro_completo' = os que têm o cadastro completo
    da Receita gravado (cadastro_atualizado_em IS NOT NULL). 'consultas_pagas' conta linhas do
    audit trail com custo > 0 (operação que efetivamente gastou crédito).
    """
    # O escritório default é técnico (fallback do modo anônimo), não um cliente real:
    # fica fora da contagem e da listagem de gestão do dashboard admin.
    total_escritorios = await _scalar(
        session,
        select(func.count(Escritorio.id)).where(Escritorio.id != settings.escritorio_default_id),
    )
    total_usuarios = await _scalar(session, select(func.count(Usuario.id)))
    total_analises = await _scalar(session, select(func.count(Analise.id)))
    fornecedores_cache_global = await _scalar(session, select(func.count(Fornecedor.id)))
    fornecedores_cadastro_completo = await _scalar(
        session,
        select(func.count(Fornecedor.id)).where(
            Fornecedor.cadastro_atualizado_em.is_not(None)
        ),
    )

    consumo_total = await _agregado_consumo(session, None, None)
    consumo_periodo = await _agregado_consumo(session, inicio, fim)

    return {
        "total_escritorios": total_escritorios,
        "total_usuarios": total_usuarios,
        "total_analises": total_analises,
        "fornecedores_cache_global": fornecedores_cache_global,
        "fornecedores_cadastro_completo": fornecedores_cadastro_completo,
        "consultas_pagas": consumo_total["consultas_pagas"],
        "creditos_consumidos": consumo_total["creditos_consumidos"],
        "custo_total_centavos": consumo_total["custo_centavos"],
        "consumo_periodo": consumo_periodo,
    }


async def _agregado_consumo(
    session: AsyncSession, inicio: datetime | None, fim: datetime | None
) -> dict:
    """Soma global do audit trail: nº de consultas pagas, créditos e custo (centavos)."""
    q = select(
        func.count(ConsultaLog.id),
        func.coalesce(func.sum(ConsultaLog.creditos_consumidos), 0),
        func.coalesce(func.sum(ConsultaLog.custo_centavos), 0),
    ).where(ConsultaLog.custo_centavos > 0)
    if inicio is not None:
        q = q.where(ConsultaLog.criado_em >= inicio)
    if fim is not None:
        q = q.where(ConsultaLog.criado_em <= fim)
    res = (await session.execute(q)).one()
    return {
        "consultas_pagas": int(res[0]),
        "creditos_consumidos": int(res[1]),
        "custo_centavos": int(res[2]),
    }


async def _consumo_por_escritorio_map(
    session: AsyncSession, inicio: datetime | None, fim: datetime | None
) -> dict[str, dict]:
    """Mapa escritorio_id -> {creditos_consumidos, custo_centavos} agregado do ConsultaLog."""
    q = select(
        ConsultaLog.escritorio_id,
        func.coalesce(func.sum(ConsultaLog.creditos_consumidos), 0),
        func.coalesce(func.sum(ConsultaLog.custo_centavos), 0),
    ).group_by(ConsultaLog.escritorio_id)
    if inicio is not None:
        q = q.where(ConsultaLog.criado_em >= inicio)
    if fim is not None:
        q = q.where(ConsultaLog.criado_em <= fim)
    res = await session.execute(q)
    return {
        row[0]: {"creditos_consumidos": int(row[1]), "custo_centavos": int(row[2])}
        for row in res.all()
    }


async def _por_servico_por_escritorio(
    session: AsyncSession, inicio: datetime | None, fim: datetime | None
) -> dict[str, dict[str, dict]]:
    """Mapa escritorio_id -> servico -> {creditos_consumidos, custo_centavos, consultas}."""
    q = select(
        ConsultaLog.escritorio_id,
        ConsultaLog.servico,
        func.count(ConsultaLog.id),
        func.coalesce(func.sum(ConsultaLog.creditos_consumidos), 0),
        func.coalesce(func.sum(ConsultaLog.custo_centavos), 0),
    ).group_by(ConsultaLog.escritorio_id, ConsultaLog.servico)
    if inicio is not None:
        q = q.where(ConsultaLog.criado_em >= inicio)
    if fim is not None:
        q = q.where(ConsultaLog.criado_em <= fim)
    res = await session.execute(q)
    out: dict[str, dict[str, dict]] = {}
    for esc_id, servico, consultas, creditos, custo in res.all():
        out.setdefault(esc_id, {})[servico] = {
            "consultas": int(consultas),
            "creditos_consumidos": int(creditos),
            "custo_centavos": int(custo),
        }
    return out


async def _contagem_por_escritorio(session: AsyncSession, coluna, tabela) -> dict[str, int]:
    """Mapa escritorio_id -> contagem de linhas de `tabela` agrupado por `coluna`."""
    res = await session.execute(
        select(coluna, func.count()).group_by(coluna)
    )
    return {row[0]: int(row[1]) for row in res.all()}


async def _ultima_atividade_map(session: AsyncSession) -> dict[str, datetime]:
    """Mapa escritorio_id -> data da atividade mais recente (análise ou consulta paga)."""
    atividade: dict[str, datetime] = {}
    for stmt in (
        select(Analise.escritorio_id, func.max(Analise.atualizado_em)).group_by(
            Analise.escritorio_id
        ),
        select(ConsultaLog.escritorio_id, func.max(ConsultaLog.criado_em)).group_by(
            ConsultaLog.escritorio_id
        ),
    ):
        for esc_id, quando in (await session.execute(stmt)).all():
            if quando is None:
                continue
            atual = atividade.get(esc_id)
            if atual is None or quando > atual:
                atividade[esc_id] = quando
    return atividade


async def escritorios_com_metricas(session: AsyncSession) -> list[dict]:
    """Lista escritórios + usuários, análises, fornecedores pesquisados, consumo e atividade.

    Consumo agregado de TODO o histórico do escritório (sem recorte de data). Ordena por
    custo desc; empate cai na atividade mais recente. Não inclui nenhum dado pessoal.
    """
    base = await session.execute(
        select(Escritorio.id, Escritorio.nome, Escritorio.criado_em)
        .where(Escritorio.id != settings.escritorio_default_id)  # escritório técnico, fora da gestão
        .order_by(Escritorio.criado_em.asc())
    )
    escritorios = base.all()

    usuarios = await _contagem_por_escritorio(session, Usuario.escritorio_id, Usuario)
    analises = await _contagem_por_escritorio(session, Analise.escritorio_id, Analise)
    fornecedores = await _contagem_por_escritorio(
        session, EscritorioFornecedor.escritorio_id, EscritorioFornecedor
    )
    consumo = await _consumo_por_escritorio_map(session, None, None)
    atividade = await _ultima_atividade_map(session)

    itens = []
    for esc_id, nome, criado_em in escritorios:
        cons = consumo.get(esc_id, {"creditos_consumidos": 0, "custo_centavos": 0})
        ult = atividade.get(esc_id)
        itens.append(
            {
                "id": esc_id,
                "nome": nome,
                "criado_em": criado_em.isoformat() if criado_em else None,
                "total_usuarios": usuarios.get(esc_id, 0),
                "total_analises": analises.get(esc_id, 0),
                "total_fornecedores_pesquisados": fornecedores.get(esc_id, 0),
                "consumo": {
                    "creditos_consumidos": cons["creditos_consumidos"],
                    "custo_centavos": cons["custo_centavos"],
                },
                "ultima_atividade": ult.isoformat() if ult else None,
            }
        )

    # Ordena por custo desc; desempate pela atividade mais recente (None por último).
    itens.sort(
        key=lambda i: (
            i["consumo"]["custo_centavos"],
            i["ultima_atividade"] or "",
        ),
        reverse=True,
    )
    return itens


async def consumo_por_escritorio(
    session: AsyncSession, inicio: datetime | None, fim: datetime | None
) -> list[dict]:
    """Série de consumo agregada por escritório no período, com quebra por serviço.

    Inclui só escritórios que tiveram consumo no recorte. Custo sempre em centavos inteiros.
    """
    nomes = dict(
        (await session.execute(select(Escritorio.id, Escritorio.nome))).all()
    )
    consumo = await _consumo_por_escritorio_map(session, inicio, fim)
    por_servico = await _por_servico_por_escritorio(session, inicio, fim)

    itens = [
        {
            "escritorio_id": esc_id,
            "nome": nomes.get(esc_id, esc_id),
            "creditos_consumidos": agg["creditos_consumidos"],
            "custo_centavos": agg["custo_centavos"],
            "por_servico": por_servico.get(esc_id, {}),
        }
        for esc_id, agg in consumo.items()
    ]
    itens.sort(key=lambda i: i["custo_centavos"], reverse=True)
    return itens


async def detalhe_escritorio(session: AsyncSession, escritorio_id: str) -> dict | None:
    """Detalhe de um escritório: usuários (sem senha), nº análises, consumo e saldos.

    Devolve None se o escritório não existir (router responde 404). Nunca expõe senha_hash.
    """
    esc = await session.get(Escritorio, escritorio_id)
    if esc is None:
        return None

    res_users = await session.execute(
        select(Usuario.id, Usuario.email, Usuario.role, Usuario.ativo, Usuario.criado_em)
        .where(Usuario.escritorio_id == escritorio_id)
        .order_by(Usuario.criado_em.asc())
    )
    usuarios = [
        {
            "id": r[0],
            "email": r[1],
            "role": r[2],
            "ativo": bool(r[3]),
            "criado_em": r[4].isoformat() if r[4] else None,
        }
        for r in res_users.all()
    ]

    total_analises = await _scalar(
        session,
        select(func.count(Analise.id)).where(Analise.escritorio_id == escritorio_id),
    )
    total_fornecedores = await _scalar(
        session,
        select(func.count(distinct(EscritorioFornecedor.cnpj))).where(
            EscritorioFornecedor.escritorio_id == escritorio_id
        ),
    )
    consumo = (await _consumo_por_escritorio_map(session, None, None)).get(
        escritorio_id, {"creditos_consumidos": 0, "custo_centavos": 0}
    )
    por_servico = (await _por_servico_por_escritorio(session, None, None)).get(
        escritorio_id, {}
    )

    return {
        "id": esc.id,
        "nome": esc.nome,
        "criado_em": esc.criado_em.isoformat() if esc.criado_em else None,
        "usuarios": usuarios,
        "total_analises": total_analises,
        "total_fornecedores_pesquisados": total_fornecedores,
        "consumo": {
            "creditos_consumidos": consumo["creditos_consumidos"],
            "custo_centavos": consumo["custo_centavos"],
            "por_servico": por_servico,
        },
    }
