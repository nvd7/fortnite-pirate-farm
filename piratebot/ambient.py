"""Movimento ambiente anti-AFK durante a partida.

O Fortnite passou a punir jogador parado dentro da partida enquanto o resto do
esquadrão farma baús. Este módulo mantém o personagem com vida: rajadas curtas
de caminhada, strafe, olhada de câmera, agachar e pular, com intervalos
aleatórios entre as rajadas. O objetivo é parecer um jogador distraído, não um
metrônomo — nada aqui é periódico.

Regras que o módulo respeita:

* só age quando o dono do bot diz que pode (``should_run``): fase de partida,
  personagem vivo, sem menu de saída aberto;
* nunca segura tecla sem soltar — todo caminho de erro passa por
  ``release_all``;
* não interrompe digitação: se o teclado/mouse do usuário foi usado há menos de
  ``respect_user_input_seconds``, a rajada é adiada;
* o backend é injetado, então o planejamento é testável sem Windows.
"""
from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from .config import AmbientConfig

# Peso relativo de cada ação. Caminhada domina porque é o que um jogador
# perdido no mapa faz; olhada vem em segundo para dar vida à câmera.
_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("walk", 32),
    ("strafe", 22),
    ("look", 18),
    ("idle", 12),
    ("jump", 10),
    ("crouch", 6),
)


class InputUnavailable(RuntimeError):
    """O backend não conseguiu colocar o jogo em primeiro plano."""


class InputBackend(Protocol):
    """Superfície mínima que o controlador do jogo precisa oferecer."""

    def begin_burst(self) -> object: ...

    def end_burst(self, token: object) -> None: ...

    def key_down(self, name: str) -> None: ...

    def key_up(self, name: str) -> None: ...

    def release_all(self) -> None: ...

    def tap_key(self, name: str, hold: float) -> None: ...

    def look(self, dx: int, dy: int) -> None: ...


@dataclass(frozen=True)
class Action:
    """Uma unidade de movimento já resolvida (sem aleatoriedade)."""

    kind: str
    duration: float = 0.0
    keys: tuple[str, ...] = ()
    dx: int = 0
    dy: int = 0


def _jitter(rng: random.Random, value: float, spread: float = 0.18) -> float:
    """Aplica variação percentual para o ritmo não ficar mecânico."""
    return max(0.05, value * (1.0 + rng.uniform(-spread, spread)))


def _enabled(kind: str, cfg: AmbientConfig) -> bool:
    if kind == "look":
        return cfg.look_enabled
    if kind == "jump":
        return cfg.jump_enabled
    if kind == "crouch":
        return cfg.crouch_enabled
    if kind == "emote":
        return cfg.emote_chance > 0.0
    return True


def _pick_action(rng: random.Random, cfg: AmbientConfig, first: bool) -> Action:
    if first:
        kind = "walk"
    else:
        total = sum(weight for name, weight in _WEIGHTS if _enabled(name, cfg))
        if total <= 0:
            return Action("idle", _jitter(rng, 0.6))
        roll = rng.uniform(0.0, total)
        kind = "idle"
        for name, weight in _WEIGHTS:
            if not _enabled(name, cfg):
                continue
            roll -= weight
            if roll <= 0:
                kind = name
                break

    if kind == "walk":
        keys = ("w", "shift") if rng.random() < cfg.sprint_chance else ("w",)
        return Action("walk", _jitter(rng, rng.uniform(0.6, 2.2)), keys)
    if kind == "strafe":
        keys = ("a",) if rng.random() < 0.5 else ("d",)
        return Action("strafe", _jitter(rng, rng.uniform(0.35, 1.1)), keys)
    if kind == "look":
        dx = rng.randint(70, 280) * (1 if rng.random() < 0.5 else -1)
        dy = rng.randint(-45, 25)
        return Action("look", _jitter(rng, 0.25), (), dx, dy)
    if kind == "jump":
        return Action("jump", 0.35)
    if kind == "crouch":
        return Action("crouch", 0.30)
    if kind == "emote":
        return Action("emote", 0.30)
    return Action("idle", _jitter(rng, rng.uniform(0.4, 1.6)))


def plan_burst(rng: random.Random, cfg: AmbientConfig) -> list[Action]:
    """Monta uma rajada curta de ações dentro do orçamento de tempo."""
    low = max(1, int(cfg.burst_min_actions))
    high = max(low, int(cfg.burst_max_actions))
    budget = max(0.5, float(cfg.max_burst_seconds))

    planned: list[Action] = []
    spent = 0.0
    for index in range(rng.randint(low, high)):
        action = _pick_action(rng, cfg, first=index == 0)
        if planned and spent + action.duration > budget:
            break
        planned.append(action)
        spent += action.duration
    if not planned:
        planned.append(Action("walk", min(1.0, budget), ("w",)))
    return planned


