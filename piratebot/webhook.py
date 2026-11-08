"""Envio opcional de capturas e recompensas para um webhook.

Discord é detectado automaticamente e recebe um payload nativo com a imagem
anexada. Qualquer outro endereço recebe ``multipart/form-data`` com os campos
``content``, ``reward``, ``reward_name``, ``kind``, ``matches`` e ``file``.
A URL nunca é gravada inteira nos logs: apenas uma versão mascarada.
"""
from __future__ import annotations

import json
import queue
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

from . import __version__
from .config import WebhookConfig

APP_NAME = "Pirate Farm"
DISCORD_HOSTS = {
    "discord.com",
    "www.discord.com",
    "ptb.discord.com",
    "canary.discord.com",
    "discordapp.com",
    "www.discordapp.com",
}
_USER_AGENT = f"PirateFarm/{__version__}"


@dataclass
class WebhookMessage:
    reward: str
    kind: str = "item"
    matches: int = 0
    elapsed: float = 0.0
    occurred_at: float = field(default_factory=time.time)
    image_bytes: Optional[bytes] = None
    filename: str = "captura.png"


@dataclass(frozen=True)
class WebhookResult:
    ok: bool
    status: int = 0
    detail: str = ""
    attempts: int = 0


def is_discord_webhook(url: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return host in DISCORD_HOSTS


def validate_webhook_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        raise ValueError("Informe a URL do webhook.")
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError as exc:
        raise ValueError(f"URL inválida: {exc}") from exc
    if parsed.scheme not in ("http", "https"):
        raise ValueError("A URL precisa começar com http:// ou https://.")
    if not parsed.netloc:
        raise ValueError("A URL do webhook não tem um domínio válido.")
    return value


def mask_webhook_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return "<URL inválida>"
    host = parsed.netloc or "?"
    if is_discord_webhook(url):
        return f"{parsed.scheme}://{host}/api/webhooks/••••/••••"
    if not parsed.path or parsed.path == "/":
        return f"{parsed.scheme}://{host}/"
    tail = parsed.path[-4:] if len(parsed.path) > 8 else "••••"
    query = "?••••" if parsed.query else ""
    return f"{parsed.scheme}://{host}/…{tail}{query}"


def _format_elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _content(message: WebhookMessage) -> str:
    if message.kind == "token":
        return f"🏴‍☠️ **{message.reward}** encontrado!"
    if message.kind == "test":
        return f"✅ Teste do {APP_NAME}: webhook configurado corretamente."
    return f"🎁 **{message.reward}**"


def _details(message: WebhookMessage) -> str:
    return (
        f"Partida: {message.matches} · Tempo: {_format_elapsed(message.elapsed)}"
    )


def _timestamp(message: WebhookMessage) -> str:
    return datetime.fromtimestamp(message.occurred_at, timezone.utc).isoformat()


def _discord_payload(message: WebhookMessage, username: str) -> dict:
    payload: dict = {
        "username": username or APP_NAME,
        "content": _content(message),
        "allowed_mentions": {"parse": []},
    }
    if message.kind != "test":
        embed = {
            "title": f"🎁 {message.reward}",
            "description": _details(message),
            "color": 0xF4C95D if message.kind == "token" else 0x34D399,
            "timestamp": _timestamp(message),
            "footer": {"text": f"{APP_NAME} • Fortnite"},
        }
        if message.image_bytes:
            embed["image"] = {"url": f"attachment://{message.filename}"}
        payload["embeds"] = [embed]
    return payload


def encode_multipart(
    fields: list[tuple[str, str]],
    files: list[tuple[str, str, str, bytes]],
) -> tuple[bytes, str]:
    boundary = "----PirateFarm" + uuid.uuid4().hex
    body = bytearray()

    for name, value in fields:
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="{name}"\r\n'.encode("utf-8")
        )
        body.extend(b"Content-Type: text/plain; charset=utf-8\r\n\r\n")
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")

    for name, filename, content_type, data in files:
        safe_name = filename.replace('"', "%22").replace("\r", "").replace("\n", "")
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            (
                f'Content-Disposition: form-data; name="{name}"; '
                f'filename="{safe_name}"\r\n'
            ).encode("utf-8")
        )
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        body.extend(data)
        body.extend(b"\r\n")

    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def build_payload(
    config: WebhookConfig,
    message: WebhookMessage,
) -> tuple[bytes, str]:
    if is_discord_webhook(config.url):
        payload = _discord_payload(message, config.username)
        fields = [
            ("payload_json", json.dumps(payload, ensure_ascii=False)),
        ]
        files = []
        if config.send_screenshot and message.image_bytes:
            files.append(
                ("files[0]", message.filename, "image/png", message.image_bytes)
            )
        return encode_multipart(fields, files)

    metadata = {
        "app": APP_NAME,
        "version": __version__,
        "reward": message.reward,
        "reward_name": message.reward,
        "kind": message.kind,
        "matches": message.matches,
        "elapsed_seconds": round(max(0.0, message.elapsed), 1),
        "timestamp": _timestamp(message),
    }
    content = _content(message)
    fields = [
        ("content", content),
        ("text", content),
        ("reward", message.reward),
        ("reward_name", message.reward),
        ("kind", message.kind),
        ("matches", str(message.matches)),
        ("elapsed", _format_elapsed(message.elapsed)),
        ("timestamp", _timestamp(message)),
        ("payload", json.dumps(metadata, ensure_ascii=False)),
    ]
    files = []
    if config.send_screenshot and message.image_bytes:
        files.append(("file", message.filename, "image/png", message.image_bytes))
    return encode_multipart(fields, files)


