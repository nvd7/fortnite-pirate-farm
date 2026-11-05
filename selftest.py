"""Testes offline do Pirate Farm.

Uso:
    .venv\\Scripts\\python.exe selftest.py
    .venv\\Scripts\\python.exe selftest.py --live
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from piratebot.config import ASSETS, load_config
from piratebot.logwatcher import LogWatcher, parse_line
from piratebot.vision import TokenDetector, imread_u

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
]

results: list[tuple[bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((bool(condition), name))
    status = "OK  " if condition else "FALHA"
    suffix = f" — {detail}" if detail else ""
    print(f"[{status}] {name}{suffix}")


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
            check("Log real acessível", False, f"não encontrado: {path}")
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
            check("Captura ao vivo", True)
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