class AmbientMovement:
    """Thread de presença: mantém o personagem em movimento durante a partida."""

    def __init__(
        self,
        config: AmbientConfig,
        backend: InputBackend,
        should_run: Callable[[], bool],
        logger: Optional[Callable[[str, str], None]] = None,
        idle_probe: Optional[Callable[[], float]] = None,
        rng: Optional[random.Random] = None,
        dry_run: bool = False,
    ) -> None:
        self.config = config
        self._backend = backend
        self._should_run = should_run
        self._log = logger or (lambda message, level="info": None)
        self._idle_probe = idle_probe
        self._rng = rng or random.Random()
        self._dry_run = dry_run

        self._enabled = bool(config.enabled)
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        self._bursts = 0
        self._keys_sent = 0
        self._last_action = ""
        self._last_burst_at = 0.0
        self._first_burst_logged = False

    # ------------------------------------------------------------- controle
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="AmbientMovement", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        thread = self._thread
        if (
            thread is not None
            and thread.is_alive()
            and thread is not threading.current_thread()
        ):
            thread.join(timeout)
        self._release_safely()

    def pause(self) -> None:
        """Bloqueia novas ações e solta o que estiver pressionado agora."""
        self._pause.set()
        self._release_safely()

    def resume(self) -> None:
        self._pause.clear()

    def set_enabled(self, value: bool) -> None:
        self._enabled = bool(value)
        if not self._enabled:
            self._release_safely()

    def stats(self) -> dict[str, object]:
        with self._lock:
            return {
                "enabled": self._enabled,
                "paused": self._pause.is_set(),
                "bursts": self._bursts,
                "keys": self._keys_sent,
                "last_action": self._last_action,
                "last_burst_at": self._last_burst_at,
            }

    # ---------------------------------------------------------------- laço
    def _loop(self) -> None:
        self._stop.wait(self._initial_delay())
        while not self._stop.is_set():
            if self._can_act():
                try:
                    self._run_burst()
                except InputUnavailable as exc:
                    self._log(f"Movimento anti-AFK adiado: {exc}", "debug")
                except Exception as exc:  # nunca derruba o farm por isso
                    self._log(f"Falha no movimento anti-AFK: {exc}", "warn")
                finally:
                    self._release_safely()
                waited = self._next_delay()
            elif self._user_busy():
                waited = min(10.0, self._next_delay())
            else:
                waited = 1.0
            self._stop.wait(max(0.2, waited))

    def _initial_delay(self) -> float:
        # Entrar no mapa leva alguns segundos; agir no carregamento é inútil.
        return max(0.0, float(self.config.start_delay))

    def _next_delay(self) -> float:
        low = max(5.0, float(self.config.interval_min))
        high = max(low, float(self.config.interval_max))
        return self._rng.uniform(low, high)

    def _can_act(self) -> bool:
        if self._stop.is_set() or not self._enabled or self._pause.is_set():
            return False
        try:
            if not self._should_run():
                return False
        except Exception:
            return False
        return not self._user_busy()

    def _user_busy(self) -> bool:
        if self._idle_probe is None:
            return False
        threshold = max(0.0, float(self.config.respect_user_input_seconds))
        if threshold <= 0:
            return False
        try:
            return self._idle_probe() < threshold
        except Exception:
            return False

    # ------------------------------------------------------------- rajadas
    def _run_burst(self) -> None:
        actions = plan_burst(self._rng, self.config)
        if self._dry_run:
            for action in actions:
                self._wait(min(action.duration, 0.2))
            self._log(
                "SIMULAÇÃO: movimento anti-AFK ("
                + ", ".join(action.kind for action in actions)
                + ").",
                "debug",
            )
            self._count_burst(actions)
            return

        token = self._backend.begin_burst()
        try:
            for action in actions:
                if not self._can_act():
                    break
                self._perform(action)
        finally:
            self._release_safely()
            try:
                self._backend.end_burst(token)
            except Exception as exc:
                self._log(
                    f"Não consegui devolver o foco após o movimento: {exc}", "debug"
                )
        self._count_burst(actions)

    def _count_burst(self, actions: list[Action]) -> None:
        with self._lock:
            self._bursts += 1
            self._last_burst_at = time.time()
        if not self._first_burst_logged:
            self._first_burst_logged = True
            self._log(
                "Movimento anti-AFK ativo: rajadas de "
                f"{int(self.config.interval_min)}–{int(self.config.interval_max)}s "
                f"({len(actions)} ações).",
                "info",
            )

    def _perform(self, action: Action) -> None:
        kind = action.kind
        if kind in ("walk", "strafe"):
            for key in action.keys:
                self._backend.key_down(key)
            self._keys_add(len(action.keys))
            # Metade da caminhada com a câmera girando: parece jogador olhando
            # o mapa, não um bot andando em linha reta.
            half = action.duration / 2.0
            self._wait(half)
            if self.config.look_enabled and self._rng.random() < 0.45:
                self._backend.look(
                    self._rng.randint(40, 140) * (1 if self._rng.random() < 0.5 else -1),
                    self._rng.randint(-20, 10),
                )
            self._wait(action.duration - half)
            for key in action.keys:
                self._backend.key_up(key)
        elif kind == "look":
            self._backend.look(action.dx, action.dy)
            self._wait(action.duration)
        elif kind == "jump":
            self._backend.tap_key("space", 0.08)
            self._keys_add(1)
        elif kind == "crouch":
            self._backend.tap_key("ctrl", 0.08)
            self._keys_add(1)
        elif kind == "emote":
            self._backend.tap_key("b", 0.08)
            self._keys_add(1)
        else:
            self._wait(action.duration)
        with self._lock:
            self._last_action = kind

    def _keys_add(self, count: int) -> None:
        with self._lock:
            self._keys_sent += count

    def _release_safely(self) -> None:
        try:
            self._backend.release_all()
        except Exception:
            pass

    def _wait(self, seconds: float) -> None:
        deadline = time.monotonic() + max(0.0, seconds)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            if self._stop.is_set() or self._pause.is_set():
                return
            time.sleep(min(0.05, remaining))
