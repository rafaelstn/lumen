"""Fixtures de teste do Módulo 01.

O arquivo real do cliente (idesan.xls) é dado fiscal confidencial e NÃO é
versionado. Coloque-o localmente em backend/tests/fixtures/idesan.xls (ou aponte
a env var IDESAN_FIXTURE). Os testes que dependem dele são pulados se ausente.
"""
import os

import pytest

_DEFAULT = os.path.join(os.path.dirname(__file__), "..", "fixtures", "idesan.xls")


@pytest.fixture
def idesan_xls() -> str:
    caminho = os.environ.get("IDESAN_FIXTURE", _DEFAULT)
    if not os.path.exists(caminho):
        pytest.skip(f"Fixture não encontrada: {caminho} (dado confidencial, não versionado)")
    return caminho
