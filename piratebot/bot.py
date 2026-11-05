"""Máquina de estados do farm: lobby -> matchmaking -> AFK -> recompensas -> lobby."""
from __future__ import annotations

import logging
import queue
import threading
import time
import traceback
from enum import StrEnum
from typing import Optional

from . import power
from .config import ASSETS, LOGS, AppConfig
from .controller import GameController
from .logwatcher import STATE_LABELS, STATE_LOBBY, STATE_LOGIN, STATE_MATCH, LogEvent, LogWatcher
from .vision import (
    GameWindow,
    ScreenCaptureError,
    ScreenGrabber,
    TokenDetector,
    find_game_window,
    imwrite_u,
)

_log = logging.getLogger("piratebot")


class Phase(StrEnum):
    STARTING = "starting"
    LOBBY = "lobby"
    QUEUING = "queuing"
    MATCH = "match"
    POSTMATCH = "postmatch"
    FINISHED = "finished"
    ERROR = "error"
    STOPPED = "stopped"


PHASE_LABELS = {
    Phase.STARTING: "Iniciando",
    Phase.LOBBY: "No lobby",
    Phase.QUEUING: "Procurando partida",
    Phase.MATCH: "Em partida (AFK)",
    Phase.POSTMATCH: "Fim de partida",
    Phase.FINISHED: "Token encontrado!",
    Phase.ERROR: "Erro",
    Phase.STOPPED: "Parado",
}


class BotError(RuntimeError):
    pass


