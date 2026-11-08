"""Testes offline do Pirate Farm.

Uso:
    .venv\\Scripts\\python.exe selftest.py
    .venv\\Scripts\\python.exe selftest.py --live
"""
from __future__ import annotations

import queue
import sys
import tempfile
import threading
import time
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from piratebot import power
from piratebot.bot import Phase, PirateBot
from piratebot.config import (
    ASSETS,
    LOGS,
    RewardConfig,
    StorageConfig,
    WebhookConfig,
    load_config,
    save_config,
)
from piratebot.logwatcher import LogEvent, LogWatcher, parse_line, player_key
from piratebot.retention import prune_snapshots
from piratebot.rewards import (
    TOKEN_NAME,
    ChestPrecue,
    RewardEvent,
    RewardGate,
    RewardScanner,
    banner_score,
    parse_reward_text,
    reward_badge_score,
)
from piratebot.squad import SquadTracker
from piratebot.vision import TokenDetector, imread_u, imwrite_u
from piratebot.webhook import (
    WebhookMessage,
    build_payload,
    mask_webhook_url,
    send_message,
    send_test,
)
from tools.check_docs import check_file
from tools.check_postmatch import inspect_frame

TEST_ASSETS = ASSETS / "test"

POSITIVE_IMAGES = [
    "token_frvr.jpg",
    "token_frvr2.jpg",
    "token_biglead.jpg",
    "banner_timesaver.jpg",
]
NEGATIVE_IMAGES = [
    "game_after_resume.png",
    "game_focused.png",
    "fortnite_now.png",
    "postmatch_elemental_icon.png",
]

