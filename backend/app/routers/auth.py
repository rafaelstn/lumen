"""Endpoints de autenticação — /api/auth.

Router fino: validação na borda (Pydantic) + orquestração do app.auth.service.
Disponível mesmo com auth_enabled=False (para o frontend de login poder cadastrar/logar
antes de a flag mestre ser ligada). O isolamento por escritório é que depende da flag.
"""
from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth import service
from app.auth.deps import Contexto, contexto_atual
from app.auth.schemas import LoginIn, SignupIn, SignupOut, TokenOut, UsuarioOut
from app.auth.security import criar_token
from app.config import settings
from app.database import async_session_factory
from app.models.usuario import Usuario
from app.ratelimit import limiter

router = APIRouter()


def _usuario_out(u: Usuario) -> UsuarioOut:
    return UsuarioOut(
        id=u.id, email=u.email, escritorio_id=u.escritorio_id, role=u.role, ativo=u.ativo
    )


def _token_out(u: Usuario) -> TokenOut:
    return TokenOut(
        access_token=criar_token(u.id, u.escritorio_id, u.role),
        expira_em_min=settings.jwt_expira_min,
    )


@router.post("/signup", response_model=SignupOut, status_code=201)
@limiter.limit("5/minute")
async def signup(request: Request, body: SignupIn):
    """Auto-cadastro: cria escritório + usuário dono e já devolve o token (login imediato).

    Decisão: devolve token no signup para o frontend logar direto (sem segundo passo).
    """
    try:
        async with async_session_factory() as session:
            usuario = await service.signup(
                session, body.nome_escritorio, body.email, body.senha
            )
    except service.EmailJaCadastrado:
        raise HTTPException(status_code=409, detail="E-mail já cadastrado.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Cadastro temporariamente indisponível.")
    return SignupOut(usuario=_usuario_out(usuario), token=_token_out(usuario))


@router.post("/login", response_model=TokenOut)
@limiter.limit("10/minute")
async def login(request: Request, body: LoginIn):
    """Login por e-mail+senha. Erro genérico (401) em credencial inválida: não revela
    se o e-mail existe."""
    try:
        async with async_session_factory() as session:
            usuario = await service.autenticar(session, body.email, body.senha)
    except Exception:
        raise HTTPException(status_code=503, detail="Login temporariamente indisponível.")
    if usuario is None:
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos.")
    return _token_out(usuario)


@router.get("/me", response_model=UsuarioOut)
async def me(ctx: Contexto = Depends(contexto_atual)):
    """Dados do usuário logado (sem senha_hash).

    Com auth_enabled=False não há usuário real (contexto anônimo default): 404, pois /me
    só faz sentido com login ligado.
    """
    if ctx.usuario_id is None:
        raise HTTPException(status_code=404, detail="Sem usuário autenticado (login desligado).")
    try:
        async with async_session_factory() as session:
            usuario = await session.get(Usuario, ctx.usuario_id)
    except Exception:
        raise HTTPException(status_code=503, detail="Indisponível no momento.")
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return _usuario_out(usuario)