def _post_once(
    config: WebhookConfig,
    message: WebhookMessage,
) -> tuple[WebhookResult, Optional[float]]:
    body, content_type = build_payload(config, message)
    request = urllib.request.Request(
        config.url,
        data=body,
        method="POST",
        headers={
            "Content-Type": content_type,
            "User-Agent": _USER_AGENT,
            "Accept": "application/json, */*",
        },
    )
    try:
        with urllib.request.urlopen(
            request, timeout=max(3.0, float(config.timeout_seconds))
        ) as response:
            response.read(1024)
            status = int(response.status)
            return WebhookResult(True, status, "ok"), None
    except urllib.error.HTTPError as exc:
        retry_after: Optional[float] = None
        if exc.code == 429:
            header = exc.headers.get("Retry-After") if exc.headers else None
            try:
                retry_after = float(header) if header is not None else None
            except ValueError:
                retry_after = None
        detail = f"HTTP {exc.code}"
        try:
            payload = exc.read(512).decode("utf-8", "replace")
            if payload:
                detail += f": {payload[:300]}"
        except Exception:
            pass
        return WebhookResult(False, exc.code, detail), retry_after
    except urllib.error.URLError as exc:
        return WebhookResult(False, 0, f"falha de rede: {exc.reason}"), None
    except Exception as exc:
        return WebhookResult(False, 0, f"erro inesperado: {exc}"), None


def send_message(
    config: WebhookConfig,
    message: WebhookMessage,
    *,
    attempts: int = 3,
    stop_event: Optional[threading.Event] = None,
) -> WebhookResult:
    result = WebhookResult(False, 0, "não enviado", 0)
    for attempt in range(1, max(1, attempts) + 1):
        result, retry_after = _post_once(config, message)
        result = WebhookResult(result.ok, result.status, result.detail, attempt)
        if result.ok:
            return result
        if result.status in (400, 401, 403, 404):
            return result
        if attempt >= attempts:
            return result

        wait = min(8.0, 1.5 * attempt)
        if result.status == 429:
            wait = min(30.0, retry_after if retry_after is not None else 2.0)
        deadline = time.time() + wait
        while time.time() < deadline:
            if stop_event is not None and stop_event.is_set():
                return result
            time.sleep(0.15)
    return result


def send_test(config: WebhookConfig) -> WebhookResult:
    """Envia uma mensagem de teste sem imagem (seguro para qualquer URL)."""
    url = validate_webhook_url(config.url)
    test_config = WebhookConfig(**{**config.__dict__, "url": url, "send_screenshot": False})
    message = WebhookMessage(
        reward="Teste do Pirate Farm",
        kind="test",
        matches=0,
        elapsed=0.0,
    )
    return send_message(test_config, message)


class WebhookNotifier:
    """Fila persistente em memória com um worker de envio."""

    def __init__(
        self,
        config: WebhookConfig,
        logger: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self.config = config
        self.logger = logger
        self._queue: "queue.Queue[Optional[WebhookMessage]]" = queue.Queue(
            maxsize=max(1, int(config.max_queue))
        )
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.sent = 0
        self.failed = 0

    def _log(self, text: str, level: str = "info") -> None:
        if self.logger is not None:
            self.logger(text, level)

    @property
    def active(self) -> bool:
        return bool(
            self.config.enabled
            and self.config.url.strip()
            and self._thread is not None
            and self._thread.is_alive()
        )

    def start(self) -> bool:
        if not self.config.enabled or not self.config.url.strip():
            return False
        if self._thread is not None and self._thread.is_alive():
            return True
        try:
            validate_webhook_url(self.config.url)
        except ValueError as exc:
            self._log(f"Webhook desativado: {exc}", "warn")
            return False
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._worker, name="WebhookNotifier", daemon=True
        )
        self._thread.start()
        self._log(
            f"Webhook ativo em {mask_webhook_url(self.config.url)}.", "success"
        )
        return True

    def enqueue(self, message: WebhookMessage, retries: int = 3) -> bool:
        if not self.active:
            return False
        try:
            self._queue.put_nowait(message)
            return True
        except queue.Full:
            self._log(
                "Fila do webhook cheia; a recompensa não foi enviada.", "warn"
            )
            return False

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._thread = None

    def _worker(self) -> None:
        while True:
            try:
                message = self._queue.get(timeout=0.5)
            except queue.Empty:
                if self._stop.is_set():
                    break
                continue
            if message is None:
                break
            if self._stop.is_set() and self._queue.empty():
                break
            result = send_message(self.config, message, stop_event=self._stop)
            if result.ok:
                self.sent += 1
                self._log(
                    f"Webhook enviado ({result.status}): {message.reward}.",
                    "success",
                )
            else:
                self.failed += 1
                self._log(
                    f"Falha no webhook ({result.status or 'sem resposta'}): "
                    f"{message.reward} — {result.detail}",
                    "warn",
                )
            self._queue.task_done()
