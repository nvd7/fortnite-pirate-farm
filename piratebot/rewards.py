"""Leitura e identificação das recompensas exibidas no centro da tela.

O Fortnite mostra banners como "VOCÊ ENCONTROU / FERRAMENTA ESPÍRITO" ou
"YOU FOUND / PIRATE SHOP ACCESS". O OCR do Windows (winrt) lê o texto em
português e o parser transforma as linhas em um nome de recompensa. Quando o
OCR não consegue ler (por exemplo, interface em árabe ou pacote de idioma
ausente), um detector visual de banners usa o rótulo genérico e a captura ainda
é enviada ao webhook.
"""
from __future__ import annotations

import asyncio
import os
import re
import tempfile
import threading
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

from .config import RewardConfig

TOKEN_NAME = "Acesso à Loja Pirata"
GENERIC_NAME = "Recompensa encontrada"

_HEADER_WORDS = {
    "encontrou",
    "encontraste",
    "found",
    # Cabeçalhos em árabe ("لقد عثرت على" / "وجدت"), caso o pacote de OCR
    # esteja instalado. O envio da captura não depende disso.
    "عثرت",
    "وجدت",
    "حصلت",
}
_PREFIX_WORDS = {"voce", "voc", "you", "vou", "tu", "has", "have", "lhe", "لقد"}
_TOKEN_PHRASES = (
    "pirate shop access",
    "acesso a loja pirata",
    "متجر القراصنة",
)
_JUNK_LINE = re.compile(
    r"^(?:\d{1,2}:\d{2}|\d{1,3}|[a-z0-9.-]+\.(?:gg|com|net|br|tv|io)|arlon\w*)$",
    re.IGNORECASE,
)
# Linhas de HUD que podem ficar centralizadas e grudar no nome da recompensa.
_NAME_STOP_PREFIXES = (
    "espaco para",
    "espaco ",
    "para instalar",
    "pressione",
    "pressiona",
    "use ",
    "usar ",
    "o cartao",
)
_TRIM = " \t\r\n\"'“”‘’«»-–—|\\/*_~`^•·:;,."
# Quantidades/artefatos que o OCR às vezes cola no fim do nome, como
# "FERRAMENTA ESPÍRITO x2" ou "ELEMENTAL (1)".
_OCR_QUANTITY_TAIL = re.compile(
    r"(?:\s*[x×]\s*\d{1,3}|\s*\d{1,3}\s*[x×]|"
    r"\s*\(\s*\d{1,3}\s*\)?|\s*\[\s*\d{1,3}\s*\]?)$",
    re.IGNORECASE,
)