class PirateBot:
    def __init__(
        self,
        config: AppConfig,
        ui_queue: "queue.Queue[dict]",
        stop_event: threading.Event,
        manual_token_event: threading.Event,
    ) -> None:
        self.config = config
        self.ui_queue = ui_queue
        self.stop_event = stop_event
        self.manual_token_event = manual_token_event

        self.phase = Phase.STARTING
        self.message = "Iniciando..."
        self.matches = 0
        self.token_found = False
        self.started_at = time.time()

        self._thread: Optional[threading.Thread] = None
        self._window: Optional[GameWindow] = None
        self._grabber: Optional[ScreenGrabber] = None
        self._controller: Optional[GameController] = None
        self._detector: Optional[TokenDetector] = None
        self._watcher: Optional[LogWatcher] = None
        self._events: "queue.Queue[LogEvent]" = queue.Queue()

        self._last_state = "unknown"
        self._counted_match = False
        self._match_started_at = 0.0
        self._endgame_at = 0.0
        self._queued_at = 0.0
        self._lobby_ready_at = 0.0
        self._starting_deadline = 0.0
        self._next_visual_check = 0.0
        self._next_scan_at = 0.0
        self._last_focus_at = 0.0
        self._last_status_at = 0.0
        self._last_suspend_check = 0.0
        self._last_queuing_check = 0.0
        self._last_play_click = 0.0
        self._last_match_report = 0.0
        self._last_capture_error = 0.0
        self._last_visual_lobby_check = 0.0
        self._last_postmatch_snapshot_at = 0.0
        self._postmatch_snapshots = 0
        self._suspend_counter = 0
        self._pressed_enter_at = 0.0
        self._pressed_space_at = 0.0
        self._clicked_postmatch_at = 0.0
        self._claim_attempted = False

    # ------------------------------------------------------------------ API
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.started_at = time.time()
        self._thread = threading.Thread(target=self._run, name="PirateBot", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self._thread and self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=3.0)

    def is_running(self) -> bool:
        return bool(
            self._thread
            and self._thread.is_alive()
            and not self.stop_event.is_set()
        )

    # -------------------------------------------------------------- execução
    def _run(self) -> None:
        try:
            self._setup()
            self._main_loop()
        except BotError as exc:
            self._fail(str(exc))
        except Exception as exc:
            self._fail(f"Erro inesperado: {exc}", exc)
        finally:
            self._cleanup()

    def _setup(self) -> None:
        self._emit_log("Procurando a janela do Fortnite...")
        self._window = find_game_window(self.config.game.window_title)
        self._emit_log(
            f"Janela encontrada: {self._window.width}x{self._window.height} "
            f"em ({self._window.client_x}, {self._window.client_y})."
        )

        self._detector = TokenDetector(ASSETS, self.config.detection)
        self._grabber = ScreenGrabber(self._window)
        self._controller = GameController(
            self._window,
            self.config,
            dry_run=self.config.behavior.dry_run,
            logger=self._emit_log,
        )

        self._watcher = LogWatcher(
            self.config.game.log_path,
            self._events,
            self.stop_event,
            logger=self._emit_log,
        )
        initial = self._watcher.prepare()
        self._watcher.start()
        self._last_state = initial
        self._emit_log(
            f"Log conectado. Estado atual: {STATE_LABELS.get(initial, initial)}."
        )

        self._starting_deadline = time.time() + 90.0
        self._next_visual_check = time.time() + 1.0
        self._last_focus_at = time.time()

        if not self.config.behavior.dry_run:
            power.set_awake("bot", True)
            self._emit_log(
                "Suspensão automática do Windows desativada durante a execução.",
                "info",
            )
            if self.config.behavior.background_mode:
                self._emit_log(
                    "Modo segundo plano ativo: captura sem roubar o foco e foco rápido "
                    "de ~1s apenas para clicar. Não minimize o Fortnite.",
                    "info",
                )
            self._resume_if_suspended(force_focus=True)

        if self.config.behavior.dry_run:
            self._emit_log(
                "MODO SIMULAÇÃO ativo: o bot não clica nem pressiona teclas. "
                "Inicie a partida manualmente para testar a detecção.",
                "warn",
            )

    def _main_loop(self) -> None:
        self._emit_status()
        time.sleep(0.4)
        self._drain_events()

        if self.phase == Phase.STARTING:
            if self._last_state == STATE_LOBBY:
                self._enter_lobby("estado inicial")
            elif self._last_state == STATE_MATCH:
                self._enter_match("estado inicial")
            else:
                self.message = "Procurando o lobby do Fortnite..."
                self._emit_status()

        while not self.stop_event.is_set():
            self._drain_events()
            if self.stop_event.is_set():
                break

            if self.manual_token_event.is_set() and not self.token_found:
                self._set_token_found("marcado manualmente")
                if self.phase in (Phase.LOBBY, Phase.STARTING, Phase.QUEUING):
                    self._finish_success("Token marcado manualmente no lobby.")
                    break

            now = time.time()
            if self.config.behavior.max_runtime_minutes > 0:
                limit = self.config.behavior.max_runtime_minutes * 60
                if now - self.started_at > limit:
                    self._stop_with_message("Limite de tempo de execução atingido.")
                    break

            if self.phase == Phase.STARTING:
                self._do_starting(now)
            elif self.phase == Phase.LOBBY:
                self._do_lobby(now)
            elif self.phase == Phase.QUEUING:
                self._do_queuing(now)
            elif self.phase == Phase.MATCH:
                self._do_match(now)
            elif self.phase == Phase.POSTMATCH:
                self._do_postmatch(now)
            elif self.phase in (Phase.FINISHED, Phase.ERROR, Phase.STOPPED):
                break

            if now - self._last_status_at >= 0.5:
                self._last_status_at = now
                self._emit_status()
            time.sleep(0.08)

    # --------------------------------------------------------------- eventos
    def _drain_events(self) -> None:
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                return
            self._handle_event(event)

    def _handle_event(self, event: LogEvent) -> None:
        if event.kind == "log_reset":
            self._fail(
                "O log do Fortnite foi reiniciado (o jogo pode ter fechado). "
                "Reinicie o bot quando o jogo estiver no lobby."
            )
            return

        if event.kind == "state":
            if event.value == STATE_LOBBY:
                self._last_state = STATE_LOBBY
                if self.phase in (Phase.MATCH, Phase.POSTMATCH, Phase.QUEUING):
                    self._returned_to_lobby()
                elif self.phase in (Phase.STARTING, Phase.LOBBY):
                    self._enter_lobby("evento do log")
            elif event.value == STATE_MATCH:
                self._last_state = STATE_MATCH
                if self.phase == Phase.POSTMATCH:
                    self._emit_log(
                        "O jogo voltou para uma partida; continuando AFK.",
                        "warn",
                    )
                    self.phase = Phase.MATCH
                    self._next_scan_at = time.time() + 1.0
                elif self.phase != Phase.MATCH:
                    if self.phase in (Phase.STARTING, Phase.LOBBY, Phase.QUEUING):
                        self._enter_match("evento do log")
            elif event.value == STATE_LOGIN:
                if self.phase == Phase.STARTING:
                    self._emit_log(
                        "O jogo está na tela de login. Entre na conta para o bot poder jogar.",
                        "warn",
                    )
            return

        if event.kind == "phase":
            if event.value == "EndGame" and self.phase == Phase.MATCH:
                self._enter_postmatch("fase EndGame")
            return

        if event.kind == "postmatch":
            if self.phase == Phase.MATCH:
                self._enter_postmatch("widget pós-partida")
            return

        if event.kind == "matchstate":
            if event.value in ("WaitingPostMatch", "LeavingMap") and self.phase == Phase.MATCH:
                self._enter_postmatch(f"MatchState {event.value}")
            return

        if event.kind == "player_died":
            if self.phase == Phase.MATCH:
                self._emit_log(
                    "Seu personagem morreu. Continuo AFK; o esquadrão ainda pode achar o token.",
                    "info",
                )
            return

        if event.kind == "readyup":
            return

    # --------------------------------------------------------------- estados
    def _enter_lobby(self, reason: str = "") -> None:
        if self.phase == Phase.LOBBY:
            return
        self.phase = Phase.LOBBY
        self._counted_match = False
        self._lobby_ready_at = time.time() + self.config.behavior.ready_delay
        self.message = "No lobby. Vou clicar em JOGAR..."
        suffix = f" ({reason})" if reason else ""
        self._emit_log(f"Lobby detectado{suffix}. Preparando para jogar.", "info")
        self._emit_status()

    def _enter_match(self, reason: str = "") -> None:
        if self.phase == Phase.MATCH:
            return
        self.phase = Phase.MATCH
        if not self._counted_match:
            self.matches += 1
            self._counted_match = True
        self._match_started_at = time.time()
        self._next_scan_at = time.time() + 1.5
        self._endgame_at = 0.0
        self._pressed_enter_at = 0.0
        self._pressed_space_at = 0.0
        self._clicked_postmatch_at = 0.0
        self._claim_attempted = False
        self._last_match_report = time.time()
        self._suspend_counter = 0
        suffix = f" ({reason})" if reason else ""
        self.message = "Partida em andamento — AFK."
        self._emit_log(
            f"Partida iniciada ({self.matches}){suffix}. AFK ativado; procurando o token.",
            "success",
        )
        self._emit_status()

    def _returned_to_lobby(self) -> None:
        self._counted_match = False
        self._endgame_at = 0.0
        self._pressed_enter_at = 0.0
        self._pressed_space_at = 0.0
        self._clicked_postmatch_at = 0.0
        if self.token_found or self.manual_token_event.is_set():
            if self.token_found and not self.manual_token_event.is_set():
                self._claim_reward_if_visible()
                if self.stop_event.is_set():
                    return
            self._finish_success("Token encontrado e de volta ao lobby.")
            return
        if (
            self.config.behavior.max_matches > 0
            and self.matches >= self.config.behavior.max_matches
        ):
            self._stop_with_message(
                f"Limite de {self.matches} partida(s) atingido. "
                "O token não apareceu; aumente max_matches no config.json se quiser continuar."
            )
            return
        self.phase = Phase.LOBBY
        self._lobby_ready_at = time.time() + self.config.behavior.ready_delay
        self.message = "De volta ao lobby. Preparando a próxima partida..."
        self._emit_log(
            "De volta ao lobby. Vou iniciar outra partida para continuar procurando.",
            "info",
        )
        self._emit_status()

    def _enter_postmatch(self, reason: str = "") -> None:
        if self.phase != Phase.MATCH:
            return
        self.phase = Phase.POSTMATCH
        self._endgame_at = time.time()
        self._pressed_enter_at = 0.0
        self._pressed_space_at = 0.0
        self._clicked_postmatch_at = 0.0
        self._postmatch_snapshots = 0
        self._last_postmatch_snapshot_at = 0.0
        self._next_scan_at = time.time() + 0.5
        self._last_visual_lobby_check = 0.0
        self.message = "Fim da partida — verificando recompensas..."
        suffix = f" ({reason})" if reason else ""
        self._emit_log(f"Fim da partida detectado{suffix}. Verificando recompensas.", "info")
        self._emit_status()

    def _do_starting(self, now: float) -> None:
        if now < self._next_visual_check:
            return
        self._next_visual_check = now + 3.0
        if self._visual_lobby_check():
            self._enter_lobby("lobby detectado pela tela")
            return
        if now > self._starting_deadline:
            self._fail(
                "Não encontrei o lobby do Fortnite. Abra o jogo na tela JOGAR "
                "e clique em INICIAR novamente."
            )

    def _do_lobby(self, now: float) -> None:
        if now < self._lobby_ready_at:
            return
        if (
            self.config.behavior.max_matches > 0
            and self.matches >= self.config.behavior.max_matches
        ):
            self._stop_with_message(f"Limite de {self.matches} partida(s) atingido.")
            return

        # Se uma tela de recompensa do token estiver aberta no lobby (por
        # exemplo, o bot foi iniciado depois de uma partida premiada), não
        # entre em outra partida: resgate e encerre.
        if not self.token_found:
            frame = self._capture("lobby", log_errors=False)
            if frame is not None and self._detector is not None:
                detection = self._detector.detect(frame)
                if detection.found and detection.best is not None:
                    best = detection.best
                    self._set_token_found(
                        f"tela de recompensa no lobby (confiança {best.score:.2f})"
                    )
                    self._save_snapshot(frame, "token_lobby")
                    if not self.config.behavior.dry_run:
                        self._claim_reward_if_visible(frame)
                        if self.stop_event.is_set():
                            return
                    self._finish_success("Token encontrado no lobby.")
                    return

        if self.config.behavior.dry_run:
            self._emit_log(
                "SIMULAÇÃO: eu clicaria em JOGAR agora. "
                "Inicie uma partida manualmente para testar a detecção.",
                "warn",
            )
            self.phase = Phase.QUEUING
            self._queued_at = time.time()
            self._last_play_click = self._queued_at
            self.message = "Simulação: aguardando você iniciar a partida..."
            self._emit_status()
            return

        self._click_play()

    def _click_play(self) -> None:
        assert self._controller is not None
        assert self._grabber is not None
        assert self._detector is not None

        background = self.config.behavior.background_mode
        if self._resume_if_suspended(force_focus=not background):
            time.sleep(0.8)

        if not background:
            if not self._controller.ensure_foreground(force=True):
                self._emit_log("Não consegui focar o Fortnite; tentarei de novo em 5s.", "warn")
                self._lobby_ready_at = time.time() + 5.0
                return

        time.sleep(0.1 if background else 0.4)
        frame = self._capture("lobby")
        hit = self._detector.find_play_button(frame) if frame is not None else None

        if hit is None:
            self._emit_log(
                "Botão JOGAR não localizado; clicando na aba JOGAR e tentando novamente.",
                "warn",
            )
            self._controller.click_ref(*self.config.ui.play_tab)
            time.sleep(1.2)
            frame = self._capture("lobby")
            hit = self._detector.find_play_button(frame) if frame is not None else None

        if hit is not None:
            self._emit_log(f"Clicando em JOGAR (confiança {hit.score:.2f}).", "info")
            clicked = self._controller.click_client(hit.center[0], hit.center[1])
        else:
            self._emit_log("Usando a coordenada calibrada do botão JOGAR.", "warn")
            clicked = self._controller.click_ref(*self.config.ui.play_button)

        if not clicked:
            self._emit_log("O clique não foi confirmado; tentarei de novo em 5s.", "warn")
            self._lobby_ready_at = time.time() + 5.0
            return

        self.phase = Phase.QUEUING
        self._queued_at = time.time()
        self._last_play_click = self._queued_at
        self.message = "Procurando partida..."
        self._emit_status()

    def _do_queuing(self, now: float) -> None:
        if now - self._last_suspend_check > 8.0:
            self._last_suspend_check = now
            if self._resume_if_suspended():
                return

        if self.config.behavior.dry_run:
            if now - self._queued_at > self.config.behavior.matchmaking_timeout:
                self._emit_log(
                    "Simulação: tempo de matchmaking esgotado; eu tentaria novamente.",
                    "warn",
                )
                self._queued_at = now
            return

        if now - self._queued_at > self.config.behavior.matchmaking_timeout:
            self._emit_log("Tempo de matchmaking esgotado; voltando a tentar do lobby.", "warn")
            self.phase = Phase.LOBBY
            self._lobby_ready_at = now + 2.0
            self._queued_at = 0.0
            self._emit_status()
            return

        if now - self._last_play_click > 12.0 and now - self._last_queuing_check > 6.0:
            self._last_queuing_check = now
            frame = self._capture("matchmaking", log_errors=False)
            if frame is not None and self._detector is not None:
                hit = self._detector.find_play_button(frame)
                if hit is not None:
                    self._emit_log(
                        "Ainda estou no lobby; o clique pode não ter registrado. "
                        "Clicando em JOGAR novamente.",
                        "warn",
                    )
                    if self._controller is not None and self._controller.click_client(
                        hit.center[0], hit.center[1]
                    ):
                        self._last_play_click = now

    def _do_match(self, now: float) -> None:
        if now >= self._next_scan_at:
            interval = 3.0 if self.token_found else self.config.behavior.scan_interval_match
            self._next_scan_at = now + interval
            frame = self._capture("partida", log_errors=False)
            if frame is not None and self._detector is not None:
                self._suspend_counter += 1
                if self._suspend_counter % 3 == 0:
                    suspend_hit = self._detector.find_suspend_button(frame)
                    if suspend_hit is not None:
                        self._emit_log(
                            "Tela de suspensão na partida. Clicando em CONTINUAR JOGANDO.",
                            "warn",
                        )
                        self._save_snapshot(frame, "suspensao")
                        if self._controller is not None:
                            self._controller.click_client(
                                suspend_hit.center[0], suspend_hit.center[1]
                            )
                        self._next_scan_at = time.time() + 2.0
                        return

                if not self.token_found:
                    detection = self._detector.detect(frame)
                    if detection.found and detection.best is not None:
                        best = detection.best
                        self._set_token_found(
                            f"banner na partida (confiança {best.score:.2f}, {best.w}x{best.h})"
                        )
                        self._save_snapshot(frame, "token_banner")

                # Se o evento de fim de partida passar despercebido, o botão
                # JOGAR na tela indica que já estamos de volta ao lobby.
                if self._suspend_counter % 6 == 0:
                    play_hit = self._detector.find_play_button(frame)
                    if play_hit is not None:
                        self._emit_log(
                            "Lobby detectado pela tela durante a partida. "
                            "Voltando para o ciclo de lobby.",
                            "warn",
                        )
                        self._returned_to_lobby()
                        return

            if now - self._last_match_report > 300.0:
                self._last_match_report = now
                minutes = int((now - self._match_started_at) / 60)
                self._emit_log(
                    f"Partida em andamento há {minutes} min. Continuo AFK.",
                    "info",
                )

        if (
            not self.config.behavior.background_mode
            and now - self._last_focus_at > self.config.behavior.focus_interval
        ):
            self._last_focus_at = now
            if self._controller is not None:
                self._controller.focus_if_needed()

    def _do_postmatch(self, now: float) -> None:
        elapsed = now - self._endgame_at

        if now >= self._next_scan_at:
            self._next_scan_at = now + self.config.behavior.scan_interval_postmatch
            frame = self._capture("pós-partida", log_errors=False)
            if frame is not None and self._detector is not None:
                self._suspend_counter += 1
                if self._suspend_counter % 4 == 0:
                    suspend_hit = self._detector.find_suspend_button(frame)
                    if suspend_hit is not None:
                        self._emit_log(
                            "Tela de suspensão no pós-partida. Clicando em CONTINUAR JOGANDO.",
                            "warn",
                        )
                        self._save_snapshot(frame, "suspensao")
                        if self._controller is not None:
                            self._controller.click_client(
                                suspend_hit.center[0], suspend_hit.center[1]
                            )
                        return

                if not self.token_found:
                    detection = self._detector.detect(frame)
                    if detection.found and detection.best is not None:
                        best = detection.best
                        self._set_token_found(
                            f"tela de recompensa (confiança {best.score:.2f}, {best.w}x{best.h})"
                        )
                        self._save_snapshot(frame, "token_recompensa")

                if now - self._last_visual_lobby_check > 4.0:
                    self._last_visual_lobby_check = now
                    play_hit = self._detector.find_play_button(frame)
                    if play_hit is not None:
                        self._emit_log(
                            "Lobby detectado pela tela (sem evento no log). Seguindo.",
                            "warn",
                        )
                        self._returned_to_lobby()
                        return

                if (
                    self._postmatch_snapshots < 6
                    and now - self._last_postmatch_snapshot_at >= 4.0
                ):
                    self._last_postmatch_snapshot_at = now
                    self._postmatch_snapshots += 1
                    self._save_snapshot(
                        frame,
                        f"pos_partida_{self._postmatch_snapshots}",
                        log=False,
                    )

        if self.config.behavior.dry_run:
            if elapsed > self.config.behavior.postmatch_timeout:
                self._fail(
                    "Não consegui voltar ao lobby após a partida. "
                    "Verifique a tela do jogo e inicie o bot novamente."
                )
            return

        click_after = (
            self.config.behavior.postmatch_click_after
            if not self.token_found
            else 90.0
        )

        if elapsed > self.config.behavior.postmatch_enter_after and self._pressed_enter_at == 0.0:
            self._emit_log("Pressionando ENTER para avançar a tela de recompensas.", "info")
            if self._controller is not None:
                self._controller.press_enter()
            self._pressed_enter_at = now
        elif elapsed > self.config.behavior.postmatch_space_after and self._pressed_space_at == 0.0:
            self._emit_log("Pressionando ESPAÇO para avançar a tela pós-partida.", "info")
            if self._controller is not None:
                self._controller.press_space()
            self._pressed_space_at = now
        elif elapsed > click_after and self._clicked_postmatch_at == 0.0:
            self._emit_log(
                "Ainda na tela pós-partida; clicando em continuar (coordenada calibrada).",
                "warn",
            )
            if self._controller is not None:
                self._controller.click_ref(*self.config.ui.postmatch_safe_click)
            self._clicked_postmatch_at = now
        elif (
            elapsed > 75.0
            and now - self._pressed_enter_at > 20.0
            and now - self._clicked_postmatch_at > 20.0
        ):
            self._emit_log("Repetindo ENTER para sair da tela pós-partida.", "warn")
            if self._controller is not None:
                self._controller.press_enter()
            self._pressed_enter_at = now

        if elapsed > self.config.behavior.postmatch_timeout:
            self._fail(
                "Não consegui voltar ao lobby após a partida. "
                "Verifique a tela do jogo e inicie o bot novamente."
            )

    # ------------------------------------------------------------- utilidades
    def _claim_reward_if_visible(self, first_frame=None) -> None:
        """Procura a tela de recompensa no lobby e clica em CLAIM ALL."""
        if self._claim_attempted:
            return
        self._claim_attempted = True

        if self.config.behavior.dry_run:
            self._emit_log(
                "SIMULAÇÃO: procuraria a tela de recompensa e clicaria em CLAIM ALL.",
                "warn",
            )
            return

        self._emit_log(
            "Procurando a tela de recompensa do token para resgatar...", "info"
        )
        deadline = time.time() + self.config.behavior.claim_timeout
        frame = first_frame
        while not self.stop_event.is_set() and time.time() < deadline:
            if frame is None:
                frame = self._capture("recompensa", log_errors=False)
            if frame is not None and self._detector is not None:
                detection = self._detector.detect(frame)
                if detection.found:
                    self._save_snapshot(frame, "tela_recompensa")
                    self._emit_log(
                        "Tela de recompensa detectada. Clicando em CLAIM ALL.",
                        "success",
                    )
                    if self._controller is not None:
                        self._controller.click_ref(*self.config.ui.claim_button)
                    time.sleep(1.2)

                    extra = self._capture("recompensa", log_errors=False)
                    if (
                        extra is not None
                        and self._detector is not None
                        and self._detector.detect(extra).found
                    ):
                        self._emit_log(
                            "A tela de recompensa ainda está aberta; "
                            "tentando novamente.",
                            "warn",
                        )
                        if self._controller is not None:
                            self._controller.press_enter()
                            time.sleep(0.5)
                            self._controller.click_ref(*self.config.ui.claim_button)
                    return
            frame = None
            time.sleep(self.config.behavior.claim_scan_interval)

        self._emit_log(
            "Tela de recompensa não encontrada. O prêmio é aplicado à conta "
            "automaticamente; encerrando.",
            "info",
        )

    def _set_token_found(self, reason: str) -> None:
        if self.token_found:
            return
        self.token_found = True
        self.message = "TOKEN ENCONTRADO! Aguardando o fim da partida."
        self._emit_log("=" * 64, "success")
        self._emit_log(f"TOKEN PIRATA DETECTADO! ({reason})", "success")
        self._emit_log(
            "Vou continuar AFK até a partida terminar e então encerrar o programa.",
            "success",
        )
        self._emit_log("=" * 64, "success")
        self._emit_status()
        self._beep_token()
        self.ui_queue.put({"type": "token", "text": "Token detectado!"})

    def _finish_success(self, message: str) -> None:
        if self.phase == Phase.FINISHED:
            return
        self.phase = Phase.FINISHED
        self.message = "TOKEN ENCONTRADO!"
        self._emit_status()
        self._beep_success()
        self.ui_queue.put(
            {
                "type": "success",
                "text": f"{message} Você já pode acessar a Loja Pirata.",
            }
        )
        self.stop_event.set()

    def _stop_with_message(self, message: str) -> None:
        self.phase = Phase.STOPPED
        self.message = message
        self._emit_log(message, "warn")
        self._emit_status()
        self.ui_queue.put({"type": "stopped", "text": message})
        self.stop_event.set()

    def _fail(self, message: str, exception: Optional[BaseException] = None) -> None:
        if self.phase == Phase.ERROR:
            return
        self.phase = Phase.ERROR
        self.message = message
        self._emit_log(message, "error")
        if exception is not None:
            self._emit_log(traceback.format_exc(), "debug")
        self._emit_status()
        self.ui_queue.put({"type": "error", "text": message})
        self.stop_event.set()

    def _cleanup(self) -> None:
        self.stop_event.set()
        power.set_awake("bot", False)
        if self._watcher is not None:
            try:
                self._watcher.join(timeout=1.5)
            except Exception:
                pass
        if self.phase not in (Phase.FINISHED, Phase.ERROR, Phase.STOPPED):
            self._emit_log("Bot encerrado.", "info")

    def _capture(self, label: str, log_errors: bool = True) -> Optional[object]:
        if self._grabber is None or self._controller is None:
            return None

        if self.config.behavior.background_mode:
            try:
                return self._grabber.capture_background()
            except ScreenCaptureError as exc:
                now = time.time()
                if log_errors and now - self._last_capture_error >= 10.0:
                    self._last_capture_error = now
                    self._emit_log(
                        f"Falha na captura em segundo plano ({label}): {exc}",
                        "warn",
                    )
                return None

        if not self._grabber.is_foreground():
            if self.config.behavior.dry_run:
                if log_errors:
                    self._emit_log(
                        f"[{label}] O Fortnite não está em primeiro plano; captura ignorada.",
                        "debug",
                    )
                return None
            if self._controller.is_own_process_foreground():
                return None
            if not self._controller.focus_if_needed():
                if log_errors:
                    self._emit_log(
                        f"[{label}] Não consegui focar o jogo para capturar a tela.",
                        "warn",
                    )
                return None
        try:
            return self._grabber.capture()
        except ScreenCaptureError as exc:
            now = time.time()
            if log_errors and now - self._last_capture_error >= 10.0:
                self._last_capture_error = now
                self._emit_log(f"Falha na captura ({label}): {exc}", "warn")
            return None

    def _visual_lobby_check(self) -> bool:
        frame = self._capture("lobby", log_errors=False)
        if frame is None or self._detector is None:
            return False
        return self._detector.find_play_button(frame) is not None

    def _resume_if_suspended(self, force_focus: bool = False) -> bool:
        if (
            self._grabber is None
            or self._controller is None
            or self._detector is None
        ):
            return False
        if self.config.behavior.dry_run:
            return False
        if self.config.behavior.background_mode:
            frame = self._capture("suspensão", log_errors=False)
            if frame is None:
                return False
        else:
            if not self._grabber.is_foreground():
                if self._controller.is_own_process_foreground() and not force_focus:
                    return False
                if not self._controller.ensure_foreground(force=force_focus):
                    return False
                time.sleep(0.35)
            try:
                frame = self._grabber.capture()
            except ScreenCaptureError:
                return False
        hit = self._detector.find_suspend_button(frame)
        if hit is None:
            return False
        self._emit_log(
            "Tela de suspensão detectada. Clicando em CONTINUAR JOGANDO.",
            "warn",
        )
        self._save_snapshot(frame, "suspensao")
        self._controller.click_client(hit.center[0], hit.center[1])
        time.sleep(1.5)
        return True

    def _save_snapshot(self, frame, prefix: str, log: bool = True) -> None:
        try:
            folder = LOGS / "snapshots"
            folder.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            path = folder / f"{prefix}_{stamp}.png"
            counter = 1
            while path.exists():
                path = folder / f"{prefix}_{stamp}_{counter}.png"
                counter += 1
            if imwrite_u(path, frame):
                if log:
                    self._emit_log(f"Captura salva em {path}.", "debug")
        except Exception as exc:
            if log:
                self._emit_log(f"Falha ao salvar captura: {exc}", "debug")

    def _emit_log(self, text: str, level: str = "info") -> None:
        level_map = {
            "debug": logging.DEBUG,
            "info": logging.INFO,
            "success": logging.INFO,
            "warn": logging.WARNING,
            "error": logging.ERROR,
        }
        _log.log(level_map.get(level, logging.INFO), text)
        self.ui_queue.put(
            {
                "type": "log",
                "text": text,
                "level": level,
                "ts": time.time(),
            }
        )

    def _emit_status(self) -> None:
        self.ui_queue.put(
            {
                "type": "status",
                "phase": self.phase.value,
                "message": self.message,
                "matches": self.matches,
                "token_found": self.token_found,
                "elapsed": time.time() - self.started_at,
            }
        )

    def _beep_token(self) -> None:
        try:
            import winsound

            winsound.Beep(1200, 180)
            winsound.Beep(1600, 180)
            winsound.Beep(2000, 320)
        except Exception:
            pass

    def _beep_success(self) -> None:
        try:
            import winsound

            for frequency in (880, 1175, 1568, 2093):
                winsound.Beep(frequency, 220)
        except Exception:
            pass