results: list[tuple[bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((bool(condition), name))
    status = "OK  " if condition else "FALHA"
    suffix = f" — {detail}" if detail else ""
    print(f"[{status}] {name}{suffix}")


class RecordingController:
    """Controlador falso para testar cliques sem tocar no jogo."""

    def __init__(self) -> None:
        self.clicks: list[tuple[int, int]] = []
        self.enter = 0
        self.space = 0
        self.escapes = 0

    def click_client(self, x: int, y: int) -> bool:
        self.clicks.append((int(x), int(y)))
        return True

    def click_ref(self, x: int, y: int) -> bool:
        self.clicks.append((int(x), int(y)))
        return True

    def press_enter(self) -> bool:
        self.enter += 1
        return True

    def press_space(self) -> bool:
        self.space += 1
        return True

    def press_escape(self) -> bool:
        self.escapes += 1
        return True

    def focus_if_needed(self) -> bool:
        return True

    def ensure_foreground(self, force: bool = False) -> bool:
        return True


def main() -> int:
    print("Pirate Farm — autoteste")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Projeto: {Path(__file__).resolve().parent}")
    print()

    config = load_config()
    print(f"Log do Fortnite: {config.game.log_path}")
    print(f"Resolução de referência: {config.game.ref_width}x{config.game.ref_height}")
    print()

    try:
        detector = TokenDetector(ASSETS, config.detection)
        check("Templates carregados", True)
    except Exception as exc:
        check("Templates carregados", False, str(exc))
        return 1

    print()
    print("Detecção do token (imagens de referência):")
    for name in POSITIVE_IMAGES:
        path = TEST_ASSETS / name
        image = imread_u(path)
        if image is None:
            check(f"Imagem {name}", False, "não encontrada")
            continue
        started = time.perf_counter()
        detection = detector.detect(image)
        elapsed = (time.perf_counter() - started) * 1000
        best = detection.best
        detail = (
            f"{best.kind} score={best.score:.2f} {best.w}x{best.h} "
            f"({elapsed:.0f} ms)"
            if best
            else f"nenhum match ({elapsed:.0f} ms)"
        )
        check(f"Token em {name}", detection.found, detail)

    print()
    print("Falsos positivos (devem ficar limpos):")
    for name in NEGATIVE_IMAGES:
        path = TEST_ASSETS / name
        if not path.exists():
            # A captura do desktop é local e não entra no repositório.
            print(f"[IGNORADO] Imagem {name} não está no repositório.")
            continue
        image = imread_u(path)
        if image is None:
            check(f"Imagem {name}", False, "não encontrada")
            continue
        started = time.perf_counter()
        detection = detector.detect(image)
        elapsed = (time.perf_counter() - started) * 1000
        best = detection.best
        detail = (
            f"falso positivo: {best.kind} score={best.score:.2f} "
            f"em ({best.x},{best.y})"
            if best
            else f"limpo ({elapsed:.0f} ms)"
        )
        check(f"Sem token em {name}", not detection.found, detail)

    print()
    print("Botões:")
    lobby = imread_u(TEST_ASSETS / "game_after_resume.png")
    suspended = imread_u(TEST_ASSETS / "game_focused.png")
    desktop = imread_u(TEST_ASSETS / "fortnite_now.png")

    if lobby is not None:
        hit = detector.find_play_button(lobby)
        check(
            "Botão JOGAR no lobby",
            hit is not None,
            f"score={hit.score:.2f} em ({hit.x},{hit.y})" if hit else "não encontrado",
        )
    else:
        check("Botão JOGAR no lobby", False, "imagem não encontrada")

    if suspended is not None:
        hit = detector.find_suspend_button(suspended)
        check(
            "Botão CONTINUAR JOGANDO na suspensão",
            hit is not None,
            f"score={hit.score:.2f}" if hit else "não encontrado",
        )
    else:
        check("Botão CONTINUAR JOGANDO na suspensão", False, "imagem não encontrada")

    if lobby is not None:
        hit = detector.find_suspend_button(lobby)
        check(
            "Sem falso positivo de suspensão no lobby",
            hit is None,
            f"score={hit.score:.2f}" if hit else "limpo",
        )
    if desktop is not None:
        hit = detector.find_play_button(desktop)
        check(
            "Sem falso positivo de JOGAR no desktop",
            hit is None,
            f"score={hit.score:.2f}" if hit else "limpo",
        )

    print()
    print("Menu de saída (seta no canto superior direito):")
    if detector.exit_icon is None:
        check("Template da seta de saída", False, "assets/exit_icon.png não encontrado")
    else:
        import numpy as np

        icon = detector.exit_icon
        canvas = np.zeros((1080, 1920, 3), dtype=np.uint8)
        x, y = 1660, 50
        canvas[y : y + icon.shape[0], x : x + icon.shape[1]] = icon
        hit = detector.find_exit_button(canvas)
        check(
            "Seta de saída em tela sintética",
            hit is not None
            and abs(hit.x - x) <= 2
            and abs(hit.y - y) <= 2,
            f"score={hit.score:.2f} em ({hit.x},{hit.y})" if hit else "não encontrada",
        )

        for name, image in (
            ("lobby", lobby),
            ("suspensão", suspended),
            ("desktop", desktop),
        ):
            if image is None:
                continue
            hit = detector.find_exit_button(image)
            check(
                f"Sem falso positivo da seta no {name}",
                hit is None,
                f"score={hit.score:.2f} em ({hit.x},{hit.y})" if hit else "limpo",
            )

    print()
    print("Botão de retorno ao lobby (tela de resumo):")
    if detector.return_lobby is None:
        check(
            "Template RETORNAR AO LOBBY",
            False,
            "assets/return_lobby.png não encontrado",
        )
    else:
        import numpy as np

        template = detector.return_lobby
        canvas = np.zeros((1080, 1920, 3), dtype=np.uint8)
        x, y = 1338, 414
        canvas[y : y + template.shape[0], x : x + template.shape[1]] = template
        hit = detector.find_return_lobby_button(canvas)
        check(
            "Botão RETORNAR AO LOBBY em tela sintética",
            hit is not None
            and abs(hit.x - x) <= 2
            and abs(hit.y - y) <= 2,
            f"score={hit.score:.2f} em ({hit.x},{hit.y})" if hit else "não encontrado",
        )
        for name, image in (
            ("lobby", lobby),
            ("suspensão", suspended),
            ("desktop", desktop),
        ):
            if image is None:
                continue
            hit = detector.find_return_lobby_button(image)
            check(
                f"Sem falso positivo do retorno no {name}",
                hit is None,
                f"score={hit.score:.2f} em ({hit.x},{hit.y})" if hit else "limpo",
            )

    print()
    print("Botão JOGAR NOVAMENTE (tela de resumo):")
    if detector.play_again is None:
        check(
            "Template JOGAR NOVAMENTE",
            False,
            "assets/play_again.png não encontrado",
        )
    else:
        template = detector.play_again
        canvas = np.zeros((1080, 1920, 3), dtype=np.uint8)
        x, y = 1338, 502
        canvas[y : y + template.shape[0], x : x + template.shape[1]] = template
        hit = detector.find_play_again_button(canvas)
        check(
            "Botão JOGAR NOVAMENTE em tela sintética",
            hit is not None
            and abs(hit.x - x) <= 2
            and abs(hit.y - y) <= 2,
            f"score={hit.score:.2f} em ({hit.x},{hit.y})" if hit else "não encontrado",
        )
        for name, image in (
            ("lobby", lobby),
            ("suspensão", suspended),
            ("desktop", desktop),
        ):
            if image is None:
                continue
            hit = detector.find_play_again_button(image)
            check(
                f"Sem falso positivo do JOGAR NOVAMENTE no {name}",
                hit is None,
                f"score={hit.score:.2f} em ({hit.x},{hit.y})" if hit else "limpo",
            )

    print()
    print("Botão Voltar ao Lobby (menu de pausa novo):")
    if detector.voltar_lobby is None:
        check(
            "Template Voltar ao Lobby",
            False,
            "assets/voltar_lobby.png não encontrado",
        )
    else:
        template = detector.voltar_lobby
        canvas = np.zeros((1080, 1920, 3), dtype=np.uint8)
        x, y = 1287, 146
        canvas[y : y + template.shape[0], x : x + template.shape[1]] = template
        hit = detector.find_voltar_lobby_button(canvas)
        check(
            "Botão Voltar ao Lobby em tela sintética",
            hit is not None
            and abs(hit.x - x) <= 2
            and abs(hit.y - y) <= 2,
            f"score={hit.score:.2f} em ({hit.x},{hit.y})" if hit else "não encontrado",
        )
        for name, image in (
            ("lobby", lobby),
            ("suspensão", suspended),
            ("desktop", desktop),
        ):
            if image is None:
                continue
            hit = detector.find_voltar_lobby_button(image)
            check(
                f"Sem falso positivo do Voltar ao Lobby no {name}",
                hit is None,
                f"score={hit.score:.2f} em ({hit.x},{hit.y})" if hit else "limpo",
            )

    print()
    print("Aba de opções do painel social (menu novo):")
    if detector.menu_tab is None:
        check(
            "Template da aba de opções",
            False,
            "assets/menu_tab.png não encontrado",
        )
    else:
        import numpy as np

        template = detector.menu_tab
        canvas = np.zeros((1080, 1920, 3), dtype=np.uint8)
        x, y = 1660, 55
        canvas[y : y + template.shape[0], x : x + template.shape[1]] = template
        hit = detector.find_menu_tab_button(canvas)
        check(
            "Aba de opções em tela sintética",
            hit is not None
            and abs(hit.center[0] - 1678) <= 2
            and abs(hit.center[1] - 71) <= 2,
            f"score={hit.score:.2f} em {hit.center}" if hit else "não encontrada",
        )
        for name, image in (
            ("lobby", lobby),
            ("suspensão", suspended),
            ("desktop", desktop),
        ):
            if image is None:
                continue
            hit = detector.find_menu_tab_button(image)
            check(
                f"Sem falso positivo da aba no {name}",
                hit is None,
                f"score={hit.score:.2f} em ({hit.x},{hit.y})" if hit else "limpo",
            )

    print()
    print("Pós-partida: clique visual, sem ENTER/ESPAÇO:")
    import numpy as np

    summary = None
    if detector.return_lobby is not None and detector.play_again is not None:
        summary = np.zeros((1080, 1920, 3), dtype=np.uint8)
        summary[414:470, 1338:1814] = detector.return_lobby
        summary[502:558, 1338:1814] = detector.play_again

    def postmatch_bot(token_found: bool) -> PirateBot:
        fake = PirateBot(
            config,
            queue.Queue(),
            threading.Event(),
            threading.Event(),
        )
        fake.phase = Phase.POSTMATCH
        fake.matches = 1
        fake._counted_match = True
        fake.token_found = token_found
        fake._endgame_at = time.time() - 10.0
        fake._next_scan_at = time.time() + 999.0
        fake._clicked_postmatch_at = 0.0
        fake._detector = detector
        fake._controller = RecordingController()
        fake._capture = lambda *args, **kwargs: summary
        return fake

    if summary is not None:
        bot_postmatch = postmatch_bot(False)
        bot_postmatch._do_postmatch(time.time())
        check(
            "Pós-partida clica em JOGAR NOVAMENTE",
            bot_postmatch._controller.clicks == [(1576, 530)]
            and bot_postmatch._controller.enter == 0
            and bot_postmatch._controller.space == 0,
            f"cliques={bot_postmatch._controller.clicks}",
        )

        # Regressão v1.1.4: depois de JOGAR NOVAMENTE a tela é a da fila,
        # sem os botões do resumo. O bot deve aguardar a partida em vez de
        # abrir o menu com ESC e voltar ao lobby.
        bot_requeue = postmatch_bot(False)
        bot_requeue._endgame_at = time.time() - 20.0
        bot_requeue._do_postmatch(time.time())
        queue_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        bot_requeue._capture = lambda *args, **kwargs: queue_frame
        bot_requeue._clicked_postmatch_at = 0.0
        bot_requeue._do_postmatch(time.time())
        check(
            "Após JOGAR NOVAMENTE, espera a partida sem abrir ESC",
            bot_requeue._controller.clicks == [(1576, 530)]
            and bot_requeue._controller.escapes == 0
            and bot_requeue._requeued_at > 0.0,
            f"cliques={bot_requeue._controller.clicks} "
            f"esc={bot_requeue._controller.escapes}",
        )

        # Se a fila estourar o tempo de matchmaking, o fallback de saída
        # precisa voltar a funcionar para não deixar o bot preso.
        expired_at = time.time() + config.behavior.matchmaking_timeout + 5.0
        bot_requeue._requeued_at = time.time() - 1.0
        bot_requeue._do_postmatch(expired_at)
        bot_requeue._do_postmatch(expired_at + 20.0)
        check(
            "Matchmaking esgotado após JOGAR NOVAMENTE libera o ESC",
            bot_requeue._requeued_at == 0.0
            and bot_requeue._controller.escapes == 1,
            f"requeued={bot_requeue._requeued_at:.0f} "
            f"esc={bot_requeue._controller.escapes}",
        )

        bot_token = postmatch_bot(True)
        bot_token._do_postmatch(time.time())
        check(
            "Com token, pós-partida clica em RETORNAR AO LOBBY",
            bot_token._controller.clicks == [(1576, 442)]
            and bot_token._controller.enter == 0
            and bot_token._controller.space == 0,
            f"cliques={bot_token._controller.clicks}",
        )
    else:
        check(
            "Templates do resumo disponíveis",
            False,
            "return_lobby.png e play_again.png são necessários",
        )

    print()
    print("Pós-partida sem resumo (último sobrevivente):")
    if detector.voltar_lobby is None:
        check(
            "Template Voltar ao Lobby disponível",
            False,
            "assets/voltar_lobby.png não encontrado",
        )
    else:
        empty_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        menu_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        menu_frame[146:198, 1287:1843] = detector.voltar_lobby

        bot_last = PirateBot(
            config,
            queue.Queue(),
            threading.Event(),
            threading.Event(),
        )
        bot_last.phase = Phase.POSTMATCH
        bot_last.matches = 1
        bot_last._counted_match = True
        bot_last._endgame_at = time.time() - 20.0
        bot_last._next_scan_at = time.time() + 999.0
        bot_last._detector = detector
        bot_last._controller = RecordingController()
        bot_last._capture = lambda *args, **kwargs: empty_frame
        bot_last._do_postmatch(time.time())
        check(
            "Sem resumo, pós-partida abre o menu com ESC",
            bot_last._controller.escapes == 1
            and bot_last._controller.clicks == []
            and bot_last._controller.enter == 0
            and bot_last._controller.space == 0,
            f"esc={bot_last._controller.escapes} cliques={bot_last._controller.clicks}",
        )

        bot_last._capture = lambda *args, **kwargs: menu_frame
        bot_last._do_postmatch(time.time())
        check(
            "Com o menu aberto, clica em Voltar ao Lobby",
            bot_last._controller.clicks == [(1565, 172)]
            and bot_last._controller.enter == 0
            and bot_last._controller.space == 0,
            f"cliques={bot_last._controller.clicks}",
        )

        if detector.menu_tab is not None:
            social_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
            tab = detector.menu_tab
            social_frame[55 : 55 + tab.shape[0], 1660 : 1660 + tab.shape[1]] = tab
            bot_last._controller.clicks.clear()
            bot_last._clicked_postmatch_at = 0.0
            bot_last._capture = lambda *args, **kwargs: social_frame
            bot_last._do_postmatch(time.time())
            bot_last._clicked_postmatch_at = 0.0
            bot_last._capture = lambda *args, **kwargs: menu_frame
            bot_last._do_postmatch(time.time())
            check(
                "Sem resumo, painel social: aba e depois Voltar ao Lobby",
                bot_last._controller.clicks == [(1678, 71), (1565, 172)]
                and bot_last._controller.escapes == 1,
                f"cliques={bot_last._controller.clicks} "
                f"esc={bot_last._controller.escapes}",
            )
        else:
            check(
                "Template da aba para o pós-partida",
                False,
                "assets/menu_tab.png não encontrado",
            )

    print()
    print("Diagnóstico do pós-partida (tools/check_postmatch.py):")
    if summary is not None:
        import numpy as np

        report = inspect_frame(detector, summary)
        play_again = report["jogar_novamente"]
        return_lobby = report["retornar_ao_lobby"]
        check(
            "Diagnóstico encontra JOGAR NOVAMENTE",
            play_again["found"] is True and play_again["center"] == (1576, 530),
            f"centro={play_again['center']} score={play_again['score']:.2f}",
        )
        check(
            "Diagnóstico encontra RETORNAR AO LOBBY",
            return_lobby["found"] is True and return_lobby["center"] == (1576, 442),
            f"centro={return_lobby['center']} score={return_lobby['score']:.2f}",
        )
        expected_keys = {
            "token",
            "jogar",
            "continuar_jogando",
            "jogar_novamente",
            "retornar_ao_lobby",
            "voltar_ao_lobby",
            "aba_menu",
            "seta_saida",
        }
        check(
            "Diagnóstico usa as mesmas chaves do relatório",
            set(report) == expected_keys,
            f"chaves={sorted(report)}",
        )
        blank = np.zeros((1080, 1920, 3), dtype=np.uint8)
        empty_report = inspect_frame(detector, blank)
        check(
            "Diagnóstico não inventa botões em tela vazia",
            not any(item["found"] for item in empty_report.values()),
            f"encontrados={[name for name, item in empty_report.items() if item['found']]}",
        )
    else:
        check(
            "Diagnóstico do pós-partida disponível",
            False,
            "templates do resumo necessários",
        )

    print()
    print("Saída da partida pelo menu novo:")
    menu = None
    if detector.voltar_lobby is not None:
        menu = np.zeros((1080, 1920, 3), dtype=np.uint8)
        menu[146:198, 1287:1843] = detector.voltar_lobby
    if menu is not None:
        def leave_bot() -> PirateBot:
            bot_leave = PirateBot(
                config,
                queue.Queue(),
                threading.Event(),
                threading.Event(),
            )
            bot_leave.phase = Phase.MATCH
            bot_leave._detector = detector
            bot_leave._controller = RecordingController()
            bot_leave._grabber = object()
            bot_leave._squad_leave_due_at = time.time() + 30.0
            bot_leave._next_scan_at = time.time() + 999.0
            return bot_leave

        bot_leave = leave_bot()
        bot_leave._capture = lambda *args, **kwargs: menu
        bot_leave._attempt_leave_match()
        check(
            "Menu já aberto: clica em Voltar ao Lobby sem ESC",
            bot_leave._controller.clicks == [(1565, 172)]
            and bot_leave._controller.escapes == 0
            and bot_leave._leave_button_clicked,
            f"cliques={bot_leave._controller.clicks} esc={bot_leave._controller.escapes}",
        )

        bot_leave_closed = leave_bot()
        empty_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        frames = [empty_frame, menu]
        bot_leave_closed._capture = (
            lambda *args, **kwargs: frames.pop(0) if frames else menu
        )
        bot_leave_closed._attempt_leave_match()
        check(
            "Menu fechado: abre com ESC e clica em Voltar ao Lobby",
            bot_leave_closed._controller.clicks == [(1565, 172)]
            and bot_leave_closed._controller.escapes == 1
            and bot_leave_closed._leave_button_clicked,
            f"cliques={bot_leave_closed._controller.clicks} "
            f"esc={bot_leave_closed._controller.escapes}",
        )

        if detector.menu_tab is not None:
            social = np.zeros((1080, 1920, 3), dtype=np.uint8)
            tab = detector.menu_tab
            social[55 : 55 + tab.shape[0], 1660 : 1660 + tab.shape[1]] = tab
            bot_leave_social = leave_bot()
            social_frames = [social, menu]
            bot_leave_social._capture = (
                lambda *args, **kwargs: social_frames.pop(0)
                if social_frames
                else menu
            )
            bot_leave_social._attempt_leave_match()
            check(
                "Painel social: abre a aba e clica em Voltar ao Lobby",
                bot_leave_social._controller.clicks == [(1678, 71), (1565, 172)]
                and bot_leave_social._controller.escapes == 0
                and bot_leave_social._leave_button_clicked,
                f"cliques={bot_leave_social._controller.clicks} "
                f"esc={bot_leave_social._controller.escapes}",
            )
        else:
            check(
                "Template da aba de opções disponível",
                False,
                "assets/menu_tab.png não encontrado",
            )
    else:
        check(
            "Template Voltar ao Lobby disponível",
            False,
            "assets/voltar_lobby.png não encontrado",
        )

    bot_transition = PirateBot(
        config,
        queue.Queue(),
        threading.Event(),
        threading.Event(),
    )
    bot_transition.phase = Phase.POSTMATCH
    bot_transition.matches = 1
    bot_transition._counted_match = True
    bot_transition._handle_event(
        LogEvent("state", "match", "", time.time())
    )
    check(
        "Partida seguinte ao resumo é contabilizada",
        bot_transition.phase == Phase.MATCH and bot_transition.matches == 2,
        f"fase={bot_transition.phase.value} partidas={bot_transition.matches}",
    )

    bot_transition._beep_token = lambda: None  # type: ignore[method-assign]
    bot_transition.token_found = False
    bot_transition._handle_reward(RewardEvent("Ferramenta Espirito", kind="item"))
    check(
        "Recompensa comum não marca o token",
        not bot_transition.token_found,
    )
    bot_transition._handle_reward(
        RewardEvent(TOKEN_NAME, kind="token", via="ocr", confidence=1.0)
    )
    check(
        "Token lido pelo OCR marca o estado do token",
        bot_transition.token_found,
    )

    false_positive = LOGS / "snapshots" / "token_banner_20261105_160659.png"
    if false_positive.exists():
        print()
        print("Falso positivo real (captura local, não versionada):")
        image = imread_u(false_positive)
        if image is None:
            check("Sem token no falso positivo do banner", False, "falha ao ler a imagem")
        else:
            detection = detector.detect(image)
            detail = (
                f"falso positivo: {detection.best.kind} "
                f"score={detection.best.score:.2f} white={detection.best.white:.2f}"
                if detection.best
                else "limpo"
            )
            check("Sem token no falso positivo do banner", not detection.found, detail)

    false_positive_gameplay = (
        LOGS / "snapshots" / "token_banner_20261106_171829.png"
    )
    if false_positive_gameplay.exists():
        print()
        print("Falso positivo em gameplay (captura local, não versionada):")
        image = imread_u(false_positive_gameplay)
        if image is None:
            check("Sem token na textura de gameplay", False, "falha ao ler a imagem")
        else:
            detection = detector.detect(image)
            check(
                "Sem token na textura de gameplay",
                not detection.found,
                (
                    f"falso positivo: {detection.best.kind} "
                    f"score={detection.best.score:.2f} em "
                    f"({detection.best.x},{detection.best.y})"
                    if detection.best
                    else "limpo"
                ),
            )

    background_lobby = LOGS / "fortnite_bg.png"
    if background_lobby.exists():
        print()
        print("Captura real em segundo plano (logs/fortnite_bg.png):")
        image = imread_u(background_lobby)
        if image is not None:
            detection = detector.detect(image)
            check(
                "Sem falso positivo de token na captura em segundo plano",
                not detection.found,
                (
                    f"falso positivo: {detection.best.kind} score={detection.best.score:.2f}"
                    if detection.best
                    else "limpo"
                ),
            )
            hit = detector.find_play_button(image)
            check(
                "Botão JOGAR na captura em segundo plano",
                hit is not None,
                f"score={hit.score:.2f}" if hit else "não encontrado",
            )

    print()
    print("Prevenção de suspensão do Windows:")
    power.set_awake("selftest", True)
    check("Estado de PC acordado ativado", power.is_awake())
    power.set_awake("selftest", False)
    check("Estado de PC acordado liberado", not power.is_awake())
    power.shutdown()

    print()
    print("Parser do log:")
    samples = [
        (
            "[2026.11.05-17.33.59:883][ 59]LogFortUI: Display: "
            "[UIManager_Athena_C] UI State changing from [None] to "
            "[UI.State.Athena.Frontend]",
            "state",
            "lobby",
        ),
        (
            "[2026.11.05-17.13.33:796][204]LogFortUI: Display: "
            "[UIManager_Athena_C] UI State changing from [None] to "
            "[UI.State.Athena.BattleRoyale]",
            "state",
            "match",
        ),
        (
            "[2026.11.05-17.33.53:941][983]LogBattleRoyaleGamePhaseLogic: "
            "UpdateGamePhaseStep. Phase = EAthenaGamePhase::EndGame",
            "phase",
            "EndGame",
        ),
        (
            "[2026.11.05-17.33.54:061][984]LogUIActionRouter: Display: "
            "Applying input config for leaf-most node [WBP_PostMatchPanelContainer_C]",
            "postmatch",
            "",
        ),
        (
            "[2026.11.05-16.01.50:430][786]LogFort: Warning: "
            "AFortPlayerControllerAthena::FixupInvalidRespawnVisuals ... OnPlayerPawnDied()",
            "player_died",
            "",
        ),
        (
            "[2026.11.05-20.35.01:008][378]LogSpectateAfterDeathViewTarget: "
            "[7a6b] [Player]  No teammates available to follow",
            "no_teammates",
            "",
        ),
    ]
    for line, expected_kind, expected_value in samples:
        event = parse_line(line)
        ok = (
            event is not None
            and event.kind == expected_kind
            and (not expected_value or event.value == expected_value)
        )
        check(
            f"Evento {expected_kind}/{expected_value or '-'}",
            ok,
            f"obtido {event.kind}/{event.value}" if event else "nenhum evento",
        )

    print()
    print("Recompensas (OCR e parser):")
    item_pt = parse_reward_text("VOCÊ ENCONTROU\nFERRAMENTA ESPÍRITO")
    check(
        "Parser identifica item em português",
        item_pt is not None
        and item_pt.kind == "item"
        and "Ferramenta" in item_pt.name,
        repr(item_pt),
    )
    token_en = parse_reward_text("YOU FOUND\nPIRATE SHOP ACCESS")
    check(
        "Parser identifica o token em inglês",
        token_en is not None
        and token_en.kind == "token"
        and token_en.name == TOKEN_NAME,
        repr(token_en),
    )
    item_en = parse_reward_text("YOU FOUND\nSPIRIT TOOL")
    check(
        "Parser identifica item em inglês",
        item_en is not None
        and item_en.kind == "item"
        and item_en.name == "Spirit Tool",
        repr(item_en),
    )
    check(
        "Parser ignora texto sem cabeçalho",
        parse_reward_text("0:03\nARLONU\n") is None,
    )
    item_ar = parse_reward_text("لقد عثرت على أداة روح")
    check(
        "Parser identifica item em árabe",
        item_ar is not None
        and item_ar.kind == "item"
        and item_ar.name == "أداة روح",
        repr(item_ar),
    )
    token_ar = parse_reward_text("لقد عثرت على متجر القراصنة")
    check(
        "Parser identifica o token em árabe",
        token_ar is not None
        and token_ar.kind == "token"
        and token_ar.name == TOKEN_NAME,
        repr(token_ar),
    )
    item_tail = parse_reward_text("VOCÊ ENCONTROU\nDISPOSITIVO\n\\ ELEMENTAL 1.,")
    check(
        "Parser remove quantidade/pontuação colada pelo OCR",
        item_tail is not None
        and item_tail.kind == "item"
        and item_tail.name == "Dispositivo Elemental",
        repr(item_tail),
    )
    item_quantity = parse_reward_text("VOCÊ ENCONTROU\nFERRAMENTA ESPÍRITO x2")
    check(
        "Parser remove quantidade no formato x2",
        item_quantity is not None
        and item_quantity.name == "Ferramenta Espírito",
        repr(item_quantity),
    )
    item_model = parse_reward_text("VOCÊ ENCONTROU\nMODELO G 63")
    check(
        "Parser preserva números de modelo com dois dígitos",
        item_model is not None and item_model.name.endswith("G 63"),
        repr(item_model),
    )

    banner_image = imread_u(TEST_ASSETS / "banner_generic.jpg")
    gameplay_image = imread_u(TEST_ASSETS / "fortnite_now.png")
    check(
        "Brasão do banner genérico é reconhecido",
        banner_image is not None
        and reward_badge_score(banner_image) >= config.rewards.fallback_banner_score,
        (
            f"score={reward_badge_score(banner_image):.2f}"
            if banner_image is not None
            else "imagem ausente"
        ),
    )
    check(
        "Gameplay normal não atinge o fallback visual",
        gameplay_image is not None
        and reward_badge_score(gameplay_image) < config.rewards.fallback_banner_score,
        (
            f"score={reward_badge_score(gameplay_image):.2f}"
            if gameplay_image is not None
            else "imagem ausente"
        ),
    )
    check(
        "Banner de recompensa ainda é localizado pelo detector antigo",
        banner_image is not None
        and banner_score(banner_image) >= 0.15,
        f"score={banner_score(banner_image):.2f}" if banner_image is not None else "imagem ausente",
    )

    if banner_image is not None:
        scanner = RewardScanner(RewardConfig(ocr_enabled=False, scan_interval=0.0))
        visual_event = scanner.scan(banner_image, now=1.0)
        check(
            "Fallback visual envia o banner sem OCR",
            visual_event is not None
            and visual_event.via == "visual"
            and visual_event.name == config.rewards.fallback_label,
            repr(visual_event),
        )
    if gameplay_image is not None:
        scanner = RewardScanner(RewardConfig(ocr_enabled=False, scan_interval=0.0))
        check(
            "Fallback visual ignora gameplay comum",
            scanner.scan(gameplay_image, now=1.0) is None,
        )

        precue = ChestPrecue(RewardConfig())
        precue.update(gameplay_image, now=1.0)
        check(
            "Precue não dispara em imagem estática",
            not precue.update(gameplay_image, now=2.0),
        )

    import cv2
    import numpy as np

    precue = ChestPrecue(RewardConfig())
    dark = np.zeros((720, 1280, 3), dtype=np.uint8)
    gold = dark.copy()
    cv2.rectangle(gold, (420, 220), (860, 560), (0, 180, 255), -1)
    check(
        "Precue usa o primeiro quadro como referência",
        not precue.update(dark, now=10.0),
    )
    check(
        "Precue detecta clarão dourado central",
        precue.update(gold, now=11.0),
    )
    precue.update(dark, now=11.5)
    check(
        "Precue respeita o cooldown entre clarões",
        not precue.update(gold, now=11.6),
    )

    if banner_image is not None:
        scanner = RewardScanner(RewardConfig(ocr_enabled=False, scan_interval=60.0))
        first = scanner.scan(banner_image, now=20.0)
        throttled = scanner.scan(banner_image, now=21.0)
        forced = scanner.scan(banner_image, now=21.1, force=True)
        check(
            "Precue força leitura mesmo dentro do intervalo do OCR",
            first is not None and throttled is None and forced is not None,
        )

    gate = RewardGate(cooldown=10.0, token_cooldown=60.0)
    event = RewardEvent("Ferramenta Espirito")
    check("Gate aceita a primeira recompensa", gate.accept(event, now=100.0))
    check(
        "Gate bloqueia a mesma recompensa no cooldown",
        not gate.accept(event, now=105.0),
    )
    check("Gate libera depois do cooldown", gate.accept(event, now=111.0))
    token_event = RewardEvent(TOKEN_NAME, kind="token")
    check("Gate aceita o token", gate.accept(token_event, now=200.0))
    check(
        "Gate não repete o token",
        not gate.accept(token_event, now=220.0),
    )

    print()
    print("Limpeza de capturas:")
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        now = time.time()
        for index in range(10):
            path = folder / f"pos_partida_{index}.png"
            path.write_bytes(b"x" * (index + 1))
            stamp = now - (index + 1) * 6 * 3600
            os.utime(path, (stamp, stamp))
        for name in ("token_banner_x.png", "reward_item_x.png", "tela_recompensa_x.png"):
            path = folder / name
            path.write_bytes(b"evidence")
            stamp = now - 96 * 3600
            os.utime(path, (stamp, stamp))
        storage = StorageConfig(
            snapshot_max_files=0,
            snapshot_max_age_days=1,
            snapshot_min_keep=2,
            snapshot_grace_seconds=60,
        )
        result = prune_snapshots(folder, storage, now=now)
        remaining = {path.name for path in folder.glob("*.png")}
        check(
            "Limpeza por idade remove as antigas",
            result.removed == 7 and "pos_partida_9.png" not in remaining,
            f"removidas={result.removed}, restantes={sorted(remaining)}",
        )
        check(
            "Limpeza preserva somente as evidências do token",
            {"token_banner_x.png", "tela_recompensa_x.png"} <= remaining
            and "reward_item_x.png" not in remaining,
        )
        check(
            "Limpeza preserva as capturas mais recentes",
            {"pos_partida_0.png", "pos_partida_1.png"} <= remaining,
        )

    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        now = time.time()
        for index in range(12):
            path = folder / f"pos_partida_{index}.png"
            path.write_bytes(b"x")
            stamp = now - (index + 1) * 30
            os.utime(path, (stamp, stamp))
        for name in ("token_banner_x.png", "reward_item_x.png", "tela_recompensa_x.png"):
            path = folder / name
            path.write_bytes(b"evidence")
            stamp = now - 60
            os.utime(path, (stamp, stamp))
        storage = StorageConfig(
            snapshot_max_files=3,
            snapshot_max_age_days=0,
            snapshot_min_keep=0,
            snapshot_grace_seconds=0,
        )
        result = prune_snapshots(folder, storage, now=now)
        remaining = list(folder.glob("*.png"))
        evidence_names = [
            "token_banner_x.png",
            "tela_recompensa_x.png",
        ]
        check(
            "Limpeza por quantidade respeita o máximo",
            result.removed > 0 and len(remaining) <= 3,
            f"removidas={result.removed}, restantes={len(remaining)}",
        )
        check(
            "Evidências do token continuam após limpeza por quantidade",
            all((folder / name).exists() for name in evidence_names)
            and not (folder / "reward_item_x.png").exists(),
        )

    print()
    print("Webhook:")
    masked = mask_webhook_url(
        "https://discord.com/api/webhooks/123456789/segredo-na-url"
    )
    check(
        "URL do Discord é mascarada",
        "segredo-na-url" not in masked and "discord.com" in masked,
        masked,
    )
    discord = WebhookConfig(
        enabled=True, url="https://discord.com/api/webhooks/1/abc"
    )
    message = WebhookMessage(
        reward=TOKEN_NAME,
        kind="token",
        matches=2,
        elapsed=90,
        image_bytes=b"\x89PNG-fake",
        filename="token.png",
    )
    body, content_type = build_payload(discord, message)
    check(
        "Payload do Discord leva anexo e nome",
        b"payload_json" in body
        and b"files[0]" in body
        and TOKEN_NAME.encode("utf-8") in body
        and b"\x89PNG-fake" in body,
        content_type,
    )
    generic = WebhookConfig(enabled=True, url="http://127.0.0.1/hook")
    body, _ = build_payload(generic, message)
    check(
        "Payload genérico leva nome e captura",
        b'name="reward"' in body
        and b'name="file"' in body
        and TOKEN_NAME.encode("utf-8") in body
        and b"\x89PNG-fake" in body,
    )

    captured: dict[str, bytes | str] = {}

    class _WebhookHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            captured["body"] = self.rfile.read(length)
            captured["ctype"] = self.headers.get("Content-Type", "")
            self.send_response(204)
            self.end_headers()

        def log_message(self, *_args) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), _WebhookHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        port = server.server_address[1]
        local = WebhookConfig(
            enabled=True,
            url=f"http://127.0.0.1:{port}/hook",
            timeout_seconds=5,
        )
        local_message = WebhookMessage(
            reward="Ferramenta Espirito",
            kind="item",
            matches=4,
            elapsed=61,
            image_bytes=b"fake-png",
            filename="reward.png",
        )
        result = send_message(local, local_message, attempts=1)
        check(
            "Webhook local responde 204",
            result.ok and result.status == 204,
            result.detail,
        )
        check(
            "Webhook local recebe nome e captura",
            b"Ferramenta Espirito" in captured.get("body", b"")
            and b"fake-png" in captured.get("body", b"")
            and "multipart/form-data" in str(captured.get("ctype", "")),
        )
        test_result = send_test(local)
        check(
            "Teste do webhook envia sem captura",
            test_result.ok and test_result.status == 204,
            test_result.detail,
        )
    finally:
        server.shutdown()
        server.server_close()

    print()
    print("Configuração (novas seções):")
    with tempfile.TemporaryDirectory() as temp:
        config_path = Path(temp) / "config.json"
        custom = load_config(config_path)
        custom.storage.snapshot_max_files = 123
        custom.storage.snapshot_max_age_days = 7
        custom.webhook.enabled = True
        custom.webhook.url = "https://example.com/hook"
        custom.rewards.fallback_label = "Recompensa teste"
        save_config(custom, config_path)
        loaded = load_config(config_path)
        check(
            "Configuração preserva retenção",
            loaded.storage.snapshot_max_files == 123
            and loaded.storage.snapshot_max_age_days == 7,
        )
        check(
            "Configuração preserva webhook",
            loaded.webhook.enabled
            and loaded.webhook.url == "https://example.com/hook",
        )
        check(
            "Configuração preserva recompensas",
            loaded.rewards.fallback_label == "Recompensa teste",
        )

    print()
    print("Documentação (links relativos):")
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        docs = base / "docs"
        docs.mkdir()
        (docs / "guia.md").write_text("# Guia\n", encoding="utf-8")
        readme = base / "README.md"
        readme.write_text(
            "[Guia](docs/guia.md)\n"
            "[Raiz](/docs/guia.md)\n"
            "[Externo](https://example.com)\n"
            "[Âncora](#secao)\n"
            "[Quebrado](docs/ausente.md)\n"
            "```markdown\n"
            "[Exemplo](docs/ausente.md)\n"
            "```\n",
            encoding="utf-8",
        )
        issues = check_file(readme, base)
        check(
            "Verificador encontra link relativo quebrado",
            len(issues) == 1
            and issues[0].target == "docs/ausente.md"
            and issues[0].line == 5,
            f"issues={issues}",
        )
        check(
            "Verificador aceita links relativos e da raiz",
            all(issue.target != "docs/guia.md" for issue in issues),
        )
        check(
            "Verificador ignora link externo, âncora e bloco de código",
            all(issue.target not in ("https://example.com", "#secao") for issue in issues)
            and len(issues) == 1,
            f"issues={issues}",
        )

    print()
    print("Preenchimentos (fills) na partida:")
    squad_samples = [
        (
            "[2026.11.05-19.17.31:450][422]LogSocialChatManager: [3b5d] "
            "[00007FF134B21540] ChannelName:BR.Any.b4d1109c873540edb3dec4d9ec88f7d1.6 "
            "Conversation:[07fE7lvGWdOflOOjFb2fnh02] with 2 players",
            "match_chat",
            "07fE7lvGWdOflOOjFb2fnh02",
        ),
        (
            "[2026.11.05-19.18.10:571][572]LogSocialChatManager: [3ba6] "
            "[00007FF134B21540] Conversation:[07fE7lvGWdOflOOjFb2fnh02] "
            "PlayerAdded:MCP:e3446...6269d",
            "squad_join",
            "07fE7lvGWdOflOOjFb2fnh02|e3446...6269d",
        ),
        (
            "[2026.11.05-19.21.41:512][897]LogSocialChatManager: [3bda] "
            "[00007FF134B21540] Conversation:[07fE7lvGWdOflOOjFb2fnh02] "
            "PlayerRemoved:MCP:004b4...374e1",
            "squad_leave",
            "07fE7lvGWdOflOOjFb2fnh02|004b4...374e1",
        ),
        (
            "[2026.11.05-14.46.12:439][568]LogFort: Display: SetHasFinishedLoading "
            "bHasClientFinishedLoading: 0 bInHasFinishedLoading: 1 "
            "Player: MCP:1b70c848f15d48f78a9d48144aeedb56",
            "local_player",
            "1b70c...edb56",
        ),
    ]
    for line, expected_kind, expected_value in squad_samples:
        event = parse_line(line)
        ok = (
            event is not None
            and event.kind == expected_kind
            and event.value == expected_value
        )
        check(
            f"Evento {expected_kind}",
            ok,
            f"obtido {event.kind}/{event.value}" if event else "nenhum evento",
        )

    check(
        "ID completo normalizado",
        player_key("004b43b61c2647cc99e410712fa374e1") == "004b4...374e1",
        player_key("004b43b61c2647cc99e410712fa374e1"),
    )

    tracker = SquadTracker()
    check("Canal da partida identificado", tracker.on_match_chat("conv"))
    tracker.on_player_join("conv", "004b4...374e1")
    tracker.on_player_join("conv", "e3446...6269d")
    tracker.on_player_join("conv", "9e23f...4b43c")
    check(
        "Três preenchimentos rastreados",
        len(tracker.players) == 3 and not tracker.empty,
        f"{len(tracker.players)} na lista",
    )
    check(
        "Jogador local identificado",
        tracker.set_local_player("1b70c...edb56") is False,
    )
    check(
        "Jogador local não conta como fill",
        not tracker.on_player_join("conv", "1b70c...edb56")
        and len(tracker.players) == 3,
    )
    check(
        "Saída em outro canal é ignorada",
        not tracker.on_player_leave("outro", "004b4...374e1")
        and len(tracker.players) == 3,
    )
    tracker.on_player_leave("conv", "004b4...374e1")
    tracker.on_player_leave("conv", "e3446...6269d")
    check(
        "Saída parcial mantém o restante",
        len(tracker.players) == 1,
        f"{len(tracker.players)} na lista",
    )
    tracker.on_player_leave("conv", "9e23f...4b43c")
    check(
        "Conjunto vazio quando todos saem",
        tracker.empty and tracker.seen_players,
    )
    tracker.on_match_chat("conv2")
    check(
        "Novo canal zera a lista",
        tracker.empty and not tracker.seen_players and tracker.local_player == "1b70c...edb56",
    )

    print()
    print("Integração da saída automática:")
    bot = PirateBot(
        config,
        queue.Queue(),
        threading.Event(),
        threading.Event(),
    )
    bot.phase = Phase.MATCH
    bot._next_scan_at = time.time() + 999.0
    bot._squad.set_local_player("1b70c...edb56")
    bot._handle_event(LogEvent("match_chat", "conv", "", time.time()))
    bot._handle_event(LogEvent("squad_join", "conv|004b4...374e1", "", time.time()))
    bot._handle_event(LogEvent("squad_join", "conv|e3446...6269d", "", time.time()))
    bot._handle_event(LogEvent("squad_leave", "conv|004b4...374e1", "", time.time()))
    check(
        "Saída não é agendada com fill restante",
        bot._squad_leave_due_at == 0.0,
        f"restam {len(bot._squad.players)}",
    )
    bot._handle_event(LogEvent("squad_leave", "conv|e3446...6269d", "", time.time()))
    check(
        "Saída agendada após o último fill",
        bot._squad_leave_due_at > time.time(),
        f"em {bot._squad_leave_due_at - time.time():.1f}s",
    )
    bot._handle_event(LogEvent("squad_join", "conv|9e23f...4b43c", "", time.time()))
    check(
        "Preenchimento que volta cancela a saída",
        bot._squad_leave_due_at == 0.0,
    )
    bot._squad.players.clear()
    bot._squad_leave_due_at = time.time() + 10.0
    bot.token_found = True
    bot._do_match(time.time())
    check(
        "Token encontrado cancela a saída",
        bot._squad_leave_due_at == 0.0,
    )
    bot.token_found = False
    bot._squad.players.clear()
    bot._squad_leave_due_at = time.time() + 10.0
    bot._handle_event(LogEvent("squad_join", "conv|004b4...374e1", "", time.time()))
    check(
        "Preenchimento que volta rearma o AFK",
        bot._squad_leave_due_at == 0.0 and len(bot._squad.players) == 1,
    )

    bot._squad_leave_due_at = 0.0
    bot.token_found = False
    bot._handle_event(LogEvent("no_teammates", "", "", time.time()))
    check(
        "Evento de espectador não agenda saída com fill vivo",
        bot._squad_leave_due_at == 0.0,
        f"restam {len(bot._squad.players)}",
    )

    bot._handle_event(LogEvent("squad_leave", "conv|004b4...374e1", "", time.time()))
    bot._squad_leave_due_at = 0.0
    bot._handle_event(LogEvent("no_teammates", "", "", time.time()))
    check(
        "Evento de espectador agenda saída com chat vazio",
        bot._squad_leave_due_at > time.time(),
        f"em {bot._squad_leave_due_at - time.time():.1f}s"
        if bot._squad_leave_due_at
        else "não agendada",
    )
    bot._squad_leave_due_at = 0.0
    bot.token_found = True
    bot._handle_event(LogEvent("no_teammates", "", "", time.time()))
    check(
        "Com token, morte sem companheiros não agenda saída",
        bot._squad_leave_due_at == 0.0,
    )
    bot.token_found = False

    try:
        path = Path(config.game.log_path)
        if path.exists():
            watcher = LogWatcher(path, __import__("queue").Queue(), __import__("threading").Event())
            state = watcher.read_initial_state()
            check(
                "Log real acessível",
                state in ("lobby", "match", "unknown"),
                f"estado inicial: {state}",
            )
        else:
            print(f"[IGNORADO] Log real não encontrado: {path}")
    except Exception as exc:
        check("Log real acessível", False, str(exc))

    if "--live" in sys.argv:
        print()
        print("Captura ao vivo (não foca nem clica no jogo):")
        try:
            from piratebot.vision import ScreenGrabber, find_game_window

            window = find_game_window(config.game.window_title)
            grabber = ScreenGrabber(window)
            frame = grabber.capture()
            detection = detector.detect(frame)
            play = detector.find_play_button(frame)
            suspend = detector.find_suspend_button(frame)
            exit_hit = detector.find_exit_button(frame)
            imwrite_u(LOGS / "live_foreground.png", frame)
            print(
                f"Janela {window.width}x{window.height}; primeiro plano: "
                f"{grabber.is_foreground()}"
            )
            print(
                "Token: "
                + (
                    f"SIM ({detection.best.kind}, score {detection.best.score:.2f})"
                    if detection.found and detection.best
                    else "não"
                )
            )
            print(f"JOGAR: {'sim' if play else 'não'}")
            print(f"Suspensão: {'sim' if suspend else 'não'}")
            print(
                "Seta de saída: "
                + (
                    f"sim, score {exit_hit.score:.2f} em "
                    f"({exit_hit.x},{exit_hit.y}) {exit_hit.w}x{exit_hit.h}"
                    if exit_hit
                    else "não"
                )
            )
            check("Captura ao vivo", True)

            print()
            print("Captura em segundo plano (PrintWindow, sem focar o jogo):")
            background_frame = grabber.capture_background()
            background_detection = detector.detect(background_frame)
            background_play = detector.find_play_button(background_frame)
            background_suspend = detector.find_suspend_button(background_frame)
            background_exit = detector.find_exit_button(background_frame)
            imwrite_u(LOGS / "live_background.png", background_frame)
            print(
                f"Janela {background_frame.shape[1]}x{background_frame.shape[0]}; "
                f"primeiro plano: {grabber.is_foreground()}"
            )
            print(
                "Token: "
                + (
                    f"SIM ({background_detection.best.kind}, "
                    f"score {background_detection.best.score:.2f})"
                    if background_detection.found and background_detection.best
                    else "não"
                )
            )
            print(f"JOGAR: {'sim' if background_play else 'não'}")
            print(f"Suspensão: {'sim' if background_suspend else 'não'}")
            print(
                "Seta de saída: "
                + (
                    f"sim, score {background_exit.score:.2f} em "
                    f"({background_exit.x},{background_exit.y}) "
                    f"{background_exit.w}x{background_exit.h}"
                    if background_exit
                    else "não"
                )
            )
            check(
                "Captura em segundo plano",
                True,
                f"{background_frame.shape[1]}x{background_frame.shape[0]}",
            )
        except Exception as exc:
            check("Captura ao vivo", False, str(exc))

    print()
    failures = [name for ok, name in results if not ok]
    if failures:
        print(f"RESULTADO: {len(failures)} teste(s) falharam.")
        for name in failures:
            print(f"  - {name}")
        return 1
    print(f"RESULTADO: todos os {len(results)} testes passaram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