def _fold(text: str) -> str:
    """Minúsculas sem acentos, para comparar palavras do OCR."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


def clean_ocr_line(line: str) -> str:
    line = re.sub(r"\s+", " ", str(line)).strip()
    line = line.strip(_TRIM)
    line = re.sub(r"^[^\wÀ-ÿ]+", "", line)
    line = re.sub(r"[^\wÀ-ÿ.!?%&]+$", "", line)
    return line.strip()


def _is_junk_line(line: str) -> bool:
    cleaned = clean_ocr_line(line)
    if not cleaned:
        return True
    if _JUNK_LINE.match(cleaned):
        return True
    folded = _fold(cleaned)
    if folded in ("timesaver", "timesaver gg"):
        return True
    return False


def _header_span(words: list[str]) -> Optional[tuple[int, int]]:
    folded = [_fold(word).strip(".,:;!?()[]") for word in words]
    for index, word in enumerate(folded):
        if word not in _HEADER_WORDS:
            continue
        start = index
        if index > 0 and folded[index - 1] in _PREFIX_WORDS:
            start = index - 1
        return start, index + 1
    return None


def _strip_ocr_tail(value: str) -> str:
    """Remove quantidade/pontuação que o OCR cola no fim do nome.

    O banner não mostra quantidade, então um número solto no fim costuma ser
    ruído de HUD (por exemplo, "Dispositivo Elemental 1"). Números com dois ou
    mais dígitos são preservados para não quebrar nomes como "G 63".
    """
    name = _OCR_QUANTITY_TAIL.sub("", value).strip(_TRIM)
    words = name.split()
    if (
        len(words) >= 2
        and len(words[-1]) == 1
        and words[-1].isdigit()
        and len(words[-2].strip(".-")) > 1
    ):
        words.pop()
        name = " ".join(words)
    return name.strip(_TRIM)


def _clean_name(value: str) -> str:
    name = clean_ocr_line(value)
    name = re.sub(r"\s+", " ", name).strip(_TRIM)
    name = _strip_ocr_tail(name)
    name = re.sub(r"\s+(?:em|at|no|na)\s+\d.*$", "", name, flags=re.IGNORECASE)
    # Em árabe o cabeçalho "لقد عثرت على" deixa a preposição "على" no início.
    name = re.sub(r"^(?:على|في)\s+", "", name)
    if len(name) < 2 or _is_junk_line(name):
        return ""
    if name.isupper():
        name = name.title()
    if len(name) > 80:
        name = name[:77].rstrip() + "..."
    return name


def _mentions_token(folded: str) -> bool:
    return any(phrase in folded for phrase in _TOKEN_PHRASES) or (
        "loja pirata" in folded and "token" in folded
    )


def parse_reward_text(text: str) -> Optional["RewardEvent"]:
    """Extrai o nome da recompensa das linhas reconhecidas pelo OCR."""
    if not text:
        return None

    lines = [clean_ocr_line(line) for line in str(text).splitlines()]
    lines = [line for line in lines if line and not _is_junk_line(line)]

    for index, line in enumerate(lines):
        words = line.split()
        span = _header_span(words)
        if span is None:
            continue

        _start, end = span
        inline_name = _clean_name(" ".join(words[end:]))
        name_parts = [inline_name] if inline_name else []
        # O nome pode ocupar duas ou três linhas centralizadas
        # ("DISPOSITIVO" / "ELEMENTAL"). Junte as linhas seguintes até outro
        # cabeçalho ou até o limite de segurança.
        for following in lines[index + 1 : index + 4]:
            if _is_junk_line(following):
                continue
            if _header_span(following.split()) is not None:
                break
            piece = _clean_name(following)
            if not piece:
                continue
            if _fold(piece).startswith(_NAME_STOP_PREFIXES):
                break
            name_parts.append(piece)
            if len(" ".join(name_parts).split()) >= 8:
                break
        name = _strip_ocr_tail(" ".join(name_parts).strip())
        if len(name) > 80:
            name = name[:77].rstrip() + "..."

        folded = _fold(text)
        if _mentions_token(folded):
            return RewardEvent(
                name=TOKEN_NAME,
                kind="token",
                raw_text=text,
                confidence=1.0,
                via="ocr",
            )

        return RewardEvent(
            name=name or GENERIC_NAME,
            kind="item" if name else "unknown",
            raw_text=text,
            confidence=0.85 if name else 0.45,
            via="ocr",
        )

    folded = _fold(text)
    if _mentions_token(folded):
        return RewardEvent(
            name=TOKEN_NAME,
            kind="token",
            raw_text=text,
            confidence=0.9,
            via="ocr",
        )
    return None


def _resize(frame: np.ndarray, width: int = 960) -> np.ndarray:
    height, current_width = frame.shape[:2]
    if current_width <= 0:
        return frame
    scale = width / float(current_width)
    if abs(scale - 1.0) < 0.05:
        return frame
    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
    return cv2.resize(frame, (width, max(1, int(height * scale))), interpolation=interpolation)


def _band_mask_score(mask: np.ndarray, density_weight: float) -> float:
    roi_h, roi_w = mask.shape[:2]
    if roi_h < 40 or roi_w < 120 or not mask.any():
        return 0.0

    row_density = (mask > 0).mean(axis=1)
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for y, density in enumerate(row_density):
        if density > 0.016:
            if start is None:
                start = y
        elif start is not None:
            runs.append((start, y))
            start = None
    if start is not None:
        runs.append((start, len(row_density)))

    merged: list[tuple[int, int]] = []
    gap = max(3, int(roi_h * 0.018))
    for run in runs:
        if merged and run[0] - merged[-1][1] <= gap:
            merged[-1] = (merged[-1][0], run[1])
        else:
            merged.append(run)

    bands: list[tuple[float, float, float, float]] = []
    for top, bottom in merged:
        band_height = bottom - top
        if band_height < roi_h * 0.012 or band_height > roi_h * 0.16:
            continue
        columns = (mask[top:bottom] > 0).mean(axis=0)
        xs = np.where(columns > 0.018)[0]
        if len(xs) < 3:
            continue
        span_ratio = (xs[-1] - xs[0]) / float(roi_w)
        if span_ratio < 0.10:
            continue
        center = ((xs[0] + xs[-1]) / 2.0) / float(roi_w)
        if not (0.20 <= center <= 0.80):
            continue
        density = mask[top:bottom].mean() / 255.0
        bands.append((float(band_height), float(span_ratio), float(center), float(density)))

    if not bands:
        return 0.0

    count = len(bands)
    widest = max(band[1] for band in bands)
    density = sum(band[3] for band in bands) / count
    center_error = max(abs(band[2] - 0.5) for band in bands)

    score = 0.0
    score += min(0.45, 0.16 * count)
    score += min(0.30, widest * 0.60)
    score += min(0.20, density * density_weight)
    if center_error < 0.18:
        score += 0.05
    if count < 2:
        score *= 0.55
    return round(min(1.0, score), 3)


def banner_score(frame: np.ndarray) -> float:
    """Confiança de que há um banner de texto grande e centralizado na tela.

    Combina duas pistas: manchas claras/douradas (banners sobre fundo escuro) e
    bordas de texto (banners sobre fundo claro). O maior valor vale, o que cobre
    os dois estilos usados pelo Fortnite sem depender do idioma.
    """
    if frame is None or getattr(frame, "size", 0) == 0:
        return 0.0
    height, width = frame.shape[:2]
    if height < 120 or width < 240:
        return 0.0

    img = _resize(frame, 960)
    h, w = img.shape[:2]
    roi = img[int(h * 0.06) : int(h * 0.82), int(w * 0.10) : int(w * 0.90)]
    if roi.shape[0] < 40 or roi.shape[1] < 120:
        return 0.0

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    white = cv2.inRange(hsv, (0, 0, 175), (180, 85, 255))
    gold = cv2.inRange(hsv, (8, 85, 145), (42, 255, 255))
    color = cv2.bitwise_or(white, gold)
    color = cv2.morphologyEx(
        color,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (9, 3)),
    )
    color_score = _band_mask_score(color, density_weight=0.9)

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 60, 160)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    text_edges = cv2.bitwise_and(color, edges)
    text_edges = cv2.dilate(
        text_edges,
        cv2.getStructuringElement(cv2.MORPH_RECT, (9, 3)),
        iterations=1,
    )
    edge_score = _band_mask_score(text_edges, density_weight=2.5)
    return max(color_score, edge_score)


def _center_gold_ratio(frame: np.ndarray) -> float:
    """Fração de pixels dourados na região central da tela."""
    if frame is None or getattr(frame, "size", 0) == 0:
        return 0.0
    height, width = frame.shape[:2]
    if height < 120 or width < 240:
        return 0.0
    roi = frame[
        int(height * 0.18) : int(height * 0.82),
        int(width * 0.18) : int(width * 0.82),
    ]
    if roi.size == 0:
        return 0.0
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    gold = cv2.inRange(hsv, (8, 90, 130), (42, 255, 255))
    return float((gold > 0).mean())


class ChestPrecue:
    """Detecta um clarão dourado central para acelerar as próximas leituras.

    Baús com token brilham e tremem por alguns segundos antes do banner, mas
    baús/recompensas comuns também podem brilhar em dourado. Por isso este
    sinal é usado apenas como precue: ele encurta o intervalo de varredura por
    alguns segundos. A confirmação do token continua sendo feita pela moeda
    dourada, pelo banner e pelo OCR.
    """

    def __init__(self, config: RewardConfig) -> None:
        self.config = config
        self.last_ratio = 0.0
        self._previous_ratio: Optional[float] = None
        self._last_trigger_at = float("-inf")

    def reset(self) -> None:
        self._previous_ratio = None

    def update(self, frame: np.ndarray, now: Optional[float] = None) -> bool:
        current = time.time() if now is None else now
        ratio = _center_gold_ratio(frame)
        self.last_ratio = ratio
        previous = self._previous_ratio
        self._previous_ratio = ratio

        if not self.config.chest_precue_enabled or previous is None:
            return False
        if current - self._last_trigger_at < max(
            0.0, float(self.config.chest_precue_cooldown_seconds)
        ):
            return False
        if ratio < max(0.0, float(self.config.chest_precue_min_gold)):
            return False
        if ratio - previous < max(0.0, float(self.config.chest_precue_delta)):
            return False

        self._last_trigger_at = current
        return True


def _gold_components(roi: np.ndarray) -> list[tuple[int, int, int, int, int, float, float, float]]:
    """Componentes dourados claros da faixa central da tela.

    O banner de recompensa do Fortnite usa sempre o mesmo brasão: um ícone
    emoldurado em dourado sobre uma faixa/asa dourada com o texto. As cores
    variam com a recompensa, mas o dourado do brasão é constante.
    """
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    gold = cv2.inRange(hsv, (10, 125, 155), (38, 255, 255))
    gold = cv2.morphologyEx(
        gold,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7)),
    )
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(gold, 8)
    roi_h, roi_w = roi.shape[:2]
    components: list[tuple[int, int, int, int, int, float, float, float]] = []
    for index in range(1, count):
        area = int(stats[index, cv2.CC_STAT_AREA])
        if area < 120:
            continue
        x = int(stats[index, cv2.CC_STAT_LEFT])
        y = int(stats[index, cv2.CC_STAT_TOP])
        width = int(stats[index, cv2.CC_STAT_WIDTH])
        height = int(stats[index, cv2.CC_STAT_HEIGHT])
        if width <= 0 or height <= 0:
            continue
        components.append(
            (
                area,
                x,
                y,
                width,
                height,
                (x + width / 2.0) / roi_w,
                (y + height / 2.0) / roi_h,
                area / float(width * height),
            )
        )
    return components


def reward_badge_score(frame: np.ndarray) -> float:
    """Confiança de que há um brasão de recompensa no centro-alto da tela.

    Diferente de ``banner_score`` (que só mede manchas claras/douradas), este
    detector exige a estrutura do banner: uma faixa dourada centralizada e um
    ícone emoldurado logo acima dela. Telas de carregamento, nomes de
    espectador e HUD não têm esse par, então não passam. Funciona em qualquer
    idioma, o que cobre a interface em árabe sem OCR.
    """
    if frame is None or getattr(frame, "size", 0) == 0:
        return 0.0
    height, width = frame.shape[:2]
    if height < 120 or width < 240:
        return 0.0

    img = _resize(frame, 960)
    h, w = img.shape[:2]
    x0, x1 = int(w * 0.15), int(w * 0.85)
    y0, y1 = int(h * 0.03), int(h * 0.50)
    roi = img[y0:y1, x0:x1]
    roi_h, roi_w = roi.shape[:2]
    if roi_h < 80 or roi_w < 200:
        return 0.0

    components = _gold_components(roi)
    if not components:
        return 0.0

    # Faixa/asa dourada: larga, centralizada e com preenchimento razoável.
    # Os limites superiores evitam que um cenário dourado inteiro (porta,
    # areia, HUD de espectador) seja confundido com a faixa do banner.
    ribbons = [
        item
        for item in components
        if roi_w * 0.12 <= item[3] <= roi_w * 0.60
        and roi_h * 0.12 <= item[4] <= roi_h * 0.60
        and 1.3 <= item[3] / float(item[4]) <= 4.0
        and item[7] >= 0.30
        and 0.40 <= item[5] <= 0.60
        and 0.30 <= item[6] <= 0.70
    ]

    best = 0.0
    for area, _x, y, _width, _height, _cx, cy, fill in ribbons:
        # Ícone acima da faixa. O miolo do ícone pode ser escuro, então vários
        # componentes pequenos são agrupados em uma única caixa.
        above = [
            item
            for item in components
            if 0.40 <= item[5] <= 0.60
            and item[6] < cy - 0.04
            and item[2] >= y - roi_h * 0.30
        ]
        if not above:
            continue
        icon_x0 = min(item[1] for item in above)
        icon_y0 = min(item[2] for item in above)
        icon_x1 = max(item[1] + item[3] for item in above)
        icon_y1 = max(item[2] + item[4] for item in above)
        icon_w = icon_x1 - icon_x0
        icon_h = icon_y1 - icon_y0
        if icon_w < roi_w * 0.05 or icon_h < roi_h * 0.07:
            continue
        # O ícone do brasão é emoldurado e aproximadamente quadrado. Nomes de
        # jogador e títulos do HUD formam faixas largas e não devem passar.
        if not (0.55 <= icon_w / float(icon_h) <= 1.90):
            continue
        icon_fill = sum(item[0] for item in above) / float(icon_w * icon_h)
        if icon_fill < 0.30:
            continue
        gap = (y - icon_y1) / float(roi_h)
        if gap > 0.10:
            continue

        score = 0.55
        score += min(0.15, (area / float(roi_h * roi_w)) * 4.0)
        score += 0.10 if fill >= 0.35 else 0.05
        score += 0.10 if icon_w >= roi_w * 0.06 else 0.05
        score += 0.10 if gap <= 0.05 else 0.05
        best = max(best, min(1.0, score))

    return round(best, 3)


@dataclass(frozen=True)
class RewardEvent:
    name: str
    kind: str = "item"
    raw_text: str = ""
    confidence: float = 0.0
    via: str = "ocr"

    @property
    def is_token(self) -> bool:
        return self.kind == "token"


def slugify(value: str, max_length: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", _fold(value)).strip("-")
    return (slug or "recompensa")[:max_length].strip("-")


class OcrReader:
    """OCR nativo do Windows, criado sob demanda e com falha silenciosa."""

    def __init__(self, logger: Optional[Callable[[str, str], None]] = None) -> None:
        self._logger = logger
        self._engine = None
        self._failed = False
        self._lock = threading.Lock()
        self._temp = Path(tempfile.gettempdir()) / f"piratefarm_ocr_{os.getpid()}_{id(self)}.png"
        self._warned = False

    def _log(self, text: str, level: str = "debug") -> None:
        if self._logger is not None:
            self._logger(text, level)

    def available(self) -> bool:
        return self._ensure_engine()

    def _ensure_engine(self) -> bool:
        if self._engine is not None:
            return True
        if self._failed:
            return False
        try:
            from winrt.windows.media.ocr import OcrEngine

            try:
                import winrt.windows.globalization  # noqa: F401
            except Exception:
                pass
            engine = OcrEngine.try_create_from_user_profile_languages()
        except Exception as exc:
            self._failed = True
            self._log(
                f"OCR do Windows indisponível ({exc}). "
                "As capturas serão enviadas com o nome genérico.",
                "warn",
            )
            return False
        if engine is None:
            self._failed = True
            self._log(
                "OCR do Windows sem pacote de idioma instalado. "
                "As capturas serão enviadas com o nome genérico.",
                "warn",
            )
            return False
        self._engine = engine
        return True

    def recognize(
        self,
        frame: np.ndarray,
        region: Optional[tuple[float, float, float, float]] = None,
    ) -> str:
        if not self._ensure_engine():
            return ""
        crop = self._crop(frame, region=region)
        if crop is None:
            return ""
        try:
            ok, encoded = cv2.imencode(".png", crop)
            if not ok:
                return ""
        except Exception:
            return ""

        with self._lock:
            try:
                encoded.tofile(str(self._temp))
                return asyncio.run(self._recognize_async(self._temp, crop.shape[1]))
            except Exception as exc:
                if not self._warned:
                    self._warned = True
                    self._log(f"Falha ao ler o texto da recompensa: {exc}", "debug")
                return ""
            finally:
                try:
                    self._temp.unlink(missing_ok=True)
                except OSError:
                    pass

    async def _recognize_async(self, path: Path, crop_width: int) -> str:
        from winrt.windows.graphics.imaging import BitmapDecoder
        from winrt.windows.storage import FileAccessMode, StorageFile

        file = await StorageFile.get_file_from_path_async(str(path.resolve()))
        stream = await file.open_async(FileAccessMode.READ)
        try:
            decoder = await BitmapDecoder.create_async(stream)
            bitmap = await decoder.get_software_bitmap_async()
            result = await self._engine.recognize_async(bitmap)  # type: ignore[union-attr]
            lines: list[tuple[str, float]] = []
            for line in result.lines:
                text = str(line.text or "").strip()
                if not text:
                    continue
                words = list(line.words)
                if words:
                    left = min(float(word.bounding_rect.x) for word in words)
                    right = max(
                        float(word.bounding_rect.x + word.bounding_rect.width)
                        for word in words
                    )
                    center = ((left + right) / 2.0) / max(1, crop_width)
                else:
                    center = 0.5
                lines.append((text, center))
            return self._filter_lines(lines)
        finally:
            try:
                stream.close()
            except Exception:
                pass

    @staticmethod
    def _filter_lines(lines: list[tuple[str, float]]) -> str:
        """Mantém apenas as linhas próximas ao banner central.

        O OCR recebe uma faixa larga da tela. Sem esse filtro, textos do HUD
        (nome do espectador, kill feed, avisos de evento) entram no nome da
        recompensa. O cabeçalho do banner define a âncora horizontal; se ele
        não for reconhecido, usamos o centro da tela.
        """
        if not lines:
            return ""
        anchor = 0.5
        for text, center in lines:
            folded = _fold(text)
            words = set(folded.replace("-", " ").split())
            if words & _HEADER_WORDS or _mentions_token(folded):
                anchor = center
                break
        kept = [
            text
            for text, center in lines
            if abs(center - anchor) <= 0.18
        ]
        return "\n".join(kept)

    @staticmethod
    def _crop(
        frame: np.ndarray,
        target_width: int = 1600,
        region: Optional[tuple[float, float, float, float]] = None,
    ) -> Optional[np.ndarray]:
        if frame is None or getattr(frame, "size", 0) == 0:
            return None
        height, width = frame.shape[:2]
        if height < 80 or width < 160:
            return None
        y0, y1, x0, x1 = region or (0.08, 0.80, 0.06, 0.94)
        crop = frame[
            int(height * y0) : int(height * y1),
            int(width * x0) : int(width * x1),
        ]
        if crop.size == 0:
            return None
        scale = target_width / float(crop.shape[1])
        if abs(scale - 1.0) > 0.12:
            interpolation = cv2.INTER_CUBIC if scale > 1.0 else cv2.INTER_AREA
            crop = cv2.resize(
                crop,
                (target_width, max(1, int(crop.shape[0] * scale))),
                interpolation=interpolation,
            )
        return crop


class RewardScanner:
    def __init__(
        self,
        config: RewardConfig,
        logger: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self.config = config
        self._ocr = OcrReader(logger=logger) if config.ocr_enabled else None
        self._last_scan_at = float("-inf")
        self.last_score = 0.0
        self.last_badge_score = 0.0

    def scan(
        self,
        frame: np.ndarray,
        *,
        token_visual: bool = False,
        force: bool = False,
        now: Optional[float] = None,
    ) -> Optional[RewardEvent]:
        current = time.time() if now is None else now
        if token_visual:
            return RewardEvent(
                name=TOKEN_NAME,
                kind="token",
                raw_text="token detectado visualmente",
                confidence=1.0,
                via="visual",
            )

        interval = max(0.4, float(self.config.scan_interval))
        if not force and current - self._last_scan_at < interval:
            return None
        self._last_scan_at = current

        # O OCR roda em todas as capturas periódicas. O banner é reconhecido
        # pelo texto ("VOCÊ ENCONTROU" / "YOU FOUND"), sem depender de um
        # limiar visual que telas de carregamento conseguem enganar.
        self.last_score = banner_score(frame)
        badge = reward_badge_score(frame)
        self.last_badge_score = badge

        text = self._ocr.recognize(frame) if self._ocr is not None else ""
        event = parse_reward_text(text)
        if event is not None:
            return RewardEvent(
                name=event.name,
                kind=event.kind,
                raw_text=event.raw_text,
                confidence=min(1.0, max(event.confidence, self.last_score)),
                via="ocr",
            )

        # Quando o brasão existe mas o texto não foi lido, tenta um recorte
        # fechado no banner. A faixa larga ajuda a achar o banner; o recorte
        # fechado aumenta a fonte para o OCR e resolve fundos carregados.
        if (
            badge >= float(self.config.fallback_banner_score)
            and self._ocr is not None
        ):
            tight_text = self._ocr.recognize(
                frame, region=(0.05, 0.42, 0.22, 0.78)
            )
            if tight_text and tight_text != text:
                tight_event = parse_reward_text(tight_text)
                if tight_event is not None:
                    return RewardEvent(
                        name=tight_event.name,
                        kind=tight_event.kind,
                        raw_text=tight_event.raw_text,
                        confidence=min(1.0, max(tight_event.confidence, badge)),
                        via="ocr",
                    )
                text = tight_text

        # Sem texto aproveitável (interface em árabe, OCR ausente): usa a
        # estrutura do brasão dourado, que é idêntica em qualquer idioma.
        if badge >= float(self.config.fallback_banner_score):
            return RewardEvent(
                name=self.config.fallback_label or GENERIC_NAME,
                kind="unknown",
                raw_text=text,
                confidence=badge,
                via="visual",
            )
        return None


class RewardGate:
    """Evita repetir a mesma recompensa enquanto o banner permanece na tela."""

    def __init__(self, cooldown: float = 12.0, token_cooldown: float = 3600.0) -> None:
        self.cooldown = max(0.0, float(cooldown))
        self.token_cooldown = max(self.cooldown, float(token_cooldown))
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def accept(self, event: RewardEvent, now: Optional[float] = None) -> bool:
        current = time.time() if now is None else now
        key = f"{event.kind}:{_fold(event.name).strip()}"
        cooldown = self.token_cooldown if event.is_token else self.cooldown
        with self._lock:
            last = self._last.get(key, 0.0)
            if current - last < cooldown:
                return False
            self._last[key] = current
            if len(self._last) > 200:
                cutoff = current - 86400.0
                self._last = {
                    name: when for name, when in self._last.items() if when >= cutoff
                }
        return True
