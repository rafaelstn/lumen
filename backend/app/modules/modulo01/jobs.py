"""Store de jobs em memória, compartilhado entre as fases (parser → CND → PDF).

Em memória é suficiente para o Módulo 01 com réplica única. Aplica TTL e cap de
quantidade para não crescer indefinidamente (DoS/OOM) nem reter dado fiscal além
do necessário. A persistência em Postgres entra nos módulos futuros.
"""
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.config import settings


class JobStore:
    def __init__(self, ttl_seconds: int, cap: int) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._criado_mono: dict[str, float] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds
        self._cap = cap

    def _expurgar(self) -> None:
        """Remove jobs expirados e, se exceder o cap, os mais antigos. Sob lock."""
        agora = time.monotonic()
        expirados = [jid for jid, t in self._criado_mono.items() if agora - t > self._ttl]
        for jid in expirados:
            self._jobs.pop(jid, None)
            self._criado_mono.pop(jid, None)

        excesso = len(self._jobs) - self._cap
        if excesso > 0:
            mais_antigos = sorted(self._criado_mono, key=self._criado_mono.get)[:excesso]
            for jid in mais_antigos:
                self._jobs.pop(jid, None)
                self._criado_mono.pop(jid, None)

    def criar(self, dados: dict[str, Any]) -> str:
        job_id = str(uuid.uuid4())
        with self._lock:
            self._expurgar()
            self._jobs[job_id] = {
                "job_id": job_id,
                "criado_em": datetime.now(timezone.utc).isoformat(),
                **dados,
            }
            self._criado_mono[job_id] = time.monotonic()
        return job_id

    def obter(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job is not None else None

    def atualizar(self, job_id: str, **campos: Any) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].update(campos)


store = JobStore(ttl_seconds=settings.job_ttl_seconds, cap=settings.job_cap)
