from app.models.base import Base

# Importa os models para registrá-los no metadata (create_all) de forma confiável.
from app.models import analise, escritorio, fornecedor, usuario  # noqa: E402,F401

__all__ = ["Base"]
