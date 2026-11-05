"""Interface gráfica do Pirate Farm."""
from __future__ import annotations

import ctypes
import logging
import os
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

# Deixa as coordenadas em pixels físicos (importante em telas com escala).
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

from piratebot.bot import PHASE_LABELS, Phase, PirateBot
from piratebot.config import ASSETS, LOGS, ROOT, load_config
from piratebot.hotkey import HotkeyListener
from piratebot.vision import (
    ScreenGrabber,
    TokenDetector,
    find_game_window,
    imwrite_u,
)

APP_TITLE = "Pirate Farm — Fortnite"

PHASE_STYLE = {
    Phase.STARTING.value: ("Iniciando...", "#2563eb"),
    Phase.LOBBY.value: ("No lobby", "#2563eb"),
    Phase.QUEUING.value: ("Procurando partida", "#7c3aed"),
    Phase.MATCH.value: ("Em partida — AFK", "#0f766e"),
    Phase.POSTMATCH.value: ("Fim de partida", "#b45309"),
    Phase.FINISHED.value: ("TOKEN ENCONTRADO!", "#15803d"),
    Phase.ERROR.value: ("Erro", "#b91c1c"),
    Phase.STOPPED.value: ("Parado", "#6b7280"),
}


def _format_elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


class PirateFarmApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.config = load_config()
        self.ui_queue: "queue.Queue[dict]" = queue.Queue()
        self.stop_event = threading.Event()
        self.manual_token = threading.Event()
        self.bot: PirateBot | None = None
        self.hotkey: HotkeyListener | None = None
        self._logs_opened = False
        self._success_scheduled = False
        self._log_line_count = 0
        self._build_ui()
        self._start_hotkey()
        self.root.after(100, self._poll)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        self.root.title(APP_TITLE)
        self.root.geometry("720x640")
        self.root.minsize(620, 520)
        self.root.configure(bg="#f1f5f9")

        try:
            icon = tk.PhotoImage(file=str(ASSETS / "coin_inner.png"))
            self.root.iconphoto(True, icon)
            self._icon = icon
        except Exception:
            pass

        container = tk.Frame(self.root, bg="#f1f5f9", padx=18, pady=14)
        container.pack(fill="both", expand=True)

        header = tk.Frame(container, bg="#f1f5f9")
        header.pack(fill="x")
        tk.Label(
            header,
            text="Pirate Farm",
            font=("Segoe UI", 22, "bold"),
            fg="#0f172a",
            bg="#f1f5f9",
        ).pack(anchor="w")
        tk.Label(
            header,
            text="Farm AFK do token Pirate Shop Access — Fortnite",
            font=("Segoe UI", 10),
            fg="#475569",
            bg="#f1f5f9",
        ).pack(anchor="w", pady=(0, 10))

        status_card = tk.Frame(
            container,
            bg="#ffffff",
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            padx=16,
            pady=12,
        )
        status_card.pack(fill="x")

        self.status_label = tk.Label(
            status_card,
            text="Pronto para iniciar",
            font=("Segoe UI", 18, "bold"),
            fg="#475569",
            bg="#ffffff",
            anchor="w",
        )
        self.status_label.pack(fill="x")

        self.detail_label = tk.Label(
            status_card,
            text=(
                "Abra o Fortnite no lobby, com Battle Royale e Squad + Fill, "
                "e clique em INICIAR."
            ),
            font=("Segoe UI", 10),
            fg="#64748b",
            bg="#ffffff",
            anchor="w",
            justify="left",
            wraplength=650,
        )
        self.detail_label.pack(fill="x", pady=(2, 8))

        stats = tk.Frame(status_card, bg="#ffffff")
        stats.pack(fill="x")
        self.matches_label = tk.Label(
            stats, text="Partidas: 0", font=("Segoe UI", 10, "bold"),
            fg="#334155", bg="#ffffff"
        )
        self.matches_label.pack(side="left")
        self.token_label = tk.Label(
            stats, text="Token: não", font=("Segoe UI", 10, "bold"),
            fg="#b91c1c", bg="#ffffff"
        )
        self.token_label.pack(side="left", padx=(24, 0))
        self.time_label = tk.Label(
            stats, text="Tempo: 00:00:00", font=("Segoe UI", 10),
            fg="#64748b", bg="#ffffff"
        )
        self.time_label.pack(side="right")

        controls = tk.Frame(container, bg="#f1f5f9")
        controls.pack(fill="x", pady=(12, 6))

        self.start_button = tk.Button(
            controls,
            text="INICIAR",
            font=("Segoe UI", 12, "bold"),
            bg="#16a34a",
            fg="#ffffff",
            activebackground="#15803d",
            activeforeground="#ffffff",
            relief="flat",
            padx=22,
            pady=10,
            cursor="hand2",
            command=self._start_bot,
        )
        self.start_button.pack(side="left")

        self.stop_button = tk.Button(
            controls,
            text="PARAR (F8)",
            font=("Segoe UI", 11, "bold"),
            bg="#dc2626",
            fg="#ffffff",
            activebackground="#b91c1c",
            activeforeground="#ffffff",
            relief="flat",
            padx=18,
            pady=10,
            cursor="hand2",
            state="disabled",
            command=lambda: self._stop_bot("Parado pelo usuário."),
        )
        self.stop_button.pack(side="left", padx=(10, 0))

        self.token_button = tk.Button(
            controls,
            text="Já tenho o token",
            font=("Segoe UI", 10, "bold"),
            bg="#f59e0b",
            fg="#1f2937",
            activebackground="#d97706",
            activeforeground="#1f2937",
            relief="flat",
            padx=14,
            pady=10,
            cursor="hand2",
            state="disabled",
            command=self._mark_token,
        )
        self.token_button.pack(side="left", padx=(10, 0))

        self.sim_var = tk.BooleanVar(value=self.config.behavior.dry_run)
        self.sim_check = tk.Checkbutton(
            controls,
            text="Simulação (não clica no jogo)",
            variable=self.sim_var,
            font=("Segoe UI", 9),
            fg="#475569",
            bg="#f1f5f9",
            activebackground="#f1f5f9",
            anchor="w",
        )
        self.sim_check.pack(side="right")

        tools = tk.Frame(container, bg="#f1f5f9")
        tools.pack(fill="x", pady=(0, 10))
        tk.Button(
            tools,
            text="Testar detecção agora",
            font=("Segoe UI", 9),
            bg="#e2e8f0",
            fg="#0f172a",
            activebackground="#cbd5e1",
            relief="flat",
            padx=12,
            pady=6,
            cursor="hand2",
            command=self._test_detection,
        ).pack(side="left")
        tk.Button(
            tools,
            text="Abrir pasta de logs",
            font=("Segoe UI", 9),
            bg="#e2e8f0",
            fg="#0f172a",
            activebackground="#cbd5e1",
            relief="flat",
            padx=12,
            pady=6,
            cursor="hand2",
            command=self._open_logs,
        ).pack(side="left", padx=(8, 0))
        tk.Label(
            tools,
            text="F8 = parada de emergência",
            font=("Segoe UI", 9),
            fg="#64748b",
            bg="#f1f5f9",
        ).pack(side="right")

        warning = tk.Frame(container, bg="#fef3c7", padx=10, pady=7)
        warning.pack(fill="x", pady=(0, 8))
        tk.Label(
            warning,
            text=(
                "Mantenha o Fortnite em primeiro plano e não use o computador "
                "enquanto o bot estiver rodando. O jogo entra em suspensão se perder o foco. "
                "Desative o bloqueio de tela e a suspensão do Windows."
            ),
            font=("Segoe UI", 9),
            fg="#92400e",
            bg="#fef3c7",
            anchor="w",
            justify="left",
            wraplength=650,
        ).pack(fill="x")

        log_header = tk.Frame(container, bg="#f1f5f9")
        log_header.pack(fill="x")
        tk.Label(
            log_header,
            text="Registro",
            font=("Segoe UI", 10, "bold"),
            fg="#334155",
            bg="#f1f5f9",
        ).pack(side="left")

        log_frame = tk.Frame(container, bg="#0f172a")
        log_frame.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(log_frame)
        scrollbar.pack(side="right", fill="y")
        self.log_text = tk.Text(
            log_frame,
            height=16,
            wrap="word",
            bg="#0f172a",
            fg="#e2e8f0",
            insertbackground="#e2e8f0",
            font=("Consolas", 9),
            relief="flat",
            padx=8,
            pady=6,
            yscrollcommand=scrollbar.set,
        )
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.log_text.yview)
        self.log_text.tag_config("info", foreground="#e2e8f0")
        self.log_text.tag_config("success", foreground="#4ade80")
        self.log_text.tag_config("warn", foreground="#fbbf24")
        self.log_text.tag_config("error", foreground="#f87171")
        self.log_text.tag_config("debug", foreground="#94a3b8")
        self.log_text.configure(state="disabled")

    def _start_hotkey(self) -> None:
        self.hotkey = HotkeyListener(lambda: self.ui_queue.put({"type": "hotkey"}))
        if not self.hotkey.start():
            error = self.hotkey.error
            self._log(
                f"Não consegui registrar o atalho F8 ({error}). Use o botão PARAR.",
                "warn",
            )

    # --------------------------------------------------------------- ações
    def _start_bot(self) -> None:
        if self.bot is not None and self.bot.is_running():
            return
        self.stop_event.clear()
        self.manual_token.clear()
        self._success_scheduled = False
        self.config.behavior.dry_run = bool(self.sim_var.get())
        self.bot = PirateBot(
            self.config,
            self.ui_queue,
            self.stop_event,
            self.manual_token,
        )
        self._log(
            "Bot iniciado"
            + (" em modo SIMULAÇÃO." if self.config.behavior.dry_run else "."),
            "success",
        )
        if not self.config.behavior.dry_run:
            self._log(
                "O bot vai colocar o Fortnite em primeiro plano. Não mexa no PC.",
                "warn",
            )
        self.bot.start()
        self._update_buttons()

    def _stop_bot(self, reason: str) -> None:
        self.stop_event.set()
        if self.bot is not None:
            self.bot.stop()
        self._log(reason, "warn")
        self._set_status(Phase.STOPPED.value, reason)
        self._update_buttons()

    def _mark_token(self) -> None:
        if self.bot is None or not self.bot.is_running():
            self._log("O bot não está rodando.", "warn")
            return
        self.manual_token.set()
        self._log(
            "Token marcado manualmente. Vou aguardar o fim da partida "
            "(se houver) e encerrar.",
            "success",
        )
        self._set_status(
            Phase.MATCH.value,
            "Token marcado manualmente. Aguardando o fim da partida...",
        )

    def _test_detection(self) -> None:
        self._log("Capturando a tela para testar a detecção...", "info")
        threading.Thread(target=self._run_detection_test, name="DetectionTest", daemon=True).start()

    def _run_detection_test(self) -> None:
        try:
            window = find_game_window(self.config.game.window_title)
            grabber = ScreenGrabber(window)
            detector = TokenDetector(ASSETS, self.config.detection)
            frame = grabber.capture()
            token = detector.detect(frame)
            play = detector.find_play_button(frame)
            suspend = detector.find_suspend_button(frame)
            LOGS.mkdir(parents=True, exist_ok=True)
            path = LOGS / "teste_tela.png"
            imwrite_u(path, frame)
            self.ui_queue.put(
                {
                    "type": "test_result",
                    "token": token.found,
                    "best": token.best,
                    "game_foreground": grabber.is_foreground(),
                    "play": play,
                    "suspend": suspend,
                    "path": str(path),
                    "size": (frame.shape[1], frame.shape[0]),
                }
            )
        except Exception as exc:
            self.ui_queue.put({"type": "test_error", "text": str(exc)})

    def _open_logs(self) -> None:
        LOGS.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(LOGS))
        except Exception as exc:
            self._log(f"Não consegui abrir a pasta de logs: {exc}", "error")

    # ---------------------------------------------------------------- poll
    def _poll(self) -> None:
        while True:
            try:
                message = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            self._handle_message(message)
        self._update_buttons()
        self.root.after(100, self._poll)

    def _handle_message(self, message: dict) -> None:
        kind = message.get("type")

        if kind == "log":
            self._log(message.get("text", ""), message.get("level", "info"))

        elif kind == "status":
            phase = message.get("phase", Phase.STARTING.value)
            detail = message.get("message", "")
            self._set_status(phase, detail)
            self.matches_label.config(text=f"Partidas: {message.get('matches', 0)}")
            token = bool(message.get("token_found"))
            self.token_label.config(
                text="Token: SIM" if token else "Token: não",
                fg="#15803d" if token else "#b91c1c",
            )
            self.time_label.config(
                text=f"Tempo: {_format_elapsed(message.get('elapsed', 0))}"
            )

        elif kind == "token":
            self.token_label.config(text="Token: SIM", fg="#15803d")
            self._set_status(
                Phase.MATCH.value,
                "Token detectado! Vou esperar a partida terminar para encerrar.",
            )

        elif kind == "success":
            text = message.get("text", "Token encontrado!")
            self._set_status(Phase.FINISHED.value, text)
            self.token_label.config(text="Token: SIM", fg="#15803d")
            self._log(text, "success")
            self._write_success_file(text)
            self._schedule_auto_close()

        elif kind == "error":
            text = message.get("text", "Erro desconhecido.")
            self._set_status(Phase.ERROR.value, text)
            self._log(text, "error")
            self.root.bell()
            try:
                messagebox.showerror(APP_TITLE, text, parent=self.root)
            except Exception:
                pass

        elif kind == "stopped":
            text = message.get("text", "Parado.")
            self._set_status(Phase.STOPPED.value, text)
            self._log(text, "warn")

        elif kind == "hotkey":
            if self.bot is not None and self.bot.is_running():
                self._stop_bot("Parada de emergência (F8).")
            else:
                self._log("F8 pressionado, mas o bot não está rodando.", "info")

        elif kind == "test_result":
            self._handle_test_result(message)

        elif kind == "test_error":
            text = message.get("text", "Falha no teste.")
            self._log(f"Teste de detecção falhou: {text}", "error")
            self._set_status(Phase.ERROR.value, f"Teste falhou: {text}")

    def _handle_test_result(self, message: dict) -> None:
        width, height = message.get("size", (0, 0))
        foreground = message.get("game_foreground")
        self._log(f"Captura de teste: {width}x{height}.", "info")
        if not foreground:
            self._log(
                "A janela do Fortnite não estava em primeiro plano; "
                "a captura pode mostrar outra janela.",
                "warn",
            )

        if message.get("token"):
            best = message.get("best")
            if best is not None:
                self._log(
                    f"TOKEN VISÍVEL na tela! ({best.kind}, confiança {best.score:.2f}, "
                    f"{best.w}x{best.h})",
                    "success",
                )
            self._set_status(
                Phase.FINISHED.value,
                "Token visível na tela! Se estiver em partida, o bot vai aguardar o fim.",
            )
        else:
            self._log("Token não visível na captura (normal fora da tela de recompensa).", "info")

        play = message.get("play")
        if play is not None:
            self._log(
                f"Botão JOGAR detectado (confiança {play.score:.2f}) em ({play.x}, {play.y}).",
                "info",
            )
        else:
            self._log("Botão JOGAR não detectado.", "info")

        suspend = message.get("suspend")
        if suspend is not None:
            self._log(
                f"Botão CONTINUAR JOGANDO detectado (confiança {suspend.score:.2f}).",
                "warn",
            )
        else:
            self._log("Tela de suspensão não detectada.", "info")

        self._log(f"Captura salva em {message.get('path')}.", "debug")

        if not message.get("token") and play is None and suspend is None:
            self._set_status(
                Phase.LOBBY.value,
                "Teste concluído: nenhum elemento conhecido na captura. "
                "Traga o Fortnite para a frente e teste de novo.",
            )
        elif play is not None and not message.get("token"):
            self._set_status(
                Phase.LOBBY.value,
                "Teste concluído: lobby detectado. O bot está pronto para jogar.",
            )
        elif suspend is not None:
            self._set_status(
                Phase.STARTING.value,
                "Teste concluído: tela de suspensão detectada.",
            )

    # ------------------------------------------------------------- helpers
    def _set_status(self, phase: str, detail: str) -> None:
        label, color = PHASE_STYLE.get(phase, (PHASE_LABELS.get(phase, phase), "#475569"))
        self.status_label.config(text=label, fg=color)
        self.detail_label.config(text=detail)

    def _log(self, text: str, level: str = "info") -> None:
        if not text:
            return
        tag = level if level in ("info", "success", "warn", "error", "debug") else "info"
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{timestamp}] {text}\n", tag)
        self._log_line_count += 1
        if self._log_line_count > 2500:
            self.log_text.delete("1.0", "600.0")
            self._log_line_count -= 599
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _update_buttons(self) -> None:
        running = bool(self.bot is not None and self.bot.is_running())
        self.start_button.config(state="disabled" if running else "normal")
        self.stop_button.config(state="normal" if running else "disabled")
        self.token_button.config(state="normal" if running else "disabled")

    def _write_success_file(self, text: str) -> None:
        try:
            stamp = time.strftime("%d/%m/%Y %H:%M:%S")
            (ROOT / "TOKEN_ENCONTRADO.txt").write_text(
                f"{text}\nDetectado em: {stamp}\n",
                encoding="utf-8",
            )
        except Exception:
            pass

    def _schedule_auto_close(self) -> None:
        if self._success_scheduled:
            return
        self._success_scheduled = True
        seconds = int(self.config.behavior.auto_close_success_seconds)
        if seconds <= 0:
            return
        self._log(f"O programa vai fechar em {seconds} segundos.", "info")
        self.root.after(seconds * 1000, lambda: self._on_close(force=True))

    def _on_close(self, force: bool = False) -> None:
        if not force and self.bot is not None and self.bot.is_running():
            if not messagebox.askyesno(
                APP_TITLE,
                "O bot está rodando. Deseja parar e sair?",
                parent=self.root,
            ):
                return
        self.stop_event.set()
        if self.bot is not None:
            self.bot.stop()
        if self.hotkey is not None:
            self.hotkey.stop()
        self.root.destroy()


def _configure_logging() -> Path:
    LOGS.mkdir(parents=True, exist_ok=True)
    path = LOGS / f"piratefarm_{time.strftime('%Y%m%d_%H%M%S')}.log"
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(handler)
    return path


def main() -> int:
    log_path = _configure_logging()

    def exception_hook(exc_type, exc_value, exc_traceback):
        logging.error("Falha não tratada", exc_info=(exc_type, exc_value, exc_traceback))
        try:
            messagebox.showerror(
                APP_TITLE,
                f"Ocorreu um erro inesperado:\n\n{exc_value}\n\nLog: {log_path}",
            )
        except Exception:
            pass

    sys.excepthook = exception_hook
    root = tk.Tk()
    app = PirateFarmApp(root)
    app._log(f"Log desta sessão: {log_path}", "debug")
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
