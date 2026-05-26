"""Endpoints administrativos — /api/admin. Acesso restrito ao admin (role='admin').

Dashboard de administração do sistema (visão sistêmica do Rafael): quantos cadastros
existem, quanto cada escritório consome de crédito e uma visão geral. TODOS os endpoints
passam por `somente_admin` (403 se não for admin). Com auth_enabled=False o contexto é
anônimo não-admin, então o dashboard fica naturalmente fechado, que é o correto.

Router fino: validação de data na borda, agregação no admin_repo. Dinheiro em centavos
inteiros. Nenhum dado pessoal (sócios) é exposto; senha_hash nunca sai.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import service as auth_service
from app.auth.deps import Contexto, somente_admin
from app.auth.schemas import (
    ConsumoEscritorioOut,
    CriarEscritorioIn,
    EscritorioCriadoOut,
    EscritorioDetalheOut,
    EscritorioMetricasOut,
    EscritorioRemovidoOut,
    ResetAmbienteApagados,
    ResetAmbienteIn,
    ResetAmbienteOut,
    ResumoAdminOut,
    TransferirEscritorioIn,
    TransferirEscritorioOut,
)
from app.database import async_session_factory
from app.models.escritorio import Escritorio
from app.modules.consumo import admin_repo
from app.modules.consumo import service as consumo_service

router = APIRouter()


def _parse_datas(inicio: str | None, fim: str | None) -> tuple[datetime | None, datetime | None]:
    """Valida inicio/fim (YYYY-MM-DD ou ISO). 422 se inválido."""
    try:
        return consumo_service.parse_data(inicio), consumo_service.parse_data(fim)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


def _inicio_mes_corrente() -> datetime:
    """Primeiro instante do mês corrente (UTC), para o recorte 'período corrente'."""
    agora = datetime.now(timezone.utc)
    return agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


@router.get("/resumo", response_model=ResumoAdminOut)
async def resumo(ctx: Contexto = Depends(somente_admin)):
    """Métricas gerais do sistema + consumo do mês corrente. Só admin."""
    inicio_mes = _inicio_mes_corrente()
    try:
        async with async_session_factory() as session:
            dados = await admin_repo.resumo_geral(session, inicio_mes, None)
    except Exception:
        raise HTTPException(status_code=503, detail="Indisponível no momento.")

    dados["consumo_periodo"] = {
        "inicio": inicio_mes.isoformat(),
        "fim": None,
        **dados["consumo_periodo"],
    }
    return ResumoAdminOut(**dados)


@router.get("/escritorios", response_model=list[EscritorioMetricasOut])
async def listar_escritorios(ctx: Contexto = Depends(somente_admin)):
    """Lista escritórios com agregações (usuários, análises, fornecedores, consumo, atividade).

    Ordenado por consumo desc; desempate pela atividade mais recente. Só admin.
    """
    try:
        async with async_session_factory() as session:
            itens = await admin_repo.escritorios_com_metricas(session)
    except Exception:
        raise HTTPException(status_code=503, detail="Indisponível no momento.")
    return [EscritorioMetricasOut(**item) for item in itens]


@router.get("/consumo-por-escritorio", response_model=list[ConsumoEscritorioOut])
async def consumo_por_escritorio(
    inicio: str | None = Query(None, description="Data inicial (YYYY-MM-DD ou ISO 8601)."),
    fim: str | None = Query(None, description="Data final (YYYY-MM-DD ou ISO 8601)."),
    ctx: Contexto = Depends(somente_admin),
):
    """Série de consumo de crédito agregada por escritório no período, com quebra por serviço."""
    ini, f = _parse_datas(inicio, fim)
    try:
        async with async_session_factory() as session:
            itens = await admin_repo.consumo_por_escritorio(session, ini, f)
    except Exception:
        raise HTTPException(status_code=503, detail="Indisponível no momento.")
    return [ConsumoEscritorioOut(**item) for item in itens]


@router.get("/escritorio/{escritorio_id}", response_model=EscritorioDetalheOut)
async def detalhe_escritorio(escritorio_id: str, ctx: Contexto = Depends(somente_admin)):
    """Detalhe de um escritório: usuários (sem senha), análises, consumo e quebra por serviço."""
    try:
        async with async_session_factory() as session:
            dados = await admin_repo.detalhe_escritorio(session, escritorio_id)
    except Exception:
        raise HTTPException(status_code=503, detail="Indisponível no momento.")
    if dados is None:
        raise HTTPException(status_code=404, detail="Escritório não encontrado.")
    return EscritorioDetalheOut(**dados)


@router.post("/escritorios", response_model=EscritorioCriadoOut, status_code=201)
async def criar_escritorio(body: CriarEscritorioIn, ctx: Contexto = Depends(somente_admin)):
    """Admin cadastra um escritório novo + usuário dono (role='escritorio').

    Reusa a lógica atômica do signup (escritório + usuário juntos, senha bcrypt, e-mail único).
    409 se o e-mail já existe; 422 (Pydantic na borda) se o payload é inválido. Só admin.
    """
    try:
        async with async_session_factory() as session:
            usuario = await auth_service.criar_escritorio_admin(
                session, body.nome, body.email, body.senha
            )
            escritorio = await session.get(Escritorio, usuario.escritorio_id)
    except auth_service.EmailJaCadastrado:
        raise HTTPException(status_code=409, detail="E-mail já cadastrado.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Indisponível no momento.")
    return EscritorioCriadoOut(
        id=usuario.escritorio_id,
        nome=escritorio.nome if escritorio else "",
        criado_em=escritorio.criado_em.isoformat() if escritorio and escritorio.criado_em else None,
        dono_usuario_id=usuario.id,
        dono_email=usuario.email,
        dono_role=usuario.role,
    )


@router.delete("/escritorio/{escritorio_id}", response_model=EscritorioRemovidoOut)
async def deletar_escritorio(escritorio_id: str, ctx: Contexto = Depends(somente_admin)):
    """Admin remove um escritório e seus dados de tenant (cascata atômica).

    Apaga usuários, análises, associações de fornecedor, tentativas de enriquecimento,
    logs de consumo e o M02 (monitorados/alertas/histórico). NÃO apaga o cache global
    de fornecedores. Protegido: 400 se for o default ou contiver um admin; 404 se não existe.
    """
    try:
        async with async_session_factory() as session:
            removidos = await auth_service.deletar_escritorio(session, escritorio_id)
    except auth_service.EscritorioInexistente:
        raise HTTPException(status_code=404, detail="Escritório não encontrado.")
    except auth_service.RemocaoProibida as exc:
        raise HTTPException(status_code=400, detail=exc.motivo)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Indisponível no momento.")
    return EscritorioRemovidoOut(id=escritorio_id, status="removido", removidos=removidos)


@router.post("/reset-ambiente", response_model=ResetAmbienteOut)
async def reset_ambiente(body: ResetAmbienteIn, ctx: Contexto = Depends(somente_admin)):
    """Zera TODOS os dados de análise/consulta/cache do sistema. Mantém contas e login. Só admin.

    Proteção contra acidente: exige body {"confirmar": "APAGAR TUDO"} exato. Qualquer outro
    texto retorna 400 sem apagar nada. Apaga (reset global) analises, fornecedores +
    fornecedor_socios, escritorio_fornecedor, enriquecimento_tentativa, consulta_logs e o M02
    (monitorados/alertas/historico_cnd). NÃO apaga Usuario nem Escritorio. Atômico.
    """
    if body.confirmar != "APAGAR TUDO":
        raise HTTPException(status_code=400, detail='Confirmação inválida. Envie {"confirmar": "APAGAR TUDO"}.')
    try:
        async with async_session_factory() as session:
            apagados = await auth_service.resetar_ambiente(session)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Indisponível no momento.")
    return ResetAmbienteOut(status="resetado", apagados=ResetAmbienteApagados(**apagados))


@router.post("/escritorios/transferir", response_model=TransferirEscritorioOut)
async def transferir_escritorio(
    body: TransferirEscritorioIn, ctx: Contexto = Depends(somente_admin)
):
    """Admin consolida todos os dados de tenant de um escritório de ORIGEM em um de DESTINO.

    Reatribui análises, associações de fornecedor, tentativas de enriquecimento, logs de
    consumo, usuários e o M02 (monitorados/alertas/histórico). Conflitos de UNIQUE no
    destino (mesmo CNPJ/nome) descartam o registro da origem em vez de duplicar. NÃO toca
    o cache global de fornecedores. Atômico. 400 se origem==destino; 404 se algum não existe.
    """
    try:
        async with async_session_factory() as session:
            movidos = await auth_service.transferir_escritorio(
                session, body.origem_id, body.destino_id
            )
    except auth_service.TransferenciaInvalida as exc:
        raise HTTPException(status_code=400, detail=exc.motivo)
    except auth_service.EscritorioInexistente:
        raise HTTPException(status_code=404, detail="Escritório de origem ou destino não encontrado.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Indisponível no momento.")
    return TransferirEscritorioOut(
        origem_id=body.origem_id,
        destino_id=body.destino_id,
        status="transferido",
        movidos=movidos,
    )
