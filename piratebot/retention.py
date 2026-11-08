"""Limpeza automática das capturas de tela do Pirate Farm.

A política é conservadora com as evidências do token: capturas ``token_*`` e
``tela_recompensa_*`` nunca são apagadas. As demais (incluindo os banners
genéricos ``reward_*``) entram na limpeza normal por idade ou por excesso de
arquivos, junto com as capturas mais antigas. As capturas mais recentes e os
arquivos recém-gravados (intervalo de carência) também são preservados. Uploads
de webhook usam os bytes da imagem em memória, então a limpeza pode rodar sem
interromper um envio em andamento.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .config import StorageConfig

EVIDENCE_PREFIXES = (
    "token",
    "tela_recompensa",
)

_PRUNE_LOCK = threading.Lock()


@dataclass(frozen=True)
class PruneResult:
    removed: int = 0
    freed_bytes: int = 0
    kept: int = 0
    protected: int = 0
    skipped: bool = False

    @property
    def freed_mb(self) -> float:
        return self.freed_bytes / (1024 * 1024)


def is_evidence(path: Path) -> bool:
    stem = path.stem.lower()
    return any(stem.startswith(prefix) for prefix in EVIDENCE_PREFIXES)


def _matches(path: Path, names: set[str]) -> bool:
    return path.name in names or str(path) in names


def prune_snapshots(
    folder: Path,
    config: StorageConfig,
    *,
    now: float | None = None,
    protect: Iterable[str | Path] = (),
) -> PruneResult:
    """Aplica a retenção à pasta de capturas.

    ``protect`` aceita nomes de arquivo ou caminhos completos que devem ser
    preservados nesta rodada (por exemplo, uma captura recém-criada antes de o
    webhook terminar de lê-la).
    """
    if not folder.exists():
        return PruneResult()

    if not _PRUNE_LOCK.acquire(blocking=False):
        # Outra limpeza já está em andamento; a próxima rodada cuida do resto.
        return PruneResult(skipped=True)

    try:
        return _prune(folder, config, now=now, protect=protect)
    finally:
        _PRUNE_LOCK.release()


def _prune(
    folder: Path,
    config: StorageConfig,
    *,
    now: float | None,
    protect: Iterable[str | Path],
) -> PruneResult:
    current = time.time() if now is None else now
    names = {str(item) for item in protect} | {Path(item).name for item in protect}

    entries: list[tuple[Path, float, int]] = []
    try:
        candidates = list(folder.glob("*.png"))
    except OSError:
        return PruneResult()

    for path in candidates:
        if _matches(path, names):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        entries.append((path, stat.st_mtime, stat.st_size))

    entries.sort(key=lambda item: item[1], reverse=True)
    grace = max(0.0, float(config.snapshot_grace_seconds))
    min_keep = max(0, int(config.snapshot_min_keep))
    keep_names: set[str] = set()

    # As N capturas mais novas nunca são apagadas, mesmo que sejam antigas ou
    # que a pasta esteja acima do limite.
    for path, _mtime, _size in entries[:min_keep]:
        keep_names.add(path.name)

    def is_protected(path: Path, mtime: float) -> bool:
        return (
            path.name in keep_names
            or is_evidence(path)
            or (current - mtime) < grace
        )

    removable = [
        (path, mtime, size)
        for path, mtime, size in entries
        if not is_protected(path, mtime)
    ]
    removable.sort(key=lambda item: item[1])  # mais antigas primeiro

    removed = 0
    freed = 0

    if int(config.snapshot_max_age_days) > 0:
        max_age = float(config.snapshot_max_age_days) * 86400.0
        for path, mtime, size in removable:
            if current - mtime <= max_age:
                continue
            try:
                path.unlink()
            except OSError:
                continue
            removed += 1
            freed += size

    remaining = len(entries) - removed
    max_files = int(config.snapshot_max_files)
    if max_files > 0 and remaining > max_files:
        for path, _mtime, size in removable:
            if remaining <= max_files:
                break
            try:
                path.unlink()
            except OSError:
                continue
            removed += 1
            freed += size
            remaining -= 1

    kept = max(0, len(entries) - removed)
    protected = len(entries) - len(removable)
    return PruneResult(
        removed=removed,
        freed_bytes=freed,
        kept=kept,
        protected=protected,
    )
